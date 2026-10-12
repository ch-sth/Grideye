from collections.abc import AsyncIterator
from typing import Protocol

from grideye_shared.schemas import FlightAttitude, FlightCommand, FlightCommandResult, UwbPosition


class UwbProvider(Protocol):
    async def positions(self) -> AsyncIterator[UwbPosition]: ...


class FlightAdapter(Protocol):
    """Future MAVLink boundary. Implementations must not bypass FC failsafes."""

    async def attitude(self) -> FlightAttitude: ...
    async def execute(self, command: FlightCommand) -> FlightCommandResult: ...


class CameraProvider(Protocol):
    async def frames(self) -> AsyncIterator[bytes]: ...
