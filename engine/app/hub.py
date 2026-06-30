from fastapi import WebSocket


class Hub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.last: dict | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)
        if self.last is not None:
            await ws.send_json(self.last)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        self.last = message
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
