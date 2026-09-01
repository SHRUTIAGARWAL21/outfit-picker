"""add garment AI columns (Step 3)

Adds the columns the worker fills in: the extracted attributes, the content
hash for deduplication, the schema version, the attempt counter and the failure
reason.

Revision ID: a1b2c3d4e5f6
Revises: 6e584b6353be
Create Date: 2026-08-31 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '6e584b6353be'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('garments', sa.Column('attributes_json', postgresql.JSONB(), nullable=True))
    op.add_column('garments', sa.Column('content_hash', sa.String(length=64), nullable=True))
    op.add_column('garments', sa.Column('schema_version', sa.Integer(), nullable=True))
    op.add_column(
        'garments',
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    )
    op.add_column('garments', sa.Column('failure_reason', sa.Text(), nullable=True))
    op.create_index(
        op.f('ix_garments_content_hash'), 'garments', ['content_hash'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_garments_content_hash'), table_name='garments')
    op.drop_column('garments', 'failure_reason')
    op.drop_column('garments', 'attempts')
    op.drop_column('garments', 'schema_version')
    op.drop_column('garments', 'content_hash')
    op.drop_column('garments', 'attributes_json')
