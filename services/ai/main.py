"""AI service integration boundary.

TODO: attach CameraProvider, ArUco ObjectDetector and publish detections.
ArUco detection is implemented in detectors.ArucoDetector; camera wiring remains pending.
"""

import time

from grideye_shared.config.logging import configure_logging
from grideye_shared.mqtt import MqttServiceClient, service_status_topic
from grideye_shared.schemas import ServiceState, ServiceStatus


def main() -> None:
    configure_logging("ai")
    mqtt = MqttServiceClient("ai")
    mqtt.connect()
    while True:
        mqtt.publish(
            service_status_topic("ai"),
            ServiceStatus(service="ai", status=ServiceState.ONLINE),
            retain=True,
        )
        time.sleep(5)


if __name__ == "__main__":
    main()
