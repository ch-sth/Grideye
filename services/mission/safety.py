from dataclasses import dataclass

from services.mission.geometry import FlightField
from services.mission.providers import FlightController, UwbManager


@dataclass
class SafetyManager:
    settings: dict
    failures: int = 0
    reason: str | None = None

    def issue(self, field: FlightField, flight: FlightController, uwb: UwbManager) -> str | None:
        if not flight.connected:
            return "Flight-Controller-Verbindung verloren"
        if uwb.age > self.settings["position_timeout_seconds"]:
            return "UWB-Kommunikation verloren"
        if sum(uwb.anchors) < self.settings["minimum_anchors"]:
            return "Zu wenige gültige UWB-Anker"
        if uwb.quality < self.settings["minimum_quality"]:
            return "UWB-Qualität zu niedrig"
        if field.zone(flight.position) == "FAILSAFE_ZONE":
            return "Erlaubte Flugzone verlassen"
        return None

    def check(self, field: FlightField, flight: FlightController, uwb: UwbManager) -> bool:
        issue = self.issue(field, flight, uwb)
        self.failures = self.failures + 1 if issue else 0
        if issue and self.failures >= self.settings["consecutive_bad_samples"]:
            self.reason = issue
        return self.reason is not None


@dataclass
class ControlManager:
    radio: bool = False
    manual: bool = False

    def source(self, failsafe: bool, auto: bool) -> str:
        if failsafe:
            return "FAILSAFE"
        if self.radio:
            return "RADIO"
        if self.manual:
            return "USB GAMEPAD"
        return "AUTO" if auto else "NONE"
