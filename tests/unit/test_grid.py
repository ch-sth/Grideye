import pytest

from grideye_shared.coordinates import GridConfig, world_to_grid

GRID = GridConfig(origin_x_m=0, origin_y_m=0, cell_size_m=0.5, rows=6, columns=30)


def test_world_coordinate_to_grid_cell() -> None:
    assert world_to_grid(0.75, 0.25, GRID).cell == "B1"
    assert world_to_grid(13.1, 1.1, GRID).cell == "AA3"


def test_outside_grid_rejected() -> None:
    with pytest.raises(ValueError):
        world_to_grid(-0.01, 0, GRID)
