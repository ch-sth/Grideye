import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import WebSocket

from grideye_shared.schemas import ServiceState, ServiceStatus


class RuntimeState:
    def __init__(self) -> None:
        self.latest: dict[str, dict[str, object]] = {}
        self.services: dict[str, ServiceStatus] = {}
        self.websockets: set[WebSocket] = set()

    def service_snapshot(self, timeout_seconds: float) -> list[dict[str, object]]:
        now = datetime.now(UTC)
        values = []
        for status in list(self.services.values()):
            copy = status.model_copy()
            if now - copy.timestamp > timedelta(seconds=timeout_seconds):
                copy.status = ServiceState.OFFLINE
            values.append(copy.model_dump(mode="json"))
        return values

    async def broadcast(self, envelope: dict[str, object]) -> None:
        async def send(socket: WebSocket) -> None:
            try:
                await asyncio.wait_for(socket.send_json(envelope), timeout=0.5)
            except Exception:
                self.websockets.discard(socket)

        await asyncio.gather(*(send(socket) for socket in list(self.websockets)))


runtime = RuntimeState()
