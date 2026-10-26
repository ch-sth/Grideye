"""ArUco detection for encoded camera images (PNG/JPEG)."""

import asyncio
from typing import Protocol

import cv2
import numpy as np

from grideye_shared.schemas import AiDetection, BoundingBox, FrameSize


class ObjectDetector(Protocol):
    async def detect(self, frame: bytes) -> list[AiDetection]: ...


class ArucoDetector:
    """Decode tags using the same dictionary as the printed markers.

    OpenCV supplies no probability score. A successfully decoded marker uses
    confidence 1.0 as an acceptance flag, not a calibrated probability.
    """

    def __init__(self, dictionary: str = "DICT_4X4_1000") -> None:
        if not dictionary.startswith("DICT_") or not hasattr(cv2.aruco, dictionary):
            raise ValueError(f"Unknown ArUco dictionary: {dictionary}")
        self.dictionary = dictionary
        self._dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary))

    async def detect(self, frame: bytes) -> list[AiDetection]:
        return await asyncio.to_thread(self._detect, frame)

    def _detect(self, frame: bytes) -> list[AiDetection]:
        if not frame:
            return []
        image = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError("Camera frame is not a valid encoded image (PNG/JPEG)")
        detector = cv2.aruco.ArucoDetector(self._dictionary, cv2.aruco.DetectorParameters())
        corners, ids, _ = detector.detectMarkers(image)
        if ids is None:
            return []
        height, width = image.shape
        detections = []
        for marker_corners, marker_id in zip(corners, ids.flatten(), strict=True):
            x, y, w, h = cv2.boundingRect(marker_corners)
            left, top = max(0, x), max(0, y)
            right, bottom = min(width, x + w), min(height, y + h)
            detections.append(
                AiDetection(
                    class_name="aruco",
                    class_confidence=1.0,
                    number=str(int(marker_id)),
                    marker_confidence=1.0,
                    bbox_px=BoundingBox(x=left, y=top, width=right - left, height=bottom - top),
                    frame=FrameSize(width=width, height=height),
                )
            )
        return detections
