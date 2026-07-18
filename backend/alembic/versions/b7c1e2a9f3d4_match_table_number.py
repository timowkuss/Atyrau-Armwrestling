"""match table_number

Revision ID: b7c1e2a9f3d4
Revises: a2f4c9e17d33
Create Date: 2026-07-18 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c1e2a9f3d4'
down_revision: Union[str, Sequence[str], None] = 'a2f4c9e17d33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('matches', sa.Column('table_number', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('matches', 'table_number')
