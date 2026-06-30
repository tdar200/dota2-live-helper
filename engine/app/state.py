from pydantic import BaseModel, Field


class GameState(BaseModel):
    clock_time: int | None = None
    raw: dict = Field(default_factory=dict)

    def update_from_raw(self, raw: dict) -> None:
        self.raw = raw
        clock = raw.get("map", {}).get("clock_time")
        if isinstance(clock, int):
            self.clock_time = clock
