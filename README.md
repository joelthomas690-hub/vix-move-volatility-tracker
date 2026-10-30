# VIX & MOVE Volatility Tracker

A dashboard that tracks equity volatility (VIX) and Treasury volatility (MOVE), flags
unusual spikes, and ties them to real-world events: scheduled macro releases, your own
curated event list, Kalshi "surprise" scores, Polymarket odds, and news headlines.

## Run it (about 5 minutes)

You need Python 3.10+.

```bash
cd vol-dashboard
python -m venv .venv
# Mac/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py
```

Your browser opens at http://localhost:8501. The first load downloads VIX and MOVE
history and caches it in `data/vol_cache.csv` for 12 hours.

**No internet / just want to look around?** Turn on *Demo mode* in the sidebar
(or run `VOL_DEMO=1 streamlit run app.py`). Every number in demo mode is made up.

**Optional:** get a free FRED API key (fred.stlouisfed.org → My Account → API Keys)
and paste it into the sidebar. That adds CPI and jobs-report dates to the event study.

## The five tabs

| Tab | What it answers |
|---|---|
| **Overview** | Where are VIX, MOVE and MOVE÷VIX now, and where did they spike? Each index has its own chart (no dual axes). |
| **Spike log** | Every spike day (z-score of the daily % rise vs the prior 20 days), which index moved first, and any scheduled or curated event within ±1 day. Pick a spike to zoom in and pull headlines. |
| **Event study** | Do FOMC (and, with a FRED key, CPI and jobs) days actually move vol more than normal days? |
| **Kalshi: macro surprises** | For each settled Kalshi event (default: Fed decisions), how surprised the market was (0 = expected, 1 = shock), plotted against that day's MOVE move. |
| **Polymarket: risk build-up** | Search a topic (tariffs, shutdown, war…), pick a market, and see its odds against VIX, plus the biggest one-day odds swings. |

## Files

```
app.py                 the dashboard (Streamlit)
vol/market_data.py     VIX + MOVE download & cache (Yahoo; FRED fallback for VIX)
vol/analytics.py       spike detection, who-moved-first, event study
vol/events.py          FOMC calendar (built in) + data/events.csv + optional FRED dates
vol/kalshi.py          Kalshi public API → surprise score
vol/polymarket.py      Polymarket public API → search + daily odds
vol/news.py            GDELT headlines (last ~3 months) + Google News date links
vol/demo.py            synthetic data for demo mode
data/events.csv        YOUR event list - edit freely
tests/test_offline.py  offline tests (python -m pytest -q)
```

## Known limits (worth knowing before an interview)

- **Correlation, not causation.** "Nearby events" are candidates. The dashboard never says an event *caused* a spike.
- **MOVE comes from Yahoo Finance.** ICE owns it; Yahoo's feed occasionally has gaps. If MOVE is missing, the app falls back to VIX only.
- **GDELT covers only about the last 3 months.** Older spikes get a Google News link filtered to that date.
- **Prediction-market history is short.** Kalshi and Polymarket mostly cover 2023 onward. Polymarket thin markets are noisy, so use the volume filter.
- **API formats change.** The Kalshi and Polymarket code was written against their public docs (Oct 2026) but couldn't be tested live. If a tab errors, the message will say which request failed. Kalshi series tickers can be checked with the *List economics series* button.

## Ideas for refining it

1. Add CPI/jobs via FRED and write up the findings: "MOVE moves X× more on CPI days than other days."
2. Add your own events to `data/events.csv` and write a short case study for 3–4 of them.
3. Use intraday data around 8:30am and 2pm ET releases for a sharper event study.
4. Track Polymarket *volume* surges (Data API) as a "something is happening" detector.
5. Deploy free on Streamlit Community Cloud so you can put a link on your resume.
