"""Event calendar: FOMC decisions (built in), your own curated events (data/events.csv),
and optionally CPI / jobs-report release dates from FRED (needs a free API key).
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Decision day (day 2) of each FOMC meeting, incl. the March 2020 emergency cuts.
FOMC_DECISIONS = """
2018-01-31 2018-03-21 2018-05-02 2018-06-13 2018-08-01 2018-09-26 2018-11-08 2018-12-19
2019-01-30 2019-03-20 2019-05-01 2019-06-19 2019-07-31 2019-09-18 2019-10-30 2019-12-11
2020-01-29 2020-03-03 2020-03-15 2020-04-29 2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16 2026-10-28 2026-12-09
""".split()

FRED_RELEASES = {"CPI": 10, "Jobs report": 50}  # FRED release ids


def fomc_events() -> pd.DataFrame:
    return pd.DataFrame(
        {"date": pd.to_datetime(FOMC_DECISIONS), "type": "FOMC", "label": "Fed rate decision"}
    )


def curated_events() -> pd.DataFrame:
    """Your own list. Edit data/events.csv to add events (date,type,label)."""
    path = DATA_DIR / "events.csv"
    if not path.exists():
        return pd.DataFrame(columns=["date", "type", "label"])
    df = pd.read_csv(path, comment="#")
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "type", "label"]]


def fred_release_dates(name: str, api_key: str, start: str = "2018-01-01") -> pd.DataFrame:
    rid = FRED_RELEASES[name]
    r = requests.get(
        "https://api.stlouisfed.org/fred/release/dates",
        params={
            "release_id": rid,
            "api_key": api_key,
            "file_type": "json",
            "realtime_start": start,
            "include_release_dates_with_no_data": "false",
            "limit": 1000,
        },
        timeout=30,
    )
    r.raise_for_status()
    dates = pd.to_datetime([d["date"] for d in r.json().get("release_dates", [])])
    return pd.DataFrame({"date": dates, "type": name, "label": f"{name} release"})


def all_events(fred_key: str | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Return (events, warnings)."""
    frames, warnings = [fomc_events(), curated_events()], []
    fred_key = fred_key or os.environ.get("FRED_API_KEY")
    if fred_key:
        for name in FRED_RELEASES:
            try:
                frames.append(fred_release_dates(name, fred_key))
            except Exception as e:
                warnings.append(f"Couldn't load {name} dates from FRED: {e}")
    else:
        warnings.append(
            "CPI and jobs-report dates are off. Add a free FRED API key in the sidebar to turn them on."
        )
    ev = pd.concat(frames, ignore_index=True).drop_duplicates(["date", "type"])
    return ev.sort_values("date").reset_index(drop=True), warnings
