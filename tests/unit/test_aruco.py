import cv2
import numpy as np
import pytest

from services.ai.detectors import ArucoDetector


def encode(image: np.ndarray) -> bytes:
    success, data = cv2.imencode(".png", image)
    assert success
    return data.tobytes()


@pytest.mark.parametrize("rotation", [0, 1, 2, 3])
async def test_detects_multiple_tags_including_zero(rotation: int) -> None:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_1000)
    image = np.full((300, 500), 255, dtype=np.uint8)
    for marker_id, x in [(0, 30), (999, 270)]:
        marker = cv2.aruco.generateImageMarker(dictionary, marker_id, 180)
        image[60:240, x : x + 180] = np.rot90(marker, rotation)
    detections = await ArucoDetector().detect(encode(image))
    assert {d.number for d in detections} == {"0", "999"}
    for detection in detections:
        assert detection.class_name == "aruco"
        assert detection.marker_confidence == 1.0
        assert detection.frame.width == 500
        assert detection.frame.height == 300
        assert detection.bbox_px.y == 60
        assert detection.bbox_px.width == 180
        assert detection.bbox_px.height == 180


async def test_empty_and_blank_images() -> None:
    detector = ArucoDetector()
    assert await detector.detect(b"") == []
    assert await detector.detect(encode(np.full((200, 200), 255, dtype=np.uint8))) == []
    with pytest.raises(ValueError, match="valid encoded image"):
        await detector.detect(b"invalid image")


def test_unknown_dictionary() -> None:
    with pytest.raises(ValueError, match="dictionary"):
        ArucoDetector("unknown")
