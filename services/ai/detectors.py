from typing import Protocol

from grideye_shared.schemas import AiDetection, BoundingBox, FrameSize


class ObjectDetector(Protocol):
    async def detect(self, frame: bytes) -> list[AiDetection]: ...


class OcrEngine(Protocol):
    async def read(self, frame: bytes, bbox: BoundingBox) -> tuple[str | None, float]: ...


class DummyDetector:
    async def detect(self, frame: bytes) -> list[AiDetection]:
        return (
            [
                AiDetection(
                    class_name="package",
                    class_confidence=0.9,
                    bbox_px=BoundingBox(x=10, y=10, width=20, height=20),
                    frame=FrameSize(width=100, height=100),
                )
            ]
            if frame
            else []
        )


class DummyOCR:
    async def read(self, frame: bytes, bbox: BoundingBox) -> tuple[str | None, float]:
        return ("4712", 0.9) if frame else (None, 0.0)
