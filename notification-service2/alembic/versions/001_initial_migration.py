"""Initial migration

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создаём enum типы
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE orderstatus AS ENUM ('confirmed', 'gathering', 'ready_for_delivery', 'courier_assigned', 'out_for_delivery', 'delivered', 'cancelled');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE notificationchannel AS ENUM ('sms', 'email', 'push', 'telegram');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE promostatus AS ENUM ('draft', 'scheduled', 'sending', 'sent', 'cancelled');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE targetaudience AS ENUM ('all', 'regular_clients', 'new_clients', 'birthday');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    
    # Создаём таблицу notifications
    op.create_table(
        'notifications',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('order_id', sa.String(), nullable=True),
        sa.Column('client_id', sa.String(), nullable=False),
        sa.Column(
            'status',
            postgresql.ENUM(
                'confirmed',
                'gathering',
                'ready_for_delivery',
                'courier_assigned',
                'out_for_delivery',
                'delivered',
                'cancelled',
                name='orderstatus',
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            'channel',
            postgresql.ENUM(
                'sms', 'email', 'push', 'telegram', name='notificationchannel', create_type=False
            ),
            nullable=False,
        ),
        sa.Column('message', sa.String(), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('estimated_delivery_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('courier_name', sa.String(), nullable=True),
        sa.Column('tracking_url', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_order_id'), 'notifications', ['order_id'], unique=False)
    op.create_index(op.f('ix_notifications_client_id'), 'notifications', ['client_id'], unique=False)
    
    # Создаём таблицу promo_notifications
    op.create_table(
        'promo_notifications',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('message', sa.String(length=1000), nullable=False),
        sa.Column('promo_code', sa.String(), nullable=True),
        sa.Column('discount_percent', sa.Integer(), nullable=True),
        sa.Column('image_url', sa.String(), nullable=True),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            'target_audience',
            postgresql.ENUM(
                'all',
                'regular_clients',
                'new_clients',
                'birthday',
                name='targetaudience',
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column('channels', sa.JSON(), nullable=True),
        sa.Column(
            'status',
            postgresql.ENUM(
                'draft',
                'scheduled',
                'sending',
                'sent',
                'cancelled',
                name='promostatus',
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Создаём таблицу client_subscriptions
    op.create_table(
        'client_subscriptions',
        sa.Column('client_id', sa.String(), nullable=False),
        sa.Column('order_sms', sa.Boolean(), nullable=True),
        sa.Column('order_email', sa.Boolean(), nullable=True),
        sa.Column('order_push', sa.Boolean(), nullable=True),
        sa.Column('order_telegram', sa.Boolean(), nullable=True),
        sa.Column('promo_sms', sa.Boolean(), nullable=True),
        sa.Column('promo_email', sa.Boolean(), nullable=True),
        sa.Column('promo_push', sa.Boolean(), nullable=True),
        sa.Column('promo_telegram', sa.Boolean(), nullable=True),
        sa.Column('quiet_hours_enabled', sa.Boolean(), nullable=True),
        sa.Column('quiet_hours_start', sa.String(), nullable=True),
        sa.Column('quiet_hours_end', sa.String(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('client_id')
    )


def downgrade() -> None:
    # Удаляем таблицы
    op.drop_table('client_subscriptions')
    op.drop_table('promo_notifications')
    op.drop_table('notifications')
    
    # Удаляем enum типы
    op.execute("DROP TYPE IF EXISTS targetaudience")
    op.execute("DROP TYPE IF EXISTS promostatus")
    op.execute("DROP TYPE IF EXISTS notificationchannel")
    op.execute("DROP TYPE IF EXISTS orderstatus")

