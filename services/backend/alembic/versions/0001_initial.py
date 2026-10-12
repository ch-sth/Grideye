"""Initial missions, detections and events tables."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "missions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "detections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mission_id", sa.Uuid(), sa.ForeignKey("missions.id"), nullable=True),
        sa.Column("class_name", sa.String(100), nullable=False),
        sa.Column("number", sa.String(100), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("world_x_m", sa.Float(), nullable=False),
        sa.Column("world_y_m", sa.Float(), nullable=False),
        sa.Column("grid_cell", sa.String(20), nullable=False),
        sa.Column("image_reference", sa.Text(), nullable=True),
    )
    op.create_table(
        "system_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_detections_timestamp", "detections", ["timestamp"])
    op.create_index("ix_detections_grid_cell", "detections", ["grid_cell"])
    op.create_index("ix_system_events_timestamp", "system_events", ["timestamp"])


def downgrade() -> None:
    op.drop_table("system_events")
    op.drop_table("detections")
    op.drop_table("missions")
