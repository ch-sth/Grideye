import asyncio
import json
import math
from uuid import UUID

from grideye_shared.config.logging import configure_logging
from grideye_shared.mqtt import TOPICS, MqttServiceClient, service_status_topic
from grideye_shared.schemas import (
    BatteryTelemetry,
    CommandStatus,
    FlightAttitude,
    FlightCommand,
    FlightCommandResult,
    FlightMode,
    ServiceState,
    ServiceStatus,
)


def correlated_result(command: FlightCommand) -> FlightCommandResult:
    return FlightCommandResult(command_id=command.command_id, status=CommandStatus.ACCEPTED)


class FlightSimulator:
    def __init__(self) -> None:
        self.mqtt = MqttServiceClient("flight-simulator", self.on_message)
        self.mqtt.subscribe(TOPICS.flight_command)

    def on_message(self, topic: str, payload: bytes) -> None:
        if topic == TOPICS.flight_command:
            try:
                command = FlightCommand.model_validate_json(payload)
                self.mqtt.publish(TOPICS.flight_command_result, correlated_result(command))
            except Exception as exc:
                raw = json.loads(payload)
                if command_id := raw.get("command_id"):
                    result = FlightCommandResult(
                        command_id=UUID(command_id), status=CommandStatus.REJECTED, message=str(exc)
                    )
                    self.mqtt.publish(TOPICS.flight_command_result, result)

    async def run(self) -> None:
        self.mqtt.connect()
        tick = 0
        while True:
            self.mqtt.publish(
                TOPICS.flight_attitude,
                FlightAttitude(roll_deg=0.2 * math.sin(tick / 10), pitch_deg=0, yaw_deg=90),
            )
            self.mqtt.publish(
                TOPICS.flight_battery,
                BatteryTelemetry(percent=max(0.2, 0.95 - tick / 10000), voltage_v=15.6),
            )
            self.mqtt.publish(TOPICS.flight_mode, FlightMode(mode="SIMULATION"), retain=True)
            if tick % 10 == 0:
                self.mqtt.publish(
                    service_status_topic("flight-simulator"),
                    ServiceStatus(service="flight-simulator", status=ServiceState.ONLINE),
                    retain=True,
                )
            tick += 1
            await asyncio.sleep(0.5)


if __name__ == "__main__":
    configure_logging("flight-simulator")
    asyncio.run(FlightSimulator().run())
