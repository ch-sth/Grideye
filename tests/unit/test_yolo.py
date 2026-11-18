from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from services.ai.model_store import ModelImportError, ModelStore
from services.ai.yolo import YoloDetector


async def test_real_yolo_checkpoint_import_reload_and_inference(tmp_path, monkeypatch):
    # Generate a small untrained checkpoint locally; no network or model weights are required.
    monkeypatch.setenv("YOLO_CONFIG_DIR", str(tmp_path / "yolo-settings"))
    monkeypatch.setenv("YOLO_AUTOINSTALL", "false")
    from ultralytics import YOLO

    path = tmp_path / "local.pt"
    model = YOLO("yolo11n.yaml")
    model.save(str(path))
    store = ModelStore(tmp_path / "models")
    state = store.import_path(str(path))
    assert state["models"][0]["classes"]
    assert state["active_id"] != "aruco"
    restored = ModelStore(store.directory)
    assert restored.selection()[0] == state["active_id"]
    ok, image = cv2.imencode(".jpg", np.zeros((200, 320, 3), dtype=np.uint8))
    assert ok
    assert await restored.selection()[1].detect(image.tobytes()) == []
    invalid = tmp_path / "invalid.pt"
    invalid.write_bytes(b"not a checkpoint")
    with pytest.raises(ModelImportError):
        store.import_path(str(invalid))
    assert store.selection()[0] == state["active_id"]


async def test_yolo_boxes_are_clipped_and_mapped(monkeypatch):
    import torch

    detector = YoloDetector.__new__(YoloDetector)
    detector.names = {"0": "package"}
    boxes = [
        SimpleNamespace(
            xyxy=torch.tensor([[-5.0, 10.0, 400.0, 190.0]]),
            cls=torch.tensor(0),
            conf=torch.tensor(0.8),
        ),
        SimpleNamespace(
            xyxy=torch.tensor([[400.0, 10.0, 410.0, 20.0]]),
            cls=torch.tensor(0),
            conf=torch.tensor(0.8),
        ),
    ]
    monkeypatch.setattr(detector, "_predict", lambda image: [SimpleNamespace(boxes=boxes)])
    ok, encoded = cv2.imencode(".png", np.zeros((200, 320, 3), dtype=np.uint8))
    assert ok
    detections = await detector.detect(encoded.tobytes())
    assert len(detections) == 1
    detection = detections[0]
    assert detection.class_name == "package"
    assert detection.class_confidence == pytest.approx(0.8)
    assert detection.bbox_px.model_dump() == {"x": 0, "y": 10, "width": 320, "height": 180}
    assert detection.frame.width == 320
