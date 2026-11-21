"""
btc_accumulator/indicators.py
Deterministic implementation of technical indicators:
- RSI(14) with Wilder's exponential smoothing
- ADX(14) with True Range and Directional Movement (DMI)
- SMA(50) and percentage price deviation
- Multi-timeframe Macro Regime & Bull Run Detector:
  * SMA(50D) = 300 candles of 4H (50 days)
  * SMA(200D) = 1,200 candles of 4H (200 days)
  * Golden Cross detection
  * Volatility Squeeze & Expansion (Bollinger Bandwidth)
"""

import numpy as np
import pandas as pd


def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    """Calculates Simple Moving Average (SMA)."""
    return series.rolling(window=period, min_periods=period).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculates Relative Strength Index (RSI) using classic Wilder's smoothing.
    Wilder's Smoothing: ewm(alpha=1/period, adjust=False).
    """
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder's smoothing
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    # Avoid division by zero
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # Boundary conditions when loss is 0
    rsi = rsi.where(avg_loss != 0, 100.0)
    rsi = rsi.where(avg_gain != 0, 0.0)
    return rsi


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Calculates Wilder's Average Directional Index (ADX) along with +DI, -DI, and TR.
    Expects columns: 'high', 'low', 'close'.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    prev_high = high.shift(1)
    prev_low = low.shift(1)

    # True Range (TR)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Directional Movement (+DM and -DM)
    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_dm_series = pd.Series(plus_dm, index=df.index)
    minus_dm_series = pd.Series(minus_dm, index=df.index)

    # Wilder's smoothing of TR and DMs
    tr_smooth = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    plus_dm_smooth = plus_dm_series.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    minus_dm_smooth = minus_dm_series.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    # Directional Indicators (+DI, -DI)
    plus_di = 100.0 * (plus_dm_smooth / tr_smooth.replace(0, np.nan))
    minus_di = 100.0 * (minus_dm_smooth / tr_smooth.replace(0, np.nan))

    # Directional Index (DX)
    di_sum = plus_di + minus_di
    di_diff = (plus_di - minus_di).abs()
    dx = 100.0 * (di_diff / di_sum.replace(0, np.nan))
    dx = dx.fillna(0.0)

    # Average Directional Index (ADX)
    adx = dx.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    result = pd.DataFrame({
        "tr": tr,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "dx": dx,
        "adx": adx
    }, index=df.index)
    return result


def calculate_sma_deviation(close: pd.Series, sma: pd.Series) -> pd.Series:
    """Calculates absolute percentage deviation from SMA: |Close - SMA| / SMA."""
    return (close - sma).abs() / sma.replace(0, np.nan)


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes and adds all strategy indicators and macro regime markers to the dataframe.
    Ensures calculations use only present and past data (zero lookahead).
    """
    df = df.copy()

    # 1. Primary strategy indicators (4-Hour resolution)
    df["rsi_14"] = calculate_rsi(df["close"], period=14)
    adx_df = calculate_adx(df, period=14)
    df["adx_14"] = adx_df["adx"]
    df["plus_di"] = adx_df["plus_di"]
    df["minus_di"] = adx_df["minus_di"]

    df["sma_50"] = calculate_sma(df["close"], period=50)
    df["sma_50_dev"] = calculate_sma_deviation(df["close"], df["sma_50"])

    # 2. Daily-equivalent Macro Regime Indicators (6 candles per 24 hours)
    # 50 Days = 300 candles of 4H
    # 200 Days = 1,200 candles of 4H
    df["sma_50d"] = calculate_sma(df["close"], period=300)
    df["sma_200d"] = calculate_sma(df["close"], period=1200)

    # Golden Cross: SMA 50D > SMA 200D
    df["golden_cross"] = (df["sma_50d"] > df["sma_200d"]).fillna(False)

    # 3. Volatility Squeeze & Expansion (Bollinger Bandwidth on 20-day window = 120 candles)
    bb_mid = df["close"].rolling(window=120).mean()
    bb_std = df["close"].rolling(window=120).std()
    df["bb_upper"] = bb_mid + (2 * bb_std)
    df["bb_lower"] = bb_mid - (2 * bb_std)
    df["bb_bandwidth"] = (df["bb_upper"] - df["bb_lower"]) / bb_mid.replace(0, np.nan)

    # 4. Macro Bull Run Active Detector
    # A true Bull Run is active when:
    # 1) Price is above the 200-day institutional SMA (or within 2% of breakout)
    # 2) Golden cross is active (SMA 50D > SMA 200D)
    # 3) Presión compradora domina: plus_di > minus_di
    df["bull_run_active"] = (
        (df["close"] > df["sma_200d"]) &
        df["golden_cross"] &
        (df["plus_di"] >= df["minus_di"])
    ).fillna(False)

    # 5. Descriptive Regime Classification for telemetry
    conditions = [
        df["bull_run_active"],
        (df["close"] > df["sma_200d"]) & df["golden_cross"],
        (df["close"] < df["sma_200d"]) & (~df["golden_cross"]),
    ]
    choices = ["BULL_RUN", "BULL_TRANSITION", "BEAR"]
    df["regime"] = np.select(conditions, choices, default="RANGE")

    return df
