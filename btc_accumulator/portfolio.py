"""
btc_accumulator/portfolio.py
Real portfolio accounting engine for BTC and USDC (V1.2).
Differentiates between:
1. Drawdown por operaciones cerradas (Realized Drawdown)
2. Drawdown de patrimonio total marcado a mercado (Mark-to-Market / Equity Drawdown)
Uses Mark-to-Market Equity Drawdown for the 5% suspension rule.
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from enum import Enum
import logging
from typing import Optional, List, Dict, Any

from btc_accumulator.config import (
    BTC_USD_MIN_AMOUNT,
    BTC_USD_MIN_VALUE,
    SATOSHIS_PER_BTC,
)

logger = logging.getLogger(__name__)


class SuspensionReason(str, Enum):
    NONE = "NONE"
    MINIMUM_ORDER_VIOLATION = "MINIMUM_ORDER_VIOLATION"
    MAX_DRAWDOWN_LIMIT_REACHED = "MAX_DRAWDOWN_LIMIT_REACHED"


@dataclass
class BalanceSnapshot:
    """Historical point-in-time portfolio ledger snapshot."""
    timestamp: str
    candle_idx: int
    btc_available: Decimal
    btc_reserved: Decimal
    usdc_available: Decimal
    usdc_reserved: Decimal
    total_btc_equity: Decimal
    total_usdc_valuation: Decimal
    current_price: Decimal
    mtm_drawdown_btc: Decimal
    mtm_drawdown_pct: float
    realized_drawdown_pct: float
    is_suspended: bool
    suspension_reason: SuspensionReason


class PortfolioManager:
    """
    Institutional portfolio accounting engine.
    Strictly forbids selling more BTC than available and buying more BTC than available USDC.
    """

    def __init__(
        self,
        initial_usdc_value: Decimal = Decimal("10.00"),
        initial_price: Decimal = Decimal("47000.00"),
        max_drawdown_limit: Decimal = Decimal("0.05"),  # 5% max drawdown suspension rule
        min_amount_btc: Decimal = BTC_USD_MIN_AMOUNT,   # 0.00000060 BTC
        min_value_usdc: Decimal = BTC_USD_MIN_VALUE,    # 0.50 USD/USDC
    ):
        self.initial_usdc_value = initial_usdc_value
        self.initial_price = initial_price
        self.max_drawdown_limit = max_drawdown_limit
        self.min_amount_btc = min_amount_btc
        self.min_value_usdc = min_value_usdc

        raw_initial_btc = initial_usdc_value / initial_price
        self.initial_btc = raw_initial_btc.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)

        # Ledger balances
        self.btc_available: Decimal = self.initial_btc
        self.btc_reserved: Decimal = Decimal("0.00000000")
        self.usdc_available: Decimal = Decimal("0.00000000")
        self.usdc_reserved: Decimal = Decimal("0.00000000")

        # Mark-to-Market Equity Tracking
        self.peak_mtm_btc_equity: Decimal = self.initial_btc
        self.max_mtm_drawdown_btc: Decimal = Decimal("0.00000000")
        self.max_mtm_drawdown_pct: float = 0.0

        # Realized (Closed Trades) Tracking
        self.peak_realized_btc: Decimal = self.initial_btc
        self.max_realized_drawdown_btc: Decimal = Decimal("0.00000000")
        self.max_realized_drawdown_pct: float = 0.0

        # Operational status
        self.is_suspended: bool = False
        self.suspension_reason: SuspensionReason = SuspensionReason.NONE

        self.snapshots: List[BalanceSnapshot] = []

    @property
    def total_btc_balance(self) -> Decimal:
        return self.btc_available + self.btc_reserved

    @property
    def total_usdc_balance(self) -> Decimal:
        return self.usdc_available + self.usdc_reserved

    def get_total_btc_equity(self, current_price: Decimal) -> Decimal:
        """Total marked-to-market net worth in BTC, valuing USDC at current price."""
        if current_price <= 0:
            return self.total_btc_balance
        usdc_in_btc = (self.total_usdc_balance / current_price).quantize(
            Decimal("0.00000001"), rounding=ROUND_DOWN
        )
        return self.total_btc_balance + usdc_in_btc

    def update_valuation_and_check_suspension(
        self,
        timestamp: str,
        candle_idx: int,
        current_price: Decimal
    ) -> BalanceSnapshot:
        """
        Updates portfolio equity, tracks both MtM and Realized drawdowns,
        and enforces the 5% MtM suspension rule.
        """
        total_btc_equity = self.get_total_btc_equity(current_price)
        total_usdc_val = total_btc_equity * current_price

        # 1. Mark-to-Market Drawdown Tracking
        if total_btc_equity > self.peak_mtm_btc_equity:
            self.peak_mtm_btc_equity = total_btc_equity

        mtm_dd_btc = self.peak_mtm_btc_equity - total_btc_equity
        if mtm_dd_btc > self.max_mtm_drawdown_btc:
            self.max_mtm_drawdown_btc = mtm_dd_btc

        mtm_dd_pct = float(mtm_dd_btc / self.peak_mtm_btc_equity) * 100.0 if self.peak_mtm_btc_equity > 0 else 0.0
        if mtm_dd_pct > self.max_mtm_drawdown_pct:
            self.max_mtm_drawdown_pct = mtm_dd_pct

        # 2. Realized Drawdown Tracking (based on closed inventory when no active trade)
        if self.btc_reserved == Decimal("0") and self.usdc_reserved == Decimal("0"):
            current_realized = self.btc_available
            if current_realized > self.peak_realized_btc:
                self.peak_realized_btc = current_realized
            realized_dd_btc = self.peak_realized_btc - current_realized
            if realized_dd_btc > self.max_realized_drawdown_btc:
                self.max_realized_drawdown_btc = realized_dd_btc
            realized_dd_pct = float(realized_dd_btc / self.peak_realized_btc) * 100.0 if self.peak_realized_btc > 0 else 0.0
            if realized_dd_pct > self.max_realized_drawdown_pct:
                self.max_realized_drawdown_pct = realized_dd_pct
        else:
            realized_dd_pct = self.max_realized_drawdown_pct

        # Suspension Rule 1: Mark-to-Market Equity Drawdown >= limit (5%)
        if not self.is_suspended and (Decimal(str(mtm_dd_pct / 100.0)) >= self.max_drawdown_limit):
            self.is_suspended = True
            self.suspension_reason = SuspensionReason.MAX_DRAWDOWN_LIMIT_REACHED
            logger.warning(
                f"SUSPENSION TRIGGERED at {timestamp}: MtM Drawdown {mtm_dd_pct:.2f}% "
                f"exceeded configured limit {float(self.max_drawdown_limit)*100:.1f}%."
            )

        # Suspension Rule 2: Minimum Exchange Constraints
        if not self.is_suspended:
            if total_btc_equity < self.min_amount_btc or total_usdc_val < self.min_value_usdc:
                self.is_suspended = True
                self.suspension_reason = SuspensionReason.MINIMUM_ORDER_VIOLATION
                logger.warning(
                    f"SUSPENSION TRIGGERED at {timestamp}: Portfolio equity ({total_btc_equity} BTC / "
                    f"${total_usdc_val:.2f}) fell below Bitso minimum permitted order size."
                )

        snapshot = BalanceSnapshot(
            timestamp=timestamp,
            candle_idx=candle_idx,
            btc_available=self.btc_available,
            btc_reserved=self.btc_reserved,
            usdc_available=self.usdc_available,
            usdc_reserved=self.usdc_reserved,
            total_btc_equity=total_btc_equity,
            total_usdc_valuation=total_usdc_val,
            current_price=current_price,
            mtm_drawdown_btc=mtm_dd_btc,
            mtm_drawdown_pct=mtm_dd_pct,
            realized_drawdown_pct=realized_dd_pct,
            is_suspended=self.is_suspended,
            suspension_reason=self.suspension_reason,
        )
        self.snapshots.append(snapshot)
        return snapshot

    def reserve_btc_for_sell(self, btc_amount: Decimal) -> bool:
        if self.is_suspended or btc_amount <= Decimal("0"):
            return False
        if btc_amount > self.btc_available:
            logger.error(
                f"OVERDRAFT PREVENTED: Requested {btc_amount} BTC, but only {self.btc_available} BTC available."
            )
            return False
        self.btc_available -= btc_amount
        self.btc_reserved += btc_amount
        return True

    def cancel_reserved_btc(self, btc_amount: Decimal) -> None:
        release_amount = min(btc_amount, self.btc_reserved)
        self.btc_reserved -= release_amount
        self.btc_available += release_amount

    def execute_sell_fill(self, btc_amount: Decimal, net_usdc_proceeds: Decimal) -> None:
        assert btc_amount <= self.btc_reserved + Decimal("0.00000001"), "Cannot fill more BTC than reserved"
        self.btc_reserved -= btc_amount
        self.usdc_available += net_usdc_proceeds

    def reserve_usdc_for_buyback(self, usdc_amount: Decimal) -> bool:
        if usdc_amount <= Decimal("0") or usdc_amount > self.usdc_available:
            return False
        self.usdc_available -= usdc_amount
        self.usdc_reserved += usdc_amount
        return True

    def cancel_reserved_usdc(self, usdc_amount: Decimal) -> None:
        release_amount = min(usdc_amount, self.usdc_reserved)
        self.usdc_reserved -= release_amount
        self.usdc_available += release_amount

    def execute_buyback_fill(self, usdc_spent: Decimal, net_btc_acquired: Decimal) -> None:
        assert usdc_spent <= self.usdc_reserved + Decimal("0.0001"), "Cannot spend more USDC than reserved"
        self.usdc_reserved -= usdc_spent
        self.btc_available += net_btc_acquired
        # Update realized peak
        if self.btc_available > self.peak_realized_btc:
            self.peak_realized_btc = self.btc_available
