"""Offline tests: analytics on synthetic data + API parsers on canned responses.

Run:  python -m pytest -q
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vol import analytics, demo, events, kalshi, news, polymarket  # noqa: E402


def test_spikes_found_on_shock_days():
    feat = analytics.add_features(demo.demo_vol("2018-01-01"))
    sp = analytics.find_spikes(feat, z=2.0, min_move_pct=5)
    dates = set(sp["date"].dt.strftime("%Y-%m-%d"))
    assert "2018-02-05" in dates and "2024-08-05" in dates
    assert {"led_by", "VIX_z"} <= set(sp.columns)


def test_events_and_matching():
    ev, warns = events.all_events(fred_key=None)
    assert (ev["type"] == "FOMC").sum() > 60
    assert warns  # no FRED key -> warning
    feat = analytics.add_features(demo.demo_vol())
    sp = analytics.match_events(analytics.find_spikes(feat), ev)
    row = sp[sp["date"] == "2023-03-13"]
    assert not row.empty and "SVB" in row.iloc[0]["nearby_events"]
    res = analytics.event_study(feat, ev, "FOMC")
    assert res["n_event_days"] > 50


def test_kalshi_surprise(monkeypatch):
    ev = {"events": [{
        "event_ticker": "KXFEDDECISION-25SEP", "title": "Fed decision Sep 2025",
        "markets": [
            {"ticker": "A-H0", "result": "no", "yes_sub_title": "Hold", "close_time": "2025-09-17T17:55:00Z"},
            {"ticker": "A-C25", "result": "yes", "yes_sub_title": "Cut 25bp", "close_time": "2025-09-17T17:55:00Z"},
        ]}], "cursor": ""}
    candles = {
        "A-H0": {"candlesticks": [{"price": {"close": 10}}, {"price": {"close": 8}}]},
        "A-C25": {"candlesticks": [{"price": {"close_dollars": "0.90"}}]},
    }

    def fake_get(url, params=None, retries=2, timeout=30):
        if url.endswith("/events"):
            return ev
        for t, c in candles.items():
            if f"/markets/{t}/candlesticks" in url:
                return c
        raise RuntimeError("unexpected " + url)

    monkeypatch.setattr(kalshi, "get_json", fake_get)
    df = kalshi.surprise_table("KXFEDDECISION")
    assert len(df) == 1
    r = df.iloc[0]
    assert r["actual"] == "Cut 25bp" and abs(r["surprise"] - 0.10) < 1e-9
    assert r["date"] == pd.Timestamp("2025-09-17") and "Cut 25bp (90%)" == r["market_expected"]


def test_polymarket_parsing(monkeypatch):
    search = {"events": [{"title": "Tariffs", "markets": [
        {"question": "Tariffs by June?", "clobTokenIds": json.dumps(["111", "222"]), "volumeNum": 5e6,
         "endDate": "2025-06-30T00:00:00Z", "closed": True}]}]}
    hist = {"history": [{"t": 1743465600, "p": 0.3}, {"t": 1743552000, "p": 0.75}]}
    monkeypatch.setattr(polymarket, "get_json",
                        lambda url, params=None, **k: search if "public-search" in url else hist)
    df = polymarket.search("tariffs")
    assert df.iloc[0]["yes_token"] == "111"
    s = polymarket.history("111")
    assert len(s) == 2
    sw = polymarket.biggest_swings(s)
    assert abs(sw.iloc[0]["move_pts"] - 45) < 1e-9


def test_news(monkeypatch):
    monkeypatch.setattr(news, "get_json", lambda *a, **k: {"articles": [{"title": "Stocks slide", "domain": "x.com", "url": "u", "seendate": "s"}]})
    assert news.headlines(pd.Timestamp("2026-10-01")).iloc[0]["title"] == "Stocks slide"
    assert "cd_min:3/9/2023" in news.google_news_link(pd.Timestamp("2023-03-10"))
