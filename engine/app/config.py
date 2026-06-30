from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel


class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 3000
    account_id: str | None = None
    dota_cfg_dir: str = str(
        Path.home()
        / ".local/share/Steam/steamapps/common/dota 2 beta"
        / "game/dota/cfg/gamestate_integration"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
