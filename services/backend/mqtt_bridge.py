import asyncio
import json
import logging
from datetime import UTC, datetime

from grideye_shared.mqtt import TOPICS, MqttServiceClient
from grideye_shared.schemas import ConfirmedDetection, ServiceStatus
from services.backend.database import DetectionRow, SessionLocal
from services.backend.state import runtime

EVENT_TYPES = {
    TOPICS.uwb_position: "uwb.position",
    TOPICS.flight_attitude: "flight.attitude",
    TOPICS.flight_battery: "flight.battery",
    TOPICS.flight_mode: "flight.mode",
    TOPICS.mission_status: "mission.status",
    TOPICS.mission_progress: "mission.progress",
    TOPICS.detection_confirmed: "detection.confirmed",
    TOPICS.system_events: "system.event",
}


class MqttBridge:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.log = logging.getLogger("backend")
        self.client = MqttServiceClient("backend", self._on_message)
        for topic in EVENT_TYPES:
            self.client.subscribe(topic)
        self.client.subscribe(TOPICS.service_status_wildcard)

    def start(self) -> None:
        self.client.connect()

    def stop(self) -> None:
        self.client.disconnect()

    def _on_message(self, topic: str, payload: bytes) -> None:
        try:
            data = json.loads(payload)
            event_type = EVENT_TYPES.get(topic)
            if topic.startswith("grideye/system/services/"):
                status = ServiceStatus.model_validate(data)
                runtime.services[status.service] = status
                event_type = "service.status"
            if event_type:
                runtime.latest[event_type] = data
                envelope = {
                    "type": event_type,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": data,
                }
                asyncio.run_coroutine_threadsafe(runtime.broadcast(envelope), self.loop)
            if topic == TOPICS.detection_confirmed:
                detection = ConfirmedDetection.model_validate(data)
                asyncio.run_coroutine_threadsafe(self._persist_detection(detection), self.loop)
        except Exception:
            self.log.exception("invalid MQTT message on %s", topic)

    async def _persist_detection(self, item: ConfirmedDetection) -> None:
        async with SessionLocal() as session:
            if await session.get(DetectionRow, item.detection_id) is None:
                session.add(
                    DetectionRow(
                        id=item.detection_id,
                        timestamp=item.timestamp,
                        mission_id=item.mission_id,
                        class_name=item.class_name,
                        number=item.number,
                        confidence=item.confidence,
                        world_x_m=item.world.x_m,
                        world_y_m=item.world.y_m,
                        grid_cell=item.grid.cell,
                        image_reference=item.image_reference,
                    )
                )
                await session.commit()
