"""
btc_accumulator/execution_simulator.py
Microstructural exchange execution simulator for Bitso Alpha (V1.3).
Evaluates execution against high-resolution 1-hour candles covering the exact 2-hour validity window.
Eliminates arbitrary partial fill assumptions (e.g., 50%).
Supports dual scenarios: Conservative (unconfirmed marked as uncertain/unfilled) vs Optimistic.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import logging
from typing import Tuple, Optional, Any, List

from btc_accumulator.config import (
    DEFAULT_MAKER_FEE_RATE,
    DEFAULT_TAKER_FEE_RATE,
    DEFAULT_TAKER_SLIPPAGE_BPS,
)
from btc_accumulator.bitso_client import BookSpecification, BitsoPublicClient

logger = logging.getLogger(__name__)


class ExecutionScenario(str, Enum):
    CONSERVATIVE = "CONSERVATIVE"
    OPTIMISTIC = "OPTIMISTIC"


class FillStatus(str, Enum):
    FULL_FILL = "FULL_FILL"
    PARTIAL_FILL = "PARTIAL_FILL"          # Retained for enum compatibility; not used in V1.3
    EXPIRED_UNFILLED = "EXPIRED_UNFILLED"
    EXPIRED_TOUCH_ONLY = "EXPIRED_TOUCH_ONLY"
    REJECTED_POST_ONLY_CROSS = "REJECTED_POST_ONLY_CROSS"
    UNCERTAIN_NO_FILL = "UNCERTAIN_NO_FILL"


@dataclass
class MakerSellFillResult:
    status: FillStatus
    filled_btc: Decimal
    fill_price: Decimal
    gross_usdc: Decimal
    fee_usdc: Decimal
    net_usdc: Decimal
    is_maker: bool
    explanation: str


@dataclass
class BuybackFillResult:
    fill_price: Decimal
    spent_usdc: Decimal
    fee_usdc: Decimal
    net_btc_acquired: Decimal
    is_maker: bool
    slippage_paid_usdc: Decimal
    explanation: str


class ExecutionSimulator:
    """
    Simulates exchange order matching using high-resolution data and dual scenarios.
    """

    def __init__(
        self,
        book_spec: BookSpecification,
        scenario: ExecutionScenario = ExecutionScenario.CONSERVATIVE,
        maker_fee: Decimal = DEFAULT_MAKER_FEE_RATE,
        taker_fee: Decimal = DEFAULT_TAKER_FEE_RATE,
        taker_slippage_bps: Decimal = DEFAULT_TAKER_SLIPPAGE_BPS,
        enable_partial_fills: bool = False,  # Deprecated in V1.3: arbitrary partial fills eliminated
    ):
        self.book_spec = book_spec
        self.scenario = scenario
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.taker_slippage_bps = taker_slippage_bps
        self.enable_partial_fills = enable_partial_fills

    def evaluate_post_only_sell_2h(
        self,
        order_btc: Decimal,
        limit_price: Decimal,
        h1_candle: Optional[Any],
        h2_candle: Optional[Any],
    ) -> MakerSellFillResult:
        """
        Evaluates a post-only limit sell within the exact 2-hour window using Hour 1 and Hour 2 candles.
        Eliminates arbitrary partial fills; unconfirmed executions are marked as uncertain.
        """
        tick_size = self.book_spec.tick_size

        # If high-resolution 1h data is missing for these hours, handle conservatively
        if h1_candle is None or h2_candle is None:
            if self.scenario == ExecutionScenario.OPTIMISTIC:
                # If optimistic and no 1h data, mark uncertain
                pass
            return MakerSellFillResult(
                status=FillStatus.UNCERTAIN_NO_FILL,
                filled_btc=Decimal("0.00000000"),
                fill_price=limit_price,
                gross_usdc=Decimal("0.00000000"),
                fee_usdc=Decimal("0.00000000"),
                net_usdc=Decimal("0.00000000"),
                is_maker=False,
                explanation="Missing high-resolution hourly data for the 2-hour window. Marked as uncertain/unfilled."
            )

        h1_open = Decimal(str(h1_candle["open"]))
        h1_high = Decimal(str(h1_candle["high"]))
        h2_high = Decimal(str(h2_candle["high"]))
        max_2h_high = max(h1_high, h2_high)
        
        # Volume extraction (handle DataFrame row or dict)
        h1_vol = Decimal(str(h1_candle.get("volume", 0) if isinstance(h1_candle, dict) else getattr(h1_candle, "volume", 0)))
        h2_vol = Decimal(str(h2_candle.get("volume", 0) if isinstance(h2_candle, dict) else getattr(h2_candle, "volume", 0)))
        total_2h_vol = h1_vol + h2_vol

        # Rule 1: Post-Only Rejection
        # If the market opens above limit price at the start of Hour 1, post-only order would cross as taker -> REJECTED
        if h1_open > limit_price:
            return MakerSellFillResult(
                status=FillStatus.REJECTED_POST_ONLY_CROSS,
                filled_btc=Decimal("0.00000000"),
                fill_price=limit_price,
                gross_usdc=Decimal("0.00000000"),
                fee_usdc=Decimal("0.00000000"),
                net_usdc=Decimal("0.00000000"),
                is_maker=False,
                explanation=f"Open of Hour 1 ({h1_open}) > Limit Price ({limit_price}): Post-only order rejected (would cross book as taker)."
            )

        # Rule 2: 2-Hour Expiration Check
        # If price never reached limit_price during Hour 1 or Hour 2, it is definitely expired at 2 hours
        if max_2h_high < limit_price:
            return MakerSellFillResult(
                status=FillStatus.EXPIRED_UNFILLED,
                filled_btc=Decimal("0.00000000"),
                fill_price=limit_price,
                gross_usdc=Decimal("0.00000000"),
                fee_usdc=Decimal("0.00000000"),
                net_usdc=Decimal("0.00000000"),
                is_maker=True,
                explanation=f"2-hour window expired: Max high in 2h ({max_2h_high}) < Limit Price ({limit_price})."
            )

        # Rule 3: Touch-Only Check
        if max_2h_high == limit_price:
            if self.scenario == ExecutionScenario.OPTIMISTIC:
                filled_btc = order_btc
                gross_usdc = filled_btc * limit_price
                fee_usdc = gross_usdc * self.maker_fee
                net_usdc = gross_usdc - fee_usdc
                return MakerSellFillResult(
                    status=FillStatus.FULL_FILL,
                    filled_btc=filled_btc,
                    fill_price=limit_price,
                    gross_usdc=gross_usdc,
                    fee_usdc=fee_usdc,
                    net_usdc=net_usdc,
                    is_maker=True,
                    explanation="Optimistic scenario: touch at exact limit price assumed filled."
                )
            else:
                # Conservative rule: Touch-only at absolute high sits at the back of the queue -> UNCERTAIN / EXPIRED
                return MakerSellFillResult(
                    status=FillStatus.EXPIRED_TOUCH_ONLY,
                    filled_btc=Decimal("0.00000000"),
                    fill_price=limit_price,
                    gross_usdc=Decimal("0.00000000"),
                    fee_usdc=Decimal("0.00000000"),
                    net_usdc=Decimal("0.00000000"),
                    is_maker=True,
                    explanation="Conservative scenario: Touch-only without penetration. Queue priority unconfirmed -> expired."
                )

        # Rule 4: Solid Penetration through limit order (High >= limit_price + 1 tick)
        if max_2h_high >= (limit_price + tick_size):
            if self.scenario == ExecutionScenario.CONSERVATIVE and total_2h_vol > 0 and total_2h_vol < order_btc:
                return MakerSellFillResult(
                    status=FillStatus.UNCERTAIN_NO_FILL,
                    filled_btc=Decimal("0.00000000"),
                    fill_price=limit_price,
                    gross_usdc=Decimal("0.00000000"),
                    fee_usdc=Decimal("0.00000000"),
                    net_usdc=Decimal("0.00000000"),
                    is_maker=False,
                    explanation=f"Conservative scenario: Volume in 2h window ({total_2h_vol} BTC) insufficient for order ({order_btc} BTC)."
                )

            filled_btc = order_btc
            gross_usdc = filled_btc * limit_price
            fee_usdc = gross_usdc * self.maker_fee
            net_usdc = gross_usdc - fee_usdc
            return MakerSellFillResult(
                status=FillStatus.FULL_FILL,
                filled_btc=filled_btc,
                fill_price=limit_price,
                gross_usdc=gross_usdc,
                fee_usdc=fee_usdc,
                net_usdc=net_usdc,
                is_maker=True,
                explanation=f"Traded through (+{max_2h_high - limit_price} USD): 100% filled as Maker within 2 hours."
            )

        return MakerSellFillResult(
            status=FillStatus.EXPIRED_UNFILLED,
            filled_btc=Decimal("0.00000000"),
            fill_price=limit_price,
            gross_usdc=Decimal("0.00000000"),
            fee_usdc=Decimal("0.00000000"),
            net_usdc=Decimal("0.00000000"),
            is_maker=True,
            explanation="Order expired unfilled within 2 hours."
        )

    def evaluate_post_only_sell(
        self,
        order_btc: Decimal,
        limit_price: Decimal,
        candle: Any,
        h1_candle: Optional[Any] = None,
        h2_candle: Optional[Any] = None,
    ) -> MakerSellFillResult:
        """
        Evaluates post-only sell. If high-resolution h1 and h2 candles are provided,
        uses exact 2-hour window. Otherwise falls back to candle-level logic with scenario guardrails.
        """
        if h1_candle is not None and h2_candle is not None:
            return self.evaluate_post_only_sell_2h(order_btc, limit_price, h1_candle, h2_candle)

        tick_size = self.book_spec.tick_size
        candle_open = Decimal(str(candle["open"]))
        candle_high = Decimal(str(candle["high"]))

        # 1. Post-only rejection: Open > limit price
        if candle_open > limit_price:
            return MakerSellFillResult(
                status=FillStatus.REJECTED_POST_ONLY_CROSS,
                filled_btc=Decimal("0.00000000"),
                fill_price=limit_price,
                gross_usdc=Decimal("0.00000000"),
                fee_usdc=Decimal("0.00000000"),
                net_usdc=Decimal("0.00000000"),
                is_maker=False,
                explanation="Open > Limit Price: Post-only order rejected (crosses as taker)."
            )

        # 2. Never reached limit price
        if candle_high < limit_price:
            return MakerSellFillResult(
                status=FillStatus.EXPIRED_UNFILLED,
                filled_btc=Decimal("0.00000000"),
                fill_price=limit_price,
                gross_usdc=Decimal("0.00000000"),
                fee_usdc=Decimal("0.00000000"),
                net_usdc=Decimal("0.00000000"),
                is_maker=True,
                explanation="High < Limit Price: Order expired unfilled."
            )

        # 3. Touch-only
        if candle_high == limit_price:
            if self.scenario == ExecutionScenario.OPTIMISTIC:
                filled_btc = order_btc
                gross_usdc = filled_btc * limit_price
                fee_usdc = gross_usdc * self.maker_fee
                net_usdc = gross_usdc - fee_usdc
                return MakerSellFillResult(
                    status=FillStatus.FULL_FILL,
                    filled_btc=filled_btc,
                    fill_price=limit_price,
                    gross_usdc=gross_usdc,
                    fee_usdc=fee_usdc,
                    net_usdc=net_usdc,
                    is_maker=True,
                    explanation="Optimistic scenario: Touch-only assumed filled."
                )
            else:
                return MakerSellFillResult(
                    status=FillStatus.EXPIRED_TOUCH_ONLY,
                    filled_btc=Decimal("0.00000000"),
                    fill_price=limit_price,
                    gross_usdc=Decimal("0.00000000"),
                    fee_usdc=Decimal("0.00000000"),
                    net_usdc=Decimal("0.00000000"),
                    is_maker=True,
                    explanation="Conservative scenario: Touch-only without penetration -> queue priority failure."
                )

        # 4. Traded through
        if candle_high >= (limit_price + tick_size):
            filled_btc = order_btc
            gross_usdc = filled_btc * limit_price
            fee_usdc = gross_usdc * self.maker_fee
            net_usdc = gross_usdc - fee_usdc
            return MakerSellFillResult(
                status=FillStatus.FULL_FILL,
                filled_btc=filled_btc,
                fill_price=limit_price,
                gross_usdc=gross_usdc,
                fee_usdc=fee_usdc,
                net_usdc=net_usdc,
                is_maker=True,
                explanation=f"Traded through (+{candle_high - limit_price} USD): Filled as Maker."
            )

        return MakerSellFillResult(
            status=FillStatus.EXPIRED_UNFILLED,
            filled_btc=Decimal("0.00000000"),
            fill_price=limit_price,
            gross_usdc=Decimal("0.00000000"),
            fee_usdc=Decimal("0.00000000"),
            net_usdc=Decimal("0.00000000"),
            is_maker=True,
            explanation="Order expired unfilled."
        )

    def execute_target_buyback(
        self,
        usdc_budget: Decimal,
        target_price: Decimal,
    ) -> BuybackFillResult:
        """Executes maker limit buyback at the 2.5% discount target without premature fee rounding."""
        fee_usdc = usdc_budget * self.maker_fee
        usdc_for_btc = usdc_budget - fee_usdc
        raw_btc = usdc_for_btc / target_price
        btc_acquired = BitsoPublicClient.quantize_btc(raw_btc)

        return BuybackFillResult(
            fill_price=target_price,
            spent_usdc=usdc_budget,
            fee_usdc=fee_usdc,
            net_btc_acquired=btc_acquired,
            is_maker=True,
            slippage_paid_usdc=Decimal("0.00000000"),
            explanation="Target hit (-2.5%): Maker Limit Buy filled."
        )

    def execute_defensive_stop(
        self,
        usdc_budget: Decimal,
        stop_trigger_price: Decimal,
    ) -> BuybackFillResult:
        """Executes defensive emergency buyback (+3% stop) as Taker with slippage."""
        slippage_factor = Decimal("1.0") + self.taker_slippage_bps
        effective_price = BitsoPublicClient.quantize_price(
            stop_trigger_price * slippage_factor, self.book_spec.tick_size
        )

        fee_usdc = usdc_budget * self.taker_fee
        usdc_for_btc = usdc_budget - fee_usdc
        raw_btc = usdc_for_btc / effective_price
        btc_acquired = BitsoPublicClient.quantize_btc(raw_btc)

        slippage_paid = (effective_price - stop_trigger_price) * (usdc_budget / effective_price)

        return BuybackFillResult(
            fill_price=effective_price,
            spent_usdc=usdc_budget,
            fee_usdc=fee_usdc,
            net_btc_acquired=btc_acquired,
            is_maker=False,
            slippage_paid_usdc=slippage_paid,
            explanation="Defensive stop triggered (+3.0%): Taker buyback executed with slippage."
        )

    def execute_time_stop(
        self,
        usdc_budget: Decimal,
        close_price: Decimal,
    ) -> BuybackFillResult:
        """Executes 7-day timeout market exit as Taker with slippage."""
        slippage_factor = Decimal("1.0") + self.taker_slippage_bps
        effective_price = BitsoPublicClient.quantize_price(
            close_price * slippage_factor, self.book_spec.tick_size
        )

        fee_usdc = usdc_budget * self.taker_fee
        usdc_for_btc = usdc_budget - fee_usdc
        raw_btc = usdc_for_btc / effective_price
        btc_acquired = BitsoPublicClient.quantize_btc(raw_btc)

        slippage_paid = (effective_price - close_price) * (usdc_budget / effective_price)

        return BuybackFillResult(
            fill_price=effective_price,
            spent_usdc=usdc_budget,
            fee_usdc=fee_usdc,
            net_btc_acquired=btc_acquired,
            is_maker=False,
            slippage_paid_usdc=slippage_paid,
            explanation="7-day time stop reached: Taker market buyback executed with slippage."
        )
