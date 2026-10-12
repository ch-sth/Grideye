from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


UtcTimestamp = Annotated[datetime, Field(default_factory=utc_now)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class Contract(BaseModel):
    schema_version: Literal["1.0"] = "1.0"

    @field_validator("schema_version")
    @classmethod
    def supported_version(cls, value: str) -> str:
        if value != "1.0":
            raise ValueError("unsupported schema version")
        return value


class Position3D(BaseModel):
    x_m: float
    y_m: float
    z_m: float


class WorldPosition(BaseModel):
    x_m: float
    y_m: float


class UwbPosition(Contract):
    timestamp: datetime = Field(default_factory=utc_now)
    position: Position3D
    quality: Confidence


class FlightAttitude(Contract):
    timestamp: datetime = Field(default_factory=utc_now)
    roll_deg: float
    pitch_deg: float
    yaw_deg: float


class FlightCommandType(StrEnum):
    GOTO = "goto"
    HOLD = "hold"
    LAND = "land"


class FlightCommand(Contract):
    command_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=utc_now)
    type: FlightCommandType
    target: Position3D | None = None


class CommandStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class FlightCommandResult(Contract):
    command_id: UUID
    timestamp: datetime = Field(default_factory=utc_now)
    status: CommandStatus
    message: str | None = None


class BoundingBox(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class FrameSize(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class AiDetection(Contract):
    detection_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=utc_now)
    class_name: str = Field(min_length=1)
    class_confidence: Confidence
    number: str | None = None
    ocr_confidence: Confidence | None = None
    bbox_px: BoundingBox
    frame: FrameSize


class GridLocation(BaseModel):
    cell: str = Field(pattern=r"^[A-Z]+[1-9][0-9]*$")
    column: int = Field(ge=0)
    row: int = Field(ge=0)


class GridDetection(AiDetection):
    world: WorldPosition
    grid: GridLocation


class ConfirmedDetection(Contract):
    detection_id: UUID
    timestamp: datetime = Field(default_factory=utc_now)
    class_name: str
    number: str | None = None
    world: WorldPosition
    grid: GridLocation
    confidence: Confidence
    mission_id: UUID | None = None
    image_reference: str | None = None


class ServiceState(StrEnum):
    STARTING = "starting"
    ONLINE = "online"
    DEGRADED = "degraded"
    ERROR = "error"
    OFFLINE = "offline"


class ServiceStatus(Contract):
    service: str
    status: ServiceState
    timestamp: datetime = Field(default_factory=utc_now)
    version: str = "0.1.0"


class BatteryTelemetry(Contract):
    timestamp: datetime = Field(default_factory=utc_now)
    percent: Confidence
    voltage_v: float = Field(gt=0)


class FlightMode(Contract):
    timestamp: datetime = Field(default_factory=utc_now)
    mode: str


class LiveEnvelope(BaseModel):
    type: str
    timestamp: datetime = Field(default_factory=utc_now)
    data: dict[str, object]
