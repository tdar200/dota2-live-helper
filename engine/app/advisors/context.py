from dataclasses import dataclass
from app.state import GameState


@dataclass
class AdviceContext:
    state: GameState
    horizon_s: int = 600
    limit: int = 6
