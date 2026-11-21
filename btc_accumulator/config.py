"""
btc_accumulator/config.py
Configuration parameters, security guardrails, and asset precision definitions.
Strict adherence to financial safety and non-custodial sandbox execution.
"""

from decimal import Decimal
import os
import sys

# ==============================================================================
# SECURITY GUARDRAILS (CRITICAL & NON-NEGOTIABLE)
# ==============================================================================
# LIVE_TRADING_ENABLED MUST BE FALSE BY DEFAULT.
# Under NO circumstances should real orders be sent in this version.
LIVE_TRADING_ENABLED: bool = os.getenv("LIVE_TRADING_ENABLED", "false").lower() in ("true", "1", "yes")

# Explicit defense: forbid live trading in V1
if LIVE_TRADING_ENABLED:
    # Hard lock prevention: V1 is strictly a simulated backtest / sandbox accumulator
    raise RuntimeError(
        "CRITICAL SECURITY EXCEPTION: LIVE_TRADING_ENABLED is prohibited in BTC-Accumulator V1. "
        "Real order dispatch is permanently disabled to protect funds."
    )

# Strict prohibition of API secrets and withdrawal keys
FORBIDDEN_ENV_KEYS = [
    "BITSO_API_SECRET",
    "BITSO_PRIVATE_KEY",
    "BITSO_WITHDRAWAL_KEY",
    "API_SECRET",
    "PRIVATE_KEY"
]

def audit_security_environment() -> None:
    """Verifies that no private keys, secrets, or withdrawal permissions are present."""
    for key in FORBIDDEN_ENV_KEYS:
        if os.getenv(key):
            raise PermissionError(
                f"SECURITY VIOLATION: '{key}' detected in environment. "
                "BTC-Accumulator V1 must NOT receive or print private keys or withdrawal credentials."
            )

# Run audit on import
audit_security_environment()

# ==============================================================================
# BITSO EXCHANGE SPECIFICATIONS & PAIR SETTINGS
# ==============================================================================
# Bitso Alpha unifies USD stablecoins (predominantly USDC) under the 'btc_usd' book.
DEFAULT_BOOK: str = "btc_usd"
COMPARISON_BOOK: str = "btc_mxn"

# Bitso official fee tiers (Base tier for 30-day volume < 1,000 USD)
# btc_usd: 0.30% maker, 0.36% taker
DEFAULT_MAKER_FEE_RATE: Decimal = Decimal("0.0030")
DEFAULT_TAKER_FEE_RATE: Decimal = Decimal("0.0036")

# Comparison fees for btc_mxn: 0.60% maker, 0.78% taker
MXN_MAKER_FEE_RATE: Decimal = Decimal("0.0060")
MXN_TAKER_FEE_RATE: Decimal = Decimal("0.0078")

# Bitso Public Market Constraints (Queried from /v3/available_books/)
# For btc_usd:
BTC_USD_MIN_AMOUNT: Decimal = Decimal("0.00000060")  # 60 satoshis
BTC_USD_MIN_VALUE: Decimal = Decimal("0.50")        # 0.50 USD / USDC
BTC_USD_TICK_SIZE: Decimal = Decimal("1.0")         # 1.0 USD
BTC_USD_MAX_AMOUNT: Decimal = Decimal("600.0")

# For btc_mxn:
BTC_MXN_MIN_AMOUNT: Decimal = Decimal("0.00000060")  # 60 satoshis
BTC_MXN_MIN_VALUE: Decimal = Decimal("10.0")        # 10.0 MXN
BTC_MXN_TICK_SIZE: Decimal = Decimal("10.0")        # 10.0 MXN

# Internal Unit Precisions
SATOSHIS_PER_BTC: Decimal = Decimal("100000000")    # 1 BTC = 10^8 satoshis
BTC_DECIMAL_PLACES: int = 8
USDC_DECIMAL_PLACES: int = 2

# ==============================================================================
# STRATEGY EXPERIMENTAL HYPOTHETICAL ALLOCATION & RULES
# ==============================================================================
# Hypothetical capital per trade: 10 USDC equivalent in BTC
CAPITAL_PER_TRADE_USDC: Decimal = Decimal("10.00")

# Strategy Signal Parameters (4-Hour Closed Candles)
CANDLE_TIMEFRAME_HOURS: int = 4
RSI_PERIOD: int = 14
RSI_ENTRY_THRESHOLD: Decimal = Decimal("65.0")      # RSI(14) >= 65

ADX_PERIOD: int = 14
ADX_ENTRY_THRESHOLD: Decimal = Decimal("20.0")      # ADX(14) < 20 (ranging/consolidation)

SMA_PERIOD: int = 50
MAX_SMA_DEVIATION_PCT: Decimal = Decimal("0.05")    # |Close - SMA(50)| / SMA(50) < 5%

# Execution Rules
POST_ONLY_TIMEOUT_HOURS: int = 2                   # Cancel maker sell if not filled in 2h
BUYBACK_TARGET_DISCOUNT: Decimal = Decimal("0.025") # Re-buy 2.5% below sell price (Profit target in BTC)
DEFENSIVE_STOP_PREMIUM: Decimal = Decimal("0.030")  # Defensive exit if price rises 3% above sell price
MAX_HOLDING_DAYS: int = 7                           # 7 days max time in USDC before emergency re-buy
MAX_HOLDING_CANDLES_4H: int = MAX_HOLDING_DAYS * 6  # 42 candles (42 * 4h = 168 hours = 7 days)

# Slippage Simulation Defaults
DEFAULT_MAKER_SLIPPAGE_BPS: Decimal = Decimal("0.0")    # Post-only limit orders don't cross spread
DEFAULT_TAKER_SLIPPAGE_BPS: Decimal = Decimal("0.0005") # 5 basis points (0.05%) for market/defensive stops
