# picamera-server

> Visit [https://picamera-server-viewer.vercel.app/](https://picamera-server-viewer.vercel.app/) to view your
> Picamera after following the [instructions](https://github.com/UnsignedArduino/picamera-server/blob/main/README.md#install)
> to start the server on the Raspberry Pi!

The server to view and control your PiCamera on your Raspberry Pi, with support for the Waveshare Pan-tilt HAT!

The web-based viewer can be found at 
[https://github.com/UnsignedArduino/picamera-server-viewer](https://github.com/UnsignedArduino/picamera-server-viewer).

## Install

1. Have `python3` installed.
2. Clone this repo.
3. Create a virtual environment.
4. Install dependencies in `requirements.txt`.
5. Install `ngrok`.
6. Copy `.env.sample` to `.env` and add the password if desired. A blank 
   password means that no password is set. 

## Development

Use `uvicorn main:app --reload` to start a development server.

## Build and serve

`python3 src/main.py` will start the ASGI server in production mode. 

Use ngrok to tunnel the server running on port 4000 with `ngrok http 4000`.
Note that not using an account with ngrok will cause the tunnel to expire in 
a couple of hours, so if you want to keep the camera permanently accessible 
without having to restart the tunnel, you will want to add your auth token 
after signing up for ngrok.

Note you must also follow the instructions to start the web viewer server. 
