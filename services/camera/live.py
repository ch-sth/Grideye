"""One shared IP-camera connection, with bounded reads and automatic reconnection."""

from threading import Event, Lock, Thread
from time import monotonic

import cv2


class LiveCamera:
    def __init__(self) -> None:
        self._lock = Lock()
        self._wake = Event()
        self._stop = Event()
        self._thread: Thread | None = None
        self._url: str | None = None
        self._revision = 0
        self._jpeg: bytes | None = None
        self._received = 0.0
        self._state = "offline"
        self._message = "Keine Kamera konfiguriert."

    def start(self) -> None:
        self._thread = Thread(target=self._run, name="ip-camera", daemon=True)
        self._thread.start()

    def configure(self, url: str | None) -> None:
        with self._lock:
            if url == self._url:
                return
            self._url = url
            self._revision += 1
            self._jpeg = None
            self._received = 0
            self._state = "starting" if url else "offline"
            self._message = "Verbindung wird aufgebaut." if url else "Keine Kamera konfiguriert."
        self._wake.set()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=8)

    def status(self) -> dict:
        with self._lock:
            fresh = self._jpeg is not None and monotonic() - self._received < 5
            return {
                "status": self._state if self._state != "online" or fresh else "degraded",
                "message": self._message if self._state != "online" or fresh else "Bild veraltet.",
                "configured": bool(self._url),
                "revision": self._revision,
                "has_frame": fresh,
            }

    def frame(self) -> bytes | None:
        with self._lock:
            return self._jpeg if monotonic() - self._received < 5 else None

    def _publish(self, revision: int, state: str, message: str, jpeg: bytes | None = None):
        with self._lock:
            if revision != self._revision:
                return
            self._state, self._message, self._jpeg = state, message, jpeg
            self._received = monotonic() if jpeg else 0

    def _current(self, revision: int) -> bool:
        with self._lock:
            return not self._stop.is_set() and revision == self._revision

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.clear()
            with self._lock:
                url, revision = self._url, self._revision
            if not url:
                self._wake.wait(1)
                continue
            capture = None
            try:
                capture = cv2.VideoCapture(
                    url,
                    cv2.CAP_FFMPEG,
                    [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000],
                )
                if not capture.isOpened():
                    raise ValueError("connection failed")
                while self._current(revision):
                    ok, image = capture.read()
                    if not ok:
                        raise ValueError("no frame")
                    # Drain the source continuously; encode at most ten preview frames per second.
                    now = monotonic()
                    with self._lock:
                        previous = self._received
                    if now - previous < 0.1:
                        continue
                    height, width = image.shape[:2]
                    if width > 1280:
                        image = cv2.resize(image, (1280, round(height * 1280 / width)))
                    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if not ok:
                        raise ValueError("encoding failed")
                    self._publish(revision, "online", "Livebild verbunden.", encoded.tobytes())
            except Exception:
                # Never expose the URL or camera credentials in API error messages.
                self._publish(
                    revision,
                    "error",
                    "Kein Livebild. Adresse, Stream-Pfad und Zugangsdaten prüfen.",
                )
            finally:
                if capture is not None:
                    capture.release()
            self._wake.wait(2)
