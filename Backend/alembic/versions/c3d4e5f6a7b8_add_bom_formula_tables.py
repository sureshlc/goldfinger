"""Add bom_formula and bom_component tables (persisted BOM cache)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-31 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'bom_formula',
        sa.Column('assembly_item_id', sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column('revision_id', sa.String(length=64), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('has_bom', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('refreshed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_error', sa.String(length=512), nullable=True),
        sa.PrimaryKeyConstraint('assembly_item_id'),
    )
    op.create_table(
        'bom_component',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('assembly_item_id', sa.BigInteger(), nullable=False),
        sa.Column('component_item_id', sa.BigInteger(), nullable=False),
        sa.Column('component_sku', sa.String(length=255), nullable=False),
        sa.Column('component_name', sa.String(length=512), nullable=True),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(length=32), nullable=True),
        sa.Column('is_phantom', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_manufacturing', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('bom_id', sa.String(length=64), nullable=True),
        sa.Column('ordinal', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.ForeignKeyConstraint(['assembly_item_id'], ['bom_formula.assembly_item_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_bom_component_assembly', 'bom_component', ['assembly_item_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_bom_component_assembly', table_name='bom_component')
    op.drop_table('bom_component')
    op.drop_table('bom_formula')
