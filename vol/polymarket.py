"""Polymarket public data: search markets by topic, pull daily probability history.

No key needed. Gamma API = discovery; CLOB API = prices.
Note: Gamma returns outcomes / clobTokenIds as JSON *strings* inside JSON.
"""
from __future__ import annotations

import json

import pandas as pd

from .http import get_json

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


def _loads(x):
    if isinstance(x, str):
        try:
            return json.loads(x)
        except ValueError:
            return []
    return x or []


def search(query: str, limit: int = 20) -> pd.DataFrame:
    """Markets matching a topic, biggest volume first."""
    data = get_json(
        f"{GAMMA}/public-search",
        params={"q": query, "limit_per_type": limit, "events_status": "all"},
    )
    rows = []
    for ev in data.get("events") or []:
        for m in ev.get("markets") or []:
            tokens = _loads(m.get("clobTokenIds"))
            if not tokens:
                continue
            rows.append(
                {
                    "question": m.get("question") or ev.get("title"),
                    "event": ev.get("title"),
                    "volume_usd": float(m.get("volumeNum") or m.get("volume") or 0),
                    "end_date": (m.get("endDate") or "")[:10],
                    "closed": bool(m.get("closed")),
                    "yes_token": tokens[0],
                }
            )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.drop_duplicates("yes_token").sort_values("volume_usd", ascending=False).reset_index(drop=True)


def history(yes_token: str) -> pd.Series:
    """Daily 'Yes' probability (0-1) for a market, indexed by date."""
    pts = []
    for params in (
        {"market": yes_token, "interval": "max", "fidelity": 1440},
        {"market": yes_token, "interval": "all", "fidelity": 1440},
    ):
        try:
            pts = get_json(f"{CLOB}/prices-history", params=params, retries=1).get("history") or []
        except Exception:
            pts = []
        if pts:
            break
    if not pts:
        return pd.Series(dtype=float)
    s = pd.Series(
        [float(p["p"]) for p in pts],
        index=pd.to_datetime([p["t"] for p in pts], unit="s").normalize(),
    )
    return s.groupby(level=0).last()


def biggest_swings(prob: pd.Series, n: int = 10) -> pd.DataFrame:
    """Largest one-day probability moves, in percentage points."""
    chg = prob.diff() * 100
    top = chg.abs().nlargest(n).index
    return pd.DataFrame({"date": top, "prob_after": prob[top].values * 100, "move_pts": chg[top].values})
