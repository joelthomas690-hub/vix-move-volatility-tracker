"""Daily VIX and MOVE closes, with a local CSV cache.

VIX: Yahoo Finance (^VIX), falling back to FRED (VIXCLS, no key needed).
MOVE: Yahoo Finance (^MOVE). ICE owns MOVE and it is not on FRED.
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_FILE = DATA_DIR / "vol_cache.csv"
CACHE_MAX_AGE_HOURS = 12
TICKERS = {"VIX": "^VIX", "MOVE": "^MOVE"}


def _from_yahoo(symbol: str, start: str) -> pd.Series:
    import yfinance as yf

    df = yf.download(symbol, start=start, progress=False, auto_adjust=False)
    if df is None or df.empty:
        return pd.Series(dtype=float)
    close = df["Close"]
    if isinstance(close, pd.DataFrame):  # newer yfinance returns multi-index columns
        close = close.iloc[:, 0]
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    return close.astype(float)


def _vix_from_fred(start: str) -> pd.Series:
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "VIX"]
    df["date"] = pd.to_datetime(df["date"])
    df["VIX"] = pd.to_numeric(df["VIX"], errors="coerce")
    s = df.dropna().set_index("date")["VIX"]
    return s[s.index >= start]


def fetch_vol(start: str = "2018-01-01") -> pd.DataFrame:
    """Download both indexes. Returns DataFrame indexed by date with VIX, MOVE."""
    out = {}
    for name, symbol in TICKERS.items():
        try:
            out[name] = _from_yahoo(symbol, start)
        except Exception:
            out[name] = pd.Series(dtype=float)
    if out["VIX"].empty:
        out["VIX"] = _vix_from_fred(start)
    df = pd.DataFrame(out).sort_index()
    df.index.name = "date"
    return df.dropna(how="all")


def load_vol(start: str = "2018-01-01", force_refresh: bool = False) -> tuple[pd.DataFrame, str]:
    """Return (data, status message). Uses the cache when fresh or when offline."""
    DATA_DIR.mkdir(exist_ok=True)
    cache_ok = CACHE_FILE.exists() and (
        datetime.now() - datetime.fromtimestamp(CACHE_FILE.stat().st_mtime)
        < timedelta(hours=CACHE_MAX_AGE_HOURS)
    )
    if cache_ok and not force_refresh:
        return _read_cache(), "Loaded from cache"
    try:
        df = fetch_vol(start)
        if df.empty or df["VIX"].dropna().empty:
            raise RuntimeError("no data returned")
        df.to_csv(CACHE_FILE)
        msg = "Downloaded fresh data"
        if df["MOVE"].dropna().empty:
            msg += " (MOVE unavailable from Yahoo right now - showing VIX only)"
        return df, msg
    except Exception as e:
        if CACHE_FILE.exists():
            return _read_cache(), f"Download failed ({e}); using older cache"
        raise


def _read_cache() -> pd.DataFrame:
    return pd.read_csv(CACHE_FILE, index_col="date", parse_dates=True)
