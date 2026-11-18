"""Copy, validate, persist and atomically switch the active object detector."""

import hashlib
import json
import os
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import BinaryIO
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from services.ai.detectors import ArucoDetector, ObjectDetector
from services.ai.yolo import YoloDetector

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
MAX_MODEL_BYTES = 512 * 1024 * 1024


class ModelImportError(ValueError):
    pass


class ModelEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    name: str
    size_bytes: int = Field(gt=0, le=MAX_MODEL_BYTES)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    imported_at: str
    classes: dict[str, str]


class Registry(BaseModel):
    models: list[ModelEntry] = Field(default_factory=list)
    active_id: str = "aruco"


class ModelStore:
    def __init__(self, directory: Path = MODEL_DIR) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._changes = Lock()
        self._state = Lock()
        self._registry = Registry()
        self._active_id = "aruco"
        self._detector: ObjectDetector = ArucoDetector()
        self._error: str | None = None
        manifest = self.directory / "registry.json"
        if manifest.exists():
            try:
                self._registry = Registry.model_validate_json(manifest.read_text())
                if self._registry.active_id != "aruco":
                    entry = self._entry(self._registry.active_id)
                    self._detector = self._load(entry)
                    self._active_id = entry.id
            except Exception:
                self._error = "Gespeichertes Modell konnte nicht geladen werden. ArUco ist aktiv."

    def snapshot(self) -> dict:
        with self._state:
            return {
                **self._registry.model_dump(),
                "active_id": self._active_id,
                "saved_active_id": self._registry.active_id,
                "error": self._error,
                "max_size_bytes": MAX_MODEL_BYTES,
            }

    def selection(self) -> tuple[str, ObjectDetector]:
        with self._state:
            return self._active_id, self._detector

    def _entry(self, model_id: str) -> ModelEntry:
        for entry in self._registry.models:
            if entry.id == model_id:
                return entry
        raise ModelImportError("Modell nicht gefunden.")

    def _load(self, entry: ModelEntry) -> YoloDetector:
        path = self.directory / f"{entry.id}.pt"
        if not path.is_file() or self._hash(path) != entry.sha256:
            raise ModelImportError("Die gespeicherte Modelldatei fehlt oder wurde verändert.")
        return YoloDetector(path)

    @staticmethod
    def _hash(path: Path) -> str:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def _commit(self, registry: Registry, detector: ObjectDetector) -> None:
        # Only switch in-memory selection after the persistent selection is safely saved.
        fd, temporary = tempfile.mkstemp(dir=self.directory, suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(registry.model_dump(), stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.directory / "registry.json")
        finally:
            Path(temporary).unlink(missing_ok=True)
        with self._state:
            self._registry, self._detector = registry, detector
            self._active_id, self._error = registry.active_id, None

    def import_path(self, source: str) -> dict:
        path = Path(source.strip()).expanduser()
        if path.suffix.lower() != ".pt":
            raise ModelImportError("Bitte eine YOLO-Modelldatei mit der Endung .pt auswählen.")
        # O_NONBLOCK also prevents a FIFO masquerading as a checkpoint from blocking a request.
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise ModelImportError("Der Pfad muss auf eine reguläre Datei zeigen.")
                if info.st_size > MAX_MODEL_BYTES:
                    raise ModelImportError("Modelldatei ist größer als 512 MiB.")
                return self.import_stream(stream, path.name)
        except OSError as exc:
            raise ModelImportError(
                "Modelldatei nicht lesbar. Der Pfad muss auf dem Server "
                "bzw. im Container existieren."
            ) from exc

    def import_stream(self, source: BinaryIO, filename: str) -> dict:
        if Path(filename).suffix.lower() != ".pt":
            raise ModelImportError("Unterstützt werden YOLO-Modelldateien im .pt-Format.")
        with self._changes:
            model_id = uuid4().hex
            target = self.directory / f"{model_id}.pt"
            try:
                size = 0
                with target.open("xb") as destination:
                    while chunk := source.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_MODEL_BYTES:
                            raise ModelImportError("Modelldatei ist größer als 512 MiB.")
                        destination.write(chunk)
                    destination.flush()
                    os.fsync(destination.fileno())
                if not size:
                    raise ModelImportError("Die Modelldatei ist leer.")
                try:
                    detector = YoloDetector(target)
                except Exception as exc:
                    raise ModelImportError(
                        "Modellprüfung fehlgeschlagen. Benötigt wird ein mit Ultralytics "
                        "kompatibles YOLO-.pt-Modell für Objekterkennung (detect)."
                    ) from exc
                entry = ModelEntry(
                    id=model_id,
                    name=Path(filename.replace("\\", "/")).name[:200],
                    size_bytes=size,
                    sha256=self._hash(target),
                    imported_at=datetime.now(UTC).isoformat(),
                    classes=detector.names,
                )
                self._commit(
                    Registry(models=[*self._registry.models, entry], active_id=model_id), detector
                )
            except BaseException:
                target.unlink(missing_ok=True)
                raise
        return self.snapshot()

    def activate(self, model_id: str) -> dict:
        with self._changes:
            try:
                detector: ObjectDetector = (
                    ArucoDetector() if model_id == "aruco" else self._load(self._entry(model_id))
                )
            except ModelImportError:
                raise
            except Exception as exc:
                raise ModelImportError("Modell konnte nicht aktiviert werden.") from exc
            self._commit(Registry(models=self._registry.models, active_id=model_id), detector)
        return self.snapshot()
