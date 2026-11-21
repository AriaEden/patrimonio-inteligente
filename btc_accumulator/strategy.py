"""
btc_accumulator/strategy.py
BTC-Accumulator V1.3 Strategy State Machine with Real Portfolio Accounting,
High-Resolution 2-Hour Execution Verification, and Intravela Exit Resolution.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import logging
from typing import Optional, List, Dict, Any
import pandas as pd

from btc_accumulator.config import (
    RSI_ENTRY_THRESHOLD,
    ADX_ENTRY_THRESHOLD,
    MAX_SMA_DEVIATION_PCT,
    CAPITAL_PER_TRADE_USDC,
    BUYBACK_TARGET_DISCOUNT,
    DEFENSIVE_STOP_PREMIUM,
    MAX_HOLDING_CANDLES_4H,
    DEFAULT_MAKER_FEE_RATE,
    DEFAULT_TAKER_FEE_RATE,
    DEFAULT_TAKER_SLIPPAGE_BPS,
    SATOSHIS_PER_BTC,
)
from btc_accumulator.bitso_client import BookSpecification, BitsoPublicClient
from btc_accumulator.portfolio import PortfolioManager, SuspensionReason
from btc_accumulator.execution_simulator import (
    ExecutionSimulator,
    ExecutionScenario,
    FillStatus,
    MakerSellFillResult,
    BuybackFillResult,
)

logger = logging.getLogger(__name__)


class SimulationMode(str, Enum):
    FIXED = "FIXED"                  # Modalidad A: Lote fijo inicial en BTC
    COMPOUNDED = "COMPOUNDED"        # Modalidad B: Capital compuesto (100% reinversión de BTC netos)


class StrategyState(str, Enum):
    IDLE = "IDLE"
    PENDING_LIMIT_SELL = "PENDING_LIMIT_SELL"
    IN_POSITION_AWAITING_BUYBACK = "IN_POSITION_AWAITING_BUYBACK"


class ExitReason(str, Enum):
    TARGET_BUYBACK = "TARGET_BUYBACK"
    DEFENSIVE_STOP = "DEFENSIVE_STOP"
    CONTRADICTORY_DEFENSIVE = "CONTRADICTORY_DEFENSIVE"  # Intravela conflict resolved defensively
    TIME_STOP = "TIME_STOP"
    POST_ONLY_EXPIRED = "POST_ONLY_EXPIRED"
    POST_ONLY_TOUCH_ONLY = "POST_ONLY_TOUCH_ONLY"
    POST_ONLY_REJECTED = "POST_ONLY_REJECTED"


@dataclass
class TradeRecord:
    """Represents a completed or canceled trading cycle with portfolio ledger details."""
    trade_id: int
    mode: SimulationMode
    entry_candle_idx: int
    entry_time: str
    exit_candle_idx: int
    exit_time: str
    regime: str
    sell_price: Decimal
    buyback_price: Decimal
    btc_sold: Decimal
    btc_bought: Decimal
    net_satoshis_pnl: int
    net_btc_pnl: Decimal
    usdc_proceeds_gross: Decimal
    usdc_proceeds_net: Decimal
    maker_fee_sell_usdc: Decimal
    buyback_fee_usdc: Decimal
    exit_reason: ExitReason
    holding_hours: int
    maker_sell: bool
    maker_buy: bool
    slippage_paid_usdc: Decimal
    portfolio_btc_after_trade: Decimal
    portfolio_equity_btc: Decimal


class BTCAccumulatorStrategy:
    """
    Finite State Machine implementing BTC Accumulator V1.3.
    Integrates high-resolution 2-hour execution validation,
    conservative contradictory exit resolution, real portfolio accounting,
    and accurate drawdown tracking.
    """

    def __init__(
        self,
        book_spec: BookSpecification,
        mode: SimulationMode = SimulationMode.FIXED,
        initial_usdc: Decimal = CAPITAL_PER_TRADE_USDC,
        initial_price: Decimal = Decimal("47000.00"),
        capital_fraction: Decimal = Decimal("1.00"),
        max_drawdown_limit: Decimal = Decimal("0.05"),  # 5% max drawdown rule
        scenario: ExecutionScenario = ExecutionScenario.CONSERVATIVE,
        maker_fee: Decimal = DEFAULT_MAKER_FEE_RATE,
        taker_fee: Decimal = DEFAULT_TAKER_FEE_RATE,
        taker_slippage_bps: Decimal = DEFAULT_TAKER_SLIPPAGE_BPS,
        enable_partial_fills: bool = False,
        enable_bull_run_filter: bool = True,
        hourly_data: Optional[Dict[str, Any]] = None,
    ):
        self.book_spec = book_spec
        self.mode = mode
        self.capital_fraction = capital_fraction
        self.scenario = scenario
        self.enable_bull_run_filter = enable_bull_run_filter
        self.hourly_data = hourly_data or {}

        self.portfolio = PortfolioManager(
            initial_usdc_value=initial_usdc,
            initial_price=initial_price,
            max_drawdown_limit=max_drawdown_limit,
            min_amount_btc=book_spec.minimum_amount,
            min_value_usdc=book_spec.minimum_value,
        )

        self.fixed_btc_lot = self.portfolio.initial_btc

        self.simulator = ExecutionSimulator(
            book_spec=book_spec,
            scenario=scenario,
            maker_fee=maker_fee,
            taker_fee=taker_fee,
            taker_slippage_bps=taker_slippage_bps,
            enable_partial_fills=enable_partial_fills,
        )

        self.state: StrategyState = StrategyState.IDLE
        self.completed_trades: List[TradeRecord] = []
        self.active_order: Optional[Dict[str, Any]] = None
        self.trade_counter: int = 0
        self.canceled_sell_orders: int = 0

    def evaluate_entry_signal(self, row: Any) -> bool:
        """Evaluates entry signal on a closed candle: RSI>=65, ADX<20, SMA dev<5%."""
        if self.state != StrategyState.IDLE or self.portfolio.is_suspended:
            return False

        # Macro Bull Run Shield: block selling when macro bull run is active
        if self.enable_bull_run_filter and bool(row.get("bull_run_active", False)):
            return False

        rsi = Decimal(str(row["rsi_14"])) if not pd_isna(row.get("rsi_14")) else Decimal("0")
        adx = Decimal(str(row["adx_14"])) if not pd_isna(row.get("adx_14")) else Decimal("100")
        sma_dev = Decimal(str(row["sma_50_dev"])) if not pd_isna(row.get("sma_50_dev")) else Decimal("1.0")

        return (rsi >= RSI_ENTRY_THRESHOLD and adx < ADX_ENTRY_THRESHOLD and sma_dev < MAX_SMA_DEVIATION_PCT)

    def _get_hourly_candle(self, ts: Any) -> Optional[Any]:
        """Looks up an hourly candle by timestamp string or pandas Timestamp."""
        if not self.hourly_data:
            return None
        ts_str = str(ts)
        if ts_str in self.hourly_data:
            return self.hourly_data[ts_str]
        # Try formatted ISO string
        try:
            parsed = pd.to_datetime(ts, utc=True)
            iso = parsed.strftime("%Y-%m-%d %H:%M:%S+00:00")
            if iso in self.hourly_data:
                return self.hourly_data[iso]
        except Exception:
            pass
        return None

    def process_candle(self, idx: int, row: Any) -> Optional[TradeRecord]:
        """Processes closed candle sequentially with real portfolio ledger accounting."""
        close_price = Decimal(str(row["close"]))
        high_price = Decimal(str(row["high"]))
        low_price = Decimal(str(row["low"]))
        timestamp_str = str(row["timestamp"])
        regime = str(row.get("regime", "RANGE"))

        # Update mark-to-market portfolio valuation and check suspension
        self.portfolio.update_valuation_and_check_suspension(timestamp_str, idx, close_price)

        if self.portfolio.is_suspended and self.state == StrategyState.IDLE:
            return None

        # ----------------------------------------------------------------------
        # STATE 1: IDLE - Check for entry signal on closed candle
        # ----------------------------------------------------------------------
        if self.state == StrategyState.IDLE:
            if self.evaluate_entry_signal(row):
                sell_limit_price = BitsoPublicClient.quantize_price(close_price, self.book_spec.tick_size)

                if self.mode == SimulationMode.FIXED:
                    btc_to_sell = min(self.fixed_btc_lot, self.portfolio.btc_available)
                else:
                    btc_to_sell = BitsoPublicClient.quantize_btc(self.portfolio.btc_available * self.capital_fraction)

                quote_val = btc_to_sell * sell_limit_price
                valid, msg = BitsoPublicClient.validate_order_constraints(btc_to_sell, quote_val, self.book_spec)
                if not valid:
                    logger.warning(f"Order rejected by Bitso rules: {msg}")
                    return None

                if not self.portfolio.reserve_btc_for_sell(btc_to_sell):
                    return None

                self.state = StrategyState.PENDING_LIMIT_SELL
                self.active_order = {
                    "signal_idx": idx,
                    "signal_time": timestamp_str,
                    "sell_limit_price": sell_limit_price,
                    "order_btc": btc_to_sell,
                    "regime": regime,
                }
            return None

        # ----------------------------------------------------------------------
        # STATE 2: PENDING_LIMIT_SELL - Simulate Post-Only fill within 2h window
        # ----------------------------------------------------------------------
        elif self.state == StrategyState.PENDING_LIMIT_SELL:
            assert self.active_order is not None
            sell_price = self.active_order["sell_limit_price"]
            order_btc = self.active_order["order_btc"]

            # Look up high-resolution 1H candles for Hour 1 and Hour 2 if available
            h1 = None
            h2 = None
            if self.hourly_data:
                try:
                    t_start = pd.to_datetime(timestamp_str, utc=True)
                    t_h1 = t_start.strftime("%Y-%m-%d %H:%M:%S+00:00")
                    t_h2 = (t_start + pd.Timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S+00:00")
                    h1 = self._get_hourly_candle(t_h1)
                    h2 = self._get_hourly_candle(t_h2)
                except Exception as e:
                    logger.debug(f"Hourly lookup failed: {e}")

            fill_res: MakerSellFillResult = self.simulator.evaluate_post_only_sell(
                order_btc, sell_price, row, h1_candle=h1, h2_candle=h2
            )

            if fill_res.status == FillStatus.FULL_FILL:
                self.portfolio.execute_sell_fill(fill_res.filled_btc, fill_res.net_usdc)

                target_buy_price = BitsoPublicClient.quantize_price(
                    sell_price * (Decimal("1.0") - BUYBACK_TARGET_DISCOUNT),
                    self.book_spec.tick_size
                )
                defensive_stop_price = BitsoPublicClient.quantize_price(
                    sell_price * (Decimal("1.0") + DEFENSIVE_STOP_PREMIUM),
                    self.book_spec.tick_size
                )

                self.portfolio.reserve_usdc_for_buyback(fill_res.net_usdc)

                self.state = StrategyState.IN_POSITION_AWAITING_BUYBACK
                self.active_order.update({
                    "entry_candle_idx": idx,
                    "entry_time": timestamp_str,
                    "actual_btc_sold": fill_res.filled_btc,
                    "gross_usdc": fill_res.gross_usdc,
                    "net_usdc": fill_res.net_usdc,
                    "maker_fee_sell_usdc": fill_res.fee_usdc,
                    "target_buy_price": target_buy_price,
                    "defensive_stop_price": defensive_stop_price,
                    "candles_held": 0,
                })
            else:
                # Expired, rejected post-only crossing, touch-only, or uncertain
                self.portfolio.cancel_reserved_btc(order_btc)
                self.canceled_sell_orders += 1
                self.state = StrategyState.IDLE
                self.active_order = None
            return None

        # ----------------------------------------------------------------------
        # STATE 3: IN_POSITION_AWAITING_BUYBACK - Manage Exit Conditions
        # ----------------------------------------------------------------------
        elif self.state == StrategyState.IN_POSITION_AWAITING_BUYBACK:
            assert self.active_order is not None
            self.active_order["candles_held"] += 1
            candles_held = self.active_order["candles_held"]

            target_price = self.active_order["target_buy_price"]
            defensive_price = self.active_order["defensive_stop_price"]
            net_usdc_allocated = self.active_order["net_usdc"]
            btc_sold = self.active_order["actual_btc_sold"]
            sell_price = self.active_order["sell_limit_price"]
            regime = self.active_order["regime"]
            entry_time = self.active_order["entry_time"]
            entry_idx = self.active_order["entry_candle_idx"]

            buyback_res: Optional[BuybackFillResult] = None
            exit_reason: Optional[ExitReason] = None

            hit_target = low_price <= target_price
            hit_defensive = high_price >= defensive_price

            # V1.3 Intravela & Conservative Resolution for Contradictory Exits
            if hit_target and hit_defensive:
                # Attempt high-resolution intravela sequence check using 1H data
                intravela_resolved = False
                if self.hourly_data:
                    try:
                        t_base = pd.to_datetime(timestamp_str, utc=True)
                        target_hour = None
                        defensive_hour = None
                        for h_offset in range(4):
                            t_h = (t_base + pd.Timedelta(hours=h_offset)).strftime("%Y-%m-%d %H:%M:%S+00:00")
                            h_candle = self._get_hourly_candle(t_h)
                            if h_candle is not None:
                                h_low = Decimal(str(h_candle["low"]))
                                h_high = Decimal(str(h_candle["high"]))
                                if target_hour is None and h_low <= target_price:
                                    target_hour = h_offset
                                if defensive_hour is None and h_high >= defensive_price:
                                    defensive_hour = h_offset

                        if target_hour is not None and defensive_hour is not None:
                            if target_hour < defensive_hour:
                                exit_reason = ExitReason.TARGET_BUYBACK
                                buyback_res = self.simulator.execute_target_buyback(net_usdc_allocated, target_price)
                                intravela_resolved = True
                            elif defensive_hour < target_hour:
                                exit_reason = ExitReason.DEFENSIVE_STOP
                                buyback_res = self.simulator.execute_defensive_stop(net_usdc_allocated, defensive_price)
                                intravela_resolved = True
                    except Exception as e:
                        logger.debug(f"Intravela check failed: {e}")

                if not intravela_resolved:
                    # Both in same hour or missing intravela data -> Conservative worst-case principle
                    exit_reason = ExitReason.CONTRADICTORY_DEFENSIVE
                    buyback_res = self.simulator.execute_defensive_stop(net_usdc_allocated, defensive_price)

            elif hit_defensive:
                exit_reason = ExitReason.DEFENSIVE_STOP
                buyback_res = self.simulator.execute_defensive_stop(net_usdc_allocated, defensive_price)
            elif hit_target:
                exit_reason = ExitReason.TARGET_BUYBACK
                buyback_res = self.simulator.execute_target_buyback(net_usdc_allocated, target_price)
            elif candles_held >= MAX_HOLDING_CANDLES_4H:
                exit_reason = ExitReason.TIME_STOP
                buyback_res = self.simulator.execute_time_stop(net_usdc_allocated, close_price)

            if exit_reason is not None and buyback_res is not None:
                self.portfolio.execute_buyback_fill(buyback_res.spent_usdc, buyback_res.net_btc_acquired)

                net_btc_pnl = buyback_res.net_btc_acquired - btc_sold
                net_satoshis = int(net_btc_pnl * SATOSHIS_PER_BTC)

                total_btc_eq = self.portfolio.get_total_btc_equity(close_price)

                self.trade_counter += 1
                record = TradeRecord(
                    trade_id=self.trade_counter,
                    mode=self.mode,
                    entry_candle_idx=entry_idx,
                    entry_time=entry_time,
                    exit_candle_idx=idx,
                    exit_time=timestamp_str,
                    regime=regime,
                    sell_price=sell_price,
                    buyback_price=buyback_res.fill_price,
                    btc_sold=btc_sold,
                    btc_bought=buyback_res.net_btc_acquired,
                    net_satoshis_pnl=net_satoshis,
                    net_btc_pnl=net_btc_pnl,
                    usdc_proceeds_gross=self.active_order["gross_usdc"],
                    usdc_proceeds_net=self.active_order["net_usdc"],
                    maker_fee_sell_usdc=self.active_order["maker_fee_sell_usdc"],
                    buyback_fee_usdc=buyback_res.fee_usdc,
                    exit_reason=exit_reason,
                    holding_hours=candles_held * 4,
                    maker_sell=True,
                    maker_buy=buyback_res.is_maker,
                    slippage_paid_usdc=buyback_res.slippage_paid_usdc,
                    portfolio_btc_after_trade=self.portfolio.btc_available,
                    portfolio_equity_btc=total_btc_eq,
                )

                self.completed_trades.append(record)
                self.state = StrategyState.IDLE
                self.active_order = None
                return record

        return None


def pd_isna(val: Any) -> bool:
    try:
        import math
        return val is None or (isinstance(val, (float, int)) and math.isnan(val))
    except Exception:
        return False
