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

    monkeypatch.setattr(
        vision, "ArucoDetector", lambda: SimpleNamespace(detect=AsyncMock(return_value=[]))
    )
    monkeypatch.setattr(vision, "persist_tagged_objects", AsyncMock())
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


def test_associates_only_unambiguous_tags():
    def detection(name, x, y, width, height, number=None):
        return AiDetection(
            class_name=name,
            class_confidence=0.9,
            number=number,
            marker_confidence=1.0 if number is not None else None,
            bbox_px=BoundingBox(x=x, y=y, width=width, height=height),
            frame=FrameSize(width=100, height=100),
        )

    objects = [detection("Trafo", 0, 0, 50, 50), detection("Kiste", 40, 0, 50, 50)]
    tag = detection("aruco", 10, 10, 5, 5, "42")
    result = vision.associate_markers(objects, [tag])
    assert [item.number for item in result] == ["42", None]
    ambiguous = detection("aruco", 42, 10, 5, 5, "43")
    assert all(item.number is None for item in vision.associate_markers(objects, [ambiguous]))
    second_tag = detection("aruco", 20, 10, 5, 5, "44")
    assert vision.associate_markers(objects, [tag, second_tag])[0].number is None


async def test_persist_tagged_objects_saves_only_new_matched_tags(monkeypatch):
    item = AiDetection(
        class_name="Trafo",
        class_confidence=0.9,
        number="42",
        bbox_px=BoundingBox(x=0, y=0, width=20, height=20),
        frame=FrameSize(width=100, height=100),
    )
    session = AsyncMock()
    session.scalar.return_value = None
    session.add = Mock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(vision, "SessionLocal", lambda: context)
    await vision.persist_tagged_objects([item])
    row = session.add.call_args.args[0]
    assert (row.class_name, row.number, row.confidence) == ("Trafo", "42", 0.9)
    session.commit.assert_awaited_once()
    session.add.reset_mock()
    session.scalar.return_value = row
    await vision.persist_tagged_objects([item])
    session.add.assert_not_called()
