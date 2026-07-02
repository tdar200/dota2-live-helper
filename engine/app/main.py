from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.state import GameState
from app.advice import build_advice, BUILD_DATA
from app.hub import Hub
from app.reviews import load_review, list_reviews

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


@app.get("/whoami")
async def whoami() -> dict:
    """The account id auto-captured from live GSI (null until a game streams).

    scripts/refresh_personal_stats.py polls this so the refresh needs no
    --account-id once you've played/spectated a game since the engine started.
    """
    return {"account_id": STATE.player.account_id}


@app.post("/networth")
async def networth(request: Request) -> dict:
    body = await request.json()
    STATE.net_worth_lead = body.get("lead")
    await HUB.broadcast(build_advice(STATE).model_dump())
    return {"ok": True, "lead": STATE.net_worth_lead}


@app.post("/roshan")
async def roshan(request: Request) -> dict:
    body = await request.json()
    STATE.roshan_dead_clock = None if body.get("clear") else STATE.clock_time
    await HUB.broadcast(build_advice(STATE).model_dump())
    return {"ok": True, "roshan_dead_clock": STATE.roshan_dead_clock}


@app.get("/review/{match_id}")
async def review(match_id: int) -> dict:
    report = load_review(match_id)
    if report is None:
        raise HTTPException(status_code=404, detail="not analyzed")
    return report


@app.get("/reviews")
async def reviews() -> list[dict]:
    return list_reviews()


if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="dashboard")
