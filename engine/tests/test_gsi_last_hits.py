import json
from pathlib import Path
from app.gsi import parse_gsi

FIX = Path(__file__).parent / "fixtures" / "gsi_early_game.json"


def test_gsi_parses_last_hits():
    raw = json.loads(FIX.read_text())
    state = parse_gsi(raw)
    assert state.player.last_hits == 20
