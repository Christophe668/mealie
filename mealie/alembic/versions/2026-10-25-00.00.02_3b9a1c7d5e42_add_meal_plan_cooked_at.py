"""Add meal plan cooked_at.

Revision ID: 3b9a1c7d5e42
Revises: 8e849a1153cf
Create Date: 2026-10-25 00:00:02

"""

import sqlalchemy as sa
from alembic import op

import mealie.db.migration_types

# revision identifiers, used by Alembic.
revision = "3b9a1c7d5e42"
down_revision: str | None = "8e849a1153cf"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade():
    with op.batch_alter_table("group_meal_plans", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cooked_at", mealie.db.migration_types.NaiveDateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("group_meal_plans", schema=None) as batch_op:
        batch_op.drop_column("cooked_at")
