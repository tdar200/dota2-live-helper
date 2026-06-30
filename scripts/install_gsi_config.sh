#!/usr/bin/env bash
set -euo pipefail
CFG_DIR="${1:-$HOME/.local/share/Steam/steamapps/common/dota 2 beta/game/dota/cfg/gamestate_integration}"
mkdir -p "$CFG_DIR"
CFG_FILE="$CFG_DIR/gamestate_integration_helper.cfg"
cat > "$CFG_FILE" <<'EOF'
"Dota 2 Live Helper"
{
    "uri"           "http://127.0.0.1:3000/gsi"
    "timeout"       "5.0"
    "buffer"        "0.1"
    "throttle"      "0.1"
    "heartbeat"     "30.0"
    "data"
    {
        "provider"      "1"
        "map"           "1"
        "player"        "1"
        "hero"          "1"
        "abilities"     "1"
        "items"         "1"
    }
}
EOF
echo "Wrote $CFG_FILE"
