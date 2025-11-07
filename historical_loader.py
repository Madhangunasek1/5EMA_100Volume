# historical_loader.py
# ------------------------------------------------------
# Fetch last 400 (historical + intraday) candles for each instrument
# Save to /candle_data/<instrument>.csv
# Then DataHandler will continue live from the latest timestamp
# ------------------------------------------------------

import os
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import upstox_client
import logging

# -------- CONFIG ---------
CANDLE_DIR = "candle_data"
os.makedirs(CANDLE_DIR, exist_ok=True)

# Limit total candles
MAX_CANDLES = 400

# --------------------------
def _extract_candles(resp):
    try:
        candles = getattr(getattr(resp, "data", None), "candles", None)
        if candles is not None:
            return candles
    except Exception:
        pass
    if isinstance(resp, dict):
        return resp.get("data", {}).get("candles", []) or []
    try:
        return resp["data"]["candles"]
    except Exception:
        return []


def candles_to_df(candles):
    """Convert Upstox candle array -> clean DataFrame."""
    if not candles:
        return pd.DataFrame(columns=["open","high","low","close","volume","open_interest"])
    base_cols = ["timestamp","open","high","low","close","volume","open_interest"]
    cols = base_cols[:len(candles[0])]
    df = pd.DataFrame(candles, columns=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert("Asia/Kolkata")
    df = df.sort_values("timestamp").set_index("timestamp")
    for c in ["open","high","low","close","volume","open_interest"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def fetch_historical_df(api, instrument_key, unit, interval, to_date, from_date=None):
    """Fetch historical candles till yesterday."""
    if from_date:
        resp = api.get_historical_candle_data1(instrument_key, unit, interval, to_date, from_date)
    else:
        resp = api.get_historical_candle_data(instrument_key, unit, interval, to_date)
    return candles_to_df(_extract_candles(resp))


def fetch_intraday_df(api, instrument_key, unit="minutes", interval="5"):
    """Fetch today's intraday data."""
    resp = api.get_intra_day_candle_data(instrument_key, unit, interval)
    return candles_to_df(_extract_candles(resp))


def get_continuous_candles(api, instrument_key, unit="minutes", interval="5", tz="Asia/Kolkata"):
    """Fetch and combine Historical (till yesterday) + Intraday (today)."""
    today = datetime.now(ZoneInfo(tz)).date()
    yday = today - timedelta(days=1)
    start = today - timedelta(days=40)  # ~400 candles if 5-min × 75/day
    frames = []

    # Historical till yesterday
    df_hist = fetch_historical_df(api, instrument_key, unit, interval, yday.isoformat(), start.isoformat())
    frames.append(df_hist)

    # Intraday today
    df_id = fetch_intraday_df(api, instrument_key, unit, interval)
    if not df_id.empty:
        df_id = df_id[df_id.index.date == today]
        frames.append(df_id)

    if not frames:
        return pd.DataFrame(columns=["open","high","low","close","volume","open_interest"])

    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.tail(MAX_CANDLES)  # keep only last 400

    return df[["open","high","low","close","volume","open_interest"]]


def preload_candles(access_token, instruments):
    """Fetch and store last 400 candles for each instrument."""
    logging.info("🕒 Fetching historical + intraday candles...")

    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    api = upstox_client.HistoryV3Api(upstox_client.ApiClient(configuration))

    all_dfs = {}
    for symbol in instruments:
        try:
            df = get_continuous_candles(api, instrument_key=symbol)
            if not df.empty:
                path = os.path.join(CANDLE_DIR, f"{symbol.replace('|','_')}.csv")
                df.to_csv(path)
                all_dfs[symbol] = df
                logging.info(f"✅ Saved {len(df)} candles for {symbol} -> {path}")
            else:
                logging.warning(f"⚠️ No data fetched for {symbol}")
        except Exception as e:
            logging.error(f"❌ Failed fetching {symbol}: {e}", exc_info=True)

    return all_dfs