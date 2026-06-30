#!/usr/bin/env python3
"""Replay a recorded GSI fixture into the engine for offline testing."""
import argparse
import json
import time
import urllib.request


def post(url: str, payload: dict) -> int:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return resp.status


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("fixture")
    ap.add_argument("--url", default="http://127.0.0.1:3000/gsi")
    ap.add_argument("--clock", type=int, default=None, help="override map.clock_time")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--interval", type=float, default=1.0)
    args = ap.parse_args()

    payload = json.loads(open(args.fixture).read())
    for i in range(args.repeat):
        if args.clock is not None:
            payload.setdefault("map", {})["clock_time"] = args.clock + i
        status = post(args.url, payload)
        print(f"POST {i+1}/{args.repeat} -> {status} (clock={payload.get('map', {}).get('clock_time')})")
        if i + 1 < args.repeat:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
