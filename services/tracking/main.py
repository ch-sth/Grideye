import time

from grideye_shared.config.files import read_config
from grideye_shared.config.logging import configure_logging
from grideye_shared.mqtt import TOPICS, MqttServiceClient, service_status_topic
from grideye_shared.schemas import GridDetection, ServiceState, ServiceStatus
from services.tracking.deduplication import DetectionTracker


def main() -> None:
    configure_logging("tracking")
    tracker = DetectionTracker(proximity_m=read_config("tracking")["proximity_m"])
    mqtt: MqttServiceClient

    def handle(topic: str, payload: bytes) -> None:
        if topic == TOPICS.grid_detection and (
            result := tracker.process(GridDetection.model_validate_json(payload))
        ):
            mqtt.publish(TOPICS.detection_confirmed, result)

    mqtt = MqttServiceClient("tracking", handle)
    mqtt.subscribe(TOPICS.grid_detection)
    mqtt.connect()
    while True:
        mqtt.publish(
            service_status_topic("tracking"),
            ServiceStatus(service="tracking", status=ServiceState.ONLINE),
            retain=True,
        )
        time.sleep(5)


if __name__ == "__main__":
    main()
