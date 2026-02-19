"""Initial schema — all tables from DB-SCHEMA.md.

Revision ID: 0001
Revises:
Create Date: 2026-02-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. REFERENCE LAYER                                                   #
    # ------------------------------------------------------------------ #

    op.create_table(
        "assets",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticker", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("asset_class", sa.Text, nullable=False),
        sa.Column("sub_class", sa.Text, nullable=False),
        sa.Column("sector", sa.Text, nullable=True),
        sa.Column("geography", sa.Text, nullable=False),
        sa.Column("currency", sa.Text, nullable=False),
        sa.Column("is_etf", sa.Boolean, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("ticker", name="uq_assets_ticker"),
    )

    op.create_table(
        "universes",
        sa.Column("universe_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("universe_type", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_universes_name"),
    )

    op.create_table(
        "data_vendors",
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.UniqueConstraint("name", name="uq_data_vendors_name"),
    )

    op.create_table(
        "universe_assets",
        sa.Column(
            "universe_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("universes.universe_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.asset_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("is_benchmark", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )

    # ------------------------------------------------------------------ #
    # 2. MARKET DATA LAYER                                                 #
    # ------------------------------------------------------------------ #

    op.create_table(
        "price_bars",
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.asset_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_vendors.vendor_id"),
            primary_key=True,
        ),
        sa.Column("bar_date", sa.Date, primary_key=True, nullable=False),
        sa.Column("frequency", sa.Text, primary_key=True, nullable=False),
        sa.Column("adj_close", sa.Double, nullable=False),
        sa.Column("close", sa.Double, nullable=True),
        sa.Column("volume", sa.BigInteger, nullable=True),
        sa.Column(
            "pulled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "return_series",
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.asset_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("bar_date", sa.Date, primary_key=True, nullable=False),
        sa.Column("frequency", sa.Text, primary_key=True, nullable=False),
        sa.Column("return_type", sa.Text, primary_key=True, nullable=False),
        sa.Column("ret", sa.Double, nullable=False),
    )

    op.create_table(
        "risk_free_series",
        sa.Column("series_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("series_code", sa.Text, nullable=False),
        sa.Column("obs_date", sa.Date, nullable=False),
        sa.Column("rf_annual", sa.Double, nullable=False),
    )

    # ------------------------------------------------------------------ #
    # 3. ESTIMATION LAYER                                                  #
    # ------------------------------------------------------------------ #

    op.create_table(
        "assumption_sets",
        sa.Column("assumption_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "universe_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("universes.universe_id"),
            nullable=False,
        ),
        sa.Column("frequency", sa.Text, nullable=False),
        sa.Column("return_type", sa.Text, nullable=False),
        sa.Column("lookback_start", sa.Date, nullable=False),
        sa.Column("lookback_end", sa.Date, nullable=False),
        sa.Column("annualization_factor", sa.Integer, nullable=False),
        sa.Column("rf_annual", sa.Double, nullable=False),
        sa.Column("estimator", sa.Text, nullable=False),
        sa.Column("cov_method", sa.Text, nullable=False),
        sa.Column("psd_repair_applied", sa.Boolean, nullable=False),
        sa.Column("psd_repair_note", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "assumption_asset_stats",
        sa.Column(
            "assumption_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assumption_sets.assumption_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.asset_id"),
            primary_key=True,
        ),
        sa.Column("mu_annual", sa.Double, nullable=False),
        sa.Column("sigma_annual", sa.Double, nullable=False),
    )

    op.create_table(
        "assumption_cov",
        sa.Column(
            "assumption_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assumption_sets.assumption_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "asset_id_i",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.asset_id"),
            primary_key=True,
        ),
        sa.Column(
            "asset_id_j",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.asset_id"),
            primary_key=True,
        ),
        sa.Column("cov_annual", sa.Double, nullable=False),
    )

    # ------------------------------------------------------------------ #
    # 4. HOLDINGS LAYER                                                    #
    # ------------------------------------------------------------------ #

    op.create_table(
        "current_holdings_snapshots",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "current_holdings_positions",
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("current_holdings_snapshots.snapshot_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.asset_id"),
            primary_key=True,
        ),
        sa.Column("weight", sa.Double, nullable=False),
        sa.Column("market_value", sa.Double, nullable=True),
    )

    # ------------------------------------------------------------------ #
    # 5. SCREENING LAYER                                                   #
    # ------------------------------------------------------------------ #

    op.create_table(
        "screening_runs",
        sa.Column("screening_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "assumption_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assumption_sets.assumption_id"),
            nullable=False,
        ),
        sa.Column(
            "candidate_pool_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("universes.universe_id"),
            nullable=False,
        ),
        sa.Column("reference_type", sa.Text, nullable=False),
        sa.Column(
            "reference_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("current_holdings_snapshots.snapshot_id"),
            nullable=True,
        ),
        sa.Column(
            "reference_universe_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("universes.universe_id"),
            nullable=True,
        ),
        sa.Column(
            "nominal_add_weight",
            sa.Double,
            nullable=False,
            server_default=sa.text("0.05"),
        ),
        sa.Column("score_weights", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Exactly one reference FK must be non-null, matching reference_type.
        sa.CheckConstraint(
            "(reference_type = 'current_holdings'"
            " AND reference_snapshot_id IS NOT NULL"
            " AND reference_universe_id IS NULL)"
            " OR"
            " (reference_type = 'seed_universe'"
            " AND reference_universe_id IS NOT NULL"
            " AND reference_snapshot_id IS NULL)",
            name="ck_screening_runs_reference_consistency",
        ),
    )

    op.create_table(
        "screening_scores",
        sa.Column(
            "screening_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("screening_runs.screening_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.asset_id"),
            primary_key=True,
        ),
        sa.Column("avg_pairwise_corr", sa.Double, nullable=False),
        sa.Column("marginal_vol_reduction", sa.Double, nullable=False),
        sa.Column("sector_gap_score", sa.Double, nullable=False),
        sa.Column("hhi_reduction", sa.Double, nullable=False),
        sa.Column("composite_score", sa.Double, nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
    )

    # ------------------------------------------------------------------ #
    # 6. OPTIMIZATION LAYER                                                #
    # ------------------------------------------------------------------ #

    op.create_table(
        "optimization_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "assumption_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assumption_sets.assumption_id"),
            nullable=False,
        ),
        sa.Column("run_type", sa.Text, nullable=False),
        sa.Column("objective", sa.Text, nullable=False),
        sa.Column("constraints", postgresql.JSONB, nullable=False),
        sa.Column(
            "reference_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("current_holdings_snapshots.snapshot_id"),
            nullable=True,
        ),
        sa.Column("target_return", sa.Double, nullable=True),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("infeasibility_reason", sa.Text, nullable=True),
        sa.Column("solver_meta", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "optimization_results",
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("optimization_runs.run_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("exp_return", sa.Double, nullable=False),
        sa.Column("variance", sa.Double, nullable=False),
        sa.Column("stdev", sa.Double, nullable=False),
        sa.Column("sharpe", sa.Double, nullable=True),
        sa.Column("hhi", sa.Double, nullable=False),
        sa.Column("effective_n", sa.Double, nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
    )

    op.create_table(
        "optimization_weights",
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("optimization_runs.run_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.asset_id"),
            primary_key=True,
        ),
        sa.Column("weight", sa.Double, nullable=False),
        sa.Column("mcr", sa.Double, nullable=False),
        sa.Column("crc", sa.Double, nullable=False),
        sa.Column("prc", sa.Double, nullable=False),
    )

    # ------------------------------------------------------------------ #
    # 7. RISK ANALYTICS                                                    #
    # ------------------------------------------------------------------ #

    op.create_table(
        "scenario_definitions",
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("shocks", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "scenario_results",
        sa.Column("result_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("optimization_runs.run_id"),
            nullable=False,
        ),
        sa.Column(
            "scenario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scenario_definitions.scenario_id"),
            nullable=False,
        ),
        sa.Column("shocked_return", sa.Double, nullable=False),
        sa.Column("shocked_vol", sa.Double, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------ #
    # 8. BACKTESTING                                                       #
    # ------------------------------------------------------------------ #

    op.create_table(
        "backtest_runs",
        sa.Column("backtest_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "universe_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("universes.universe_id"),
            nullable=False,
        ),
        sa.Column(
            "benchmark_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.asset_id"),
            nullable=True,
        ),
        sa.Column("strategy", sa.Text, nullable=False),
        sa.Column("rebal_freq", sa.Text, nullable=False),
        sa.Column("rebal_threshold", sa.Double, nullable=True),
        sa.Column("window_length", sa.Integer, nullable=False),
        sa.Column("transaction_cost_bps", sa.Double, nullable=False),
        sa.Column("constraints", postgresql.JSONB, nullable=False),
        sa.Column("survivorship_bias_note", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "backtest_points",
        sa.Column(
            "backtest_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("backtest_runs.backtest_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("obs_date", sa.Date, primary_key=True, nullable=False),
        sa.Column("portfolio_value", sa.Double, nullable=False),
        sa.Column("portfolio_ret", sa.Double, nullable=False),
        sa.Column("portfolio_ret_net", sa.Double, nullable=False),
        sa.Column("benchmark_ret", sa.Double, nullable=True),
        sa.Column("active_ret", sa.Double, nullable=True),
        sa.Column("turnover", sa.Double, nullable=False),
        sa.Column("drawdown", sa.Double, nullable=False),
    )

    op.create_table(
        "backtest_summary",
        sa.Column(
            "backtest_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("backtest_runs.backtest_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("total_return", sa.Double, nullable=False),
        sa.Column("annualized_return", sa.Double, nullable=False),
        sa.Column("annualized_vol", sa.Double, nullable=False),
        sa.Column("sharpe", sa.Double, nullable=False),
        sa.Column("max_drawdown", sa.Double, nullable=False),
        sa.Column("var_95", sa.Double, nullable=False),
        sa.Column("cvar_95", sa.Double, nullable=False),
        sa.Column("avg_turnover", sa.Double, nullable=False),
        sa.Column("tracking_error", sa.Double, nullable=True),
        sa.Column("information_ratio", sa.Double, nullable=True),
    )

    # ------------------------------------------------------------------ #
    # 9. DRIFT DETECTION                                                   #
    # ------------------------------------------------------------------ #

    op.create_table(
        "drift_checks",
        sa.Column("drift_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("optimization_runs.run_id"),
            nullable=False,
        ),
        sa.Column("check_date", sa.Date, nullable=False),
        sa.Column(
            "threshold_pct",
            sa.Double,
            nullable=False,
            server_default=sa.text("0.05"),
        ),
        sa.Column("any_breach", sa.Boolean, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "drift_check_positions",
        sa.Column(
            "drift_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("drift_checks.drift_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.asset_id"),
            primary_key=True,
        ),
        sa.Column("target_weight", sa.Double, nullable=False),
        sa.Column("current_weight", sa.Double, nullable=False),
        sa.Column("drift_abs", sa.Double, nullable=False),
        sa.Column("breached", sa.Boolean, nullable=False),
        # NULL when breached = False; application layer enforces NOT NULL when breached = True
        sa.Column("explanation", sa.Text, nullable=True),
    )

    # ------------------------------------------------------------------ #
    # INDEXES (created after all tables exist)                             #
    # ------------------------------------------------------------------ #

    op.create_index("ix_price_bars_asset_date", "price_bars", ["asset_id", "bar_date"])
    op.create_index("ix_price_bars_freq_date", "price_bars", ["frequency", "bar_date"])
    op.create_index("ix_return_series_asset_date", "return_series", ["asset_id", "bar_date"])
    op.create_index("ix_risk_free_series_obs_date", "risk_free_series", ["obs_date"])


def downgrade() -> None:
    # Drop in reverse dependency order (leaves first, roots last).
    op.drop_index("ix_risk_free_series_obs_date", table_name="risk_free_series")
    op.drop_index("ix_return_series_asset_date", table_name="return_series")
    op.drop_index("ix_price_bars_freq_date", table_name="price_bars")
    op.drop_index("ix_price_bars_asset_date", table_name="price_bars")

    op.drop_table("drift_check_positions")
    op.drop_table("drift_checks")
    op.drop_table("backtest_summary")
    op.drop_table("backtest_points")
    op.drop_table("backtest_runs")
    op.drop_table("scenario_results")
    op.drop_table("scenario_definitions")
    op.drop_table("optimization_weights")
    op.drop_table("optimization_results")
    op.drop_table("optimization_runs")
    op.drop_table("screening_scores")
    op.drop_table("screening_runs")
    op.drop_table("current_holdings_positions")
    op.drop_table("current_holdings_snapshots")
    op.drop_table("assumption_cov")
    op.drop_table("assumption_asset_stats")
    op.drop_table("assumption_sets")
    op.drop_table("risk_free_series")
    op.drop_table("return_series")
    op.drop_table("price_bars")
    op.drop_table("universe_assets")
    op.drop_table("data_vendors")
    op.drop_table("universes")
    op.drop_table("assets")
