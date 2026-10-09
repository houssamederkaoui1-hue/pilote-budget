"""phase 3: budget allocation table (monthly income/needs/wants/savings/other)

The planning tables ``budgets``, ``goals``, ``recurring_transactions`` and
``debts`` were part of the initial schema; this revision only adds the
per-period *allocation* row that sits alongside the per-category budgets.

Revision ID: c3d4e5f6a7b8
Revises: a1c9f2d4b7e1
Create Date: 2026-10-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'a1c9f2d4b7e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "budget_allocations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("income_amount", sa.Double(), nullable=False, server_default="0"),
        sa.Column("needs_amount", sa.Double(), nullable=False, server_default="0"),
        sa.Column("wants_amount", sa.Double(), nullable=False, server_default="0"),
        sa.Column("savings_amount", sa.Double(), nullable=False, server_default="0"),
        sa.Column("other_amount", sa.Double(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budget_allocations")),
        sa.UniqueConstraint("month", name=op.f("uq_budget_allocations_month")),
    )
    op.create_index(
        op.f("ix_budget_allocations_month"), "budget_allocations", ["month"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_budget_allocations_month"), table_name="budget_allocations")
    op.drop_table("budget_allocations")