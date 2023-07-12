import asyncio as aio
import logging
from contextlib import asynccontextmanager
from io import BytesIO

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from picamera import PiCamera
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from logger import create_logger

logger = create_logger(name=__name__, level=logging.DEBUG)

RATE_LIMIT = "60/minute"
CAMERA_PERIOD = 0.1

camera = None
last_frame = bytes()


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
        await aio.sleep(CAMERA_PERIOD)


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    global camera
    camera = PiCamera()
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
            await aio.sleep(CAMERA_PERIOD)
    except WebSocketDisconnect:
        logger.info("Client disconnect from websocket stream")


if __name__ == "__main__":
    logger.info("Starting ASGI server")
    uvicorn.run("main:app", host="0.0.0.0", port=4000)
