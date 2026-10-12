from grideye_shared.coordinates import GridConfig
from grideye_shared.schemas import (
    AiDetection,
    BoundingBox,
    FlightAttitude,
    FrameSize,
    Position3D,
    UwbPosition,
)
from services.grid_mapping.projection import CameraCalibration, project_nadir


def test_center_pixel_projects_below_drone() -> None:
    detection = AiDetection(
        class_name="package",
        class_confidence=0.9,
        bbox_px=BoundingBox(x=45, y=45, width=10, height=10),
        frame=FrameSize(width=100, height=100),
    )
    result = project_nadir(
        detection,
        UwbPosition(position=Position3D(x_m=1, y_m=1, z_m=1), quality=1),
        FlightAttitude(roll_deg=0, pitch_deg=0, yaw_deg=0),
        CameraCalibration(100, 100, 50, 50),
        GridConfig(0, 0, 0.5, 4, 4),
    )
    assert result.world.x_m == result.world.y_m == 1
    assert result.grid.cell == "C3"
