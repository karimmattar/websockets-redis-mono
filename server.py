import asyncio

import websockets
import os
import json
import uvloop
from websockets import WebSocketServerProtocol
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorChangeStream
from websockets.frames import CloseCode
from functools import wraps
import redis.asyncio as redis

# load environment variables
load_dotenv()
# database connection
mongo_uri = os.environ.get("DATABASE_URL")
mongo_client = AsyncIOMotorClient(mongo_uri)
db = mongo_client.get_database("chat")
# redis connection
redis_uri = os.environ.get("REDIS_URL")
redis_pool = redis.ConnectionPool.from_url(redis_uri)
redis_client = redis.Redis.from_pool(redis_pool)

projection_ = {
    "_id": False
}

CONNECTIONS = set()


async def find_user(**kwargs):
    collection = db.get_collection("user")
    # _user = await collection.find_one(filter=kwargs, projection=projection_)
    _user = await collection.find_one(filter=kwargs)
    return _user


async def find_room(**kwargs):
    collection = db.get_collection("room")
    # _room = await collection.find_one(filter=kwargs, projection=projection_)
    _room = await collection.find_one(filter=kwargs)
    return _room


async def insert_message(user, room, message):
    collection = db.get_collection("room")
    _id = room["_id"]
    _messages = room["messages"]
    _message = {"user": user, "message": message}
    _messages.append(_message)
    return await collection.replace_one({"_id": _id}, {"messages": _messages})


def authenticate(fn):
    @wraps(fn)
    async def wrapper(websocket: WebSocketServerProtocol, *args, **kwargs):
        token = websocket.request_headers.get("x-token", None)
        filters_ = {"token": token}
        user = await find_user(**filters_)

        if user is None:
            return await websocket.close(code=CloseCode.INVALID_DATA, reason="Invalid token")
        websocket.user = user
        return await fn(websocket, *args, **kwargs)

    return wrapper


def validate_room(fn):
    @wraps(fn)
    async def wrapper(websocket: WebSocketServerProtocol, path: str, *args, **kwargs):
        filters_ = {"name": path.split("/")[-1]}
        room = await find_room(**filters_)
        if room is None:
            return await websocket.close(code=CloseCode.INVALID_DATA, reason="Invalid room name")
        websocket.room = room
        return await fn(websocket, path, *args, **kwargs)

    return wrapper


# @authenticate
# @validate_room
@authenticate
@validate_room
async def handler(websocket: WebSocketServerProtocol, path: str):
    if websocket not in CONNECTIONS:
        CONNECTIONS.add(websocket)
    try:
        async for message in websocket:
            await redis_client.lpush(websocket.room["name"], message)
            # await insert_message(websocket.user, websocket.room, message)
            websockets.broadcast(CONNECTIONS, message)
    except websockets.exceptions.ConnectionClosedError:
        print("Connection closed.")
    finally:
        print("Connection closed.")


async def main():
    await websockets.serve(handler, "0.0.0.0", 8000)


if __name__ == "__main__":
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = uvloop.new_event_loop()
    asyncio.set_event_loop(loop)

    server = asyncio.ensure_future(main())

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        server.cancel()
        loop.run_until_complete(server)
    finally:
        loop.close()
