import asyncio as aio
import logging
from contextlib import asynccontextmanager
from io import BytesIO

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from picamera import PiCamera, PiCameraValueError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from logger import create_logger

logger = create_logger(name=__name__, level=logging.DEBUG)

RATE_LIMIT = "60/minute"

camera = None
last_frame = bytes()

settings = {
    "AWB_mode": {
        "selected": "auto",
        "available": [
            "off",
            "auto",
            "sunlight",
            "cloudy",
            "shade",
            "tungsten",
            "fluorescent",
            "incandescent",
            "flash",
            "horizon"
        ]
    },
    "Brightness": {
        "min": 0,
        "max": 100,
        "value": 50
    },
    "Contrast": {
        "min": -100,
        "max": 100,
        "value": 0
    },
    "Effect": {
        "selected": "none",
        "available": [
            "none",
            "negative",
            "solarize",
            "sketch",
            "denoise",
            "emboss",
            "oilpaint",
            "hatch",
            "gpen",
            "pastel",
            "watercolor",
            "film",
            "blur",
            "saturation",
            "colorswap",
            "washedout",
            "posterise",
            "colorpoint",
            "colorbalance",
            "cartoon",
            "deinterlace1",
            "deinterlace2"
        ]
    },
    "ISO": {
        "selected": 0,
        "available": [
            0,
            100,
            200,
            320,
            400,
            500,
            640,
            800
        ]
    },
    "Resolution": {
        "selected": "720x480",
        "available": [
            "128x96",
            "160x120",
            "160x144",
            "176x144",
            "180x132",
            "180x135",
            "192x144",
            "234x60",
            "256x192",
            "320x200",
            "320x240",
            "320x288",
            "320x400",
            "352x288",
            "352x240",
            "384x256",
            "384x288",
            "392x72",
            "400x300",
            "460x55",
            "480x320",
            "468x32",
            "468x60",
            "512x342",
            "512x384",
            "544x372",
            "640x350",
            "640x480",
            "640x576",
            "704x576",
            "720x350",
            "720x400",
            "720x480",
            "720x483",
            "720x484",
            "720x486",
            "720x540",
            "720x576",
            "729x348",
            "768x576",
            "800x600",
            "832x624",
            "856x480",
            "896x600",
            "960x720",
            "1024x576",
            "1024x768",
            "1080x720",
            "1152x768",
            "1152x864",
            "1152x870",
            "1152x900",
            "1280x720",
            "1280x800",
            "1280x854",
            "1280x960",
            "1280x992",
            "1280x1024",
            "1360x766",
            "1365x768",
            "1366x768",
            "1365x1024",
            "1400x788",
            "1400x1050",
            "1440x900",
            "1520x856",
            "1536x1536",
            "1600x900",
            "1600x1024",
            "1600x1200",
            "1792x1120",
            "1792x1344",
            "1824x1128",
            "1824x1368",
            "1856x1392",
            "1920x1080",
            "1920x1200",
            "1920x1440",
            "2000x1280",
            "2048x1152",
            "2048x1536",
            "2048x2048",
            "2500x1340",
            "2560x1600",
            "3072x2252",
            "3600x2400"
        ]
    },
    "Saturation": {
        "min": -100,
        "max": 100,
        "value": 0
    }
}


async def capture_frames():
    global last_frame
    logger.debug("Starting frame capture loop")
    buffer = BytesIO()
    while True:
        buffer.seek(0)
        buffer.truncate(0)
        camera.capture(buffer, format="jpeg")
        buffer.seek(0)
        last_frame = buffer.read()
        await aio.sleep(0)


def apply_settings(new_s):
    camera.awb_mode = new_s["AWB_mode"]["selected"]
    camera.brightness = new_s["Brightness"]["value"]
    camera.contrast = new_s["Contrast"]["value"]
    camera.image_effect = new_s["Effect"]["selected"]
    camera.iso = int(new_s["ISO"]["selected"])
    camera.resolution = tuple(
        int(x) for x in tuple(new_s["Resolution"]["selected"].split("x")))
    camera.saturation = new_s["Saturation"]["value"]


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    global camera
    camera = PiCamera()
    camera.rotation = 180
    apply_settings(settings)
    logger.debug("Initialized camera")
    aio.create_task(capture_frames())
    yield
    camera.close()


limiter = Limiter(key_func=get_remote_address)
app = FastAPI(lifespan=app_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.websocket("/stream")
async def websocket_stream(ws: WebSocket):
    await ws.accept()
    logger.info("Client connected to websocket stream")
    try:
        while True:
            await ws.send_bytes(last_frame)
            await aio.sleep(0)
    except WebSocketDisconnect:
        logger.info("Client disconnected from websocket stream")


control_clients: list[WebSocket] = []


@app.websocket("/control")
async def websocket_control(ws: WebSocket):
    global settings
    await ws.accept()
    control_clients.append(ws)
    logger.info("Client connect to websocket control")
    try:
        while True:
            for client in control_clients:
                await client.send_json({
                    "type": "settings",
                    "settings": settings
                })
            logger.debug("Waiting for new settings")
            new_settings = await ws.receive_json()
            logger.debug("Received new settings to set")
            try:
                apply_settings(new_settings)
            except PiCameraValueError as e:
                logger.warning("Failed to set new settings")
                logger.exception(e)
                apply_settings(settings)
                await ws.send_json({
                    "type": "result",
                    "result": False,
                })
            else:
                logger.info("Set new settings successfully")
                settings = new_settings
                await ws.send_json({
                    "type": "result",
                    "result": True,
                })
            await aio.sleep(0)
    except WebSocketDisconnect:
        logger.info("Client disconnected from websocket control")
    finally:
        control_clients.remove(ws)


if __name__ == "__main__":
    logger.info("Starting ASGI server")
    uvicorn.run("main:app", host="0.0.0.0", port=4000)
