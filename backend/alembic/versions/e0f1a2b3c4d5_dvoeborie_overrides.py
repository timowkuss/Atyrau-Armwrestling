"""dvoeborie_overrides

Revision ID: e0f1a2b3c4d5
Revises: d3e4f5a6b7c8
Create Date: 2026-08-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0f1a2b3c4d5'
down_revision: Union[str, Sequence[str], None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'dvoeborie_overrides',
        sa.Column('competition_id', sa.Integer(), sa.ForeignKey('competitions.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('categories.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('participant_id', sa.Integer(), sa.ForeignKey('competition_participants.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('manual_rank', sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('dvoeborie_overrides')
