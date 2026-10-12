from dataclasses import dataclass

from grideye_shared.coordinates import GridConfig, world_to_grid
from grideye_shared.schemas import (
    AiDetection,
    FlightAttitude,
    GridDetection,
    UwbPosition,
    WorldPosition,
)


@dataclass(frozen=True)
class CameraCalibration:
    fx_px: float
    fy_px: float
    cx_px: float
    cy_px: float


def project_nadir(
    detection: AiDetection,
    position: UwbPosition,
    attitude: FlightAttitude,
    calibration: CameraCalibration,
    grid: GridConfig,
) -> GridDetection:
    """Simplified pinhole projection for exact nadir and level attitude only.

    TODO: homography, yaw/extrinsics and distortion correction.
    """
    if abs(attitude.roll_deg) > 1e-9 or abs(attitude.pitch_deg) > 1e-9:
        raise ValueError("simplified projection requires roll=pitch=0")
    bbox = detection.bbox_px
    pixel_x, pixel_y = bbox.x + bbox.width / 2, bbox.y + bbox.height / 2
    altitude = position.position.z_m
    world = WorldPosition(
        x_m=position.position.x_m + (pixel_x - calibration.cx_px) * altitude / calibration.fx_px,
        y_m=position.position.y_m + (pixel_y - calibration.cy_px) * altitude / calibration.fy_px,
    )
    return GridDetection(
        **detection.model_dump(), world=world, grid=world_to_grid(world.x_m, world.y_m, grid)
    )
