"""Insert recognizable dashboard test detections without replacing existing records.

Run from the project root:
docker compose --env-file .env -f compose.yaml exec -T backend python < scripts/seed_test_data.py
Repeated runs skip test records that already exist.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from grideye_shared.config.files import read_config
from grideye_shared.coordinates.grid import GridConfig, world_to_grid
from services.backend.database import DetectionRow, SessionLocal, engine


async def main() -> None:
    config = read_config("grid")
    grid = GridConfig(
        origin_x_m=config["origin"]["x_m"], origin_y_m=config["origin"]["y_m"],
        cell_size_m=config["cell_size_m"], rows=config["rows"], columns=config["columns"],
    )
    positions = [(0, 0), (1, 0), (2, 1), (2, 1), (3, 2), (4, 3),
                 (5, 4), (6, 5), (7, 5), (0, 4), (4, 0), (7, 2)]
    classes = ["TEST-Paket", "TEST-Behälter", "TEST-Etikett"]
    now = datetime.now(UTC)
    added = 0
    async with SessionLocal() as session:
        for index, (column, row) in enumerate(positions, start=1):
            detection_id = uuid5(NAMESPACE_URL, f"grideye/dashboard-test/v1/{index}")
            if await session.get(DetectionRow, detection_id) is not None:
                continue
            x = grid.origin_x_m + (column % grid.columns + 0.5) * grid.cell_size_m
            y = grid.origin_y_m + (row % grid.rows + 0.5) * grid.cell_size_m
            cell = world_to_grid(x, y, grid).cell
            session.add(DetectionRow(
                id=detection_id, timestamp=now - timedelta(minutes=len(positions) - index),
                class_name=classes[(index - 1) % len(classes)], number=f"TEST-{index:03d}",
                confidence=round(0.80 + (index % 5) * 0.04, 2),
                world_x_m=x, world_y_m=y, grid_cell=cell,
                mission_id=None, image_reference=None,
            ))
            added += 1
            print(f"TEST-{index:03d}: {cell} ({x:.2f} / {y:.2f} m)")
        await session.commit()
    await engine.dispose()
    print(f"{added} Testeinträge gespeichert; {len(positions) - added} bereits vorhanden.")


if __name__ == "__main__":
    asyncio.run(main())
