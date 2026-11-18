"""Model management endpoints; heavy model loading runs outside the API event loop."""

import tempfile

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from services.ai.model_store import MAX_MODEL_BYTES, ModelImportError, ModelStore

router = APIRouter(prefix="/api/v1/ai")


class ImportPath(BaseModel):
    path: str = Field(min_length=1, max_length=4000)


class Activation(BaseModel):
    model_id: str = Field(min_length=1, max_length=40)


def store(request: Request) -> ModelStore:
    instance = getattr(request.app.state, "model_store", None)
    if instance is None:
        raise HTTPException(503, "KI-Modellverwaltung nicht gestartet")
    return instance


def import_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ModelImportError):
        return HTTPException(422, str(exc))
    return HTTPException(503, "Modell konnte nicht gespeichert werden. Speicherplatz prüfen.")


@router.get("/models")
def models(request: Request) -> dict:
    return store(request).snapshot()


@router.post("/models/import")
def import_model(request: Request, body: ImportPath) -> dict:
    try:
        return store(request).import_path(body.path)
    except (ModelImportError, OSError) as exc:
        raise import_error(exc) from exc


@router.post("/models/upload")
async def upload_model(request: Request, filename: str = Query(max_length=200)) -> dict:
    instance = store(request)
    if not filename.lower().endswith(".pt"):
        raise HTTPException(422, "Bitte eine .pt-Modelldatei auswählen.")
    size = 0
    try:
        with tempfile.TemporaryFile() as upload:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_MODEL_BYTES:
                    raise HTTPException(413, "Modelldatei ist größer als 512 MiB.")
                await run_in_threadpool(upload.write, chunk)
            upload.seek(0)
            return await run_in_threadpool(instance.import_stream, upload, filename)
    except (ModelImportError, OSError) as exc:
        raise import_error(exc) from exc


@router.post("/models/activate")
def activate_model(request: Request, body: Activation) -> dict:
    try:
        return store(request).activate(body.model_id)
    except (ModelImportError, OSError) as exc:
        raise import_error(exc) from exc


@router.get("/result")
def result(request: Request) -> dict:
    instance = store(request)
    value = getattr(request.app.state, "ai_result", {})
    camera = getattr(request.app.state, "camera", None)
    status = camera.status() if camera else {}
    if (
        value.get("active_id") != instance.snapshot()["active_id"]
        or value.get("camera_revision") != status.get("revision")
        or not status.get("has_frame")
    ):
        return {
            "status": "waiting",
            "message": "Warte auf ein aktuelles Kamerabild.",
            "detections": [],
        }
    return value
