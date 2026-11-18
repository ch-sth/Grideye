"""Ultralytics YOLO object-detection checkpoints, using CPU inference."""

import asyncio
import os
from pathlib import Path
from threading import Lock

import cv2
import numpy as np

from grideye_shared.schemas import AiDetection, BoundingBox, FrameSize


class YoloDetector:
    def __init__(self, path: Path) -> None:
        # Prevent implicit downloads and keep settings outside the model directory.
        os.environ.setdefault("YOLO_AUTOINSTALL", "false")
        os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/grideye-yolo")
        from ultralytics import YOLO

        if not path.is_file():
            raise ValueError("Modelldatei nicht gefunden.")
        self._lock = Lock()
        self._model = YOLO(str(path))
        if self._model.task != "detect":
            raise ValueError("Unterstützt werden YOLO-Objekterkennungsmodelle (Task: detect).")
        self.names = {str(key): str(value) for key, value in self._model.names.items()}
        # A checkpoint is usable only if it can perform an actual forward pass.
        self._predict(np.zeros((320, 320, 3), dtype=np.uint8))

    def _predict(self, image):
        with self._lock:
            return self._model.predict(
                source=image,
                device="cpu",
                imgsz=640,
                conf=0.25,
                verbose=False,
                save=False,
                max_det=100,
            )

    async def detect(self, frame: bytes) -> list[AiDetection]:
        return await asyncio.to_thread(self._detect, frame)

    def _detect(self, frame: bytes) -> list[AiDetection]:
        if not frame:
            return []
        image = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Ungültiges Kamerabild.")
        height, width = image.shape[:2]
        detections = []
        for result in self._predict(image):
            if result.boxes is None:
                continue
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().tolist()
                left, top = max(0, int(x1)), max(0, int(y1))
                right, bottom = min(width, int(np.ceil(x2))), min(height, int(np.ceil(y2)))
                if right <= left or bottom <= top:
                    continue
                detections.append(
                    AiDetection(
                        class_name=self.names[str(int(box.cls.item()))],
                        class_confidence=float(box.conf.item()),
                        bbox_px=BoundingBox(x=left, y=top, width=right - left, height=bottom - top),
                        frame=FrameSize(width=width, height=height),
                    )
                )
        return detections
