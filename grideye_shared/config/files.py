"""Validated configuration files shared by the API and service processes."""

import os
import stat
import tempfile
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Origin(ConfigModel):
    x_m: float
    y_m: float


class GridSettings(ConfigModel):
    origin: Origin
    cell_size_m: float = Field(gt=0, le=100)
    rows: int = Field(gt=0, le=100)
    columns: int = Field(gt=0, le=100)
    axis_convention: str


class MissionSettings(ConfigModel):
    nominal_flight_height_m: float = Field(gt=0, le=100)
    speed_m_s: float = Field(gt=0, le=20)
    overlap: float = Field(ge=0, lt=1)
    scan_strategy: Literal["boustrophedon"]


class SystemSettings(ConfigModel):
    service_timeout_seconds: float = Field(ge=5, le=300)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Frame(ConfigModel):
    width: int = Field(gt=0, le=16384)
    height: int = Field(gt=0, le=16384)


class Intrinsics(ConfigModel):
    fx_px: float = Field(gt=0)
    fy_px: float = Field(gt=0)
    cx_px: float
    cy_px: float


class Distortion(ConfigModel):
    model: str = Field(min_length=1, max_length=100)
    coefficients: list[float] = Field(max_length=14)


class Mount(ConfigModel):
    x_m: float
    y_m: float
    z_m: float
    roll_deg: float
    pitch_deg: float
    yaw_deg: float


class Stream(ConfigModel):
    rtsp_url: str | None = Field(default=None, max_length=2000)
    gstreamer_pipeline: str | None = Field(default=None, max_length=4000)


class CameraSettings(ConfigModel):
    frame: Frame
    intrinsics: Intrinsics
    distortion: Distortion
    mount: Mount
    stream: Stream


class UwbSettings(ConfigModel):
    width_m: float = Field(default=4, gt=0, le=1000)
    height_m: float = Field(default=3, gt=0, le=1000)
    altitude_m: float = Field(default=1.2, gt=0, le=100)


class TrackingSettings(ConfigModel):
    proximity_m: float = Field(default=0.5, gt=0, le=100)


class SafetySettings(ConfigModel):
    flight_margin_m: float = Field(default=0.25, ge=0.05, le=2)
    minimum_anchors: int = Field(default=3, ge=3, le=4)
    minimum_quality: float = Field(default=0.5, ge=0, le=1)
    consecutive_bad_samples: int = Field(default=3, ge=1, le=100)
    position_timeout_seconds: float = Field(default=2, ge=0.2, le=30)
    gamepad_timeout_seconds: float = Field(default=1, ge=0.2, le=10)
    gamepad_deadzone: float = Field(default=0.18, ge=0.05, le=0.5)
    landing_speed_m_s: float = Field(default=0.3, gt=0, le=1)


class AnchorSettings(ConfigModel):
    mode: Literal["single", "master_slave"] = "single"
    devices: list[str | None] = Field(
        default_factory=lambda: list[str | None](f"SIM-UWB-{i:03d}" for i in range(1, 5)),
        min_length=4,
        max_length=4,
    )

    @model_validator(mode="after")
    def unique_devices(self) -> "AnchorSettings":
        selected = [device for device in self.devices if device]
        if len(selected) != len(set(selected)):
            raise ValueError("Ein UWB-Gerät darf nur einem Anker zugeordnet werden.")
        if any(not device.startswith("SIM-UWB-") for device in selected):
            raise ValueError("Im Simulationsmodus sind nur simulierte UWB-Geräte verfügbar.")
        if any(device not in {f"SIM-UWB-{i:03d}" for i in range(1, 5)} for device in selected):
            raise ValueError("Unbekanntes simuliertes UWB-Gerät.")
        return self


MODELS: dict[str, type[BaseModel]] = {
    "grid": GridSettings,
    "mission": MissionSettings,
    "system": SystemSettings,
    "camera": CameraSettings,
    "uwb": UwbSettings,
    "tracking": TrackingSettings,
    "safety": SafetySettings,
    "anchors": AnchorSettings,
}


def read_config(name: str) -> dict:
    model = MODELS[name]
    path = CONFIG_DIR / f"{name}.yaml"
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    return model.model_validate(data).model_dump()


def write_config(name: str, data: dict) -> dict:
    validated = MODELS[name].model_validate(data).model_dump()
    path = CONFIG_DIR / f"{name}.yaml"
    fd, temporary = tempfile.mkstemp(prefix=f".{name}-", suffix=".tmp", dir=CONFIG_DIR)
    try:
        with os.fdopen(fd, "w") as stream:
            if path.exists():
                existing = path.stat()
                os.fchmod(stream.fileno(), stat.S_IMODE(existing.st_mode))
                if os.geteuid() == 0:
                    os.fchown(stream.fileno(), existing.st_uid, existing.st_gid)
            else:
                os.fchmod(stream.fileno(), 0o644)
            yaml.safe_dump(validated, stream, sort_keys=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return validated
