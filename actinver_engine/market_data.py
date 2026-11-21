"""
actinver_engine/market_data.py
Módulo de Datos de Mercado Bursátil en Vivo para BMV y SIC.
Consulta cotizaciones públicas en tiempo real (CERO CLAVES PRIVADAS).
Calcula indicadores técnicos de Swing Trading (RSI, Medias Móviles y Bandas Bollinger).
"""

from decimal import Decimal
import json
import logging
import time
from typing import Dict, Any, Optional, List, Tuple
import urllib.request
import urllib.parse
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class ActinverMarketDataClient:
    """Fetches real-time stock and ETF quotes and historical candles from public market sources."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    def fetch_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetches current price and day change for a given symbol.
        Works for BMV (.MX) and US ETFs.
        """
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range=5d"
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                result = data.get("chart", {}).get("result")
                if not result:
                    return None
                meta = result[0].get("meta", {})
                current_price = meta.get("regularMarketPrice")
                prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
                currency = meta.get("currency", "MXN")

                pct_change = 0.0
                if prev_close and prev_close > 0 and current_price:
                    pct_change = ((current_price - prev_close) / prev_close) * 100.0

                return {
                    "symbol": symbol,
                    "price": Decimal(str(current_price)) if current_price is not None else None,
                    "prev_close": Decimal(str(prev_close)) if prev_close is not None else None,
                    "pct_change": round(pct_change, 2),
                    "currency": currency,
                    "timestamp": time.time(),
                }
        except Exception as e:
            logger.warning(f"Aviso de consulta de mercado para {symbol}: {e}")
            return None

    def fetch_historical_candles(self, symbol: str, range_period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
        """Fetches historical OHLCV candles to compute RSI, SMA50, and Bollinger Bands."""
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval={interval}&range={range_period}"
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                result = data.get("chart", {}).get("result")
                if not result:
                    return pd.DataFrame()
                
                res = result[0]
                timestamps = res.get("timestamp", [])
                indicators = res.get("indicators", {}).get("quote", [{}])[0]
                
                df = pd.DataFrame({
                    "timestamp": pd.to_datetime(timestamps, unit="s", utc=True),
                    "open": indicators.get("open", []),
                    "high": indicators.get("high", []),
                    "low": indicators.get("low", []),
                    "close": indicators.get("close", []),
                    "volume": indicators.get("volume", []),
                })
                # Drop rows with null close
                df = df.dropna(subset=["close"]).reset_index(drop=True)
                return df
        except Exception as e:
            logger.warning(f"Error descargando historial para {symbol}: {e}")
            return pd.DataFrame()

    def calculate_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Adds RSI 14, SMA 50, SMA 200, and Bollinger Bands to candle dataframe."""
        if df.empty or len(df) < 15:
            return df

        df = df.copy()

        # SMA 50 and SMA 200
        df["sma_50"] = df["close"].rolling(window=50, min_periods=10).mean()
        df["sma_200"] = df["close"].rolling(window=200, min_periods=30).mean()

        # Bollinger Bands (20-day, 2 std)
        bb_sma = df["close"].rolling(window=20, min_periods=10).mean()
        bb_std = df["close"].rolling(window=20, min_periods=10).std()
        df["bb_upper"] = bb_sma + (bb_std * 2)
        df["bb_lower"] = bb_sma - (bb_std * 2)
        df["bb_mid"] = bb_sma

        # RSI 14
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=14, min_periods=14).mean()
        avg_loss = loss.rolling(window=14, min_periods=14).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        df["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))
        df["rsi_14"] = df["rsi_14"].fillna(50.0)

        return df

    def get_market_analysis(self, symbol: str) -> Dict[str, Any]:
        """Provides full technical analysis for a stock/ETF."""
        df = self.fetch_historical_candles(symbol)
        if df.empty:
            quote = self.fetch_quote(symbol)
            price = quote["price"] if quote else Decimal("0")
            return {
                "symbol": symbol,
                "price": price,
                "rsi_14": Decimal("50.0"),
                "sma_50": price,
                "sma_200": price,
                "bb_upper": price,
                "bb_lower": price,
                "trend": "NEUTRAL",
                "condition": "NEUTRAL",
            }

        df = self.calculate_technical_indicators(df)
        latest = df.iloc[-1]
        price = Decimal(str(round(latest["close"], 2)))
        rsi = Decimal(str(round(latest["rsi_14"], 1)))
        sma_50 = Decimal(str(round(latest.get("sma_50", latest["close"]), 2)))
        sma_200 = Decimal(str(round(latest.get("sma_200", latest["close"]), 2)))

        # Trend analysis
        if price > sma_50 and sma_50 > sma_200:
            trend = "BULLISH_STRONG"
        elif price > sma_50:
            trend = "BULLISH_RECOVERY"
        elif price < sma_50 and price < sma_200:
            trend = "BEARISH"
        else:
            trend = "SIDEWAYS"

        # Overbought / Oversold Condition
        if rsi >= Decimal("70.0"):
            condition = "OVERBOUGHT_TAKE_PROFIT"
        elif rsi <= Decimal("35.0"):
            condition = "OVERSOLD_ACCUMULATE"
        else:
            condition = "NEUTRAL"

        return {
            "symbol": symbol,
            "price": price,
            "rsi_14": rsi,
            "sma_50": sma_50,
            "sma_200": sma_200,
            "trend": trend,
            "condition": condition,
        }
