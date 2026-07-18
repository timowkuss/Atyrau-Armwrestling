"""elo rating fields

Revision ID: a2f4c9e17d33
Revises: 861d708b8a1a
Create Date: 2026-07-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2f4c9e17d33'
down_revision: Union[str, Sequence[str], None] = '861d708b8a1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'athlete_statistics',
        sa.Column('elo_left', sa.Integer(), nullable=False, server_default='1000'),
    )
    op.add_column(
        'athlete_statistics',
        sa.Column('elo_right', sa.Integer(), nullable=False, server_default='1000'),
    )
    op.add_column(
        'matches',
        sa.Column('elo_applied', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column('matches', sa.Column('elo_delta_p1', sa.Integer(), nullable=True))
    op.add_column('matches', sa.Column('elo_delta_p2', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('matches', 'elo_delta_p2')
    op.drop_column('matches', 'elo_delta_p1')
    op.drop_column('matches', 'elo_applied')
    op.drop_column('athlete_statistics', 'elo_right')
    op.drop_column('athlete_statistics', 'elo_left')
