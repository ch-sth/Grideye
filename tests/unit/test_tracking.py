from services.tracking.deduplication import DetectionTracker
from tests.unit.test_schemas import make_grid_detection


def test_deduplicates_same_number_nearby() -> None:
    tracker = DetectionTracker(proximity_m=0.5)
    assert tracker.process(make_grid_detection(x=1.0)) is not None
    assert tracker.process(make_grid_detection(x=1.2)) is None
    assert tracker.process(make_grid_detection(number="999", x=1.2)) is not None
