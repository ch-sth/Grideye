import asyncio
import os

from grideye_shared.adapters import UwbProvider
from grideye_shared.config.files import read_config
from grideye_shared.config.logging import configure_logging
from grideye_shared.mqtt import TOPICS, MqttServiceClient, service_status_topic
from grideye_shared.schemas import Position3D, ServiceState, ServiceStatus, UwbPosition


class SimulatedUwbProvider(UwbProvider):
    def __init__(self, width: float = 4.0, height: float = 3.0, altitude: float = 1.2) -> None:
        self.width, self.height, self.altitude = width, height, altitude

    async def positions(self):  # type: ignore[override]
        tick = 0
        while True:
            phase = (tick % 400) / 400
            perimeter = 2 * (self.width + self.height)
            distance = phase * perimeter
            if distance < self.width:
                x, y = distance, 0.0
            elif distance < self.width + self.height:
                x, y = self.width, distance - self.width
            elif distance < 2 * self.width + self.height:
                x, y = 2 * self.width + self.height - distance, self.height
            else:
                x, y = 0.0, perimeter - distance
            yield UwbPosition(position=Position3D(x_m=x, y_m=y, z_m=self.altitude), quality=0.95)
            tick += 1
            await asyncio.sleep(0.1)


async def run() -> None:
    service = "uwb-simulator"
    configure_logging(service)
    mqtt = MqttServiceClient(service)
    mqtt.connect()
    config = read_config("uwb")
    provider = SimulatedUwbProvider(
        float(os.getenv("UWB_GRID_WIDTH_M", config["width_m"])),
        float(os.getenv("UWB_GRID_HEIGHT_M", config["height_m"])),
        config["altitude_m"],
    )
    heartbeat_at = 0.0
    loop = asyncio.get_running_loop()
    async for position in provider.positions():
        mqtt.publish(TOPICS.uwb_position, position)
        if loop.time() >= heartbeat_at:
            mqtt.publish(
                service_status_topic(service),
                ServiceStatus(service=service, status=ServiceState.ONLINE),
                retain=True,
            )
            heartbeat_at = loop.time() + 5


if __name__ == "__main__":
    asyncio.run(run())
