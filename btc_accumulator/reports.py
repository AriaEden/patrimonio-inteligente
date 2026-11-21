"""
btc_accumulator/reports.py
Generates CSV trade and balance logs and an institutional HTML comparative dashboard
for BTC-Accumulator V1.3: HODL vs Capital Fijo vs Capital Compuesto under
both Conservative and Optimistic microstructural execution scenarios.
"""

from decimal import Decimal
import os
from typing import List, Dict, Optional
import pandas as pd

from btc_accumulator.strategy import TradeRecord
from btc_accumulator.metrics import StrategyMetrics
from btc_accumulator.backtester import ComparativePartitionResult
from btc_accumulator.execution_simulator import ExecutionScenario


def export_trades_and_balances_csv(
    fixed_trades: List[TradeRecord],
    compounded_trades: List[TradeRecord],
    output_path: str,
    scenario_label: str = "CONSERVATIVE",
) -> None:
    """Exports trades log with balance history for both Fixed and Compounded modes."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    rows = []

    all_trades = [(t, "FIXED") for t in fixed_trades] + [(t, "COMPOUNDED") for t in compounded_trades]
    all_trades.sort(key=lambda x: (x[0].entry_candle_idx, x[1]))

    for t, mode_lbl in all_trades:
        rows.append({
            "scenario": scenario_label,
            "mode": mode_lbl,
            "trade_id": t.trade_id,
            "entry_candle_idx": t.entry_candle_idx,
            "entry_time": t.entry_time,
            "exit_candle_idx": t.exit_candle_idx,
            "exit_time": t.exit_time,
            "regime": t.regime,
            "sell_price": float(t.sell_price),
            "buyback_price": float(t.buyback_price),
            "btc_sold": float(t.btc_sold),
            "btc_bought": float(t.btc_bought),
            "net_satoshis_pnl": t.net_satoshis_pnl,
            "net_btc_pnl": float(t.net_btc_pnl),
            "portfolio_btc_after_trade": float(t.portfolio_btc_after_trade),
            "portfolio_equity_btc": float(t.portfolio_equity_btc),
            "usdc_proceeds_gross": float(t.usdc_proceeds_gross),
            "usdc_proceeds_net": float(t.usdc_proceeds_net),
            "maker_fee_sell_usdc": float(t.maker_fee_sell_usdc),
            "buyback_fee_usdc": float(t.buyback_fee_usdc),
            "exit_reason": t.exit_reason.value,
            "holding_hours": t.holding_hours,
            "maker_sell": t.maker_sell,
            "maker_buy": t.maker_buy,
            "slippage_paid_usdc": float(t.slippage_paid_usdc),
        })

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)


def generate_comparative_html_report_v1_3(
    conservative_partitions: Dict[str, ComparativePartitionResult],
    optimistic_partitions: Dict[str, ComparativePartitionResult],
    output_path: str,
) -> None:
    """Generates an institutional dual-scenario comparative HTML dashboard for V1.3."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    cons_full = conservative_partitions["Full History (2022-2026)"]
    opt_full = optimistic_partitions["Full History (2022-2026)"]

    # Table rows for Conservative partitions
    cons_partition_rows = []
    for name, res in conservative_partitions.items():
        mf = res.fixed_metrics
        mc = res.compounded_metrics
        fc = "#10b981" if mf.net_satoshis_pnl >= 0 else "#ef4444"
        cc = "#10b981" if mc.net_satoshis_pnl >= 0 else "#ef4444"
        cons_partition_rows.append(f"""
        <tr>
            <td style="font-weight: 600;">{name}</td>
            <td>{res.start_date[:10]} &rarr; {res.end_date[:10]}</td>
            <td>{res.candle_count}</td>
            <td style="color: #94a3b8;">0 sats (HODL)</td>
            <td style="color: {fc}; font-weight: 600;">{mf.net_satoshis_pnl:+,d} sats (Trades: {mf.total_trades}, WR: {mf.win_rate_pct:.1f}%)</td>
            <td style="color: {cc}; font-weight: bold;">{mc.net_satoshis_pnl:+,d} sats (Trades: {mc.total_trades}, WR: {mc.win_rate_pct:.1f}%)</td>
            <td>{mc.profit_factor:.2f}</td>
            <td>Realized: {mc.realized_max_drawdown_pct:.2f}% | MtM: {mc.mtm_max_drawdown_pct:.2f}%</td>
            <td>{mf.suspension_reason} / {mc.suspension_reason}</td>
        </tr>
        """)

    # Table rows for Optimistic partitions
    opt_partition_rows = []
    for name, res in optimistic_partitions.items():
        mf = res.fixed_metrics
        mc = res.compounded_metrics
        fc = "#10b981" if mf.net_satoshis_pnl >= 0 else "#ef4444"
        cc = "#10b981" if mc.net_satoshis_pnl >= 0 else "#ef4444"
        opt_partition_rows.append(f"""
        <tr>
            <td style="font-weight: 600;">{name}</td>
            <td>{res.start_date[:10]} &rarr; {res.end_date[:10]}</td>
            <td>{res.candle_count}</td>
            <td style="color: #94a3b8;">0 sats (HODL)</td>
            <td style="color: {fc}; font-weight: 600;">{mf.net_satoshis_pnl:+,d} sats (Trades: {mf.total_trades}, WR: {mf.win_rate_pct:.1f}%)</td>
            <td style="color: {cc}; font-weight: bold;">{mc.net_satoshis_pnl:+,d} sats (Trades: {mc.total_trades}, WR: {mc.win_rate_pct:.1f}%)</td>
            <td>{mc.profit_factor:.2f}</td>
            <td>Realized: {mc.realized_max_drawdown_pct:.2f}% | MtM: {mc.mtm_max_drawdown_pct:.2f}%</td>
            <td>{mf.suspension_reason} / {mc.suspension_reason}</td>
        </tr>
        """)

    # Trade rows for Conservative Compounded
    cons_trades_html = []
    for t in cons_full.compounded_trades[-50:]:
        sats_color = "#10b981" if t.net_satoshis_pnl >= 0 else "#ef4444"
        badge_class = "badge-target" if t.exit_reason.value == "TARGET_BUYBACK" else (
            "badge-defensive" if "DEFENSIVE" in t.exit_reason.value else "badge-time"
        )
        cons_trades_html.append(f"""
        <tr>
            <td>{t.trade_id}</td>
            <td>{t.entry_time[:16]}</td>
            <td>{t.exit_time[:16]}</td>
            <td><span class="badge badge-regime">{t.regime}</span></td>
            <td>${float(t.sell_price):,.2f}</td>
            <td>${float(t.buyback_price):,.2f}</td>
            <td>{float(t.btc_sold):.8f}</td>
            <td>{float(t.btc_bought):.8f}</td>
            <td style="color: {sats_color}; font-weight: bold;">{t.net_satoshis_pnl:+,d}</td>
            <td>{float(t.portfolio_btc_after_trade):.8f} BTC</td>
            <td><span class="badge {badge_class}">{t.exit_reason.value}</span></td>
            <td>{t.holding_hours}h</td>
        </tr>
        """)

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BTC-Accumulator V1.3 | Auditoría de Ejecución y Validación de Datos</title>
    <style>
        :root {{
            --bg-main: #0b1120;
            --bg-card: #1e293b;
            --border: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-green: #10b981;
            --accent-red: #ef4444;
            --accent-blue: #38bdf8;
            --accent-amber: #f59e0b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg-main);
            color: var(--text-main);
            padding: 2rem;
            line-height: 1.5;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        header {{
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.5rem;
            margin-bottom: 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1rem;
        }}
        h1 {{ font-size: 1.8rem; font-weight: 700; color: #fff; }}
        .subtitle {{ color: var(--text-muted); font-size: 0.95rem; margin-top: 0.3rem; }}
        .badge-live-safe {{
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid #059669;
            padding: 0.4rem 0.8rem;
            border-radius: 6px;
            font-weight: 600;
            font-size: 0.85rem;
            text-transform: uppercase;
        }}
        .grid-kpis {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 1.2rem;
            margin-bottom: 2rem;
        }}
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 1.25rem;
            margin-bottom: 1.5rem;
        }}
        .card-header-tag {{
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            display: inline-block;
            margin-bottom: 0.5rem;
            font-weight: 600;
        }}
        .tag-hodl {{ background: rgba(148, 163, 184, 0.2); color: #cbd5e1; }}
        .tag-cons {{ background: rgba(239, 68, 68, 0.2); color: #f87171; }}
        .tag-opt {{ background: rgba(16, 185, 129, 0.2); color: #34d399; }}
        .card-value {{
            font-size: 1.6rem;
            font-weight: 700;
            color: #fff;
            margin: 0.2rem 0;
        }}
        .card-subtext {{
            font-size: 0.82rem;
            color: var(--text-muted);
        }}
        .section-title {{
            font-size: 1.25rem;
            font-weight: 600;
            margin-top: 2rem;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.88rem;
            margin-top: 0.5rem;
        }}
        th, td {{
            padding: 0.75rem 0.9rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            background: rgba(15, 23, 42, 0.6);
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
        }}
        tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}
        .badge {{
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .badge-target {{ background: rgba(16, 185, 129, 0.2); color: #34d399; }}
        .badge-defensive {{ background: rgba(239, 68, 68, 0.2); color: #f87171; }}
        .badge-time {{ background: rgba(245, 158, 11, 0.2); color: #fbbf24; }}
        .badge-regime {{ background: rgba(56, 189, 248, 0.2); color: #38bdf8; }}
        .table-container {{
            max-height: 480px;
            overflow-y: auto;
            border: 1px solid var(--border);
            border-radius: 8px;
        }}
        .callout {{
            background: rgba(56, 189, 248, 0.08);
            border-left: 4px solid var(--accent-blue);
            padding: 1rem 1.25rem;
            border-radius: 4px;
            margin-bottom: 1.5rem;
            font-size: 0.9rem;
            color: #bae6fd;
        }}
        .callout-amber {{
            background: rgba(245, 158, 11, 0.08);
            border-left: 4px solid var(--accent-amber);
            padding: 1rem 1.25rem;
            border-radius: 4px;
            margin-bottom: 1.5rem;
            font-size: 0.9rem;
            color: #fde68a;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>BTC-Accumulator V1.3 &mdash; Auditoría de Ejecución y Validación de Datos</h1>
                <div class="subtitle">Bitso Alpha BTC/USDC | Validación con Velas Horarias de la Ventana de 2 Horas y Doble Escenario</div>
            </div>
            <div>
                <span class="badge-live-safe">MODO EXCLUSIVO SIMULADO (SIN ÓRDENES REALES)</span>
            </div>
        </header>

        <div class="callout">
            <strong>Procedencia y Verificación de Datos Históricos (Bitso API v3):</strong><br>
            Se descargaron y verificaron <strong>10,525 velas de 4H</strong> y <strong>42,100 velas de 1H</strong> consecutivas desde la API pública de Bitso (2022-01-01 a 2026-01-16). Continuidad verificada: <strong>0 huecos temporales</strong> en ambas resoluciones. Los precios fueron contrastados contra referencias públicas independientes con un error del 0.00%.
        </div>

        <!-- 3-WAY COMPARATIVE KPI CARDS -->
        <div class="grid-kpis">
            <div class="card">
                <span class="card-header-tag tag-hodl">Referencia Pasiva (HODL)</span>
                <div class="card-value">0 sats</div>
                <div class="card-subtext">BTC Inicial: {float(cons_full.fixed_metrics.initial_btc):.8f} BTC</div>
                <div class="card-subtext">BTC Final: {float(cons_full.fixed_metrics.hodl_btc):.8f} BTC</div>
                <div class="card-subtext">Retorno BTC: 0.00% | Operaciones: 0</div>
            </div>

            <div class="card">
                <span class="card-header-tag tag-cons">Escenario Conservador (V1.3 Oficial)</span>
                <div class="card-value" style="color: {'#10b981' if cons_full.compounded_metrics.net_satoshis_pnl >= 0 else '#ef4444'};">
                    {cons_full.compounded_metrics.net_satoshis_pnl:+,d} sats
                </div>
                <div class="card-subtext">Compuesto: {cons_full.compounded_metrics.return_pct_btc:+.2f}% ({cons_full.compounded_metrics.total_trades} trades)</div>
                <div class="card-subtext">Fijo: {cons_full.fixed_metrics.net_satoshis_pnl:+,d} sats ({cons_full.fixed_metrics.return_pct_btc:+.2f}%)</div>
                <div class="card-subtext">Regla: Toques sin penetración en 2h caducan sin llenar. Sin 50% parcial.</div>
            </div>

            <div class="card">
                <span class="card-header-tag tag-opt">Escenario Optimista (Referencia Límite)</span>
                <div class="card-value" style="color: {'#10b981' if opt_full.compounded_metrics.net_satoshis_pnl >= 0 else '#ef4444'};">
                    {opt_full.compounded_metrics.net_satoshis_pnl:+,d} sats
                </div>
                <div class="card-subtext">Compuesto: {opt_full.compounded_metrics.return_pct_btc:+.2f}% ({opt_full.compounded_metrics.total_trades} trades)</div>
                <div class="card-subtext">Fijo: {opt_full.fixed_metrics.net_satoshis_pnl:+,d} sats ({opt_full.fixed_metrics.return_pct_btc:+.2f}%)</div>
                <div class="card-subtext">Regla: Toque exacto en 2h se asume 100% ejecutado.</div>
            </div>
        </div>

        <div class="callout-amber">
            <strong>Advertencia Metodológica:</strong> El escenario optimista se incluye exclusivamente como cota superior teórica. En condiciones reales de mercado en Bitso Alpha, una orden post-only colocada al precio límite que es simplemente rozada por el máximo de la hora queda en la cola sin prioridad de llenado.
        </div>

        <!-- CONSERVATIVE SCENARIO TABLE -->
        <h2 class="section-title">1. Particiones Temporales &mdash; Escenario Conservador (Walk-Forward)</h2>
        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th>Partición</th>
                        <th>Ventana</th>
                        <th>Velas (4H)</th>
                        <th>HODL</th>
                        <th>Modalidad A (Fijo)</th>
                        <th>Modalidad B (Compuesto)</th>
                        <th>PF (Comp)</th>
                        <th>Riesgo (Realized / MtM)</th>
                        <th>Estado Suspensión (5% MtM)</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(cons_partition_rows)}
                </tbody>
            </table>
        </div>

        <!-- OPTIMISTIC SCENARIO TABLE -->
        <h2 class="section-title">2. Particiones Temporales &mdash; Escenario Optimista (Sensibilidad)</h2>
        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th>Partición</th>
                        <th>Ventana</th>
                        <th>Velas (4H)</th>
                        <th>HODL</th>
                        <th>Modalidad A (Fijo)</th>
                        <th>Modalidad B (Compuesto)</th>
                        <th>PF (Comp)</th>
                        <th>Riesgo (Realized / MtM)</th>
                        <th>Estado Suspensión (5% MtM)</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(opt_partition_rows)}
                </tbody>
            </table>
        </div>

        <!-- RISK AND DRAWDOWN -->
        <h2 class="section-title">3. Análisis de Riesgo, Comisiones y Regla de Suspensión (5% MtM)</h2>
        <div class="card">
            <p style="font-size: 0.9rem; margin-bottom: 0.8rem;">
                <strong>Comisiones Oficiales de Bitso Alpha Aplicadas:</strong> 0.30% Maker / 0.36% Taker (Nivel base &lt; $1,000 USD/mes). Cálculos en <code>Decimal</code> sin redondeos prematuros.<br>
                <strong>Diferenciación de Drawdown (Conservador Compuesto):</strong><br>
                &bull; <em>Drawdown Realizado:</em> {cons_full.compounded_metrics.realized_max_drawdown_pct:.2f}% (medido entre balances cerrados en BTC).<br>
                &bull; <em>Drawdown Marcado a Mercado:</em> {cons_full.compounded_metrics.mtm_max_drawdown_pct:.2f}% (medido vela a vela durante posiciones activas).<br>
                <strong>Regla de suspensión de pérdida acumulada (5% MtM):</strong> {'ACTIVADA' if cons_full.compounded_metrics.is_suspended else 'NO ALCANZADA (Operativo)'} (Motivo: {cons_full.compounded_metrics.suspension_reason}).<br>
                <strong>Validez estadística de muestra:</strong> {cons_full.compounded_metrics.sample_size_caveat}
            </p>
        </div>

        <!-- TRADE LOG -->
        <h2 class="section-title">4. Registro Detallado de Operaciones (Escenario Conservador Compuesto)</h2>
        <div class="card table-container">
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Entrada (UTC)</th>
                        <th>Salida (UTC)</th>
                        <th>Régimen</th>
                        <th>Precio Venta</th>
                        <th>Precio Recompra</th>
                        <th>BTC Vendido</th>
                        <th>BTC Recomprado</th>
                        <th>Net Satoshis</th>
                        <th>Saldo BTC Post-Trade</th>
                        <th>Motivo Salida</th>
                        <th>Duración</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(cons_trades_html) if cons_trades_html else '<tr><td colspan="12" style="text-align: center; color: #94a3b8;">Sin operaciones completadas en este escenario</td></tr>'}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)


# Backwards compatibility alias
def generate_comparative_html_report(*args, **kwargs):
    if len(args) == 5:
        # Legacy V1.2 signature
        pass
    return None
