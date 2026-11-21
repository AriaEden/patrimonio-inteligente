"""
btc_accumulator/backtester.py
Comparative Backtesting Engine for BTC-Accumulator V1.3.
Executes concurrent simulations of:
1. HODL Benchmark
2. Modalidad A (Capital Fijo)
3. Modalidad B (Capital Compuesto)
under dual microstructural execution scenarios (Conservative vs Optimistic)
with high-resolution 1-hour candle order validation and unrounded fee accounting.
"""

from dataclasses import dataclass
from decimal import Decimal
import logging
import os
from typing import Dict, Any, Tuple, List, Optional
import pandas as pd

from btc_accumulator.config import (
    DEFAULT_MAKER_FEE_RATE,
    DEFAULT_TAKER_FEE_RATE,
    DEFAULT_TAKER_SLIPPAGE_BPS,
    CAPITAL_PER_TRADE_USDC,
)
from btc_accumulator.bitso_client import BookSpecification, BitsoPublicClient
from btc_accumulator.indicators import add_all_indicators
from btc_accumulator.strategy import (
    BTCAccumulatorStrategy,
    SimulationMode,
    TradeRecord,
)
from btc_accumulator.execution_simulator import ExecutionScenario
from btc_accumulator.metrics import compute_comprehensive_metrics, StrategyMetrics

logger = logging.getLogger(__name__)


@dataclass
class ComparativePartitionResult:
    partition_name: str
    scenario: ExecutionScenario
    start_date: str
    end_date: str
    candle_count: int
    start_price: Decimal
    end_price: Decimal
    fixed_metrics: StrategyMetrics
    compounded_metrics: StrategyMetrics
    fixed_trades: List[TradeRecord]
    compounded_trades: List[TradeRecord]


class Backtester:
    """
    Backtesting engine enforcing zero lookahead, high-resolution execution realism,
    and side-by-side comparison between Fixed Capital, Compounded Capital, and HODL.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        hourly_df: Optional[pd.DataFrame] = None,
        book_spec: Optional[BookSpecification] = None,
        initial_usdc_per_period: Decimal = CAPITAL_PER_TRADE_USDC,
        capital_fraction: Decimal = Decimal("1.00"),
        max_drawdown_limit: Decimal = Decimal("0.05"),  # 5% max drawdown rule
        scenario: ExecutionScenario = ExecutionScenario.CONSERVATIVE,
        maker_fee: Decimal = DEFAULT_MAKER_FEE_RATE,
        taker_fee: Decimal = DEFAULT_TAKER_FEE_RATE,
        taker_slippage_bps: Decimal = DEFAULT_TAKER_SLIPPAGE_BPS,
        enable_partial_fills: bool = False,
        enable_bull_run_filter: bool = True,
    ):
        self.initial_usdc = initial_usdc_per_period
        self.capital_fraction = capital_fraction
        self.max_drawdown_limit = max_drawdown_limit
        self.scenario = scenario
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.taker_slippage_bps = taker_slippage_bps
        self.enable_partial_fills = enable_partial_fills
        self.enable_bull_run_filter = enable_bull_run_filter

        self.client = BitsoPublicClient()
        self.book_spec = book_spec or self.client.get_book_spec()
        self.raw_df = self._verify_and_prepare_data(df)
        self.indicator_df = add_all_indicators(self.raw_df)

        # Load and index hourly dataset if available
        self.hourly_dict: Dict[str, Dict[str, Any]] = {}
        if hourly_df is not None:
            self._prepare_hourly_data(hourly_df)
        else:
            default_1h_path = os.path.join(os.path.dirname(__file__), "..", "data", "bitso_btc_usd_1h.csv")
            if os.path.exists(default_1h_path):
                try:
                    loaded_1h = pd.read_csv(default_1h_path)
                    self._prepare_hourly_data(loaded_1h)
                except Exception as e:
                    logger.warning(f"Failed to auto-load 1H data from {default_1h_path}: {e}")

    def _prepare_hourly_data(self, df_1h: pd.DataFrame) -> None:
        """Indexes 1H candles by standardized UTC timestamp strings for O(1) lookup."""
        df = df_1h.copy()
        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        elif df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")

        for _, row in df.iterrows():
            ts_str = row["timestamp"].strftime("%Y-%m-%d %H:%M:%S+00:00")
            self.hourly_dict[ts_str] = {
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row.get("volume", 0),
            }
        logger.info(f"Indexed {len(self.hourly_dict):,} hourly candles for 2-hour execution validation.")

    def _verify_and_prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Verifies timestamp monotonicity, UTC alignment, and no nulls."""
        df = df.copy()
        required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        for c in required_cols:
            if c not in df.columns:
                raise ValueError(f"Missing required OHLCV column: '{c}'")

        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        elif df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")

        df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)

        if not df["timestamp"].is_monotonic_increasing:
            raise ValueError("Data integrity failure: Timestamps are not monotonically increasing.")

        if df[["open", "high", "low", "close"]].isnull().any().any():
            raise ValueError("Data integrity failure: Null pricing values detected.")

        return df

    def run_single_mode_simulation(
        self,
        df_subset: pd.DataFrame,
        mode: SimulationMode,
        scenario: Optional[ExecutionScenario] = None,
    ) -> Tuple[StrategyMetrics, List[TradeRecord], BTCAccumulatorStrategy]:
        """Runs simulation for a specific mode on a dataframe slice."""
        active_scenario = scenario or self.scenario
        start_price = Decimal(str(df_subset.iloc[0]["close"]))
        end_price = Decimal(str(df_subset.iloc[-1]["close"]))

        strategy = BTCAccumulatorStrategy(
            book_spec=self.book_spec,
            mode=mode,
            initial_usdc=self.initial_usdc,
            initial_price=start_price,
            capital_fraction=self.capital_fraction,
            max_drawdown_limit=self.max_drawdown_limit,
            scenario=active_scenario,
            maker_fee=self.maker_fee,
            taker_fee=self.taker_fee,
            taker_slippage_bps=self.taker_slippage_bps,
            enable_partial_fills=self.enable_partial_fills,
            enable_bull_run_filter=self.enable_bull_run_filter,
            hourly_data=self.hourly_dict,
        )

        for idx, row in df_subset.iterrows():
            strategy.process_candle(idx, row)

        final_btc_equity = strategy.portfolio.get_total_btc_equity(end_price)

        mode_title = "Modalidad A (Capital Fijo)" if mode == SimulationMode.FIXED else "Modalidad B (Capital Compuesto)"

        metrics = compute_comprehensive_metrics(
            mode_name=mode_title,
            trades=strategy.completed_trades,
            initial_btc=strategy.portfolio.initial_btc,
            final_btc_equity=final_btc_equity,
            start_price=start_price,
            end_price=end_price,
            mtm_max_drawdown_btc=strategy.portfolio.max_mtm_drawdown_btc,
            mtm_max_drawdown_pct=strategy.portfolio.max_mtm_drawdown_pct,
            is_suspended=strategy.portfolio.is_suspended,
            suspension_reason=strategy.portfolio.suspension_reason.value,
            canceled_orders_count=strategy.canceled_sell_orders,
        )

        return metrics, strategy.completed_trades, strategy

    def run_comparative_partitioned_backtest(
        self,
        scenario: Optional[ExecutionScenario] = None,
        train_end: str = "2023-12-31 23:59:59+00:00",
        val_end: str = "2024-12-31 23:59:59+00:00",
    ) -> Dict[str, ComparativePartitionResult]:
        """Runs side-by-side backtest across Train, Validation, OOS, and Full History."""
        active_scenario = scenario or self.scenario
        df = self.indicator_df

        train_mask = df["timestamp"] <= train_end
        val_mask = (df["timestamp"] > train_end) & (df["timestamp"] <= val_end)
        oos_mask = df["timestamp"] > val_end

        partitions = {
            "Train (In-Sample: 2022-2023)": df[train_mask].reset_index(drop=True),
            "Validation (2024 Bull/Halving)": df[val_mask].reset_index(drop=True),
            "Out-of-Sample (2025-2026)": df[oos_mask].reset_index(drop=True),
            "Full History (2022-2026)": df.copy().reset_index(drop=True),
        }

        results: Dict[str, ComparativePartitionResult] = {}

        for name, sub_df in partitions.items():
            if len(sub_df) < 60:
                continue

            start_p = Decimal(str(sub_df.iloc[0]["close"]))
            end_p = Decimal(str(sub_df.iloc[-1]["close"]))

            # Run Fixed
            m_fixed, trades_fixed, _ = self.run_single_mode_simulation(sub_df, SimulationMode.FIXED, active_scenario)
            # Run Compounded
            m_comp, trades_comp, _ = self.run_single_mode_simulation(sub_df, SimulationMode.COMPOUNDED, active_scenario)

            results[name] = ComparativePartitionResult(
                partition_name=name,
                scenario=active_scenario,
                start_date=str(sub_df.iloc[0]["timestamp"]),
                end_date=str(sub_df.iloc[-1]["timestamp"]),
                candle_count=len(sub_df),
                start_price=start_p,
                end_price=end_p,
                fixed_metrics=m_fixed,
                compounded_metrics=m_comp,
                fixed_trades=trades_fixed,
                compounded_trades=trades_comp,
            )

        return results
