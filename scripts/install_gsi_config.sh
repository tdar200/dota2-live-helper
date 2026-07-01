#!/usr/bin/env bash
# Install the Dota 2 Game State Integration config so Dota POSTs live state to the engine.
# Usage: install_gsi_config.sh [PORT] [CFG_DIR]
#   PORT     engine port the dashboard/engine runs on (default 3000)
#   CFG_DIR  explicit gamestate_integration dir (skips auto-detection)
# Auto-detects the Dota 2 install across ALL Steam libraries (reads libraryfolders.vdf),
# so it works even when Dota lives on a secondary drive (e.g. /mnt/data/SteamLibrary).
set -euo pipefail

PORT="${1:-3000}"

if [ -n "${2:-}" ]; then
    CFG_DIR="$2"
else
    # Collect candidate Steam library roots: the well-known ones + every path in libraryfolders.vdf.
    declare -a ROOTS=("$HOME/.local/share/Steam" "$HOME/.steam/steam" "$HOME/.steam/root")
    for vdf in "$HOME/.local/share/Steam/steamapps/libraryfolders.vdf" \
               "$HOME/.steam/steam/steamapps/libraryfolders.vdf"; do
        if [ -f "$vdf" ]; then
            while IFS= read -r p; do
                [ -n "$p" ] && ROOTS+=("$p")
            done < <(grep -oE '"path"[[:space:]]+"[^"]+"' "$vdf" \
                     | sed -E 's/.*"path"[[:space:]]+"([^"]+)".*/\1/')
        fi
    done

    DOTA=""
    for root in "${ROOTS[@]}"; do
        d="$root/steamapps/common/dota 2 beta"
        if [ -d "$d/game/dota/cfg" ]; then
            DOTA="$d"
            break
        fi
    done

    if [ -z "$DOTA" ]; then
        echo "ERROR: could not find a Dota 2 install in any Steam library." >&2
        echo "Pass the cfg dir explicitly:" >&2
        echo "  $0 $PORT '/path/to/dota 2 beta/game/dota/cfg/gamestate_integration'" >&2
        exit 1
    fi
    CFG_DIR="$DOTA/game/dota/cfg/gamestate_integration"
fi

mkdir -p "$CFG_DIR"
CFG_FILE="$CFG_DIR/gamestate_integration_helper.cfg"
cat > "$CFG_FILE" <<EOF
"Dota 2 Live Helper"
{
    "uri"           "http://127.0.0.1:$PORT/gsi"
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
echo "Wrote $CFG_FILE (engine port $PORT)"
echo "IMPORTANT: fully restart the Dota 2 client — GSI configs load only at launch."
