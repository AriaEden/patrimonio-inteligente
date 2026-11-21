"""
actinver_engine/rebalance_engine.py
Motor de Rebalanceo Táctico y Señales de Swing Trading para Actinver.
Calcula desbalances de cartera, señales de toma de ganancia (take-profit),
y diseña órdenes exactas de reasignación hacia FIBRAs generadoras de dividendos.
"""

from decimal import Decimal
import logging
from typing import Dict, Any, List, Optional
from actinver_engine.config import (
    MAX_EMERGING_MARKET_WEIGHT,
    MIN_FIBRA_WEIGHT,
    CORE_TARGET_WEIGHT,
    SATELLITE_TARGET_WEIGHT,
    SWING_RSI_OVERBOUGHT,
    SWING_RSI_OVERSOLD,
    SWING_TARGET_PROFIT_PCT,
    SWING_STOP_LOSS_PCT,
    MUTUAL_FUNDS_LIQUIDATION_SCHEDULE,
    CROSS_ASSET_FLYWHEEL_CONFIG,
)
from actinver_engine.portfolio_manager import ActinverPortfolioManager

logger = logging.getLogger(__name__)


class ActinverRebalanceEngine:
    """Computes portfolio rebalance needs and swing trading triggers."""

    def __init__(self, portfolio_mgr: ActinverPortfolioManager):
        self.portfolio_mgr = portfolio_mgr

    def evaluate_initial_rebalance(self, live_quotes: Optional[Dict[str, Decimal]] = None) -> Dict[str, Any]:
        """
        Evaluates the specific Step 2 rebalancing plan agreed with the user:
        1. Partial profit taking on CEMEX CPO (50 titles to lock in ~60% gain).
        2. Partial rebalance on INDA (3 titles to trim 28% concentration).
        3. Initial deployment into Nearshoring FIBRA (FIBRAMQ12) to start dividend compounding.
        """
        quotes = live_quotes or {}
        val = self.portfolio_mgr.calculate_valuation(quotes)
        total_mxn = val["total_valuation_mxn"]
        stocks = val["stock_breakdown"]

        orders = []

        # 1. CEMEX CPO Partial Take-Profit
        cemex = stocks.get("CEMEX CPO")
        if cemex and cemex["titles"] >= 100:
            cemex_p = Decimal(str(quotes.get("CEMEX CPO", cemex["price"])))
            sell_titles = 50
            released_cash = sell_titles * cemex_p
            orders.append({
                "action": "SELL",
                "symbol": "CEMEX CPO",
                "name": "Cemex CPO",
                "titles": sell_titles,
                "order_type": "LÍMITE (Limit)",
                "suggested_price_mxn": cemex_p,
                "est_total_mxn": released_cash,
                "reason": "Toma de ganancia parcial (+59.6% acumulado). Asegura $375 MXN de utilidad neta y libera capital.",
                "pocket": "SATELLITE",
                "priority": "ALTA"
            })

        # 2. INDA * Concentration Trim
        inda = stocks.get("INDA *")
        if inda and inda["titles"] >= 12:
            inda_p = Decimal(str(quotes.get("INDA *", inda["price"])))
            sell_titles = 3
            released_cash = sell_titles * inda_p
            orders.append({
                "action": "SELL",
                "symbol": "INDA *",
                "name": "iShares MSCI India ETF (SIC)",
                "titles": sell_titles,
                "order_type": "LÍMITE (Limit)",
                "suggested_price_mxn": inda_p,
                "est_total_mxn": released_cash,
                "reason": "Rebalanceo por sobreconcentración (28% -> 21%). Pasa a niveles de riesgo más prudentes.",
                "pocket": "SATELLITE",
                "priority": "ALTA"
            })

        # Calculate total deployable capital: pending sales + current idle cash in Bursanet
        pending_sales_cash = sum(o["est_total_mxn"] for o in orders if o["action"] == "SELL")
        idle_cash = Decimal(str(val["cash_mxn"]))

        fibramq_p = Decimal(str(quotes.get("FIBRAMQ12", "43.35")))
        ivvpeso_p = Decimal(str(quotes.get("IVVPESO ISHRS", "153.00")))
        deployed_total = Decimal("0.0")

        # Check existing holdings
        fibramq_titles = stocks.get("FIBRAMQ12", {}).get("titles", 0)
        ivv_titles_held = stocks.get("IVVPESO ISHRS", {}).get("titles", 0)
        phase_1_completed = fibramq_titles >= 37 and ivv_titles_held >= 36

        # If user already executed Phase 1 purchase, acknowledge it!
        if phase_1_completed:
            total_deployable_mxn = Decimal("0.0")
        elif pending_sales_cash > Decimal("1000") and fibramq_titles < 37:
            buy_titles = int(pending_sales_cash // fibramq_p)
            deployed_cash = buy_titles * fibramq_p
            deployed_total += deployed_cash
            orders.append({
                "action": "BUY",
                "symbol": "FIBRAMQ12",
                "name": "Fibra Macquarie (Nearshoring Industrial)",
                "titles": buy_titles,
                "order_type": "LÍMITE (Limit)",
                "suggested_price_mxn": fibramq_p,
                "est_total_mxn": deployed_cash,
                "reason": "Incorporación de activo generador de rentas en efectivo (rendimiento ~8% anual). Inicia Interés Compuesto DRIP.",
                "pocket": "CORE",
                "priority": "ALTA"
            })
            total_deployable_mxn = pending_sales_cash
        elif idle_cash >= Decimal("500") and fibramq_titles < 37:
            total_deployable_mxn = idle_cash
            fibra_budget = idle_cash * Decimal("0.60")
            fibra_titles = int(fibra_budget // fibramq_p)
            if fibra_titles > 0:
                fibra_cost = fibra_titles * fibramq_p
                deployed_total += fibra_cost
                orders.append({
                    "action": "BUY",
                    "symbol": "FIBRAMQ12",
                    "name": "Fibra Macquarie (Nearshoring Industrial)",
                    "titles": fibra_titles,
                    "order_type": "LÍMITE (Limit)",
                    "suggested_price_mxn": fibramq_p,
                    "est_total_mxn": fibra_cost,
                    "reason": "Generación de rentas trimestrales en efectivo (rendimiento ~8% anual). Inicia Interés Compuesto DRIP.",
                    "pocket": "CORE",
                    "priority": "ALTA"
                })

            rem_cash = idle_cash - deployed_total
            ivv_titles = int(rem_cash // ivvpeso_p)
            if ivv_titles > 0:
                ivv_cost = ivv_titles * ivvpeso_p
                deployed_total += ivv_cost
                orders.append({
                    "action": "BUY",
                    "symbol": "IVVPESO ISHRS",
                    "name": "iShares Core S&P 500 en Pesos",
                    "titles": ivv_titles,
                    "order_type": "LÍMITE (Limit)",
                    "suggested_price_mxn": ivvpeso_p,
                    "est_total_mxn": ivv_cost,
                    "reason": "Acumulación en el índice líder mundial (S&P 500) para el retiro con comisiones bajas.",
                    "pocket": "CORE",
                    "priority": "MEDIA"
                })
        else:
            total_deployable_mxn = Decimal("0.0")

        cash_rem = float(total_deployable_mxn - deployed_total)

        return {
            "current_valuation_mxn": total_mxn,
            "total_released_liquidity_mxn": total_deployable_mxn,
            "recommended_orders": orders,
            "phase_1_completed": phase_1_completed,
            "fibramq_titles": fibramq_titles,
            "ivv_titles": ivv_titles_held,
            "expected_outcome": {
                "core_pocket_boost": "+10% en FIBRAs de renta mensual/trimestral",
                "locked_profit": "Asegura ganancias en bolsillo satélite",
                "reduced_india_risk": "Baja exposición a India al ~21%",
                "cash_remaining": cash_rem
            }
        }

    def check_swing_signals(self, market_analyses: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Evaluates swing buy/sell triggers for satellite pocket stocks."""
        signals = []
        val = self.portfolio_mgr.calculate_valuation()
        stocks = val["stock_breakdown"]

        for name, analysis in market_analyses.items():
            symbol = analysis.get("symbol", name)
            price = analysis.get("price", Decimal("0"))
            rsi = analysis.get("rsi_14", Decimal("50.0"))
            condition = analysis.get("condition", "NEUTRAL")

            # Check if user already owns this asset
            owned = stocks.get(name)

            # Buy Signal (Oversold in healthy trend)
            if condition == "OVERSOLD_ACCUMULATE" and (not owned or owned["titles"] < 100):
                signals.append({
                    "action": "BUY",
                    "symbol": name,
                    "price_mxn": price,
                    "rsi": rsi,
                    "reason": f"Sobreventa técnica detectada (RSI {rsi:.1f}). Precio en soporte favorable para swing trade.",
                    "order_type": "LÍMITE (Limit)",
                    "pocket": "SATELLITE"
                })

            # Sell / Take-Profit Signal
            elif condition == "OVERBOUGHT_TAKE_PROFIT" and owned and owned["titles"] > 0:
                signals.append({
                    "action": "SELL",
                    "symbol": name,
                    "price_mxn": price,
                    "rsi": rsi,
                    "reason": f"Sobrecompra técnica extrema (RSI {rsi:.1f}). Momento de tomar ganancias parciales en swing.",
                    "order_type": "LÍMITE (Limit)",
                    "pocket": "SATELLITE"
                })

        return signals

    def evaluate_mutual_funds_liquidation(self) -> Dict[str, Any]:
        """
        Plans the orderly liquidation of the 8 scattered mutual funds in Actinver ($14,553 MXN).
        Divides the process into Phase 1 (Residuals) and Phase 2 (Core liquidation).
        """
        phase_1 = [f for f in MUTUAL_FUNDS_LIQUIDATION_SCHEDULE if f["phase"] == 1]
        phase_2 = [f for f in MUTUAL_FUNDS_LIQUIDATION_SCHEDULE if f["phase"] == 2]

        total_phase_1_mxn = sum(f["value_mxn"] for f in phase_1)
        total_phase_2_mxn = sum(f["value_mxn"] for f in phase_2)
        total_funds_mxn = total_phase_1_mxn + total_phase_2_mxn

        return {
            "total_dormant_capital_mxn": total_funds_mxn,
            "phase_1_immediate": {
                "funds": phase_1,
                "total_mxn": total_phase_1_mxn,
                "objective": "Limpiar posiciones microscópicas y rescatar $1,685 MXN inmediatos.",
                "reinvestment_target": "Acumular 35 títulos más de FIBRAMQ12 (rentas en efectivo)."
            },
            "phase_2_strategic": {
                "funds": phase_2,
                "total_mxn": total_phase_2_mxn,
                "objective": "Eliminar comisiones parasitarias del 2.5% anual y liberar $12,868 MXN.",
                "reinvestment_target": "Comprar 2 títulos más de QQQM (Nasdaq 100) y reforzar FIBRAs."
            }
        }

    def evaluate_cross_asset_flywheel(self, btc_price_usd: Decimal) -> Optional[Dict[str, Any]]:
        """
        Evaluates macro cyclical conditions for Cross-Asset capital rotation between Bitcoin and Actinver.
        """
        harvest_p = CROSS_ASSET_FLYWHEEL_CONFIG["BTC_MACRO_HARVEST_PRICE_USD"]
        buy_p = CROSS_ASSET_FLYWHEEL_CONFIG["BTC_MACRO_BUY_PRICE_USD"]

        # 1. Macro Peak / Euphoria Harvesting Signal (BTC -> Actinver)
        if btc_price_usd >= harvest_p:
            return {
                "direction": "CRIPTO_A_ACTINVER",
                "action": "COSECHAR_BITCOIN",
                "btc_price_usd": btc_price_usd,
                "trigger_threshold_usd": harvest_p,
                "reason": (
                    f"Bitcoin alcanzó zona de euforia macro (${btc_price_usd:,.2f} USD >= ${harvest_p:,.2f}). "
                    f"Momento de cosechar el 50% de las ganancias en USD/MXN y fondear Actinver "
                    f"para amarrar rentas vitalicias del 10% en FIBRAs."
                ),
                "transfer_advice": "Vender 50% de BTC en Bitso, transferir MXN vía SPEI a Bursanet/Actinver."
            }

        # 2. Macro Winter / Generational Bottom Signal (Actinver Rents -> BTC)
        elif btc_price_usd <= buy_p:
            return {
                "direction": "ACTINVER_A_CRIPTO",
                "action": "RECOMPRA_GENERACIONAL_BITCOIN",
                "btc_price_usd": btc_price_usd,
                "trigger_threshold_usd": buy_p,
                "reason": (
                    f"Bitcoin cayó a precio de remate de invierno (${btc_price_usd:,.2f} USD <= ${buy_p:,.2f}). "
                    f"Momento de utilizar el 50% del flujo de rentas acumuladas de Actinver para "
                    f"comprar Bitcoin con descuento extremo antes del próximo Halving."
                ),
                "transfer_advice": "Retirar efectivo disponible de rentas en Actinver y transferir a Bitso para comprar satoshis."
            }

        return None
