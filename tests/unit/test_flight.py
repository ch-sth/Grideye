from uuid import uuid4

from grideye_shared.schemas import FlightCommand, FlightCommandType, Position3D
from simulation.flight_simulator.main import correlated_result


def test_result_keeps_command_correlation_id() -> None:
    command = FlightCommand(
        command_id=uuid4(), type=FlightCommandType.GOTO, target=Position3D(x_m=1, y_m=2, z_m=1.2)
    )
    assert correlated_result(command).command_id == command.command_id
