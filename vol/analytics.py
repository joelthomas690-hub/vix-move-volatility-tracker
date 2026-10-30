"""Spike detection, lead/lag, and event studies. Pure pandas, no network."""
from __future__ import annotations

import numpy as np
import pandas as pd


def add_features(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Daily % change and a rolling z-score of that change for each index.

    The z-score uses the *previous* `window` days only, so a spike can't
    inflate its own baseline.
    """
    out = df.copy()
    for col in ["VIX", "MOVE"]:
        if col not in out or out[col].dropna().empty:
            continue
        s = out[col].ffill()
        chg = s.pct_change() * 100
        mu = chg.shift(1).rolling(window, min_periods=window // 2).mean()
        sd = chg.shift(1).rolling(window, min_periods=window // 2).std()
        out[f"{col}_chg"] = chg
        out[f"{col}_z"] = (chg - mu) / sd
        out[f"{col}_pctile"] = s.rolling(252, min_periods=60).rank(pct=True) * 100
    if "MOVE" in out and "VIX" in out:
        out["MOVE_VIX_ratio"] = out["MOVE"] / out["VIX"]
    return out


def find_spikes(feat: pd.DataFrame, z: float = 2.0, min_move_pct: float = 5.0) -> pd.DataFrame:
    """Days where either index rose with z >= threshold AND at least min_move_pct %.

    Returns one row per spike day with which index spiked and which one moved first
    (looking at the 3 trading days before).
    """
    rows = []
    for date, r in feat.iterrows():
        hits = []
        for col in ["VIX", "MOVE"]:
            zc, chg = r.get(f"{col}_z"), r.get(f"{col}_chg")
            if pd.notna(zc) and zc >= z and pd.notna(chg) and chg >= min_move_pct:
                hits.append(col)
        if hits:
            rows.append(
                {
                    "date": date,
                    "spiked": " + ".join(hits),
                    "VIX": r.get("VIX"),
                    "VIX_chg": r.get("VIX_chg"),
                    "VIX_z": r.get("VIX_z"),
                    "MOVE": r.get("MOVE"),
                    "MOVE_chg": r.get("MOVE_chg"),
                    "MOVE_z": r.get("MOVE_z"),
                    "led_by": _who_led(feat, date),
                }
            )
    return pd.DataFrame(rows)


def _who_led(feat: pd.DataFrame, date, lookback: int = 3) -> str:
    """Which index had the larger cumulative z-score in the days just before."""
    if "MOVE_z" not in feat:
        return "n/a"
    idx = feat.index.get_loc(date)
    win = feat.iloc[max(0, idx - lookback) : idx]
    v, m = win["VIX_z"].clip(lower=0).sum(), win["MOVE_z"].clip(lower=0).sum()
    if max(v, m) < 1.5:
        return "neither (sudden)"
    if abs(v - m) < 0.75:
        return "together"
    return "rates (MOVE) first" if m > v else "equities (VIX) first"


def match_events(spikes: pd.DataFrame, events: pd.DataFrame, tolerance_days: int = 1) -> pd.DataFrame:
    """Attach scheduled/curated events within +/- tolerance calendar days of each spike."""
    if spikes.empty:
        return spikes.assign(nearby_events="")
    labels = []
    for d in spikes["date"]:
        near = events[(events["date"] - d).abs() <= pd.Timedelta(days=tolerance_days)]
        labels.append("; ".join(f"{t}: {l}" for t, l in zip(near["type"], near["label"])))
    return spikes.assign(nearby_events=labels)


def event_study(feat: pd.DataFrame, events: pd.DataFrame, event_type: str) -> dict:
    """Compare absolute daily moves on event days vs all other days."""
    days = set(events.loc[events["type"] == event_type, "date"])
    is_event = feat.index.isin(days)
    res = {"event_type": event_type, "n_event_days": int(is_event.sum())}
    for col in ["VIX", "MOVE"]:
        c = f"{col}_chg"
        if c not in feat:
            continue
        a = feat[c].abs()
        res[f"{col}_event_avg"] = float(a[is_event].mean()) if is_event.any() else np.nan
        res[f"{col}_other_avg"] = float(a[~is_event].mean())
        res[f"{col}_spike_rate"] = (
            float((feat.loc[is_event, f"{col}_z"] >= 2).mean() * 100) if is_event.any() else np.nan
        )
    return res
