"""phase_8_reconciliation

Revision ID: phase_8
Revises: bf2809408e7c
Create Date: 2026-05-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'phase_8_reconciliation'
down_revision = 'add_platform_connections'
dependencies = []


def upgrade():
    # Enum types
    ledger_entry_type = sa.Enum('order_payment', 'platform_fee', 'delivery_fee', 'refund', 'payout', 'adjustment', 'tax', 'tip', name='ledger_entry_type')
    ledger_entry_status = sa.Enum('pending', 'confirmed', 'reconciled', 'disputed', 'written_off', name='ledger_entry_status')
    reconciliation_run_status = sa.Enum('pending', 'in_progress', 'completed', 'failed', 'partial', name='reconciliation_run_status')
    discrepancy_type = sa.Enum('missing_order', 'orphan_order', 'amount_mismatch', 'fee_mismatch', 'duplicate_payout', 'missing_payout', 'tax_mismatch', 'status_mismatch', name='discrepancy_type')
    discrepancy_status = sa.Enum('open', 'under_review', 'resolved', 'escalated', 'ignored', name='discrepancy_status')
    payout_status = sa.Enum('expected', 'scheduled', 'in_transit', 'received', 'failed', 'disputed', name='payout_status')
    report_type = sa.Enum('daily', 'weekly', 'monthly', 'custom', name='report_type')

    ledger_entry_type.create(op.get_bind(), checkfirst=True)
    ledger_entry_status.create(op.get_bind(), checkfirst=True)
    reconciliation_run_status.create(op.get_bind(), checkfirst=True)
    discrepancy_type.create(op.get_bind(), checkfirst=True)
    discrepancy_status.create(op.get_bind(), checkfirst=True)
    payout_status.create(op.get_bind(), checkfirst=True)
    report_type.create(op.get_bind(), checkfirst=True)

    # Add columns to existing tables
    op.add_column('orders', sa.Column('platform_connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('platform_connections.id'), nullable=True))
    op.add_column('orders', sa.Column('order_number', sa.String(), nullable=True))

    # financial_ledger
    op.create_table(
        'financial_ledger',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('merchant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('merchants.id'), nullable=False, index=True),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('orders.id'), nullable=True, index=True),
        sa.Column('platform_connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('platform_connections.id'), nullable=True, index=True),
        sa.Column('payout_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('payouts.id'), nullable=True, index=True),
        sa.Column('entry_type', ledger_entry_type, nullable=False, index=True),
        sa.Column('status', ledger_entry_status, default='pending', nullable=False),
        sa.Column('currency', sa.String(3), default='BHD', nullable=False),
        sa.Column('gross_amount', sa.Numeric(12, 4), nullable=False),
        sa.Column('fee_amount', sa.Numeric(12, 4), default=0.0),
        sa.Column('tax_amount', sa.Numeric(12, 4), default=0.0),
        sa.Column('net_amount', sa.Numeric(12, 4), nullable=False),
        sa.Column('platform_reference', sa.String(255), nullable=True, index=True),
        sa.Column('platform_order_id', sa.String(255), nullable=True, index=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('meta_data', postgresql.JSONB, default=dict),
        sa.Column('reconciliation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('reconciliation_runs.id'), nullable=True),
        sa.Column('transaction_date', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
    )

    # reconciliation_runs
    op.create_table(
        'reconciliation_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('merchant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('merchants.id'), nullable=False, index=True),
        sa.Column('platform_connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('platform_connections.id'), nullable=True),
        sa.Column('date_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('date_to', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', reconciliation_run_status, default='pending'),
        sa.Column('total_orders_checked', sa.Integer, default=0),
        sa.Column('total_orders_matched', sa.Integer, default=0),
        sa.Column('total_discrepancies_found', sa.Integer, default=0),
        sa.Column('total_discrepancies_resolved', sa.Integer, default=0),
        sa.Column('total_amount_checked', sa.Numeric(14, 4), default=0.0),
        sa.Column('total_variance', sa.Numeric(14, 4), default=0.0),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('triggered_by', sa.String(50), default='system'),
        sa.Column('config_snapshot', postgresql.JSONB, default=dict),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # discrepancies
    op.create_table(
        'discrepancies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('merchant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('merchants.id'), nullable=False, index=True),
        sa.Column('reconciliation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('reconciliation_runs.id'), nullable=False, index=True),
        sa.Column('discrepancy_type', discrepancy_type, nullable=False),
        sa.Column('status', discrepancy_status, default='open'),
        sa.Column('severity', sa.String(20), default='medium'),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('orders.id'), nullable=True),
        sa.Column('platform_order_id', sa.String(255), nullable=True),
        sa.Column('platform_connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('platform_connections.id'), nullable=True),
        sa.Column('payout_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('payouts.id'), nullable=True),
        sa.Column('expected_amount', sa.Numeric(12, 4), nullable=True),
        sa.Column('actual_amount', sa.Numeric(12, 4), nullable=True),
        sa.Column('variance', sa.Numeric(12, 4), nullable=True),
        sa.Column('currency', sa.String(3), default='BHD'),
        sa.Column('expected_value', sa.Text, nullable=True),
        sa.Column('actual_value', sa.Text, nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('resolution_notes', sa.Text, nullable=True),
        sa.Column('resolved_by', sa.String(100), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
    )

    # payouts
    op.create_table(
        'payouts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('merchant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('merchants.id'), nullable=False, index=True),
        sa.Column('platform_connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('platform_connections.id'), nullable=False, index=True),
        sa.Column('platform_payout_id', sa.String(255), nullable=False, index=True),
        sa.Column('platform_period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('platform_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', payout_status, default='expected'),
        sa.Column('currency', sa.String(3), default='BHD', nullable=False),
        sa.Column('gross_sales', sa.Numeric(14, 4), default=0.0),
        sa.Column('total_fees', sa.Numeric(14, 4), default=0.0),
        sa.Column('total_refunds', sa.Numeric(14, 4), default=0.0),
        sa.Column('total_adjustments', sa.Numeric(14, 4), default=0.0),
        sa.Column('net_payout', sa.Numeric(14, 4), nullable=False),
        sa.Column('breakdown', postgresql.JSONB, default=dict),
        sa.Column('bank_reference', sa.String(255), nullable=True),
        sa.Column('bank_account_last4', sa.String(4), nullable=True),
        sa.Column('expected_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('received_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
    )

    # settlement_reports
    op.create_table(
        'settlement_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('merchant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('merchants.id'), nullable=False, index=True),
        sa.Column('report_type', report_type, default='daily'),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('platform_connection_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('platform_connections.id'), nullable=True),
        sa.Column('total_orders', sa.Integer, default=0),
        sa.Column('total_sales', sa.Numeric(14, 4), default=0.0),
        sa.Column('total_fees', sa.Numeric(14, 4), default=0.0),
        sa.Column('total_refunds', sa.Numeric(14, 4), default=0.0),
        sa.Column('total_payouts', sa.Numeric(14, 4), default=0.0),
        sa.Column('net_revenue', sa.Numeric(14, 4), default=0.0),
        sa.Column('platform_breakdown', postgresql.JSONB, default=dict),
        sa.Column('payment_method_breakdown', postgresql.JSONB, default=dict),
        sa.Column('file_url', sa.String(500), nullable=True),
        sa.Column('file_format', sa.String(10), nullable=True),
        sa.Column('is_final', sa.Boolean, default=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
    )

    # Indexes
    op.create_index('ix_ledger_merchant_date', 'financial_ledger', ['merchant_id', 'transaction_date'])
    op.create_index('ix_ledger_platform_order', 'financial_ledger', ['platform_order_id', 'merchant_id'])
    op.create_index('ix_discrepancy_status', 'discrepancies', ['status', 'merchant_id'])
    op.create_index('ix_payout_platform_ref', 'payouts', ['platform_payout_id', 'platform_connection_id'])
    op.create_index('ix_settlement_period', 'settlement_reports', ['merchant_id', 'period_start', 'period_end'])


def downgrade():
    op.drop_index('ix_settlement_period', table_name='settlement_reports')
    op.drop_index('ix_payout_platform_ref', table_name='payouts')
    op.drop_index('ix_discrepancy_status', table_name='discrepancies')
    op.drop_index('ix_ledger_platform_order', table_name='financial_ledger')
    op.drop_index('ix_ledger_merchant_date', table_name='financial_ledger')

    op.drop_table('settlement_reports')
    op.drop_table('payouts')
    op.drop_table('discrepancies')
    op.drop_table('reconciliation_runs')
    op.drop_table('financial_ledger')

    op.drop_column('orders', 'platform_connection_id')
    op.drop_column('orders', 'order_number')

    sa.Enum(name='ledger_entry_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='ledger_entry_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='reconciliation_run_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='discrepancy_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='discrepancy_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='payout_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='report_type').drop(op.get_bind(), checkfirst=True)
