import asyncio
from collections.abc import AsyncIterator


class DummyFrameProvider:
    """Produces explicit fake frames; no RTSP/GStreamer dependency."""

    async def frames(self) -> AsyncIterator[bytes]:
        while True:
            yield b"GRIDEYE_DUMMY_FRAME"
            await asyncio.sleep(1)


TestImageProvider = DummyFrameProvider
