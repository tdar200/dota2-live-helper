# Dota 2 Live Helper

A VAC-safe, second-monitor assistant for climbing in Dota 2 (patch 7.41d).
Reads Valve's official Game State Integration (GSI) and shows live timings.
Built on top of ../dota2-knowledge-base.

## Setup (once)

```bash
# 1. Engine deps
cd engine && python -m pip install -r requirements.txt

# 2. Install the GSI config into Dota
../scripts/install_gsi_config.sh

# 3. Build the dashboard
cd ../dashboard && npm install && npm run build
```

## Run (each session)

```bash
cd engine && python -m uvicorn app.main:app --host 127.0.0.1 --port 3000
```

Open http://127.0.0.1:3000 on your second monitor. Launch Dota; once in a match,
timings appear live. (Restart Dota after first installing the GSI config.)

## Offline testing (no game needed)

```bash
python scripts/replay_gsi.py engine/tests/fixtures/gsi_early_game.json --clock 300 --repeat 10 --interval 1
```

## Tests

```bash
cd engine && python -m pytest tests -v
```
