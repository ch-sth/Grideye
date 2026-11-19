"""Persist tagged object observations without inventing a position."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tagged_objects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("class_name", sa.String(100), nullable=False),
        sa.Column("number", sa.String(100), nullable=False, unique=True),
        sa.Column("confidence", sa.Float(), nullable=False),
    )
    op.create_index("ix_tagged_objects_timestamp", "tagged_objects", ["timestamp"])


def downgrade() -> None:
    op.drop_table("tagged_objects")
