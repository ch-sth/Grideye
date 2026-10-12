"""Persist full mission routes without changing existing missions or detections."""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mission_plans",
        sa.Column("mission_id", sa.Uuid(), sa.ForeignKey("missions.id"), primary_key=True),
        sa.Column("plan", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("mission_plans")
