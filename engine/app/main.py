from fastapi import FastAPI, Request
from app.state import GameState

app = FastAPI(title="Dota 2 Live Helper")
STATE = GameState()


@app.post("/gsi")
async def gsi(request: Request) -> dict:
    raw = await request.json()
    STATE.update_from_raw(raw)
    return {"ok": True}
