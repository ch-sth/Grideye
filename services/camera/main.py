"""Legacy standalone heartbeat. IP-camera capture runs in the backend via camera.live."""

import time

from grideye_shared.config.logging import configure_logging
from grideye_shared.mqtt import MqttServiceClient, service_status_topic
from grideye_shared.schemas import ServiceState, ServiceStatus


def main() -> None:
    configure_logging("camera")
    mqtt = MqttServiceClient("camera")
    mqtt.connect()
    while True:
        mqtt.publish(
            service_status_topic("camera"),
            ServiceStatus(service="camera", status=ServiceState.ONLINE),
            retain=True,
        )
        time.sleep(5)


if __name__ == "__main__":
    main()
