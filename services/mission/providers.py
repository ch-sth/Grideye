"""Provider boundaries. These implementations never send commands to real motors."""

from dataclasses import dataclass, field
from math import hypot
from typing import Protocol

from services.mission.models import GamepadInput, Point


class FlightController(Protocol):
    position: Point
    altitude: float
    connected: bool

    def move(self, target: Point, speed: float, dt: float) -> bool: ...
    def vertical(self, target: float, speed: float, dt: float) -> bool: ...
    def manual(self, x: float, y: float, z: float, dt: float) -> None: ...


class UwbManager(Protocol):
    quality: float
    connected: bool
    anchors: list[bool]
    age: float

    def tick(self, dt: float) -> None: ...


class GamepadManager(Protocol):
    state: GamepadInput
    age: float

    def update(self, state: GamepadInput) -> None: ...
    def tick(self, dt: float) -> None: ...


@dataclass
class SimulatedFlightController:
    position: Point = field(default_factory=lambda: Point(x=0.1, y=0.1))
    altitude: float = 0
    connected: bool = True

    def move(self, target: Point, speed: float, dt: float) -> bool:
        distance = hypot(target.x - self.position.x, target.y - self.position.y)
        if distance <= speed * dt:
            self.position = target.model_copy()
            return True
        fraction = speed * dt / distance
        self.position = Point(
            x=self.position.x + (target.x - self.position.x) * fraction,
            y=self.position.y + (target.y - self.position.y) * fraction,
        )
        return False

    def vertical(self, target: float, speed: float, dt: float) -> bool:
        difference = target - self.altitude
        self.altitude += max(-speed * dt, min(speed * dt, difference))
        return abs(target - self.altitude) < 1e-9

    def manual(self, x: float, y: float, z: float, dt: float) -> None:
        self.position = Point(x=self.position.x + x * dt * 0.3, y=self.position.y + y * dt * 0.3)
        self.altitude = max(0, min(10, self.altitude + z * dt * 0.3))


@dataclass
class SimulatedUwbProvider:
    quality: float = 0.96
    connected: bool = True
    anchors: list[bool] = field(default_factory=lambda: [True] * 4)
    age: float = 0

    def tick(self, dt: float) -> None:
        self.age = 0 if self.connected else self.age + dt


@dataclass
class SimulatedGamepad:
    state: GamepadInput = field(default_factory=GamepadInput)
    age: float = 0

    def update(self, state: GamepadInput) -> None:
        self.state, self.age = state, 0

    def tick(self, dt: float) -> None:
        self.age += dt
