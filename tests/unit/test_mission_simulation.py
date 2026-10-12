import pytest
from pydantic import ValidationError

from grideye_shared.config.files import AnchorSettings, read_config
from services.mission.geometry import FlightField
from services.mission.manager import MissionManager
from services.mission.models import GamepadInput, MissionPlan, Point, SimulationInput


@pytest.fixture
def manager():
    return MissionManager(
        {"origin": {"x_m": 0, "y_m": 0}, "cell_size_m": 0.2, "rows": 10, "columns": 10},
        read_config("safety"),
    )


@pytest.fixture
def plan():
    return MissionPlan(
        name="Unit mission",
        start=Point(x=-0.1, y=0.1),
        waypoints=[Point(x=0.3, y=0.3), Point(x=0.5, y=0.5)],
        end=Point(x=2.1, y=0.5),
        hover_time=0.5,
        altitude=0.2,
        speed=2,
    )


def advance(manager, seconds):
    for _ in range(round(seconds / 0.1)):
        manager.tick(0.1)


@pytest.mark.parametrize(
    "point,zone,cell",
    [
        (Point(x=0, y=0), "GRID", "A1"),
        (Point(x=2, y=2), "GRID", "J10"),
        (Point(x=-0.25, y=1), "FLIGHT_ZONE", None),
        (Point(x=2.25, y=2.25), "FLIGHT_ZONE", None),
        (Point(x=2.25001, y=1), "FAILSAFE_ZONE", None),
    ],
)
def test_grid_and_flight_zone_boundaries(manager, point, zone, cell):
    assert manager.field.zone(point) == zone
    assert manager.field.cell(point) == cell


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("free", (0.43, 0.61)),
        ("center", (0.5, 0.7)),
        ("intersection", (0.4, 0.6)),
        ("auto", (0.4, 0.6)),
    ],
)
def test_snapping(manager, mode, expected):
    point = manager.field.snap(Point(x=0.43, y=0.61), mode)
    assert (point.x, point.y) == pytest.approx(expected)


def test_start_and_end_are_unsnapped_and_validated(manager, plan):
    manager.start("mission", plan)
    assert manager.plan.start.x == -0.1
    assert manager.plan.end.x == 2.1
    invalid = plan.model_copy(update={"waypoints": [Point(x=-0.1, y=0.1)]})
    with pytest.raises(ValueError):
        manager.field.validate(invalid)


def test_hover_pause_and_completion(manager, plan):
    manager.start("mission", plan)
    while manager.state != "HOVER":
        manager.tick(0.1)
    index = manager.index
    manager.pause()
    hover_remaining = manager.hover_remaining
    advance(manager, 1)
    assert manager.hover_remaining == hover_remaining
    manager.resume()
    advance(manager, 0.2)
    assert manager.index == index
    assert manager.hover_remaining < hover_remaining
    advance(manager, 10)
    assert manager.state == "LANDED"
    assert manager.mission_status == "completed"
    assert manager.flight.altitude == 0
    assert manager.flight.position == plan.end
    manager.start("mission", plan)
    assert manager.state == "TAKEOFF"
    assert manager.index == 0


def test_abort_and_reset_preserve_path(manager, plan):
    manager.start("mission", plan)
    advance(manager, 1)
    manager.land()
    advance(manager, 2)
    assert manager.mission_status == "aborted"
    assert manager.plan is plan
    manager.reset()
    assert manager.plan is plan
    manager.start("mission", plan)
    assert manager.state == "TAKEOFF"


def test_radio_gamepad_auto_priorities(manager, plan):
    manager.start("mission", plan)
    manager.inject(SimulationInput(gamepad=GamepadInput(l1=True, r1=True)))
    assert manager.snapshot()["control_source"] == "USB GAMEPAD"
    assert manager.state == "PAUSED"
    manager.inject(SimulationInput(radio=True))
    assert manager.snapshot()["control_source"] == "RADIO"
    manager.inject(SimulationInput(gamepad=GamepadInput(l2=True, r2=True)))
    assert manager.control.manual  # USB release is ignored while radio controls.
    manager.inject(SimulationInput(radio=False))
    manager.inject(SimulationInput(gamepad=GamepadInput(l2=True, r2=True)))
    assert manager.snapshot()["control_source"] == "NONE"
    manager.resume()
    assert manager.snapshot()["control_source"] == "AUTO"


def test_single_bad_sample_recovers(manager, plan):
    manager.start("mission", plan)
    safe = manager.flight.position
    manager.inject(SimulationInput(position=Point(x=3, y=1)))
    manager.tick(0.1)
    manager.inject(SimulationInput(position=safe))
    manager.tick(0.1)
    assert manager.safety.reason is None


@pytest.mark.parametrize(
    "input",
    [
        SimulationInput(position=Point(x=3, y=1)),
        SimulationInput(anchor_connected=[True, True, False, False]),
        SimulationInput(quality=0.1),
        SimulationInput(flight_connected=False),
    ],
)
def test_failsafe_aborts_and_lands_without_horizontal_motion(manager, plan, input):
    manager.start("mission", plan)
    advance(manager, 1)
    manager.inject(input)
    for _ in range(3):
        manager.tick(0.1)
    assert manager.safety.reason is not None
    assert manager.snapshot()["control_source"] == "FAILSAFE"
    frozen_position = manager.flight.position.model_copy()
    advance(manager, 5)
    assert manager.state == "LANDED"
    assert manager.mission_status == "aborted"
    assert manager.flight.position == frozen_position
    assert manager.plan is plan
    with pytest.raises(ValueError):
        manager.start("mission", plan)


def test_uwb_timeout(manager, plan):
    manager.start("mission", plan)
    manager.inject(SimulationInput(uwb_connected=False))
    advance(manager, 1)
    assert manager.safety.reason is None
    advance(manager, 2)
    assert "UWB-Kommunikation" in manager.safety.reason


def test_gamepad_timeout_and_failsafe_at_landed_state(manager):
    manager.state = "LANDED"
    manager.inject(SimulationInput(gamepad=GamepadInput(l1=True, r1=True, z=1)))
    manager.tick(0.2)
    assert manager.flight.altitude > 0
    manager.inject(SimulationInput(position=Point(x=3, y=1)))
    advance(manager, 3)
    assert manager.safety.reason is not None
    assert manager.flight.altitude == 0


def test_gamepad_timeout(manager, plan):
    manager.start("mission", plan)
    advance(manager, 1)
    manager.inject(SimulationInput(gamepad=GamepadInput(l1=True, r1=True)))
    advance(manager, 2)
    assert manager.safety.reason == "USB-Gamepad-Verbindung verloren"
    advance(manager, 2)
    assert manager.flight.altitude == 0


def test_manual_failsafe_can_reset(manager, plan):
    manager.start("mission", plan)
    advance(manager, 1)
    manager.inject(SimulationInput(gamepad=GamepadInput(l1=True, r1=True)))
    manager.inject(SimulationInput(position=Point(x=3, y=1)))
    advance(manager, 3)
    assert manager.state == "LANDED"
    assert manager.control.manual is False
    manager.inject(SimulationInput(position=Point(x=0.1, y=0.1)))
    manager.reset()
    assert manager.safety.reason is None
    assert manager.plan is plan


def test_deadzone_circle_and_radio_failsafe(manager):
    origin = manager.flight.position.model_copy()
    manager.inject(SimulationInput(gamepad=GamepadInput(l1=True, r1=True, x=0.1)))
    manager.tick(0.1)
    assert manager.flight.position == origin
    manager.inject(SimulationInput(gamepad=GamepadInput(z=1)))
    manager.tick(0.1)
    manager.inject(SimulationInput(gamepad=GamepadInput(circle=True)))
    advance(manager, 1)
    assert manager.flight.altitude == 0
    manager.inject(SimulationInput(radio=True, position=Point(x=3, y=1)))
    advance(manager, 1)
    assert manager.snapshot()["control_source"] == "FAILSAFE"


def test_anchor_configuration_unique():
    with pytest.raises(ValidationError):
        AnchorSettings(devices=["SIM-UWB-001"] * 4)


def test_custom_grid():
    field = FlightField(
        {"origin": {"x_m": 5, "y_m": 8}, "cell_size_m": 0.5, "rows": 6, "columns": 8}
    )
    assert field.cell(Point(x=5.25, y=8.25)) == "A1"
    assert field.zone(Point(x=4.8, y=8)) == "FLIGHT_ZONE"
