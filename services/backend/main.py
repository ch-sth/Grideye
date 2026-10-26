import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import select, text, update

from grideye_shared.config import Settings
from grideye_shared.config.files import MODELS, read_config, write_config
from grideye_shared.config.logging import configure_logging
from grideye_shared.mqtt import TOPICS, service_status_topic
from grideye_shared.schemas import (
    BatteryTelemetry,
    FlightAttitude,
    FlightMode,
    Position3D,
    ServiceState,
    ServiceStatus,
    UwbPosition,
)
from services.backend.database import DetectionRow, MissionRow, SessionLocal, create_schema
from services.backend.mission_api import configure_manager
from services.backend.mission_api import router as mission_router
from services.backend.mqtt_bridge import MqttBridge
from services.backend.state import runtime
from services.camera.live import LiveCamera
from services.mission.geometry import FlightField

settings = Settings()
log = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await create_schema()
    async with SessionLocal() as session:
        await session.execute(
            update(MissionRow)
            .where(MissionRow.status.in_(["running", "paused"]))
            .values(status="interrupted")
        )
        await session.commit()
    controller = configure_manager()
    controller.uwb.anchors = [device is not None for device in read_config("anchors")["devices"]]
    _app.state.mission_manager = controller
    bridge = MqttBridge(asyncio.get_running_loop())
    bridge.start()
    _app.state.bridge = bridge
    runtime.services["backend"] = ServiceStatus(service="backend", status=ServiceState.ONLINE)

    async def heartbeat() -> None:
        while True:
            status = ServiceStatus(service="backend", status=ServiceState.ONLINE)
            runtime.services["backend"] = status
            bridge.client.publish(service_status_topic("backend"), status, retain=True)
            await asyncio.sleep(5)

    async def physics() -> None:
        loop = asyncio.get_running_loop()
        previous = loop.time()
        while True:
            now = loop.time()
            controller.tick(now - previous)
            previous = now
            await asyncio.sleep(0.1)

    async def simulation_telemetry() -> None:
        last_status = None
        while True:
            snapshot = controller.snapshot()
            point = snapshot["position"]
            if controller.uwb.connected:
                bridge.client.publish(
                    TOPICS.uwb_position,
                    UwbPosition(
                        position=Position3D(x_m=point["x"], y_m=point["y"], z_m=point["z"]),
                        quality=controller.uwb.quality,
                    ),
                )
            if controller.flight.connected:
                bridge.client.publish(
                    TOPICS.flight_mode,
                    FlightMode(mode="SIMULATION"),
                    retain=True,
                )
                bridge.client.publish(
                    TOPICS.flight_attitude, FlightAttitude(roll_deg=0, pitch_deg=0, yaw_deg=0)
                )
                bridge.client.publish(
                    TOPICS.flight_battery, BatteryTelemetry(percent=0.95, voltage_v=15.6)
                )
            await runtime.broadcast({"type": "simulation.telemetry", "data": snapshot})
            for service in ["mission", "uwb-simulator", "flight-simulator"]:
                status = ServiceStatus(service=service, status=ServiceState.ONLINE)
                runtime.services[service] = status
            key = (controller.mission_id, controller.mission_status)
            if key != last_status and controller.mission_id:
                try:
                    async with SessionLocal() as session:
                        row = await session.scalar(
                            select(MissionRow)
                            .where(MissionRow.id == UUID(controller.mission_id))
                            .with_for_update()
                        )
                        if row and row.status != "path_deleted":
                            row.status = controller.mission_status
                            await session.commit()
                    last_status = key
                except Exception:
                    log.exception("mission status persistence failed")
                    controller.land()
            await asyncio.sleep(0.2)

    camera = LiveCamera()
    _app.state.camera = camera
    camera.configure(read_config("camera")["stream"]["rtsp_url"])
    camera.start()
    tasks = [asyncio.create_task(job()) for job in [heartbeat, physics, simulation_telemetry]]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        await asyncio.to_thread(camera.close)
        bridge.stop()


app = FastAPI(title="Grideye API", version="0.1.0", lifespan=lifespan)
app.include_router(mission_router)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


def detection_dict(row: DetectionRow) -> dict[str, object]:
    return {
        "id": str(row.id),
        "timestamp": row.timestamp.isoformat(),
        "mission_id": str(row.mission_id) if row.mission_id else None,
        "class_name": row.class_name,
        "number": row.number,
        "confidence": row.confidence,
        "world": {"x_m": row.world_x_m, "y_m": row.world_y_m},
        "grid_cell": row.grid_cell,
        "image_reference": row.image_reference,
    }


@app.get("/api/v1/system/health")
async def health() -> dict[str, object]:
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat(), "version": "0.1.0"}


@app.get("/api/v1/system/services")
async def services() -> list[dict[str, object]]:
    return runtime.service_snapshot(read_config("system")["service_timeout_seconds"])


@app.get("/api/v1/system/connections")
async def connections() -> dict[str, object]:
    bridge = getattr(app.state, "bridge", None)
    database_connected = False
    try:
        async with SessionLocal() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=2)
            database_connected = True
    except Exception:
        pass
    return {
        "mqtt": bool(bridge and bridge.client.client.is_connected()),
        "database": database_connected,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.get("/api/v1/drone/status")
async def drone_status() -> dict[str, object]:
    return {
        "position": await position(),
        "mode": runtime.latest.get("flight.mode"),
        "battery": runtime.latest.get("flight.battery"),
    }


@app.get("/api/v1/drone/position")
async def position() -> dict[str, object]:
    controller = getattr(app.state, "mission_manager", None)
    if controller:
        snapshot = controller.snapshot()
        point = snapshot["position"]
        return {
            "timestamp": snapshot["timestamp"],
            "quality": snapshot["uwb_quality"],
            "position": {"x_m": point["x"], "y_m": point["y"], "z_m": point["z"]},
        }
    return runtime.latest.get("uwb.position", {})


@app.get("/api/v1/drone/telemetry")
async def telemetry() -> dict[str, object]:
    return {key: value for key, value in runtime.latest.items() if key.startswith("flight.")}


@app.get("/api/v1/detections")
async def detections() -> list[dict[str, object]]:
    async with SessionLocal() as session:
        rows = (
            await session.scalars(select(DetectionRow).order_by(DetectionRow.timestamp.desc()))
        ).all()
        return [detection_dict(row) for row in rows]


@app.get("/api/v1/detections/{detection_id}")
async def detection(detection_id: UUID) -> dict[str, object]:
    async with SessionLocal() as session:
        row = await session.get(DetectionRow, detection_id)
        if row is None:
            raise HTTPException(404, "detection not found")
        return detection_dict(row)


@app.get("/api/v1/grid")
async def grid() -> dict[str, object]:
    return read_config("grid")


@app.get("/api/v1/grid/cells")
async def grid_cells() -> list[dict[str, object]]:
    items = await detections()
    grouped: dict[str, int] = {}
    for item in items:
        cell = str(item["grid_cell"])
        grouped[cell] = grouped.get(cell, 0) + 1
    return [{"cell": cell, "detections": count} for cell, count in sorted(grouped.items())]


@app.get("/api/v1/grid/cells/{cell}")
async def grid_cell(cell: str) -> dict[str, object]:
    items = [item for item in await detections() if item["grid_cell"] == cell.upper()]
    return {"cell": cell.upper(), "detections": items}


@app.get("/api/v1/config")
async def config() -> dict[str, object]:
    return {name: read_config(name) for name in MODELS}


@app.put("/api/v1/config/{name}")
async def update_config(name: str, body: dict) -> dict[str, object]:
    if name not in MODELS:
        raise HTTPException(404, "Unbekannte Konfiguration")
    controller = getattr(app.state, "mission_manager", None)
    if controller and name in {"grid", "safety", "anchors"}:
        if controller.active or controller.flight.altitude > 0:
            raise HTTPException(409, "Konfiguration erst nach Landung ändern")
    try:
        saved = write_config(name, body)
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(503, "Konfiguration konnte nicht gespeichert werden") from exc
    if controller:
        if name in {"grid", "safety"}:
            controller.field = FlightField(
                read_config("grid"), read_config("safety")["flight_margin_m"]
            )
            controller.safety.settings = read_config("safety")
        if name == "anchors":
            controller.uwb.anchors = [device is not None for device in saved["devices"]]
    if name == "camera" and hasattr(app.state, "camera"):
        app.state.camera.configure(saved["stream"]["rtsp_url"])
    return {"config": saved, "restart_required": name in {"uwb", "tracking", "system"}}


@app.get("/api/v1/camera/status")
async def camera_status() -> dict:
    camera = getattr(app.state, "camera", None)
    if camera is None:
        raise HTTPException(503, "Kameradienst nicht gestartet")
    return camera.status()


@app.get("/api/v1/camera/frame.jpg")
async def camera_frame() -> Response:
    camera = getattr(app.state, "camera", None)
    frame = camera.frame() if camera else None
    if frame is None:
        raise HTTPException(503, "Kein aktuelles Kamerabild")
    return Response(frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.websocket("/ws/live")
async def websocket_live(socket: WebSocket) -> None:
    await socket.accept()
    runtime.websockets.add(socket)
    try:
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        runtime.websockets.discard(socket)


@app.get("/", include_in_schema=False)
async def dashboard_root(ansicht: str | None = None) -> Response:
    if ansicht != "neu":
        return RedirectResponse(
            "/?ansicht=neu",
            status_code=307,
            headers={"Cache-Control": "no-store, max-age=0"},
        )
    return await dashboard()


@app.get("/services/{service}", include_in_schema=False)
async def dashboard() -> FileResponse:
    return FileResponse(
        Path(__file__).parent / "static/index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


configure_logging("backend")
