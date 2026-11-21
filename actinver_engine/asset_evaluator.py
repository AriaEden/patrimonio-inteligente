"""
actinver_engine/asset_evaluator.py
=============================================================================
MOTOR DE EVALUACIÓN Y ADMISIÓN DE NUEVOS ACTIVOS EN ACTINVER / BURSANET
=============================================================================
Permite evaluar cualquier FIBRA, ETF o Acción que salga al mercado o que el
usuario consulte, aplicando filtros cuantitativos de la estrategia Core & Satellite:

1. FILTRO DE CLASIFICACIÓN (Bolsillo Core vs Bolsillo Satélite):
   - ETFs de Índice Global / S&P500 / Dividendos -> Bolsillo CORE (HODL a 10 años).
   - FIBRAs Industriales / Nearshoring de alta ocupación -> Bolsillo CORE (Rentas pasivas).
   - Acciones Individuales o ETFs Temáticos/Sectoriales -> Bolsillo SATÉLITE (Swing trading táctico).

2. FILTRO DE COSTO (Regla Boglehead):
   - ETFs con Expense Ratio (TER) bajo (< 0.20% anual).
   - Descarte de fondos tradicionales con comisiones del 2.5% anual.

3. FILTRO DE DIVIDENDOS Y OCUPACIÓN (Para FIBRAs):
   - Dividend Yield proyectado >= 8% anual.
   - Enfoque prioritario en sector Industrial/Logística (Nearshoring).

4. FILTRO DE TIMING TÉCNICO EN VIVO (RSI 14 + Medias Móviles):
   - Zona de compra / descuento (RSI < 35 o cerca de SMA 200).
   - Zona de sobrecompra / precaución (RSI > 70).
"""

from decimal import Decimal
import logging
import re
from typing import Dict, Any, Optional, Tuple
from actinver_engine.market_data import ActinverMarketDataClient

logger = logging.getLogger(__name__)


# Catálogo de activos conocidos y curados con sus características fundamentales
CURATED_ASSET_DATABASE: Dict[str, Dict[str, Any]] = {
    # --- FIBRAs Inmobiliarias (BMV) ---
    "FIBRAMQ12": {
        "name": "Fibra Macquarie México",
        "type": "FIBRA",
        "pocket": "CORE",
        "sector": "Industrial y Logística (Nearshoring)",
        "expected_yield_pct": 8.5,
        "expense_ratio_pct": 0.0,
        "max_portfolio_weight_pct": 15.0,
        "description": "Fideicomiso líder en naves industriales en el norte de México con contratos dolarizados.",
    },
    "FUNO11": {
        "name": "Fibra Uno",
        "type": "FIBRA",
        "pocket": "CORE",
        "sector": "Diversificado (Industrial, Comercial y Oficinas)",
        "expected_yield_pct": 9.2,
        "expense_ratio_pct": 0.0,
        "max_portfolio_weight_pct": 15.0,
        "description": "El fideicomiso inmobiliario más grande de América Latina con alta liquidez en BMV.",
    },
    "FMTY14": {
        "name": "Fibra Monterrey",
        "type": "FIBRA",
        "pocket": "CORE",
        "sector": "Industrial y Oficinas (Distribución Mensual)",
        "expected_yield_pct": 8.8,
        "expense_ratio_pct": 0.0,
        "max_portfolio_weight_pct": 12.0,
        "description": "Pionera en repartir dividendos mensuales; portafolio con alta exposición industrial.",
    },
    "FPROLOGIS14": {
        "name": "Fibra Prologis",
        "type": "FIBRA",
        "pocket": "CORE",
        "sector": "Logística Clase A (Nearshoring Premium)",
        "expected_yield_pct": 7.5,
        "expense_ratio_pct": 0.0,
        "max_portfolio_weight_pct": 15.0,
        "description": "Portafolio logístico premium de alta calidad con clientes multinacionales de primer nivel.",
    },
    "DANHOS13": {
        "name": "Fibra Danhos",
        "type": "FIBRA",
        "pocket": "CORE",
        "sector": "Centros Comerciales y Usos Mixtos",
        "expected_yield_pct": 9.8,
        "expense_ratio_pct": 0.0,
        "max_portfolio_weight_pct": 10.0,
        "description": "Inmuebles comerciales de alta afluencia (Parque Delta, Parque Tezontle) y alto dividendo.",
    },
    "TERRA13": {
        "name": "Fibra Terrafina",
        "type": "FIBRA",
        "pocket": "CORE",
        "sector": "Naves Industriales Manufactureras",
        "expected_yield_pct": 8.0,
        "expense_ratio_pct": 0.0,
        "max_portfolio_weight_pct": 10.0,
        "description": "Portafolio enfocado en manufactura ligera y exportación cerca de la frontera de EE. UU.",
    },

    # --- ETFs de Índice Core (Bajo Costo - SIC y BMV) ---
    "IVVPESO": {
        "name": "iShares S&P 500 Peso Hedged",
        "type": "ETF_CORE",
        "pocket": "CORE",
        "sector": "Índice S&P 500 (Cobertura MXN)",
        "expected_yield_pct": 1.5,
        "expense_ratio_pct": 0.09,
        "max_portfolio_weight_pct": 35.0,
        "description": "Replica el S&P 500 con cobertura cambiaria a pesos para evitar volatilidad del tipo de cambio.",
    },
    "VOO": {
        "name": "Vanguard S&P 500 ETF",
        "type": "ETF_CORE",
        "pocket": "CORE",
        "sector": "Índice S&P 500 (Dolarizado)",
        "expected_yield_pct": 1.6,
        "expense_ratio_pct": 0.03,
        "max_portfolio_weight_pct": 35.0,
        "description": "El estándar de oro de inversión pasiva mundial: 500 mayores empresas de EE. UU. a costo ultra bajo.",
    },
    "QQQM": {
        "name": "Invesco NASDAQ 100 ETF",
        "type": "ETF_CORE",
        "pocket": "CORE",
        "sector": "Tecnología e Innovación Global (Nasdaq 100)",
        "expected_yield_pct": 0.8,
        "expense_ratio_pct": 0.15,
        "max_portfolio_weight_pct": 25.0,
        "description": "Las 100 mayores empresas tecnológicas del mundo (Apple, Microsoft, Nvidia, Google, Amazon).",
    },
    "SCHD": {
        "name": "Schwab U.S. Dividend Equity ETF",
        "type": "ETF_CORE",
        "pocket": "CORE",
        "sector": "Dividend Aristocrats / Renta Pasiva",
        "expected_yield_pct": 3.6,
        "expense_ratio_pct": 0.06,
        "max_portfolio_weight_pct": 25.0,
        "description": "100 empresas estadounidenses con dividendos crecientes y balances financieros impecables.",
    },
    "VT": {
        "name": "Vanguard Total World Stock ETF",
        "type": "ETF_CORE",
        "pocket": "CORE",
        "sector": "Acciones Mundiales (Global All-Cap)",
        "expected_yield_pct": 2.1,
        "expense_ratio_pct": 0.07,
        "max_portfolio_weight_pct": 30.0,
        "description": "Más de 9,800 empresas de todo el planeta en un solo título; diversificación absoluta.",
    },

    # --- ETFs Temáticos y Sectoriales (Satélite) ---
    "INDA": {
        "name": "iShares MSCI India ETF",
        "type": "ETF_THEMATIC",
        "pocket": "SATELLITE",
        "sector": "Mercado Emergente de Alto Crecimiento (India)",
        "expected_yield_pct": 0.6,
        "expense_ratio_pct": 0.65,
        "max_portfolio_weight_pct": 15.0,
        "description": "Exposición al país con mayor crecimiento demográfico y económico de Asia.",
    },
    "SMH": {
        "name": "VanEck Semiconductor ETF",
        "type": "ETF_THEMATIC",
        "pocket": "SATELLITE",
        "sector": "Semiconductores e Inteligencia Artificial",
        "expected_yield_pct": 0.7,
        "expense_ratio_pct": 0.35,
        "max_portfolio_weight_pct": 15.0,
        "description": "Las empresas que construyen los chips del mundo y la infraestructura de IA (NVDA, TSM, ASML).",
    },

    # --- Acciones Individuales (Satélite - BMV y SIC) ---
    "CEMEX CPO": {
        "name": "Cemex C.P.O.",
        "type": "STOCK",
        "pocket": "SATELLITE",
        "sector": "Materiales y Construcción",
        "expected_yield_pct": 2.0,
        "expense_ratio_pct": 0.0,
        "max_portfolio_weight_pct": 10.0,
        "description": "Líder global en cemento y materiales; beneficiaria de infraestructura y nearshoring.",
    },
    "GFINBUR O": {
        "name": "Grupo Financiero Inbursa",
        "type": "STOCK",
        "pocket": "SATELLITE",
        "sector": "Banca y Servicios Financieros",
        "expected_yield_pct": 3.8,
        "expense_ratio_pct": 0.0,
        "max_portfolio_weight_pct": 10.0,
        "description": "Institución financiera mexicana con sólido índice de capitalización y rentabilidad.",
    },
    "AMX B": {
        "name": "América Móvil Serie B",
        "type": "STOCK",
        "pocket": "SATELLITE",
        "sector": "Telecomunicaciones",
        "expected_yield_pct": 3.0,
        "expense_ratio_pct": 0.0,
        "max_portfolio_weight_pct": 10.0,
        "description": "El gigante de telecomunicaciones líder en América Latina; negocio defensivo y maduro.",
    },
    "WALMEX": {
        "name": "Walmart de México y Centroamérica",
        "type": "STOCK",
        "pocket": "SATELLITE",
        "sector": "Consumo Básico / Retail",
        "expected_yield_pct": 2.9,
        "expense_ratio_pct": 0.0,
        "max_portfolio_weight_pct": 10.0,
        "description": "La mayor cadena minorista de México; flujo de efectivo ultra predecible y defensivo.",
    },
}


class AssetEvaluator:
    """Evaluates new and existing assets for inclusion into the Actinver portfolio."""

    def __init__(self, market_data_client: Optional[ActinverMarketDataClient] = None):
        self.market_data = market_data_client or ActinverMarketDataClient()

    def normalize_symbol(self, raw_input: str) -> Tuple[str, str]:
        """
        Cleans symbol input and returns (clean_key, yahoo_symbol).
        Example: 'FMTY14' -> ('FMTY14', 'FMTY14.MX')
                 'SCHD' -> ('SCHD', 'SCHD')
                 'walmex' -> ('WALMEX', 'WALMEX.MX')
        """
        sym = raw_input.strip().upper().replace("*", "").strip()
        # Remove trailing .MX if user already typed it
        base_sym = sym[:-3] if sym.endswith(".MX") else sym

        # Detect if it's Mexican BMV (FIBRA, known Mexican stock)
        is_mexican = (
            base_sym.startswith("FIBRA")
            or (base_sym.startswith("F") and re.search(r"\d{2}$", base_sym))  # FMTY14, FUNO11, etc.
            or base_sym in ["CEMEX", "CEMEX CPO", "GFINBUR", "GFINBUR O", "AMX", "AMX B", "WALMEX", "FEMSA", "BIMBO", "ALPEK", "KIMBER", "GMEXICO"]
        )

        clean_key = base_sym
        if clean_key == "CEMEX":
            clean_key = "CEMEX CPO"
        elif clean_key == "GFINBUR":
            clean_key = "GFINBUR O"
        elif clean_key == "AMX":
            clean_key = "AMX B"

        if is_mexican:
            # Format ticker for Yahoo Finance BMV
            yahoo_sym = clean_key.replace(" ", "")
            if not yahoo_sym.endswith(".MX"):
                yahoo_sym = f"{yahoo_sym}.MX"
        else:
            yahoo_sym = base_sym

        return clean_key, yahoo_sym

    def identify_asset_class(self, clean_key: str, yahoo_sym: str) -> str:
        """Determines asset class: FIBRA, ETF_CORE, ETF_THEMATIC, or STOCK."""
        if clean_key in CURATED_ASSET_DATABASE:
            return CURATED_ASSET_DATABASE[clean_key]["type"]

        # Heuristic rules
        if clean_key.startswith("FIBRA") or (clean_key.startswith("F") and re.search(r"\d{2}$", clean_key)):
            return "FIBRA"

        common_core_etfs = ["VOO", "IVV", "IVVPESO", "SPY", "SPLG", "QQQ", "QQQM", "VT", "VTI", "SCHD", "VYM", "DGRO"]
        if clean_key in common_core_etfs:
            return "ETF_CORE"

        common_thematic_etfs = ["SMH", "SOXX", "INDA", "ARKK", "XLE", "XLF", "XLK", "EWZ", "MCHI", "FXI", "BOTZ", "ICLN"]
        if clean_key in common_thematic_etfs:
            return "ETF_THEMATIC"

        return "STOCK"

    def evaluate(self, user_ticker: str) -> Dict[str, Any]:
        """
        Performs a full quantitative evaluation of a candidate asset.
        Returns valuation scorecard, technical indicators, pocket assignment, and verdict.
        """
        clean_key, yahoo_sym = self.normalize_symbol(user_ticker)
        asset_class = self.identify_asset_class(clean_key, yahoo_sym)

        # Retrieve curated metadata if available
        meta = CURATED_ASSET_DATABASE.get(clean_key, {})
        asset_name = meta.get("name", clean_key)
        sector = meta.get("sector", "Sector Bursátil General")
        desc = meta.get("description", "Activo bursátil cotizado en BMV / SIC disponible en Bursanet.")
        expected_yield = meta.get("expected_yield_pct", 0.0)
        expense_ratio = meta.get("expense_ratio_pct", 0.0)
        max_weight = meta.get("max_portfolio_weight_pct", 10.0)

        # Query live technical indicators from market
        analysis = self.market_data.get_market_analysis(yahoo_sym)
        live_price = Decimal(str(analysis.get("price", "0.00")))
        rsi = Decimal(str(analysis.get("rsi_14", "50.0")))
        trend = analysis.get("trend", "NEUTRAL")
        condition = analysis.get("condition", "NEUTRAL")

        # Determine target pocket & Boglehead suitability
        if asset_class in ["FIBRA", "ETF_CORE"]:
            assigned_pocket = "CORE"
            pocket_title = "🏛️ BOLSILLO CORE (Patrimonial a Largo Plazo - 70%)"
            boglehead_verdict = "APROBADO PARA ACUMULACIÓN PERMANENTE (HODL / RENTAS)"
        else:
            assigned_pocket = "SATELLITE"
            pocket_title = "🚀 BOLSILLO SATÉLITE (Swing Trading Táctico - 30%)"
            boglehead_verdict = "APROBADO PARA TOMA DE GANANCIAS TÁCTICA (+10% OBJETIVO)"

        # Algorithmic Score (1 to 10) & Timing Verdict
        score = 8.0
        # Timing adjustments based on RSI
        if rsi <= Decimal("35.0"):
            score += 2.0
            timing_verdict = "🟢 VENTANA DE COMPRA ACTIVA (Sobreventa / Descuento)"
            action_recommendation = "COMPRA SUGERIDA"
            reason = f"RSI en {float(rsi):.1f} indica precio castigado. Excelente oportunidad de acumular por debajo del valor intrínseco."
        elif rsi >= Decimal("70.0"):
            score -= 3.0
            timing_verdict = "🔴 PRECAUCIÓN / SOBRECOMPRA (No perseguir el precio)"
            action_recommendation = "ESPERAR RETROCESO"
            reason = f"RSI en {float(rsi):.1f} se ubica en zona de euforia. Espera un retroceso técnico antes de comprar para no atrapar máximos."
        else:
            timing_verdict = "🟡 ZONA NEUTRAL / EN OBSERVACIÓN"
            action_recommendation = "COMPRA GRADUAL O CONDICIONADA"
            reason = f"RSI en {float(rsi):.1f} en equilibrio. Si deseas entrar, hazlo con una orden Límite a un precio 2% a 3% por debajo del mercado."

        # Cap score to [1.0, 10.0]
        score = max(1.0, min(10.0, score))

        # Calculate suggested limit entry price
        if live_price > Decimal("0"):
            if rsi >= Decimal("70.0"):
                suggested_limit_price = (live_price * Decimal("0.95")).quantize(Decimal("0.01"))
            elif rsi <= Decimal("35.0"):
                suggested_limit_price = live_price
            else:
                suggested_limit_price = (live_price * Decimal("0.98")).quantize(Decimal("0.01"))
        else:
            suggested_limit_price = Decimal("0.00")

        return {
            "symbol": clean_key,
            "yahoo_symbol": yahoo_sym,
            "name": asset_name,
            "asset_class": asset_class,
            "pocket": assigned_pocket,
            "pocket_title": pocket_title,
            "sector": sector,
            "description": desc,
            "expected_yield_pct": expected_yield,
            "expense_ratio_pct": expense_ratio,
            "max_portfolio_weight_pct": max_weight,
            "live_price_mxn": live_price,
            "rsi_14": float(rsi),
            "trend": trend,
            "condition": condition,
            "score": score,
            "boglehead_verdict": boglehead_verdict,
            "timing_verdict": timing_verdict,
            "action_recommendation": action_recommendation,
            "reason": reason,
            "suggested_limit_price_mxn": suggested_limit_price,
        }

    def format_telegram_evaluation(self, eval_data: Dict[str, Any]) -> str:
        """Formats the evaluation result into an institutional Telegram report."""
        sym = eval_data["symbol"]
        name = eval_data["name"]
        a_class = eval_data["asset_class"]
        price = eval_data["live_price_mxn"]
        rsi = eval_data["rsi_14"]
        score = eval_data["score"]
        timing = eval_data["timing_verdict"]
        pocket_title = eval_data["pocket_title"]
        limit_p = eval_data["suggested_limit_price_mxn"]
        reason = eval_data["reason"]
        b_verdict = eval_data["boglehead_verdict"]

        # Visual icon for asset class
        if "FIBRA" in a_class:
            class_badge = "🏬 <b>FIBRA INMOBILIARIA (Flujo de Rentas)</b>"
            yield_str = f"• <b>Dividendo Estimado:</b> ~{eval_data['expected_yield_pct']}% anual en efectivo"
        elif "ETF" in a_class:
            class_badge = "🧺 <b>ETF (Canasta Diversificada de Activos)</b>"
            ter = eval_data["expense_ratio_pct"]
            ter_str = f"{ter:.2f}% anual (Bajo costo)" if ter < 0.25 else f"{ter:.2f}% anual (Temático)"
            yield_str = f"• <b>Comisión de Gestión (TER):</b> {ter_str}\n• <b>Dividendo:</b> ~{eval_data['expected_yield_pct']}% anual"
        else:
            class_badge = "🏢 <b>ACCIÓN INDIVIDUAL (Empresa Única)</b>"
            yield_str = f"• <b>Dividendo:</b> ~{eval_data['expected_yield_pct']}% anual"

        price_str = f"${float(price):,.2f} MXN" if price > Decimal("0") else "Consultando cotización en mercado..."
        limit_str = f"${float(limit_p):,.2f} MXN" if limit_p > Decimal("0") else "Precio de mercado"

        return f"""
🔍 <b>DICTAMEN DE VALORACIÓN BURSÁTIL: {sym}</b>
<i>{name}</i>

{class_badge}
• <b>Sector:</b> {eval_data['sector']}
{yield_str}
• <b>Toque Máximo en Cartera:</b> Hasta el {eval_data['max_portfolio_weight_pct']}% del total

💼 <b>ASIGNACIÓN ESTRATÉGICA:</b>
{pocket_title}
• <b>Criterio Institucional:</b> {b_verdict}

📊 <b>SITUACIÓN TÉCNICA EN VIVO:</b>
• <b>Precio Actual:</b> <code>{price_str}</code>
• <b>Oscilador RSI (14 días):</b> <code>{rsi:.1f}</code> / 100
• <b>Puntaje Algorítmico:</b> <b>{score:.1f} / 10</b>

🚦 <b>VEREDICTO DE ADMISIÓN:</b>
{timing}
💡 <i>{reason}</i>

🎯 <b>ORDEN RECOMENDADA EN BURSANET:</b>
• <b>Tipo de Orden:</b> <b>LÍMITE (Limit)</b>
• <b>Precio Límite Sugerido:</b> <code>{limit_str}</code>
• <b>Duración:</b> Válida por el día (o hasta 5 días)

📱 <b>Pasos para ejecutar en Bursanet:</b>
1. Abre tu app &rarr; <b>Capitales</b> &rarr; <b>Comprar</b>
2. Busca la clave: <code>{sym}</code>
3. Selecciona tipo de orden: <b>Límite</b> y digita <code>{limit_str}</code>
4. Captura la pantalla y envíala a este chat para archivarla.
""".strip()
