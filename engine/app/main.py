from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from app.state import GameState
from app.advice import build_advice
from app.hub import Hub

app = FastAPI(title="Dota 2 Live Helper")
STATE = GameState()
HUB = Hub()


@app.post("/gsi")
async def gsi(request: Request) -> dict:
    raw = await request.json()
    STATE.update_from_raw(raw)
    payload = build_advice(STATE).model_dump()
    await HUB.broadcast(payload)
    return {"ok": True}


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await HUB.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # we don't expect client messages; keeps it open
    except WebSocketDisconnect:
        HUB.disconnect(websocket)
