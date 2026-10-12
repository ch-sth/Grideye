from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from grideye_shared.config import Settings


class Base(AsyncAttrs, DeclarativeBase):
    pass


class MissionRow(Base):
    __tablename__ = "missions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DetectionRow(Base):
    __tablename__ = "detections"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    mission_id: Mapped[UUID | None] = mapped_column(ForeignKey("missions.id"), nullable=True)
    class_name: Mapped[str] = mapped_column(String(100))
    number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    world_x_m: Mapped[float] = mapped_column(Float)
    world_y_m: Mapped[float] = mapped_column(Float)
    grid_cell: Mapped[str] = mapped_column(String(20), index=True)
    image_reference: Mapped[str | None] = mapped_column(Text, nullable=True)


class MissionPlanRow(Base):
    __tablename__ = "mission_plans"
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("missions.id"), primary_key=True)
    plan: Mapped[dict] = mapped_column(JSON)


class SystemEventRow(Base):
    __tablename__ = "system_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    payload_json: Mapped[str] = mapped_column(Text)


settings = Settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def create_schema() -> None:
    # Alembic is authoritative for production; this makes the bootstrap self-starting.
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
