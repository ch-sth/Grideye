from unittest.mock import Mock

import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from grideye_shared.config.files import Stream
from services.camera.live import LiveCamera


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("192.168.1.50", "rtsp://192.168.1.50"),
        ("192.168.1.50:554/live", "rtsp://192.168.1.50:554/live"),
        (" http://cam.local/video ", "http://cam.local/video"),
        ("rtsp://user:pass@cam.local/stream1", "rtsp://user:pass@cam.local/stream1"),
        ("", None),
        (None, None),
    ],
)
def test_camera_address_normalization(value, expected):
    assert Stream(rtsp_url=value).rtsp_url == expected


@pytest.mark.parametrize("value", ["file:///etc/passwd", "rtsp://", "rtsp://cam:99999", "bad host"])
def test_rejects_invalid_camera_address(value):
    with pytest.raises(ValidationError):
        Stream(rtsp_url=value)


def test_switch_clears_frame_and_rejects_previous_camera():
    camera = LiveCamera()
    camera.configure("rtsp://first/live")
    revision = camera.status()["revision"]
    camera._publish(revision, "online", "Livebild", b"first")
    assert camera.frame() == b"first"
    camera.configure("rtsp://second/live")
    assert camera.frame() is None
    camera._publish(revision, "online", "old frame", b"late")
    assert camera.frame() is None
    assert camera.status()["status"] == "starting"
    camera.configure(None)
    assert camera.status()["configured"] is False
    assert camera.status()["status"] == "offline"


def test_worker_decodes_jpeg_and_releases_capture(monkeypatch):
    camera = LiveCamera()
    camera.configure("rtsp://test/live")
    capture = Mock()
    capture.isOpened.return_value = True
    capture.read.return_value = (True, np.zeros((100, 200, 3), dtype=np.uint8))
    factory = Mock(return_value=capture)
    monkeypatch.setattr(cv2, "VideoCapture", factory)
    publish = camera._publish

    def receive(*args):
        publish(*args)
        camera._stop.set()

    monkeypatch.setattr(camera, "_publish", receive)
    # No delay after the synthetic stream ends.
    monkeypatch.setattr(camera._wake, "wait", lambda timeout: None)
    camera._run()
    assert camera.status()["has_frame"] is True
    decoded = cv2.imdecode(np.frombuffer(camera.frame(), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == (100, 200, 3)
    assert factory.call_args.args[0] == "rtsp://test/live"
    assert cv2.CAP_PROP_READ_TIMEOUT_MSEC in factory.call_args.args[2]
    capture.release.assert_called_once()


def test_worker_connection_failure_is_retryable_and_redacted(monkeypatch):
    camera = LiveCamera()
    camera.configure("rtsp://user:secret@bad/live")
    capture = Mock()
    capture.isOpened.return_value = False
    monkeypatch.setattr(cv2, "VideoCapture", Mock(return_value=capture))
    monkeypatch.setattr(camera._wake, "wait", lambda timeout: camera._stop.set())
    camera._run()
    assert camera.status()["status"] == "error"
    assert "secret" not in str(camera.status())
    assert camera.frame() is None
    capture.release.assert_called_once()


def test_live_capture_from_http_mjpeg(monkeypatch):
    """Exercise the actual FFmpeg network decoder against a local camera stand-in."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Event, Thread

    stop = Event()
    received = Event()
    ok, encoded = cv2.imencode(".jpg", np.zeros((120, 160, 3), dtype=np.uint8))
    assert ok
    jpeg = encoded.tobytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while not stop.is_set():
                    self.wfile.write(
                        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + str(len(jpeg)).encode()
                        + b"\r\n\r\n"
                        + jpeg
                        + b"\r\n"
                    )
                    self.wfile.flush()
                    stop.wait(0.02)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    camera = LiveCamera()
    original = camera._publish

    def publish(*args):
        original(*args)
        if args[1] == "online":
            received.set()

    monkeypatch.setattr(camera, "_publish", publish)
    try:
        camera.configure(f"http://127.0.0.1:{server.server_port}/video")
        camera.start()
        assert received.wait(10), camera.status()
        assert camera.status()["status"] == "online"
        assert camera.frame().startswith(b"\xff\xd8")
        camera.configure(None)
        assert camera.frame() is None
    finally:
        stop.set()
        camera.close()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)
