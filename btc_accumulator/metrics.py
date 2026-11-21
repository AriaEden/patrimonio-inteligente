"""
btc_accumulator/metrics.py
Quantitative metrics engine for BTC-Accumulator V1.2.
Differentiates explicitly between:
- Drawdown de operaciones cerradas (Realized Drawdown)
- Drawdown de patrimonio total marcado a mercado (Mark-to-Market / Equity Drawdown)
Accurately reports independent trade counts and exact unrounded fees.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Dict, Any, Optional

from btc_accumulator.strategy import TradeRecord, ExitReason, SimulationMode
from btc_accumulator.config import SATOSHIS_PER_BTC


@dataclass
class RegimeStats:
    regime: str
    trade_count: int
    wins: int
    losses: int
    win_rate_pct: float
    net_satoshis: int
    net_btc: Decimal
    gross_usdc_vol: Decimal


@dataclass
class SequenceAnalysis:
    max_consecutive_wins: int
    max_consecutive_losses: int
    compounding_drag_satoshis: int
    compounding_drag_note: str


@dataclass
class StrategyMetrics:
    mode_name: str
    initial_btc: Decimal
    final_btc: Decimal
    hodl_btc: Decimal
    net_satoshis_pnl: int
    net_btc_pnl: Decimal
    return_pct_btc: float
    outperformance_btc: Decimal
    outperformance_pct: float
    
    initial_usdc_val: Decimal
    final_usdc_val: Decimal
    hodl_usdc_val: Decimal
    
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    profit_factor: float
    avg_win_satoshis: float
    avg_loss_satoshis: float
    
    # Dual Drawdown reporting
    realized_max_drawdown_btc: Decimal
    realized_max_drawdown_pct: float
    mtm_max_drawdown_btc: Decimal
    mtm_max_drawdown_pct: float
    
    total_fees_usdc: Decimal
    total_slippage_usdc: Decimal
    canceled_orders_count: int
    
    target_exits: int
    defensive_exits: int
    time_stop_exits: int
    
    is_suspended: bool
    suspension_reason: str
    
    regime_breakdown: Dict[str, RegimeStats] = field(default_factory=dict)
    sequence_analysis: Optional[SequenceAnalysis] = None
    sample_size_reliable: bool = False
    sample_size_caveat: str = ""


def compute_comprehensive_metrics(
    mode_name: str,
    trades: List[TradeRecord],
    initial_btc: Decimal,
    final_btc_equity: Decimal,
    start_price: Decimal,
    end_price: Decimal,
    mtm_max_drawdown_btc: Decimal = Decimal("0.0"),
    mtm_max_drawdown_pct: float = 0.0,
    is_suspended: bool = False,
    suspension_reason: str = "NONE",
    canceled_orders_count: int = 0,
) -> StrategyMetrics:
    """Computes comprehensive quantitative performance metrics for a specific simulation mode."""
    total_trades = len(trades)
    hodl_btc = initial_btc

    net_btc_pnl = final_btc_equity - initial_btc
    net_satoshis_pnl = int(net_btc_pnl * SATOSHIS_PER_BTC)
    return_pct_btc = float(net_btc_pnl / initial_btc) * 100.0 if initial_btc > 0 else 0.0

    outperformance_btc = final_btc_equity - hodl_btc
    outperformance_pct = float(outperformance_btc / hodl_btc) * 100.0 if hodl_btc > 0 else 0.0

    if total_trades == 0:
        return StrategyMetrics(
            mode_name=mode_name,
            initial_btc=initial_btc,
            final_btc=final_btc_equity,
            hodl_btc=hodl_btc,
            net_satoshis_pnl=0,
            net_btc_pnl=Decimal("0.0"),
            return_pct_btc=0.0,
            outperformance_btc=Decimal("0.0"),
            outperformance_pct=0.0,
            initial_usdc_val=initial_btc * start_price,
            final_usdc_val=final_btc_equity * end_price,
            hodl_usdc_val=hodl_btc * end_price,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate_pct=0.0,
            profit_factor=0.0,
            avg_win_satoshis=0.0,
            avg_loss_satoshis=0.0,
            realized_max_drawdown_btc=Decimal("0.0"),
            realized_max_drawdown_pct=0.0,
            mtm_max_drawdown_btc=mtm_max_drawdown_btc,
            mtm_max_drawdown_pct=mtm_max_drawdown_pct,
            total_fees_usdc=Decimal("0.0"),
            total_slippage_usdc=Decimal("0.0"),
            canceled_orders_count=canceled_orders_count,
            target_exits=0,
            defensive_exits=0,
            time_stop_exits=0,
            is_suspended=is_suspended,
            suspension_reason=suspension_reason,
            regime_breakdown={},
            sample_size_reliable=False,
            sample_size_caveat="N=0: Sin operaciones realizadas."
        )

    wins = [t for t in trades if t.net_satoshis_pnl > 0]
    losses = [t for t in trades if t.net_satoshis_pnl < 0]
    winning_count = len(wins)
    losing_count = len(losses)
    win_rate = (winning_count / total_trades) * 100.0

    total_won_sats = sum(t.net_satoshis_pnl for t in wins)
    total_lost_sats = abs(sum(t.net_satoshis_pnl for t in losses))

    profit_factor = (float(total_won_sats) / float(total_lost_sats)) if total_lost_sats > 0 else (
        float("inf") if total_won_sats > 0 else 1.0
    )

    avg_win_sats = float(total_won_sats) / len(wins) if wins else 0.0
    avg_loss_sats = float(total_lost_sats) / len(losses) if losses else 0.0

    # Realized (closed trades) drawdown
    cumulative_btc = initial_btc
    peak_closed_btc = initial_btc
    max_closed_dd_btc = Decimal("0.0")
    max_closed_dd_pct = 0.0

    for t in trades:
        cumulative_btc += t.net_btc_pnl
        if cumulative_btc > peak_closed_btc:
            peak_closed_btc = cumulative_btc
        dd = peak_closed_btc - cumulative_btc
        if dd > max_closed_dd_btc:
            max_closed_dd_btc = dd
            if peak_closed_btc > 0:
                max_closed_dd_pct = float(dd / peak_closed_btc) * 100.0

    total_fees_usdc = sum(t.maker_fee_sell_usdc + t.buyback_fee_usdc for t in trades)
    total_slippage_usdc = sum(t.slippage_paid_usdc for t in trades)

    target_count = sum(1 for t in trades if t.exit_reason == ExitReason.TARGET_BUYBACK)
    defensive_count = sum(1 for t in trades if t.exit_reason in (ExitReason.DEFENSIVE_STOP, ExitReason.CONTRADICTORY_DEFENSIVE))
    time_count = sum(1 for t in trades if t.exit_reason == ExitReason.TIME_STOP)

    # Sequence analysis
    current_win_streak = 0
    max_win_streak = 0
    current_loss_streak = 0
    max_loss_streak = 0

    for t in trades:
        if t.net_satoshis_pnl > 0:
            current_win_streak += 1
            current_loss_streak = 0
            if current_win_streak > max_win_streak:
                max_win_streak = current_win_streak
        elif t.net_satoshis_pnl < 0:
            current_loss_streak += 1
            current_win_streak = 0
            if current_loss_streak > max_loss_streak:
                max_loss_streak = current_loss_streak

    seq_analysis = SequenceAnalysis(
        max_consecutive_wins=max_win_streak,
        max_consecutive_losses=max_loss_streak,
        compounding_drag_satoshis=0,
        compounding_drag_note=(
            "En reinversión compuesta, las rachas adversas disminuyen la base operativa, "
            "exigiendo retornos proporcionalmente mayores para restaurar el máximo patrimonial previo."
        )
    )

    regimes = set(t.regime for t in trades)
    regime_dict: Dict[str, RegimeStats] = {}
    for r in regimes:
        r_trades = [t for t in trades if t.regime == r]
        r_wins = sum(1 for t in r_trades if t.net_satoshis_pnl > 0)
        r_losses = sum(1 for t in r_trades if t.net_satoshis_pnl < 0)
        r_sats = sum(t.net_satoshis_pnl for t in r_trades)
        r_btc = Decimal(str(r_sats)) / SATOSHIS_PER_BTC
        r_vol = sum(t.usdc_proceeds_gross for t in r_trades)
        r_wr = (r_wins / len(r_trades)) * 100.0 if r_trades else 0.0

        regime_dict[r] = RegimeStats(
            regime=r,
            trade_count=len(r_trades),
            wins=r_wins,
            losses=r_losses,
            win_rate_pct=r_wr,
            net_satoshis=r_sats,
            net_btc=r_btc,
            gross_usdc_vol=r_vol,
        )

    sample_size_reliable = total_trades >= 30
    caveat = (
        f"Muestra N={total_trades} estadísticamente suficiente para estimación preliminar."
        if sample_size_reliable
        else f"ADVERTENCIA METODOLÓGICA: Muestra N={total_trades} (<30 operaciones). Insuficiente para significancia estadística concluyente."
    )

    return StrategyMetrics(
        mode_name=mode_name,
        initial_btc=initial_btc,
        final_btc=final_btc_equity,
        hodl_btc=hodl_btc,
        net_satoshis_pnl=net_satoshis_pnl,
        net_btc_pnl=net_btc_pnl,
        return_pct_btc=return_pct_btc,
        outperformance_btc=outperformance_btc,
        outperformance_pct=outperformance_pct,
        initial_usdc_val=initial_btc * start_price,
        final_usdc_val=final_btc_equity * end_price,
        hodl_usdc_val=hodl_btc * end_price,
        total_trades=total_trades,
        winning_trades=winning_count,
        losing_trades=losing_count,
        win_rate_pct=win_rate,
        profit_factor=profit_factor,
        avg_win_satoshis=avg_win_sats,
        avg_loss_satoshis=avg_loss_sats,
        realized_max_drawdown_btc=max_closed_dd_btc,
        realized_max_drawdown_pct=max_closed_dd_pct,
        mtm_max_drawdown_btc=mtm_max_drawdown_btc,
        mtm_max_drawdown_pct=mtm_max_drawdown_pct,
        total_fees_usdc=total_fees_usdc,
        total_slippage_usdc=total_slippage_usdc,
        canceled_orders_count=canceled_orders_count,
        target_exits=target_count,
        defensive_exits=defensive_count,
        time_stop_exits=time_count,
        is_suspended=is_suspended,
        suspension_reason=suspension_reason,
        regime_breakdown=regime_dict,
        sequence_analysis=seq_analysis,
        sample_size_reliable=sample_size_reliable,
        sample_size_caveat=caveat,
    )
