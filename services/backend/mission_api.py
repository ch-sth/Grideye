from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from grideye_shared.config.files import read_config
from services.backend.database import MissionPlanRow, MissionRow, SessionLocal
from services.mission.manager import MissionManager
from services.mission.models import MissionPlan, SimulationInput, SnapRequest

router = APIRouter(prefix="/api/v1")


def manager(request: Request) -> MissionManager:
    value = getattr(request.app.state, "mission_manager", None)
    if value is None:
        raise HTTPException(503, "Simulation wird initialisiert")
    return value


def serialize(row: MissionRow, plan: MissionPlanRow | None = None) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
        "plan": plan.plan if plan else None,
    }


@router.get("/simulation")
async def simulation(request: Request) -> dict:
    return manager(request).snapshot()


@router.post("/simulation/input")
async def simulation_input(body: SimulationInput, request: Request) -> dict:
    value = manager(request)
    value.inject(body)
    return value.snapshot()


@router.post("/simulation/reset")
async def simulation_reset(request: Request) -> dict:
    value = manager(request)
    try:
        value.reset()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return value.snapshot()


@router.post("/simulation/land")
async def simulation_land(request: Request) -> dict:
    value = manager(request)
    value.land()
    return value.snapshot()


@router.post("/missions/snap")
async def snap(body: SnapRequest, request: Request) -> dict:
    try:
        return manager(request).field.snap(body.point, body.mode).model_dump()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/missions")
async def missions() -> list[dict]:
    async with SessionLocal() as session:
        rows = await session.execute(
            select(MissionRow, MissionPlanRow)
            .outerjoin(MissionPlanRow, MissionPlanRow.mission_id == MissionRow.id)
            .order_by(MissionRow.created_at.desc())
        )
        return [serialize(row, plan) for row, plan in rows]


@router.get("/missions/{mission_id}")
async def get_mission(mission_id: UUID) -> dict:
    async with SessionLocal() as session:
        row = await session.get(MissionRow, mission_id)
        if not row:
            raise HTTPException(404, "Mission nicht gefunden")
        return serialize(row, await session.get(MissionPlanRow, mission_id))


@router.post("/missions", status_code=201)
async def create_mission(body: MissionPlan, request: Request) -> dict:
    value = manager(request)
    try:
        value.field.validate(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    async with SessionLocal() as session:
        row = MissionRow(name=body.name, created_at=datetime.now(UTC))
        session.add(row)
        await session.flush()
        plan = MissionPlanRow(mission_id=row.id, plan=body.model_dump())
        session.add(plan)
        await session.commit()
        return serialize(row, plan)


@router.put("/missions/{mission_id}")
async def update_mission(mission_id: UUID, body: MissionPlan, request: Request) -> dict:
    value = manager(request)
    try:
        value.field.validate(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    async with SessionLocal() as session:
        # Lock before checking runtime state: concurrent requests cannot start a stale plan.
        row = await session.scalar(
            select(MissionRow).where(MissionRow.id == mission_id).with_for_update()
        )
        if not row:
            raise HTTPException(404, "Mission nicht gefunden")
        if value.mission_id == str(mission_id) and (value.active or value.flight.altitude > 0):
            raise HTTPException(409, "Aktive Mission kann nicht bearbeitet werden")
        plan = await session.get(MissionPlanRow, mission_id)
        if plan:
            plan.plan = body.model_dump()
        else:
            plan = MissionPlanRow(mission_id=mission_id, plan=body.model_dump())
            session.add(plan)
        row.name, row.status = body.name, "draft"
        await session.commit()
        return serialize(row, plan)


@router.delete("/missions/{mission_id}", status_code=204)
async def delete_mission(mission_id: UUID, request: Request) -> None:
    value = manager(request)
    async with SessionLocal() as session:
        row = await session.scalar(
            select(MissionRow).where(MissionRow.id == mission_id).with_for_update()
        )
        if not row:
            raise HTTPException(404, "Mission nicht gefunden")
        if value.mission_id == str(mission_id) and (value.active or value.flight.altitude > 0):
            raise HTTPException(409, "Aktive Mission kann nicht gelöscht werden")
        plan = await session.get(MissionPlanRow, mission_id)
        # Keep mission metadata: detections may still reference this mission.
        if plan:
            await session.delete(plan)
        row.status = "path_deleted"
        await session.commit()
        if value.mission_id == str(mission_id):
            value.plan, value.mission_id = None, None


@router.post("/missions/{mission_id}/{action}")
async def mission_action(mission_id: UUID, action: str, request: Request) -> dict:
    if action not in {"start", "pause", "resume", "abort"}:
        raise HTTPException(404, "Unbekannte Missionsaktion")
    value = manager(request)
    async with SessionLocal() as session:
        row = await session.scalar(
            select(MissionRow).where(MissionRow.id == mission_id).with_for_update()
        )
        if not row:
            raise HTTPException(404, "Mission nicht gefunden")
        plan = await session.get(MissionPlanRow, mission_id)
        try:
            if action == "start":
                if not plan:
                    raise ValueError("Mission hat keinen gespeicherten Pfad.")
                value.start(str(mission_id), MissionPlan.model_validate(plan.plan))
            else:
                if value.mission_id != str(mission_id):
                    raise ValueError("Diese Mission ist nicht aktiv.")
                if action == "pause":
                    value.pause()
                elif action == "resume":
                    value.resume()
                else:
                    value.land()
            row.status = value.mission_status
            await session.commit()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception:
            value.land()
            raise
        return serialize(row, plan)


@router.get("/uwb/devices")
async def uwb_devices() -> dict:
    # Real serial nodes are inventory only, never proof of a functioning UWB protocol.
    serial = []
    for directory in [Path("/dev/serial/by-id"), Path("/dev")]:
        if directory.exists():
            for path in sorted(directory.iterdir()):
                if directory.name == "by-id" or path.name.startswith(("ttyACM", "ttyUSB")):
                    serial.append({"id": path.name, "path": str(path), "status": "UNVERIFIED"})
    return {
        "mode": "SIMULATION",
        "devices": [
            {"id": f"SIM-UWB-{i:03d}", "label": f"Simulierter UWB-Anker {i}"} for i in range(1, 5)
        ],
        "serial_inventory": serial,
        "note": (
            "USB-Inventar nur aus dem Backend-Gerätenamensraum; im Container ist "
            "der Host nicht automatisch sichtbar. UWB-Protokolladapter fehlen noch."
        ),
    }


def configure_manager() -> MissionManager:
    return MissionManager(read_config("grid"), read_config("safety"))
