import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from grideye_shared.mqtt import TOPICS
from grideye_shared.schemas import AiDetection, BoundingBox, FrameSize
from services.backend import vision


@pytest.mark.parametrize("change_during_inference", [None, "model", "camera"])
async def test_live_loop_uses_active_detector_and_discards_stale_results(
    monkeypatch, change_during_inference
):
    detection = AiDetection(
        class_name="package",
        class_confidence=0.8,
        bbox_px=BoundingBox(x=0, y=0, width=20, height=20),
        frame=FrameSize(width=100, height=100),
    )
    current = {"model": "first", "camera": 1}
    camera = Mock()
    camera.frame.return_value = b"frame"
    camera.status.side_effect = lambda: {"revision": current["camera"], "has_frame": True}

    async def detect(frame):
        assert frame == b"frame"
        if change_during_inference == "model":
            current["model"] = "second"
        if change_during_inference == "camera":
            current["camera"] = 2
        return [detection]

    detector = SimpleNamespace(detect=detect)
    store = Mock()
    store.selection.side_effect = lambda: (current["model"], detector)
    bridge = SimpleNamespace(client=Mock())
    state = SimpleNamespace(camera=camera, model_store=store, bridge=bridge)
    app = SimpleNamespace(state=state)
    runtime = SimpleNamespace(latest={}, services={}, broadcast=AsyncMock())
    monkeypatch.setattr(vision, "runtime", runtime)

    async def stop_after_iteration(seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(vision, "asyncio", SimpleNamespace(sleep=stop_after_iteration))
    with pytest.raises(asyncio.CancelledError):
        await vision.vision_loop(app)
    published = [
        call.args
        for call in bridge.client.publish.call_args_list
        if call.args[0] == TOPICS.ai_detection
    ]
    if change_during_inference:
        assert published == []
        assert not hasattr(state, "ai_result")
    else:
        assert published == [(TOPICS.ai_detection, detection)]
        assert state.ai_result["active_id"] == "first"
        assert state.ai_result["detections"][0]["class_name"] == "package"
        runtime.broadcast.assert_awaited_once()
