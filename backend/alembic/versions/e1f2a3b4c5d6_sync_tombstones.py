"""sync tombstones for admin -> desktop pull sync

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-07-24 12:00:00.000000

Десктоп-приложение теперь не только отправляет изменения на сервер, но и
периодически спрашивает "что изменилось в админке с прошлого раза"
(см. GET /api/v1/sync/athletes/changes). Обновления ловятся по
Athlete.updated_at, а вот жёсткие удаления — нет (после DELETE строки
уже нет, сравнивать не с чем), поэтому нужен отдельный лог "что и когда
удалили".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sync_tombstones',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('entity_type', sa.String(length=30), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        'ix_sync_tombstones_type_time', 'sync_tombstones', ['entity_type', 'deleted_at']
    )


def downgrade() -> None:
    op.drop_index('ix_sync_tombstones_type_time', table_name='sync_tombstones')
    op.drop_table('sync_tombstones')
