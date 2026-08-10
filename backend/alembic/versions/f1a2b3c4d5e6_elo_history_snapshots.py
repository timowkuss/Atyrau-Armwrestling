"""elo history snapshots

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-08-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e0f1a2b3c4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'elo_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('athlete_id', sa.Integer(), nullable=False),
        sa.Column('competition_id', sa.Integer(), nullable=False),
        sa.Column('hand', sa.String(length=10), nullable=False),
        sa.Column('elo', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['competition_id'], ['competitions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'athlete_id', 'competition_id', 'hand', name='uq_elo_history_athlete_competition_hand'
        ),
    )
    op.create_index(
        'ix_elo_history_athlete', 'elo_history', ['athlete_id', 'created_at']
    )


def downgrade() -> None:
    op.drop_index('ix_elo_history_athlete', table_name='elo_history')
    op.drop_table('elo_history')
