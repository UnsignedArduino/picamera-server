from logger import create_logger
import logging
from picamera import PiCamera
from io import BytesIO
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

logger = create_logger(name=__name__, level=logging.DEBUG)

RATE_LIMIT = "60/minute"

camera = None

@asynccontextmanager
async def app_lifespan(_: FastAPI):
    global camera
    camera = PiCamera()
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
        buffer = BytesIO()
        while True:
            buffer.seek(0)
            buffer.truncate(0)
            camera.capture(buffer, format="jpeg")
            buffer.seek(0)
            await ws.send_bytes(buffer.read())
    except WebSocketDisconnect:
        logger.info("Client disconnect from websocket stream")


if __name__ == "__main__":
    logger.info("Starting ASGI server")
    uvicorn.run("main:app", host="0.0.0.0", port=4000)
