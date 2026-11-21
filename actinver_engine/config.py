"""
actinver_engine/config.py
Configuración Integral del Copiloto Patrimonial para Actinver (Bursanet).
Estrategia Core & Satellite con Interés Compuesto para Renta Variable y FIBRAs.
"""

from decimal import Decimal
import os
from typing import Dict, Any, List

# Moneda y Configuración Básica
BASE_CURRENCY = "MXN"
MARKET_TIMEZONE = "America/Mexico_City"

# Horario Bursátil Mexicano (Lunes a Viernes, 08:30 a 15:00 hrs CDMX)
MARKET_OPEN_HOUR = 8
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 0

# Tickers y Mapeos de Yahoo Finance / BMV / SIC
TICKER_MAP = {
    "CEMEX CPO": {"symbol": "CEMEXCPO.MX", "name": "Cemex CPO", "currency": "MXN", "pocket": "SATELLITE"},
    "GFINBUR O": {"symbol": "GFINBURO.MX", "name": "Grupo Financiero Inbursa", "currency": "MXN", "pocket": "SATELLITE"},
    "AMX B": {"symbol": "AMXB.MX", "name": "América Móvil B", "currency": "MXN", "pocket": "SATELLITE"},
    "INDA *": {"symbol": "INDA", "name": "iShares MSCI India ETF", "currency": "USD_SIC", "pocket": "SATELLITE"},
    "IVVPESO ISHRS": {"symbol": "IVVPESO.MX", "name": "iShares S&P 500 Peso Hedged", "currency": "MXN", "pocket": "CORE"},
    "QQQM *": {"symbol": "QQQM", "name": "Invesco NASDAQ 100 ETF", "currency": "USD_SIC", "pocket": "CORE"},
    # Nuevos Activos Recomendados para Incorporar
    "FIBRAMQ12": {"symbol": "FIBRAMQ12.MX", "name": "Fibra Macquarie (Nearshoring)", "currency": "MXN", "pocket": "CORE"},
    "FUNO11": {"symbol": "FUNO11.MX", "name": "Fibra Uno (Industrial y Comercial)", "currency": "MXN", "pocket": "CORE"},
    "SCHD *": {"symbol": "SCHD", "name": "Schwab US Dividend Equity ETF", "currency": "USD_SIC", "pocket": "CORE"},
    "VOO *": {"symbol": "VOO", "name": "Vanguard S&P 500 ETF (Dolarizado)", "currency": "USD_SIC", "pocket": "CORE"},
}

# Snapshot Verificado del Portafolio del Usuario en Actinver (Bursanet)
INITIAL_PORTFOLIO_SNAPSHOT = {
    "cash_mxn": Decimal("2.50"),
    "divisas_mxn": Decimal("632.20"),
    "stocks_etfs": {
        "FIBRAMQ12": {"titles": 67, "entry_price": Decimal("44.07"), "current_price": Decimal("44.00"), "pocket": "CORE"},
        "GFINBUR O": {"titles": 29, "entry_price": Decimal("44.44"), "current_price": Decimal("47.579655"), "pocket": "SATELLITE"},
        "IVVPESO ISHRS": {"titles": 43, "entry_price": Decimal("152.82"), "current_price": Decimal("141.00"), "pocket": "CORE"},
        "QQQM *": {"titles": 1, "entry_price": Decimal("4998.96"), "current_price": Decimal("4908.53"), "pocket": "CORE"},
    },
    "debt_funds": {
        "ACTIREN B": {"titles": 1282, "value_mxn": Decimal("13841.18"), "price": Decimal("10.796558"), "pocket": "DEFENSIVE"},
    },
    "equity_funds": {
        "ACT2060 B-1": {"titles": 2261, "value_mxn": Decimal("3155.19"), "price": Decimal("1.395486"), "pocket": "CORE"},
        "BTGALFA B1": {"titles": 1000, "value_mxn": Decimal("2499.11"), "price": Decimal("2.499116"), "pocket": "CORE"},
        "FT-GLOB BF3": {"titles": 466, "value_mxn": Decimal("2945.11"), "price": Decimal("6.319986"), "pocket": "CORE"},
    }
}

# Calendario y Prioridad de Liquidación de Fondos Dispersos ($14,553 MXN de capital latente)
MUTUAL_FUNDS_LIQUIDATION_SCHEDULE = [
    # Fase 1: Liquidación Inmediata de Posiciones Residuales y Atomizadas (Total: $1,685 MXN)
    {"symbol": "ACTIMED B", "category": "Deuda", "value_mxn": Decimal("33.28"), "settlement_days": "24h (T+1)", "phase": 1, "priority": "INMEDIATA"},
    {"symbol": "PRINFGU F1", "category": "Deuda", "value_mxn": Decimal("319.43"), "settlement_days": "24h (T+1)", "phase": 1, "priority": "INMEDIATA"},
    {"symbol": "DEUDAOP B1", "category": "Deuda", "value_mxn": Decimal("626.42"), "settlement_days": "24h (T+1)", "phase": 1, "priority": "INMEDIATA"},
    {"symbol": "SCOT-RV L", "category": "Renta Variable", "value_mxn": Decimal("706.21"), "settlement_days": "48h (T+2)", "phase": 1, "priority": "INMEDIATA"},
    # Fase 2: Liquidación de Fondos de Mayor Monto (Total: $12,868 MXN)
    {"symbol": "BTGALFA B1", "category": "Renta Variable", "value_mxn": Decimal("2410.88"), "settlement_days": "48h (T+2)", "phase": 2, "priority": "ALTA"},
    {"symbol": "FT-GLOB BF3", "category": "Renta Variable", "value_mxn": Decimal("3053.76"), "settlement_days": "48h (T+2)", "phase": 2, "priority": "ALTA"},
    {"symbol": "ACT2060 B-1", "category": "Retiro Ciclo Vida", "value_mxn": Decimal("3314.80"), "settlement_days": "48h (T+2)", "phase": 2, "priority": "ALTA"},
    {"symbol": "ACTIREN B", "category": "Deuda Mediano Plazo", "value_mxn": Decimal("4108.46"), "settlement_days": "24h (T+1)", "phase": 2, "priority": "ALTA"},
]

# Parámetros del Volante de Inercia Cruzado (Cross-Asset Flywheel: Cripto <-> Actinver)
CROSS_ASSET_FLYWHEEL_CONFIG = {
    # Nivel de Euforia / Cosecha: Si BTC supera este precio en el pico del ciclo
    "BTC_MACRO_HARVEST_PRICE_USD": Decimal("95000.00"),
    "BTC_HARVEST_FRACTION": Decimal("0.50"),  # Cosechar 50% de las ganancias para transferir a Actinver FIBRAs/Core
    # Nivel de Remate / Compra en Invierno Cripto: Si BTC cae en pánico de bear market
    "BTC_MACRO_BUY_PRICE_USD": Decimal("50000.00"),
    "FIBRA_RENT_TO_BTC_FRACTION": Decimal("0.50"),  # Destinar el 50% de las rentas cobradas a acumular BTC barato
}

# Metas de Asignación Táctica Patrimonial
MAX_EMERGING_MARKET_WEIGHT = Decimal("0.15")  # Máximo 15% en un mercado emergente como India
MIN_FIBRA_WEIGHT = Decimal("0.10")            # Mínimo 10% en FIBRAs de Nearshoring generadoras de rentas
CORE_TARGET_WEIGHT = Decimal("0.70")          # 70% en Bolsillo Core (HODL a largo plazo)
SATELLITE_TARGET_WEIGHT = Decimal("0.30")     # 30% en Bolsillo Satélite (Swing trading)

# Parámetros de Swing Trading para el Bolsillo Satélite
SWING_RSI_OVERBOUGHT = Decimal("70.0")     # Zona de toma de ganancias / venta parcial
SWING_RSI_OVERSOLD = Decimal("35.0")       # Zona de compra / acumulación con descuento
SWING_TARGET_PROFIT_PCT = Decimal("0.10")  # Meta base +10% de ganancia en swing
SWING_STOP_LOSS_PCT = Decimal("0.05")      # Freno de protección -5%
