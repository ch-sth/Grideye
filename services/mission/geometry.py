from math import floor, hypot

from grideye_shared.coordinates.grid import GridConfig, world_to_grid
from services.mission.models import MissionPlan, Point


class FlightField:
    def __init__(self, config: dict, margin: float = 0.25) -> None:
        self.x = config["origin"]["x_m"]
        self.y = config["origin"]["y_m"]
        self.cell_size = config["cell_size_m"]
        self.rows, self.columns = config["rows"], config["columns"]
        self.width = self.columns * self.cell_size
        self.height = self.rows * self.cell_size
        self.margin = margin

    def zone(self, point: Point) -> str:
        if self.x <= point.x <= self.x + self.width and self.y <= point.y <= self.y + self.height:
            return "GRID"
        if (
            self.x - self.margin <= point.x <= self.x + self.width + self.margin
            and self.y - self.margin <= point.y <= self.y + self.height + self.margin
        ):
            return "FLIGHT_ZONE"
        return "FAILSAFE_ZONE"

    def cell(self, point: Point) -> str | None:
        if self.zone(point) != "GRID":
            return None
        # The outer grid edge belongs to the final cell, never to the flight-zone margin.
        x = min(point.x, self.x + self.width - 1e-9)
        y = min(point.y, self.y + self.height - 1e-9)
        return world_to_grid(
            x, y, GridConfig(self.x, self.y, self.cell_size, self.rows, self.columns)
        ).cell

    def snap(self, point: Point, mode: str) -> Point:
        if self.zone(point) != "GRID":
            raise ValueError("Wegpunkte müssen im Arbeitsraster liegen.")
        if mode == "free":
            return point
        col = min(floor((point.x - self.x) / self.cell_size), self.columns - 1)
        row = min(floor((point.y - self.y) / self.cell_size), self.rows - 1)
        center = Point(
            x=self.x + (col + 0.5) * self.cell_size, y=self.y + (row + 0.5) * self.cell_size
        )
        intersection = Point(
            x=self.x + floor((point.x - self.x) / self.cell_size + 0.5) * self.cell_size,
            y=self.y + floor((point.y - self.y) / self.cell_size + 0.5) * self.cell_size,
        )
        if mode == "center":
            return center
        if mode == "intersection":
            return intersection
        if mode == "auto":
            return min([center, intersection], key=lambda p: hypot(p.x - point.x, p.y - point.y))
        raise ValueError("Unbekannter Snap-Modus")

    def validate(self, plan: MissionPlan) -> None:
        if self.zone(plan.start) == "FAILSAFE_ZONE" or self.zone(plan.end) == "FAILSAFE_ZONE":
            raise ValueError("Start und Ende müssen innerhalb der erlaubten Flugzone liegen.")
        if any(self.zone(point) != "GRID" for point in plan.waypoints):
            raise ValueError("Alle Wegpunkte müssen im Arbeitsraster liegen.")
