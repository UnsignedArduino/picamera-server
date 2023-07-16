import asyncio as aio
import logging
from contextlib import asynccontextmanager
from io import BytesIO
from time import time as unix

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from picamera import PiCamera, PiCameraValueError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from PCA9685 import PCA9685
from logger import create_logger

logger = create_logger(name=__name__, level=logging.DEBUG)

RATE_LIMIT = "60/minute"

camera = None
pwm = None
last_frame = bytes()

capture_fps = 0
settings = {
    "AWB_mode": {
        "selected": "auto",
        "default": "auto",
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
        "value": 50,
        "default": 50
    },
    "Contrast": {
        "min": -100,
        "max": 100,
        "value": 0,
        "default": 0
    },
    "Effect_(*in_captures_only)": {
        "selected": "none",
        "default": "none",
        "available": [
            "none",
            "negative",
            "solarize",
            "sketch*",
            "denoise*",
            "emboss*",
            "oilpaint*",
            "hatch*",
            "gpen*",
            "pastel*",
            "watercolor*",
            "film*",
            "blur*",
            "saturation*",
            "colorswap*",
            "washedout*",
            "posterise*",
            "colorpoint*",
            "colorbalance*",
            "cartoon*",
            "deinterlace1*",
            "deinterlace2*"
        ]
    },
    "Exposure_compensation_(1/6_stop)": {
        "min": -25,
        "max": 25,
        "value": 0,
        "default": 0
    },
    "Exposure_mode": {
        "selected": "auto",
        "default": "auto",
        "available": [
            "off",
            "auto",
            "night",
            "nightpreview",
            "backlight",
            "spotlight",
            "sports",
            "snow",
            "beach",
            "verylong",
            "fixedfps",
            "antishake",
            "fireworks"
        ]
    },
    "ISO": {
        "selected": "0",
        "default": "0",
        "zero_is_auto": True,
        "available": [
            "0",
            "100",
            "200",
            "320",
            "400",
            "500",
            "640",
            "800"
        ]
    },
    "Meter_mode": {
        "selected": "average",
        "default": "average",
        "available": [
            "average",
            "spot",
            "matrix",
            "backlit"
        ]
    },
    "Resolution": {
        "selected": "720x480",
        "default": "720x480",
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
        "value": 0,
        "default": 0
    },
    "Sharpness": {
        "min": -100,
        "max": 100,
        "value": 0,
        "default": 0
    },
    "Shutter_speed_(µs)": {
        "min": 0,
        "max": 33333,
        "value": 0,
        "default": 0,
        "zero_is_auto": True
    }
}
pan_tilt = {
"Pan": {
        "min": 0,
        "max": 180,
        "value": 90,
        "default": 90
    },
    "Tilt": {
        "min": 0,
        "max": 80,
        "value": 40,
        "default": 40
    }
}
stream_fps = 0
stop_capture = False
stopped_captures = False


async def capture_frames():
    global last_frame, capture_fps, stop_capture, stopped_captures
    logger.debug("Starting frame capture loop")
    buffer = BytesIO()
    stop_capture = False
    stopped_captures = False
    while True:
        for _ in camera.capture_continuous(buffer, "jpeg",
                                           use_video_port=True):
            start = unix()
            buffer.seek(0)
            last_frame = buffer.read()
            buffer.seek(0)
            buffer.truncate(0)
            await aio.sleep(0)
            capture_fps = 1 / (unix() - start)
            if stop_capture:
                break
        logger.debug("Stopping capture momentarily")
        stopped_captures = True
        while stop_capture:
            await aio.sleep(0.2)
        stopped_captures = False
        logger.debug("Resuming capture")


async def pause_captures():
    global stop_capture
    logger.debug("Signaling to pause captures")
    stop_capture = True
    while not stopped_captures:
        await aio.sleep(0.1)
    logger.debug("Paused captures")


async def resume_captures():
    global stop_capture
    logger.debug("Signaling to resume captures")
    stop_capture = False
    while stopped_captures:
        await aio.sleep(0.1)
    logger.debug("Resumed captures")


async def apply_settings(new_s, pause=True):
    if pause:
        await pause_captures()
    camera.awb_mode = new_s["AWB_mode"]["selected"]
    camera.brightness = new_s["Brightness"]["value"]
    camera.contrast = new_s["Contrast"]["value"]
    camera.image_effect = new_s["Effect_(*in_captures_only)"][
        "selected"].replace("*", "")
    camera.exposure_compensation = new_s["Exposure_compensation_(1/6_stop)"][
        "value"]
    camera.exposure_mode = new_s["Exposure_mode"]["selected"]
    camera.iso = int(new_s["ISO"]["selected"])
    camera.meter_mode = new_s["Meter_mode"]["selected"]
    camera.resolution = tuple(
        int(x) for x in tuple(new_s["Resolution"]["selected"].split("x")))
    camera.saturation = new_s["Saturation"]["value"]
    camera.sharpness = new_s["Sharpness"]["value"]
    camera.shutter_speed = new_s["Shutter_speed_(µs)"]["value"]
    if pause:
        await resume_captures()


async def apply_pan_tilt(new_pt):
    pwm.setRotationAngle(0, new_pt["Tilt"]["max"] - new_pt["Tilt"]["value"])
    pwm.setRotationAngle(1, new_pt["Pan"]["max"] - new_pt["Pan"]["value"])


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    global camera, pwm
    camera = PiCamera()
    camera.vflip = True
    camera.hflip = True
    await apply_settings(settings, False)
    aio.create_task(capture_frames())
    logger.debug("Initialized camera")
    pwm = PCA9685()
    pwm.setPWMFreq(50)
    logger.debug("Initialized pan-tilt controller")
    yield
    camera.close()
    pwm.exit_PCA9685()


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

stream_clients: list[WebSocket] = []


@app.websocket("/stream")
async def websocket_stream(ws: WebSocket):
    global stream_fps
    await ws.accept()
    stream_clients.append(ws)
    logger.info("Client connected to websocket stream")
    try:
        while True:
            start = unix()
            await ws.send_bytes(last_frame)
            await aio.sleep(0)
            stream_fps = 1 / (unix() - start)
    except WebSocketDisconnect:
        logger.info("Client disconnected from websocket stream")
    finally:
        stream_clients.remove(ws)


control_clients: list[WebSocket] = []


async def broadcast_control(message: object):
    for client in control_clients:
        await client.send_json(message)


@app.websocket("/control")
async def websocket_control(ws: WebSocket):
    global settings, pan_tilt
    await ws.accept()
    control_clients.append(ws)
    logger.info("Client connect to websocket control")
    try:
        while True:
            logger.debug("Broadcasting settings and pan-tilt")
            await broadcast_control({
                    "type": "settings",
                    "settings": settings
                })
            await broadcast_control({
                    "type": "pan_tilt",
                    "pan_tilt": pan_tilt
                })
            logger.debug("Waiting for new message")
            msg = await ws.receive_json()
            if msg["type"] == "settings":
                logger.debug("Received new settings to set")
                try:
                    await apply_settings(msg["settings"])
                except PiCameraValueError as e:
                    logger.warning("Failed to set new settings")
                    logger.exception(e)
                    await apply_settings(settings)
                    await broadcast_control({
                        "type": "status",
                        "status": "Failed to update settings!",
                    })
                else:
                    logger.info("Set new settings successfully")
                    settings = msg["settings"]
                    await broadcast_control({
                        "type": "status",
                        "status": "Successfully updated settings!",
                    })
            elif msg["type"] == "pan_tilt":
                logger.debug("New pan-tilt")
                await apply_pan_tilt(msg["pan_tilt"])
                logger.info("Set new pan-tilt successfully")
                pan_tilt = msg["pan_tilt"]
                await broadcast_control({
                    "type": "status",
                    "status": "Successfully updated camera direction!",
                })
            else:
                logger.warning(f"Received message with unknown type: {msg['type']}")
            await aio.sleep(0)
    except WebSocketDisconnect:
        logger.info("Client disconnected from websocket control")
    finally:
        control_clients.remove(ws)


if __name__ == "__main__":
    logger.info("Starting ASGI server")
    uvicorn.run("main:app", host="0.0.0.0", port=4000)
