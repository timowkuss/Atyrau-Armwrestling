"""coaches profile fields (first/last name, birth_date, iin, qualification, city)

Revision ID: a1b2c3d4e5f6
Revises: f2a3b4c5d6e7
Create Date: 2026-07-27 10:00:00.000000

Карточка тренера в админке теперь требует: Имя, Фамилию, возраст (дату
рождения), ИИН (12 цифр), тренерское звание, клуб и город/район. full_name
остаётся как есть (пересчитывается сервером из first_name+last_name) —
все существующие места, читающие coach.full_name, не трогаем.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('coaches', sa.Column('first_name', sa.String(length=100), nullable=True))
    op.add_column('coaches', sa.Column('last_name', sa.String(length=100), nullable=True))
    op.add_column('coaches', sa.Column('birth_date', sa.Date(), nullable=True))
    op.add_column('coaches', sa.Column('iin', sa.String(length=12), nullable=True))
    op.add_column('coaches', sa.Column('qualification', sa.String(length=100), nullable=True))
    op.add_column('coaches', sa.Column('city_id', sa.Integer(), nullable=True))
    op.create_unique_constraint('uq_coaches_iin', 'coaches', ['iin'])
    op.create_foreign_key(
        'fk_coaches_city_id_cities', 'coaches', 'cities', ['city_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_coaches_city_id_cities', 'coaches', type_='foreignkey')
    op.drop_constraint('uq_coaches_iin', 'coaches', type_='unique')
    op.drop_column('coaches', 'city_id')
    op.drop_column('coaches', 'qualification')
    op.drop_column('coaches', 'iin')
    op.drop_column('coaches', 'birth_date')
    op.drop_column('coaches', 'first_name')
    op.drop_column('coaches', 'last_name')
