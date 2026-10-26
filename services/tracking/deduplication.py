from dataclasses import dataclass
from math import hypot

from grideye_shared.schemas import ConfirmedDetection, GridDetection


@dataclass
class DetectionTracker:
    proximity_m: float = 0.5

    def __post_init__(self) -> None:
        self.confirmed: list[ConfirmedDetection] = []

    def process(self, detection: GridDetection) -> ConfirmedDetection | None:
        duplicate = any(
            item.number == detection.number
            and hypot(item.world.x_m - detection.world.x_m, item.world.y_m - detection.world.y_m)
            <= self.proximity_m
            for item in self.confirmed
        )
        if duplicate:
            return None
        result = ConfirmedDetection(
            detection_id=detection.detection_id,
            timestamp=detection.timestamp,
            class_name=detection.class_name,
            number=detection.number,
            world=detection.world,
            grid=detection.grid,
            confidence=min(
                detection.class_confidence,
                (detection.marker_confidence if detection.marker_confidence is not None else 1.0),
            ),
        )
        self.confirmed.append(result)
        return result
