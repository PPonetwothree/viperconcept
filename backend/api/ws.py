"""WebSocket push channel: snapshots (5 Hz), new events, event updates,
observations (for data-flow animation) and log lines."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    runtime = ws.app.state.runtime
    queue: asyncio.Queue = asyncio.Queue(maxsize=500)

    def listener(msg):
        try:
            queue.put_nowait(msg)
        except asyncio.QueueFull:
            # Slow client: drop snapshots first, never events.
            if msg.get("type") != "snapshot":
                try:
                    queue.get_nowait()
                    queue.put_nowait(msg)
                except Exception:
                    pass

    runtime.listeners.append(listener)
    sender = None
    try:
        await ws.send_text(json.dumps({"type": "hello", "sim": runtime.sim_status(),
                                       "snapshot": runtime.snapshot()}))
        sender = asyncio.create_task(_pump(ws, queue))
        while True:
            # Client messages are not required; reading detects disconnects.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if listener in runtime.listeners:
            runtime.listeners.remove(listener)
        if sender:
            sender.cancel()


async def _pump(ws: WebSocket, queue: asyncio.Queue):
    while True:
        msg = await queue.get()
        await ws.send_text(json.dumps(msg, default=str))
