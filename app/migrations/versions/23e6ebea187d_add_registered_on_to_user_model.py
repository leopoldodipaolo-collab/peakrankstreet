"""Add registered_on to User model

Revision ID: 23e6ebea187d
Revises: <precedente_revision_id>
Create Date: 2025-10-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import DateTime
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '23e6ebea187d'
down_revision = '<precedente_revision_id>'
branch_labels = None
depends_on = None

def upgrade():
    # Aggiungi la colonna registered_on alla tabella user
    with op.batch_alter_table('user') as batch_op:
        batch_op.add_column(sa.Column('registered_on', sa.DateTime(), nullable=True))

    # Aggiorna i valori NULL con datetime corrente
    user_table = table('user', column('registered_on', DateTime))
    op.execute(
        user_table.update()
        .where(user_table.c.registered_on == None)
        .values(registered_on=datetime.utcnow())
    )

def downgrade():
    # Rimuovi la colonna registered_on se fai downgrade
    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_column('registered_on')
