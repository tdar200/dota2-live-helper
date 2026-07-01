from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.state import GameState
from app.advice import build_advice, BUILD_DATA
from app.hub import Hub

app = FastAPI(title="Dota 2 Live Helper")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
STATE = GameState()
HUB = Hub()

_DIST = Path(__file__).resolve().parents[2] / "dashboard" / "dist"


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


@app.post("/enemies")
async def enemies(request: Request) -> dict:
    body = await request.json()
    STATE.enemy_heroes = list(body.get("heroes", []))
    await HUB.broadcast(build_advice(STATE).model_dump())
    return {"ok": True, "count": len(STATE.enemy_heroes)}


@app.post("/allies")
async def allies(request: Request) -> dict:
    body = await request.json()
    STATE.ally_heroes = list(body.get("heroes", []))
    await HUB.broadcast(build_advice(STATE).model_dump())
    return {"ok": True, "count": len(STATE.ally_heroes)}


@app.get("/heroes")
async def heroes() -> list[dict]:
    return BUILD_DATA.heroes


if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="dashboard")
