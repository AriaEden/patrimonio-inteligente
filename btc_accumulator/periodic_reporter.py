"""
btc_accumulator/periodic_reporter.py
Generador de Rendición de Cuentas Periódico en Lenguaje Claro y Accesible.
Diseñado para que cualquier persona, sin conocimientos previos en finanzas o criptomonedas,
pueda entender con total transparencia:
1. ¿Con cuánto dinero empezamos?
2. ¿Cuánto tenemos hoy?
3. ¿Cuánto hemos ganado en Bitcoin puro frente a no hacer nada (HODL)?
4. ¿Cuál es el estado actual del mercado (Modo Blindaje vs Modo Acumulador)?
5. ¿Qué está haciendo el bot en este momento?
"""

from decimal import Decimal
import os
from typing import Optional, Dict, Any, List
import pandas as pd

from btc_accumulator.strategy import TradeRecord
from btc_accumulator.portfolio import PortfolioManager


class PlainLanguageReporter:
    """Generates ultra-clear financial reports in plain Spanish with zero confusing jargon."""

    @staticmethod
    def format_money_usdc(val: Decimal) -> str:
        return f"${float(val):,.2f} USD"

    @staticmethod
    def format_satoshis(satoshis: int) -> str:
        return f"{satoshis:,} satoshis"

    @staticmethod
    def format_btc(btc: Decimal) -> str:
        return f"{float(btc):.8f} BTC"

    @classmethod
    def generate_executive_text_summary(
        cls,
        period_title: str,
        initial_usdc: Decimal,
        initial_btc: Decimal,
        current_btc_equity: Decimal,
        current_btc_price: Decimal,
        trades: List[TradeRecord],
        is_bull_run_active: bool,
        is_suspended: bool,
        suspension_reason: str = "NONE",
    ) -> str:
        """
        Generates a human-friendly periodic report formatted for WhatsApp, Telegram, email, or terminal.
        """
        initial_sats = int(initial_btc * Decimal("100000000"))
        current_sats = int(current_btc_equity * Decimal("100000000"))
        net_sats_earned = current_sats - initial_sats
        pct_btc_gain = ((current_btc_equity - initial_btc) / initial_btc) * 100 if initial_btc > 0 else Decimal("0")

        current_val_usdc = current_btc_equity * current_btc_price
        initial_val_at_current_price = initial_btc * current_btc_price
        dollar_advantage = current_val_usdc - initial_val_at_current_price

        # Emoji / Icon indicators
        profit_emoji = "🟢 GANANDO" if net_sats_earned >= 0 else "🔴 CON PÉRDIDA CONTROLADA"
        
        if is_bull_run_active:
            status_text = "🛡️ MODO BLINDAJE HODL ACTIVO"
            action_text = "Bitcoin está en tendencia alcista fuerte (Bull Run). El bot tiene las ventas BLOQUEADAS para que no te quedes fuera de la subida y aproveches toda la ganancia en dólares de tus monedas."
        elif is_suspended:
            status_text = "⏸️ SISTEMA EN PAUSA PREVENTIVA"
            action_text = f"El sistema se pausó automáticamente ({suspension_reason}) para proteger el 95% de tu capital tras alcanzar el límite de riesgo permitido."
        else:
            status_text = "🎯 MODO ACUMULADOR ACTIVO"
            action_text = "El mercado está tranquilo o en rango lateral. El bot vigila el mercado cada 4 horas para vender caro y recomprar 2.5% más barato."

        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.net_satoshis_pnl > 0)
        losing_trades = sum(1 for t in trades if t.net_satoshis_pnl < 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        summary = f"""
================================================================================
 📊 REPORTE PERIÓDICO DE TU CUENTA | {period_title.upper()}
================================================================================

1️⃣ ¿CON CUÁNTO DINERO EMPEZAMOS?
   • Capital inicial en Dólares : {cls.format_money_usdc(initial_usdc)}
   • Cantidad inicial en Bitcoin : {cls.format_btc(initial_btc)} ({initial_sats:,} satoshis)

2️⃣ ¿CÓMO VAMOS HOY?
   • Cantidad actual en Bitcoin  : {cls.format_btc(current_btc_equity)} ({current_sats:,} satoshis)
   • Valor actual en Dólares    : {cls.format_money_usdc(current_val_usdc)} (Precio BTC: ${float(current_btc_price):,.2f})
   • Estado general de tu cuenta: {profit_emoji}

3️⃣ ¿CUÁNTO HEMOS GANADO COMPARADO CON NO HACER NADA (HODL)?
   • Ganancia neta en Bitcoin   : {net_sats_earned:+,d} satoshis ({pct_btc_gain:+.2f}% de crecimiento puro)
   • Ventaja extra en Dólares   : {dollar_advantage:+,.2f} USD generados por el bot
   • ¿Qué es esto en cristiano? : Si solo hubieras guardado tus monedas sin hacer nada,
                                  tendrías {initial_sats:,} satoshis. Gracias al bot,
                                  ahora tienes {current_sats:,} satoshis.

4️⃣ ESTADO DEL MERCADO Y ACTIVIDAD DEL BOT:
   • Estado actual: {status_text}
   • ¿Qué está haciendo el bot? :
     {action_text}

5️⃣ RESUMEN DE OPERACIONES:
   • Operaciones completadas    : {total_trades}
   • Operaciones con ganancia   : {winning_trades} ({win_rate:.1f}% de efectividad)
   • Operaciones con pérdida    : {losing_trades} (cortadas a tiempo con freno de seguridad)

================================================================================
"""
        return summary

    @classmethod
    def generate_plain_html_dashboard(
        cls,
        period_title: str,
        initial_usdc: Decimal,
        initial_btc: Decimal,
        current_btc_equity: Decimal,
        current_btc_price: Decimal,
        trades: List[TradeRecord],
        is_bull_run_active: bool,
        is_suspended: bool,
        output_path: str,
        suspension_reason: str = "NONE",
    ) -> None:
        """Generates an ultra-clear, beautiful visual dashboard in HTML for beginners."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        initial_sats = int(initial_btc * Decimal("100000000"))
        current_sats = int(current_btc_equity * Decimal("100000000"))
        net_sats_earned = current_sats - initial_sats
        pct_btc_gain = ((current_btc_equity - initial_btc) / initial_btc) * 100 if initial_btc > 0 else Decimal("0")

        current_val_usdc = current_btc_equity * current_btc_price
        initial_val_at_current_price = initial_btc * current_btc_price
        dollar_advantage = current_val_usdc - initial_val_at_current_price

        accent_color = "#10b981" if net_sats_earned >= 0 else "#ef4444"
        badge_bg = "rgba(16, 185, 129, 0.15)" if net_sats_earned >= 0 else "rgba(239, 68, 68, 0.15)"

        if is_bull_run_active:
            market_badge = "🛡️ MODO BLINDAJE HODL (VENTAS BLOQUEADAS)"
            market_desc = "El mercado de Bitcoin está en fase alcista fuerte (Bull Run). Para proteger tus monedas y evitar que vendas antes de tiempo, el bot tiene prohibido vender. Tus Bitcoin están seguros creciendo en valor."
            market_card_color = "#38bdf8"
        elif is_suspended:
            market_badge = "⏸️ SISTEMA EN PAUSA PREVENTIVA"
            market_desc = f"El sistema se pausó automáticamente ({suspension_reason}) para proteger el 95% de tu dinero tras alcanzar el límite de pérdida máxima."
            market_card_color = "#f59e0b"
        else:
            market_badge = "🎯 MODO ACUMULADOR ACTIVO"
            market_desc = "El mercado está en calma o rango lateral. El bot busca picos para vender con orden límite y recomprar un 2.5% más barato para ganar satoshis."
            market_card_color = "#10b981"

        trade_rows = []
        for t in trades:
            t_color = "#10b981" if t.net_satoshis_pnl >= 0 else "#ef4444"
            trade_rows.append(f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #334155;">#{t.trade_id}</td>
                <td style="padding: 12px; border-bottom: 1px solid #334155;">{t.entry_time[:10]}</td>
                <td style="padding: 12px; border-bottom: 1px solid #334155;">${float(t.sell_price):,.2f}</td>
                <td style="padding: 12px; border-bottom: 1px solid #334155;">${float(t.buyback_price):,.2f}</td>
                <td style="padding: 12px; border-bottom: 1px solid #334155; color: {t_color}; font-weight: bold;">{t.net_satoshis_pnl:+,d} sats</td>
                <td style="padding: 12px; border-bottom: 1px solid #334155;">{t.exit_reason.value}</td>
            </tr>
            """)

        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reporte de Rendimientos en Lenguaje Claro | BTC-Accumulator</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            margin: 0;
            padding: 24px;
        }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        .header {{
            background: #1e293b;
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 24px;
            border: 1px solid #334155;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .card {{
            background: #1e293b;
            padding: 20px;
            border-radius: 12px;
            border: 1px solid #334155;
        }}
        .card-label {{ font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; font-weight: 600; }}
        .card-value {{ font-size: 1.8rem; font-weight: 700; margin: 8px 0; color: #fff; }}
        .card-subtext {{ font-size: 0.9rem; color: #cbd5e1; }}
        .market-banner {{
            background: #1e293b;
            border-left: 6px solid {market_card_color};
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 24px;
        }}
        table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 0.95rem; }}
        th {{ background: #0f172a; padding: 12px; color: #94a3b8; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0; font-size: 1.6rem;">📊 Tu Estado de Cuenta de Bitcoin</h1>
            <p style="margin: 6px 0 0 0; color: #94a3b8;">Período analizado: <strong>{period_title}</strong> | Todo explicado sin términos complicados.</p>
        </div>

        <div class="grid">
            <div class="card">
                <div class="card-label">1. ¿Con cuánto empezamos?</div>
                <div class="card-value">{cls.format_money_usdc(initial_usdc)}</div>
                <div class="card-subtext">Equivalente a <strong>{initial_sats:,} satoshis</strong><br>({cls.format_btc(initial_btc)})</div>
            </div>

            <div class="card">
                <div class="card-label">2. ¿Cuánto tenemos hoy?</div>
                <div class="card-value">{cls.format_money_usdc(current_val_usdc)}</div>
                <div class="card-subtext">Equivalente a <strong>{current_sats:,} satoshis</strong><br>({cls.format_btc(current_btc_equity)})</div>
            </div>

            <div class="card" style="border-color: {accent_color};">
                <div class="card-label">3. Tus Ganancias Netas</div>
                <div class="card-value" style="color: {accent_color};">{net_sats_earned:+,d} sats</div>
                <div class="card-subtext" style="color: {accent_color}; font-weight: 600;">{pct_btc_gain:+.2f}% de crecimiento en Bitcoin puro</div>
                <div class="card-subtext" style="margin-top: 4px; font-size: 0.8rem; color: #94a3b8;">+{dollar_advantage:+,.2f} USD extra sobre HODL</div>
            </div>
        </div>

        <div class="market-banner">
            <h3 style="margin: 0 0 8px 0; color: {market_card_color};">{market_badge}</h3>
            <p style="margin: 0; line-height: 1.5; font-size: 0.95rem;">{market_desc}</p>
        </div>

        <div class="card">
            <h3 style="margin-top: 0; margin-bottom: 16px;">Historial de Operaciones Realizadas</h3>
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Fecha</th>
                        <th>Precio Venta</th>
                        <th>Precio Recompra</th>
                        <th>Ganancia (Satoshis)</th>
                        <th>Resultado</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(trade_rows) if trade_rows else '<tr><td colspan="6" style="padding: 16px; text-align: center; color: #94a3b8;">No hubo operaciones en este período (el bot protegió tus monedas sin arriesgar).</td></tr>'}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
