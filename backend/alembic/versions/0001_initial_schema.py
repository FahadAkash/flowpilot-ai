"""Initial FlowPilot AI schema with all 12 core tables.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-18
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

from flowpilot.db.models import Base

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
