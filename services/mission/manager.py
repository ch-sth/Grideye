"""Authoritative simulation loop: missions continue independently of browser tabs."""

from collections import deque
from datetime import UTC, datetime

from services.mission.geometry import FlightField
from services.mission.models import MissionPlan, Point, SimulationInput
from services.mission.providers import (
    FlightController,
    GamepadManager,
    SimulatedFlightController,
    SimulatedGamepad,
    SimulatedUwbProvider,
    UwbManager,
)
from services.mission.safety import ControlManager, SafetyManager


class MissionManager:
    def __init__(
        self,
        grid: dict,
        safety: dict,
        flight: FlightController | None = None,
        uwb: UwbManager | None = None,
        gamepad: GamepadManager | None = None,
    ) -> None:
        self.field = FlightField(grid, safety["flight_margin_m"])
        self.safety = SafetyManager(safety)
        self.flight = flight or SimulatedFlightController(
            position=Point(
                x=self.field.x + self.field.cell_size / 2,
                y=self.field.y + self.field.cell_size / 2,
            )
        )
        self.uwb = uwb or SimulatedUwbProvider()
        self.gamepad = gamepad or SimulatedGamepad()
        self.control = ControlManager()
        self.plan: MissionPlan | None = None
        self.mission_id: str | None = None
        self.mission_status = "draft"
        self.state = "READY"
        self.index = 0
        self.hover_remaining = 0.0
        self.resume_state = "AUTO_MISSION"
        self.events: deque[dict] = deque(maxlen=50)
        self.event("Simulation bereit")

    @property
    def active(self) -> bool:
        return self.state in {"TAKEOFF", "AUTO_MISSION", "HOVER", "PAUSED", "LANDING"}

    def event(self, message: str) -> None:
        self.events.append({"timestamp": datetime.now(UTC).isoformat(), "message": message})

    def start(self, mission_id: str, plan: MissionPlan) -> None:
        self.field.validate(plan)
        if self.active or self.flight.altitude > 0.01:
            raise ValueError("Zuerst die aktive Mission beenden und landen.")
        if self.safety.reason:
            raise ValueError("Failsafe ist verriegelt. Ursache beheben und Reset ausführen.")
        if not self.uwb.connected:
            raise ValueError("UWB ist nicht verbunden.")
        issue = self.safety.issue(self.field, self.flight, self.uwb)
        if issue:
            raise ValueError(issue)
        if self.control.radio or self.control.manual:
            raise ValueError("Funk- oder USB-Handsteuerung ist aktiv.")
        self.plan, self.mission_id = plan, mission_id
        self.index, self.hover_remaining = 0, 0
        self.state, self.mission_status = "TAKEOFF", "running"
        self.event(f"Mission gestartet: {plan.name}")

    def pause(self) -> None:
        if self.state not in {"TAKEOFF", "AUTO_MISSION", "HOVER"}:
            raise ValueError("Keine pausierbare Mission aktiv.")
        self.resume_state, self.state = self.state, "PAUSED"
        self.mission_status = "paused"
        self.event("Mission pausiert; Position wird gehalten")

    def resume(self) -> None:
        if self.state != "PAUSED" or not self.plan:
            raise ValueError("Keine pausierte Mission vorhanden.")
        if self.control.radio or self.control.manual or self.safety.reason:
            raise ValueError("Handsteuerung oder Failsafe ist aktiv.")
        issue = self.safety.issue(self.field, self.flight, self.uwb)
        if issue:
            raise ValueError(issue)
        self.state, self.mission_status = self.resume_state, "running"
        self.event("Mission fortgesetzt")

    def land(self, aborted: bool = True) -> None:
        if aborted and self.plan:
            self.mission_status = "aborted"
        self.control.manual = False
        self.state = "FAILSAFE" if self.safety.reason else "LANDING"
        self.event("Kontrollierte Landung eingeleitet")

    def reset(self) -> None:
        if self.flight.altitude > 0.01 or self.active:
            raise ValueError("Reset ist erst nach der Landung möglich.")
        issue = self.safety.issue(self.field, self.flight, self.uwb)
        if issue:
            raise ValueError(f"Ursache zuerst beheben: {issue}")
        if self.control.radio or self.control.manual:
            raise ValueError("Handsteuerung zuerst freigeben.")
        self.safety.reason, self.safety.failures = None, 0
        self.state, self.index, self.hover_remaining = "READY", 0, 0
        self.event("Reset; gespeicherter Missionspfad bleibt erhalten")

    def inject(self, body: SimulationInput) -> None:
        if body.position is not None:
            self.flight.position = body.position
        if body.radio is not None:
            self.control.radio = body.radio
            if body.radio and self.state in {"TAKEOFF", "AUTO_MISSION", "HOVER"}:
                self.pause()
        if body.quality is not None:
            self.uwb.quality = body.quality
        if body.uwb_connected is not None:
            self.uwb.connected = body.uwb_connected
        if body.flight_connected is not None:
            self.flight.connected = body.flight_connected
        if body.anchor_connected is not None:
            self.uwb.anchors = body.anchor_connected
        if body.gamepad is not None:
            pad = body.gamepad
            self.gamepad.update(pad)
            if not self.control.radio and not self.safety.reason:
                if pad.l1 and pad.r1 and pad.connected:
                    if self.state in {"TAKEOFF", "AUTO_MISSION", "HOVER"}:
                        self.pause()
                    self.control.manual = True
                if pad.l2 and pad.r2:
                    self.control.manual = False
                if pad.circle:
                    self.land()

    def tick(self, dt: float) -> None:
        dt = max(0, min(dt, 0.25))
        self.uwb.tick(dt)
        self.gamepad.tick(dt)
        # Safety runs for every source, even while paused or under radio override.
        if self.safety.check(self.field, self.flight, self.uwb):
            if self.state != "FAILSAFE" and (self.state != "LANDED" or self.flight.altitude > 0):
                self.control.manual = False
                self.mission_status = "aborted" if self.plan else "draft"
                self.state = "FAILSAFE"
                self.event(f"FAILSAFE: {self.safety.reason}")
        pad_lost = (
            not self.gamepad.state.connected
            or self.gamepad.age > self.safety.settings["gamepad_timeout_seconds"]
        )
        if self.control.manual and pad_lost:
            if not self.control.radio and self.flight.altitude > 0:
                self.safety.reason = "USB-Gamepad-Verbindung verloren"
                self.state, self.mission_status = "FAILSAFE", "aborted"
                self.event(f"FAILSAFE: {self.safety.reason}")
            self.control.manual = False
        if self.state in {"FAILSAFE", "LANDING"}:
            if self.flight.vertical(0, self.safety.settings["landing_speed_m_s"], dt):
                self.state = "LANDED"
                if self.mission_status == "running":
                    self.mission_status = "completed"
                self.event("LANDED")
            return
        if self.safety.reason or self.control.radio:
            return
        if self.control.manual:
            if self.gamepad.age > self.safety.settings["gamepad_timeout_seconds"]:
                return
            pad = self.gamepad.state
            deadzone = self.safety.settings["gamepad_deadzone"]
            x, y, z = (v if abs(v) > deadzone else 0 for v in [pad.x, pad.y, pad.z])
            self.flight.manual(x, y, z, dt)
            return
        if self.state == "TAKEOFF" and self.plan:
            if self.flight.vertical(self.plan.altitude, 0.4, dt):
                self.state = "AUTO_MISSION"
        elif self.state == "HOVER":
            self.hover_remaining = max(0, self.hover_remaining - dt)
            if self.hover_remaining <= 1e-9:
                self.index += 1
                self.state = "AUTO_MISSION"
        elif self.state == "AUTO_MISSION" and self.plan:
            points = [self.plan.start, *self.plan.waypoints, self.plan.end]
            # Restore nominal altitude after manual takeover without advancing the route.
            if not self.flight.vertical(self.plan.altitude, 0.4, dt):
                return
            if self.flight.move(points[self.index], self.plan.speed, dt):
                if self.index == len(points) - 1:
                    self.land(aborted=False)
                elif self.index == 0:
                    self.index += 1
                else:
                    self.state, self.hover_remaining = "HOVER", self.plan.hover_time

    def snapshot(self) -> dict:
        position = self.flight.position
        source = self.control.source(
            bool(self.safety.reason), self.state in {"TAKEOFF", "AUTO_MISSION", "HOVER"}
        )
        display_state = (
            "RADIO OVERRIDE"
            if source == "RADIO"
            else ("MANUAL USB" if source == "USB GAMEPAD" else self.state)
        )
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "mode": "SIMULATION",
            "position": {"x": position.x, "y": position.y, "z": self.flight.altitude},
            "grid": self.field.cell(position),
            "zone": self.field.zone(position),
            "flight_state": display_state,
            "mission_state": self.state,
            "control_source": source,
            "failsafe": self.safety.reason is not None,
            "failsafe_reason": self.safety.reason,
            "valid_anchors": sum(self.uwb.anchors),
            "anchor_connected": self.uwb.anchors,
            "uwb_quality": self.uwb.quality,
            "uwb_age": self.uwb.age,
            "uwb_connected": self.uwb.connected,
            "flight_connected": self.flight.connected,
            "gamepad_connected": self.gamepad.state.connected,
            "gamepad_age": self.gamepad.age,
            "mission": {
                "id": self.mission_id,
                "status": self.mission_status,
                "active": self.active,
                "waypoint": self.index,
                "waypoint_count": len(self.plan.waypoints) if self.plan else 0,
                "hover_remaining": self.hover_remaining,
            },
            "events": list(self.events),
        }
