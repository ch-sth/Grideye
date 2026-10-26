from services.tracking.deduplication import DetectionTracker
from tests.unit.test_schemas import make_grid_detection


def test_deduplicates_same_number_nearby() -> None:
    tracker = DetectionTracker(proximity_m=0.5)
    assert tracker.process(make_grid_detection(x=1.0)) is not None
    assert tracker.process(make_grid_detection(x=1.2)) is None
    assert tracker.process(make_grid_detection(number="999", x=1.2)) is not None


def test_zero_marker_confidence_is_preserved() -> None:
    detection = make_grid_detection()
    detection.marker_confidence = 0.0
    result = DetectionTracker().process(detection)
    assert result is not None
    assert result.confidence == 0.0
