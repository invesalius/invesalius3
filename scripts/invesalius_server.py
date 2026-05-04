#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# This scripts allows sending events to InVesalius via Socket.IO, mimicking InVesalius's
# internal communication. It can be useful for developing and debugging InVesalius.
#
# Example usage:
#
#     - (In console window 1) Run the script by: python scripts/invesalius_server.py 5000
#
#     - (In console window 2) Run InVesalius by: python app.py --remote-host http://localhost:5000
#
#     - If InVesalius connected to the server successfully, a message should appear in console window 1,
#       asking to provide the topic name.
#
#     - Enter the topic name, such as "Add marker" (without quotes).
#
#     - Enter the data, such as {"ball_id": 0, "size": 2, "colour": [1.0, 1.0, 0.0], "coord": [10.0, 20.0, 30.0]}
#
#     - If successful, a message should now appear in console window 2, indicating that the event was received.

import asyncio
import json
import sys

import aioconsole
import nest_asyncio
import socketio
import uvicorn

nest_asyncio.apply()

if len(sys.argv) != 2:
    print("""This script allows sending events to InVesalius.

Usage:  python invesalius_server.py port""")
    sys.exit(1)

port = int(sys.argv[1])

sio = socketio.AsyncServer(async_mode="asgi")
app = socketio.ASGIApp(sio)

connected = False


@sio.event
def connect(sid, environ):
    global connected
    connected = True


def print_json_error(e):
    print("Invalid JSON")
    print(e.doc)
    print(" " * e.pos + "^")
    print(e.msg)
    print("")


async def run():
    while True:
        if not connected:
            await asyncio.sleep(1)
            continue

        print("Enter topic: ")
        topic = await aioconsole.ainput()
        print("Enter data as JSON: ")
        data = await aioconsole.ainput()

        try:
            decoded = json.loads(data)
        except json.decoder.JSONDecodeError as e:
            print_json_error(e)
            continue

        await sio.emit(
            event="to_neuronavigation",
            data={
                "topic": topic,
                "data": decoded,
            },
        )


async def main():
    asyncio.create_task(run())
    uvicorn.run(app, port=port, host="0.0.0.0", loop="asyncio")


if __name__ == "__main__":
    asyncio.run(main(), debug=True)
