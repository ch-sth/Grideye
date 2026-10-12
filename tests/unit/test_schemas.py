from uuid import uuid4

import pytest
from pydantic import ValidationError

from grideye_shared.schemas import (
    BoundingBox,
    FrameSize,
    GridDetection,
    GridLocation,
    Position3D,
    UwbPosition,
    WorldPosition,
)


def test_uwb_position_serializes_utc_iso8601() -> None:
    model = UwbPosition(position=Position3D(x_m=1.245, y_m=0.834, z_m=1.182), quality=0.94)
    assert model.model_dump(mode="json")["timestamp"].endswith("Z")
    assert UwbPosition.model_validate_json(model.model_dump_json()) == model


def test_confidence_is_bounded() -> None:
    with pytest.raises(ValidationError):
        UwbPosition(position=Position3D(x_m=0, y_m=0, z_m=0), quality=1.01)


def make_grid_detection(number: str = "4712", x: float = 1) -> GridDetection:
    return GridDetection(
        detection_id=uuid4(),
        class_name="package",
        class_confidence=0.94,
        number=number,
        ocr_confidence=0.91,
        bbox_px=BoundingBox(x=1, y=2, width=3, height=4),
        frame=FrameSize(width=100, height=100),
        world=WorldPosition(x_m=x, y_m=1),
        grid=GridLocation(cell="B1", column=1, row=0),
    )
