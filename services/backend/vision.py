"""Apply the selected detector to live frames independently of API requests."""

import asyncio
from datetime import UTC, datetime

from grideye_shared.mqtt import TOPICS, service_status_topic
from grideye_shared.schemas import ServiceState, ServiceStatus
from services.backend.state import runtime


async def vision_loop(app) -> None:
    camera, store, bridge = app.state.camera, app.state.model_store, app.state.bridge
    previous_frame = None
    previous_id = None
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
