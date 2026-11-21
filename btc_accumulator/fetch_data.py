"""
btc_accumulator/fetch_data.py
Reproducible fetcher and data integrity verifier for Bitso Alpha historical data (V1.3).
Downloads 4-Hour signals data and 1-Hour high-resolution execution data.
Verifies continuity, zero gaps, excludes unclosed candles, and contrasts against benchmark dates.
"""

from datetime import datetime, timezone
import json
import logging
import os
import urllib.request
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DataFetcher")

BASE_URL = "https://api.bitso.com/v3/ohlc/?book=btc_usd"

# Known external historical market benchmarks for independent validation
BENCHMARK_PRICES = {
    "2022-01-01": {"expected_close_approx": 46834.0, "tolerance_pct": 0.05},
    "2022-11-21": {"expected_close_approx": 16046.0, "tolerance_pct": 0.05},
    "2023-01-01": {"expected_close_approx": 16578.0, "tolerance_pct": 0.05},
    "2024-03-14": {"expected_close_approx": 73337.0, "tolerance_pct": 0.05},
    "2024-12-31": {"expected_close_approx": 92328.0, "tolerance_pct": 0.05},
}


def download_ohlc_dataset(time_bucket: int, start_ms: int = 1640995200000) -> pd.DataFrame:
    """Queries Bitso Alpha public OHLC endpoint for a specified time_bucket in seconds."""
    url = f"{BASE_URL}&time_bucket={time_bucket}&start={start_ms}"
    logger.info(f"Querying Bitso OHLC (bucket={time_bucket}s): {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "BTC-Accumulator-V1.3/AuditableFetcher"})

    with urllib.request.urlopen(req, timeout=45) as resp:
        raw_json = json.loads(resp.read().decode("utf-8"))

    if not raw_json.get("success", False):
        raise RuntimeError(f"Bitso API error response: {raw_json.get('error')}")

    payload = raw_json["payload"]
    logger.info(f"Received {len(payload):,} candles for bucket {time_bucket}s.")

    df = pd.DataFrame(payload)
    df["timestamp"] = pd.to_datetime(df["bucket_start_time"], unit="ms", utc=True)
    df = df.rename(columns={
        "first_rate": "open",
        "max_rate": "high",
        "min_rate": "low",
        "last_rate": "close",
        "trade_count": "trades"
    })

    for col in ["open", "high", "low", "close", "volume", "vwap"]:
        df[col] = df[col].astype(float)

    # Exclude currently unclosed candle
    now_utc = datetime.now(timezone.utc)
    duration_ms = time_bucket * 1000
    closed_mask = (df["bucket_start_time"] + duration_ms) <= int(now_utc.timestamp() * 1000)
    unclosed_count = len(df) - closed_mask.sum()
    if unclosed_count > 0:
        logger.info(f"Excluding {unclosed_count} unclosed candle(s) for bucket {time_bucket}s.")
    df = df[closed_mask].copy()

    # Sort and remove duplicates
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)

    # Invariant checks
    assert df["timestamp"].is_monotonic_increasing, "Timestamps not monotonic."
    assert not df[["open", "high", "low", "close"]].isnull().any().any(), "Null prices detected."
    assert (df["high"] >= df["low"]).all(), "High < Low detected."

    # Gap checks
    diffs = df["timestamp"].diff().dropna()
    expected_delta = pd.Timedelta(seconds=time_bucket)
    gaps = (diffs > expected_delta).sum()
    if gaps > 0:
        logger.warning(f"Detected {gaps} gaps greater than {time_bucket}s in dataset!")
    else:
        logger.info(f"Continuity check PASSED: Exactly 0 gaps > {time_bucket}s.")

    clean_cols = ["timestamp", "bucket_start_time", "open", "high", "low", "close", "volume", "vwap", "trades"]
    return df[clean_cols]


def verify_against_benchmarks(df: pd.DataFrame) -> bool:
    """Verifies that key dates in the dataset closely match global BTC benchmark prices."""
    df_ts = df.set_index("timestamp")
    all_matched = True
    for date_str, bench in BENCHMARK_PRICES.items():
        matching = df[df["timestamp"].dt.strftime("%Y-%m-%d") == date_str]
        if matching.empty:
            logger.warning(f"Benchmark date {date_str} not found in dataset!")
            all_matched = False
            continue
        actual_close = matching.iloc[0]["close"]
        expected = bench["expected_close_approx"]
        pct_diff = abs(actual_close - expected) / expected
        if pct_diff <= bench["tolerance_pct"]:
            logger.info(f"Benchmark {date_str}: Bitso Close=${actual_close:,.2f} vs Ref=${expected:,.2f} (Diff: {pct_diff*100:.2f}%) - PASSED")
        else:
            logger.warning(f"Benchmark {date_str} exceeded tolerance: Bitso=${actual_close} vs Ref=${expected}")
            all_matched = False
    return all_matched


def fetch_and_save_all(data_dir: str) -> None:
    os.makedirs(data_dir, exist_ok=True)

    # 1. 4-Hour Dataset (Signals)
    df_4h = download_ohlc_dataset(time_bucket=14400)
    path_4h = os.path.join(data_dir, "bitso_btc_usd_4h.csv")
    df_4h.to_csv(path_4h, index=False)
    logger.info(f"Saved 4H dataset ({len(df_4h):,} candles) to {path_4h}")

    # 2. 1-Hour Dataset (High-resolution execution window)
    df_1h = download_ohlc_dataset(time_bucket=3600)
    path_1h = os.path.join(data_dir, "bitso_btc_usd_1h.csv")
    df_1h.to_csv(path_1h, index=False)
    logger.info(f"Saved 1H dataset ({len(df_1h):,} candles) to {path_1h}")

    # 3. Independent Benchmark Verification
    logger.info("Running independent benchmark verification...")
    passed = verify_against_benchmarks(df_4h)
    if passed:
        logger.info("Independent verification complete: Bitso historical prices conform to global benchmarks.")
    else:
        logger.warning("Independent verification encountered discrepancies.")


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_directory = os.path.join(current_dir, "..", "data")
    fetch_and_save_all(data_directory)
