"""Headlines around a date, from GDELT (free, no key).

GDELT's article search only covers roughly the last 3 months, so older spikes
get a ready-made Google News link instead.
"""
from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote_plus

import pandas as pd

from .http import get_json

GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
DEFAULT_QUERY = (
    '(stocks OR "stock market" OR treasury OR "bond yields" OR "federal reserve" '
    'OR tariffs OR selloff OR volatility) sourcelang:english'
)


def headlines(date: pd.Timestamp, query: str = DEFAULT_QUERY, max_records: int = 25) -> pd.DataFrame:
    start = (date - timedelta(days=1)).strftime("%Y%m%d000000")
    end = (date + timedelta(days=1)).strftime("%Y%m%d235959")
    data = get_json(
        GDELT,
        params={
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": max_records,
            "sort": "hybridrel",
            "startdatetime": start,
            "enddatetime": end,
        },
        retries=1,
    )
    arts = data.get("articles") or []
    return pd.DataFrame(
        [{"title": a.get("title"), "source": a.get("domain"), "url": a.get("url"), "seen": a.get("seendate")} for a in arts]
    )


def google_news_link(date: pd.Timestamp, terms: str = "stock market volatility") -> str:
    d0, d1 = (date - timedelta(days=1)), (date + timedelta(days=1))
    fmt = lambda d: f"{d.month}/{d.day}/{d.year}"  # noqa: E731
    return (
        f"https://www.google.com/search?q={quote_plus(terms)}&tbm=nws"
        f"&tbs=cdr:1,cd_min:{fmt(d0)},cd_max:{fmt(d1)}"
    )
