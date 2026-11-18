"""AI service integration boundary.

Legacy standalone heartbeat only.
Live inference and model switching run in the backend via backend.vision and model_api.
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
