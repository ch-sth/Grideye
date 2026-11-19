"""Apply the selected detector to live frames independently of API requests."""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from grideye_shared.mqtt import TOPICS, service_status_topic
from grideye_shared.schemas import ServiceState, ServiceStatus
from services.ai.detectors import ArucoDetector
from services.backend.database import SessionLocal, TaggedObjectRow
from services.backend.state import runtime


def associate_markers(objects, markers):
    """Associate a tag only when its center belongs to exactly one object."""
    matches = [[] for _ in objects]
    for marker in markers:
        b = marker.bbox_px
        x, y = b.x + b.width / 2, b.y + b.height / 2
        candidates = [
            i
            for i, obj in enumerate(objects)
            if obj.frame == marker.frame
            and obj.bbox_px.x <= x <= obj.bbox_px.x + obj.bbox_px.width
            and obj.bbox_px.y <= y <= obj.bbox_px.y + obj.bbox_px.height
        ]
        if len(candidates) == 1 and marker.number is not None:
            matches[candidates[0]].append(marker)
    return [
        obj.model_copy(
            update={"number": found[0].number, "marker_confidence": found[0].marker_confidence}
        )
        if len(found) == 1
        else obj
        for obj, found in zip(objects, matches, strict=True)
    ]


async def persist_tagged_objects(detections):
    if not any(item.number is not None for item in detections):
        return
    async with SessionLocal() as session:
        for item in detections:
            if item.number is None:
                continue
            existing = await session.scalar(
                select(TaggedObjectRow).where(TaggedObjectRow.number == item.number)
            )
            if existing is None:
                session.add(
                    TaggedObjectRow(
                        id=item.detection_id,
                        timestamp=item.timestamp,
                        class_name=item.class_name,
                        number=item.number,
                        confidence=item.class_confidence,
                    )
                )
        await session.commit()


async def vision_loop(app) -> None:
    camera, store, bridge = app.state.camera, app.state.model_store, app.state.bridge
    previous_frame = None
    previous_id = None
    aruco = ArucoDetector()
    while True:
        frame = camera.frame()
        camera_status = camera.status()
        model_id, detector = store.selection()
        if frame is None:
            app.state.ai_result = {
                "active_id": model_id,
                "camera_revision": camera_status["revision"],
                "status": "waiting",
                "message": "Warte auf Kamerabild.",
                "detections": [],
            }
        elif frame is not previous_frame or model_id != previous_id:
            try:
                detections = await detector.detect(frame)
                if model_id != "aruco":
                    markers = await aruco.detect(frame)
                    detections = associate_markers(detections, markers)
                value = {
                    "active_id": model_id,
                    "camera_revision": camera_status["revision"],
                    "timestamp": datetime.now(UTC).isoformat(),
                    "status": "online",
                    "message": "Kamerabild ausgewertet.",
                    "detections": [item.model_dump(mode="json") for item in detections],
                }
                if (
                    store.selection()[0] == model_id
                    and camera.status()["revision"] == camera_status["revision"]
                    and camera.status()["has_frame"]
                ):
                    app.state.ai_result = value
                    runtime.latest["ai.detections"] = value
                    if model_id != "aruco":
                        try:
                            await persist_tagged_objects(detections)
                        except Exception:
                            logging.getLogger(__name__).exception("Saving tagged objects failed")
                            value["status"] = "error"
                            value["message"] = "Erkennung erfolgreich, Speichern fehlgeschlagen."
                    for detection in detections:
                        bridge.client.publish(TOPICS.ai_detection, detection)
                    await runtime.broadcast({"type": "ai.detections", "data": value})
            except Exception:
                app.state.ai_result = {
                    "active_id": model_id,
                    "camera_revision": camera_status["revision"],
                    "status": "error",
                    "message": "Auswertung mit dem aktiven Modell fehlgeschlagen.",
                    "detections": [],
                }
            previous_frame, previous_id = frame, model_id
        state = getattr(app.state, "ai_result", {}).get("status")
        status = ServiceStatus(
            service="ai", status=ServiceState.ERROR if state == "error" else ServiceState.ONLINE
        )
        runtime.services["ai"] = status
        bridge.client.publish(service_status_topic("ai"), status, retain=True)
        await asyncio.sleep(0.5)
