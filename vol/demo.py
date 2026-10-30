"""Synthetic data so the dashboard runs with no internet (demo mode).

Shapes match the real loaders exactly; numbers are made up.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def demo_vol(start: str = "2018-01-01", seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, pd.Timestamp.today().normalize())
    n = len(idx)
    vix, move = np.empty(n), np.empty(n)
    vix[0], move[0] = 15.0, 70.0
    shocks = {
        "2018-02-05": (1.0, 0.2), "2020-03-09": (0.35, 0.4), "2020-03-16": (0.45, 0.3),
        "2022-06-13": (0.25, 0.25), "2022-09-28": (0.1, 0.25), "2023-03-13": (0.2, 0.35),
        "2024-08-05": (0.65, 0.1), "2025-04-03": (0.4, 0.15), "2025-04-04": (0.35, 0.15),
    }
    shock_pos = {idx.get_indexer([pd.Timestamp(d)], method="bfill")[0]: v for d, v in shocks.items()}
    for t in range(1, n):
        # mean-reverting in logs, so levels stay realistic
        lv = np.log(vix[t - 1]) + 0.05 * (np.log(16) - np.log(vix[t - 1])) + rng.normal(0, 0.035)
        lm = np.log(move[t - 1]) + 0.04 * (np.log(95) - np.log(move[t - 1])) + rng.normal(0, 0.02)
        vix[t], move[t] = np.exp(lv), np.exp(lm)
        if t in shock_pos:
            sv, sm = shock_pos[t]
            vix[t] *= 1 + sv
            move[t] *= 1 + sm
    return pd.DataFrame({"VIX": vix.round(2), "MOVE": move.round(2)}, index=idx.rename("date"))


def demo_kalshi() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    dates = pd.to_datetime(
        ["2024-09-18", "2024-11-07", "2024-12-18", "2025-01-29", "2025-03-19", "2025-05-07",
         "2025-06-18", "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10", "2026-01-28"]
    )
    surprise = np.clip(rng.beta(1.2, 5, len(dates)), 0.01, 0.95)
    surprise[0] = 0.62  # a 50bp cut that was close to a coin flip
    return pd.DataFrame(
        {
            "date": dates,
            "event": [f"Fed decision {d:%b %Y} (demo)" for d in dates],
            "market_expected": ["Hold (80%)"] * len(dates),
            "actual": ["Hold"] * len(dates),
            "surprise": surprise.round(2),
        }
    )


def demo_polymarket_search() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "question": ["Demo: New tariffs announced by June 30?", "Demo: Government shutdown in 2025?"],
            "event": ["Demo tariffs", "Demo shutdown"],
            "volume_usd": [12_400_000.0, 3_100_000.0],
            "end_date": ["2025-06-30", "2025-12-31"],
            "closed": [True, True],
            "yes_token": ["demo-1", "demo-2"],
        }
    )


def demo_polymarket_history(token: str) -> pd.Series:
    rng = np.random.default_rng(abs(hash(token)) % 1000)
    idx = pd.bdate_range("2025-01-02", "2025-06-30")
    p = np.clip(0.3 + np.cumsum(rng.normal(0, 0.02, len(idx))), 0.02, 0.98)
    jump = idx.get_indexer([pd.Timestamp("2025-04-02")], method="bfill")[0]
    p[jump:] = np.clip(p[jump:] + 0.35, 0.02, 0.98)
    return pd.Series(p, index=idx)
