"""Kalshi public market data -> a 'surprise score' for each settled event.

No API key needed. Kalshi structure: Series (e.g. Fed decisions) -> Events
(one meeting) -> Markets (one outcome each, e.g. "Hold", "Cut 25bp").

Surprise score for an event = the largest gap between what a market priced the
day before and how it actually settled (1 = yes, 0 = no).
  0.0 -> the market fully expected the outcome
  1.0 -> the market was completely blindsided
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from .http import get_json

BASE = "https://api.elections.kalshi.com/trade-api/v2"
SUGGESTED_SERIES = ["KXFEDDECISION", "KXFED", "KXCPIYOY", "KXCPI", "KXPAYROLLS"]


def list_series(category: str = "Economics") -> pd.DataFrame:
    data = get_json(f"{BASE}/series", params={"category": category})
    rows = [{"ticker": s.get("ticker"), "title": s.get("title")} for s in data.get("series") or []]
    return pd.DataFrame(rows)


def settled_events(series_ticker: str, max_pages: int = 10) -> list[dict]:
    events, cursor = [], None
    for _ in range(max_pages):
        params = {
            "series_ticker": series_ticker,
            "status": "settled",
            "with_nested_markets": "true",
            "limit": 200,
        }
        if cursor:
            params["cursor"] = cursor
        data = get_json(f"{BASE}/events", params=params)
        events.extend(data.get("events") or [])
        cursor = data.get("cursor")
        if not cursor:
            break
    return events


def _num(x):
    """Kalshi returns cents as ints, or dollars as strings in newer fields."""
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _candle_price(c: dict):
    """Probability (0-1) from one candlestick, trying the known field layouts."""
    price = c.get("price") or {}
    for key, scale in (("close_dollars", 1), ("close", 100)):
        v = _num(price.get(key))
        if v is not None:
            return v / scale
    bid, ask = c.get("yes_bid") or {}, c.get("yes_ask") or {}
    for key, scale in (("close_dollars", 1), ("close", 100)):
        b, a = _num(bid.get(key)), _num(ask.get(key))
        if b is not None and a is not None:
            return (b + a) / 2 / scale
    return None


def price_before(series_ticker: str, market: dict, cutoff: datetime) -> float | None:
    """Implied probability of `market` at the last daily close before `cutoff`."""
    ticker = market["ticker"]
    end_ts = int(cutoff.timestamp())
    start_ts = end_ts - 10 * 86400
    params = {"start_ts": start_ts, "end_ts": end_ts, "period_interval": 1440}
    for url in (
        f"{BASE}/series/{series_ticker}/markets/{ticker}/candlesticks",
        f"{BASE}/historical/markets/{ticker}/candlesticks",
    ):
        try:
            candles = get_json(url, params=params, retries=0).get("candlesticks") or []
        except Exception:
            continue
        prices = [p for p in (_candle_price(c) for c in candles) if p is not None]
        if prices:
            return prices[-1]
    # Fallback: last trade before the cutoff
    try:
        trades = get_json(
            f"{BASE}/markets/trades", params={"ticker": ticker, "max_ts": end_ts, "limit": 1}, retries=0
        ).get("trades") or []
        if trades:
            t = trades[0]
            v = _num(t.get("yes_price_dollars"))
            return v if v is not None else _num(t.get("yes_price")) / 100
    except Exception:
        pass
    return None


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def surprise_table(series_ticker: str, max_events: int = 40, progress=None) -> pd.DataFrame:
    """One row per settled event: date, title, expected outcome, actual outcome, surprise."""
    events = settled_events(series_ticker)
    events = sorted(
        events,
        key=lambda e: max((m.get("close_time") or "") for m in e.get("markets") or [{}]),
        reverse=True,
    )[:max_events]
    rows = []
    for i, ev in enumerate(events):
        if progress:
            progress((i + 1) / max(len(events), 1), ev.get("title", ""))
        markets = [m for m in ev.get("markets") or [] if m.get("result") in ("yes", "no")]
        if not markets:
            continue
        close = max(_parse_ts(m["close_time"]) for m in markets if m.get("close_time"))
        # Cutoff = midnight UTC on the decision day -> prior day's close.
        cutoff = close.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        priced = []
        for m in markets:
            p = price_before(series_ticker, m, cutoff)
            if p is not None:
                outcome = 1.0 if m["result"] == "yes" else 0.0
                label = m.get("yes_sub_title") or m.get("subtitle") or m["ticker"]
                priced.append((label, p, outcome))
        if not priced:
            continue
        expected = max(priced, key=lambda x: x[1])
        actual = [lbl for lbl, _, o in priced if o == 1.0]
        rows.append(
            {
                "date": pd.Timestamp(close.astimezone(timezone.utc).date()),
                "event": ev.get("title") or ev.get("event_ticker"),
                "market_expected": f"{expected[0]} ({expected[1]:.0%})",
                "actual": ", ".join(actual) if actual else "-",
                "surprise": max(abs(o - p) for _, p, o in priced),
            }
        )
    return pd.DataFrame(rows)
