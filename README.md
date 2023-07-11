# picamera-server-api

The backend to view and control your PiCamera on your Raspberry Pi, with support for the Waveshare Pan-tilt HAT!

The frontend can be found 
at [https://github.com/UnsignedArduino/picamera-server](https://github.com/UnsignedArduino/picamera-server).

## Install

1. Have `python3` installed.
2. Clone this repo.
3. Create a virtual environment.
4. Install dependencies in `requirements.txt`.

## Development

Use `uvicorn main:app --reload` to start a development server.

## Build and serve

`python3 src/main.py` will start the ASGI server in production mode. 

Note you must also follow the instructions to start the frontend server. 
