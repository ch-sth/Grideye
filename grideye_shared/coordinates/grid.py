from dataclasses import dataclass
from math import floor

from grideye_shared.schemas import GridLocation


@dataclass(frozen=True)
class GridConfig:
    origin_x_m: float
    origin_y_m: float
    cell_size_m: float
    rows: int
    columns: int

    def __post_init__(self) -> None:
        if self.cell_size_m <= 0 or self.rows <= 0 or self.columns <= 0:
            raise ValueError("cell size and dimensions must be positive")


def _column_label(index: int) -> str:
    label = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        label = chr(65 + remainder) + label
    return label


def world_to_grid(x_m: float, y_m: float, config: GridConfig) -> GridLocation:
    column = floor((x_m - config.origin_x_m) / config.cell_size_m)
    row = floor((y_m - config.origin_y_m) / config.cell_size_m)
    if not 0 <= column < config.columns or not 0 <= row < config.rows:
        raise ValueError("coordinate outside configured grid")
    return GridLocation(cell=f"{_column_label(column)}{row + 1}", column=column, row=row)
