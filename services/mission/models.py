"""Mission and simulation contracts, independent of browser and hardware."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Point(Model):
    x: float = Field(ge=-1000, le=1000)
    y: float = Field(ge=-1000, le=1000)


class MissionPlan(Model):
    name: str = Field(min_length=1, max_length=200)
    start: Point
    waypoints: list[Point] = Field(min_length=1, max_length=500)
    end: Point
    hover_time: float = Field(default=3, ge=0, le=300)
    altitude: float = Field(default=1, gt=0, le=10)
    speed: float = Field(default=0.3, gt=0, le=3)
    snap: Literal["free", "center", "intersection", "auto"] = "center"


class GamepadInput(Model):
    connected: bool = True
    x: float = Field(default=0, ge=-1, le=1)
    y: float = Field(default=0, ge=-1, le=1)
    z: float = Field(default=0, ge=-1, le=1)
    l1: bool = False
    r1: bool = False
    l2: bool = False
    r2: bool = False
    circle: bool = False


class SimulationInput(Model):
    radio: bool | None = None
    gamepad: GamepadInput | None = None
    position: Point | None = None
    quality: float | None = Field(default=None, ge=0, le=1)
    uwb_connected: bool | None = None
    flight_connected: bool | None = None
    anchor_connected: list[bool] | None = Field(default=None, min_length=4, max_length=4)


class SnapRequest(Model):
    point: Point
    mode: Literal["free", "center", "intersection", "auto"]
