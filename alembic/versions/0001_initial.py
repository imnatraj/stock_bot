"""Initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-06-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'trades',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('action', sa.String(length=10), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(18, 4), nullable=False),
        sa.Column('trade_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'positions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(length=20), nullable=False, unique=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('average_price', sa.Numeric(18, 4), nullable=False),
        sa.Column('current_price', sa.Numeric(18, 4), nullable=True),
        sa.Column('unrealized_pnl', sa.Numeric(18, 4), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'signals',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('score', sa.Numeric(10, 2), nullable=True),
        sa.Column('buy_price', sa.Numeric(18, 4), nullable=True),
        sa.Column('stop_loss', sa.Numeric(18, 4), nullable=True),
        sa.Column('target_price', sa.Numeric(18, 4), nullable=True),
        sa.Column('signal_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'portfolio_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('portfolio_value', sa.Numeric(18, 4), nullable=False),
        sa.Column('cash_available', sa.Numeric(18, 4), nullable=False),
        sa.Column('realized_pnl', sa.Numeric(18, 4), nullable=False),
        sa.Column('unrealized_pnl', sa.Numeric(18, 4), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
    )

    op.create_table(
        'backtest_runs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('strategy_name', sa.String(length=100), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('cagr', sa.Numeric(18, 4)),
        sa.Column('sharpe_ratio', sa.Numeric(18, 4)),
        sa.Column('max_drawdown', sa.Numeric(18, 4)),
        sa.Column('win_rate', sa.Numeric(18, 4)),
        sa.Column('profit_factor', sa.Numeric(18, 4)),
        sa.Column('total_return', sa.Numeric(18, 4)),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'backtest_trades',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('run_id', sa.Integer(), sa.ForeignKey('backtest_runs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('entry_date', sa.Date(), nullable=False),
        sa.Column('exit_date', sa.Date(), nullable=True),
        sa.Column('entry_price', sa.Numeric(18, 4), nullable=False),
        sa.Column('exit_price', sa.Numeric(18, 4), nullable=True),
        sa.Column('pnl_percent', sa.Numeric(18, 4), nullable=True),
    )

    op.create_table(
        'ai_reports',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('report_date', sa.Date(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('recommendations', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'telegram_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('message_type', sa.String(length=50), nullable=False),
        sa.Column('message_body', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
    )

    # Create indexes mapping to models
    op.create_index('ix_positions_symbol', 'positions', ['symbol'], unique=True)
    op.create_index('ix_trades_symbol', 'trades', ['symbol'], unique=False)
    op.create_index('ix_signals_symbol', 'signals', ['symbol'], unique=False)
    op.create_index('ix_backtest_trades_run_id', 'backtest_trades', ['run_id'], unique=False)
    op.create_index('ix_signals_symbol_signal_date', 'signals', ['symbol', 'signal_date'], unique=False)
    op.create_index('ix_trades_symbol_trade_date', 'trades', ['symbol', 'trade_date'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_trades_symbol_trade_date', table_name='trades')
    op.drop_index('ix_signals_symbol_signal_date', table_name='signals')
    op.drop_index('ix_backtest_trades_run_id', table_name='backtest_trades')
    op.drop_index('ix_signals_symbol', table_name='signals')
    op.drop_index('ix_trades_symbol', table_name='trades')
    op.drop_index('ix_positions_symbol', table_name='positions')

    op.drop_table('telegram_logs')
    op.drop_table('ai_reports')
    op.drop_table('backtest_trades')
    op.drop_table('backtest_runs')
    op.drop_table('portfolio_snapshots')
    op.drop_table('signals')
    op.drop_table('positions')
    op.drop_table('trades')

