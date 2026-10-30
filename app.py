"""VIX & MOVE volatility dashboard.

Run:  streamlit run app.py
Demo (no internet):  VOL_DEMO=1 streamlit run app.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from vol import analytics, demo, events, kalshi, market_data, news, polymarket

st.set_page_config(page_title="VIX & MOVE Volatility Tracker", layout="wide")

# Colors follow the entity everywhere: VIX is always blue, MOVE always orange.
C_VIX, C_MOVE, C_RATIO, C_PM = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6"
C_EVENT, C_FOMC, C_GRID = "#52514e", "#b9b8b2", "rgba(128,128,128,0.15)"

# ----------------------------------------------------------------- sidebar
st.sidebar.title("Settings")
demo_mode = st.sidebar.toggle(
    "Demo mode (made-up data, no internet)", value=os.environ.get("VOL_DEMO") == "1"
)
start = st.sidebar.date_input("History starts", pd.Timestamp("2018-01-01"))
z_thresh = st.sidebar.slider("Spike threshold (z-score)", 1.5, 4.0, 2.0, 0.25,
                             help="How unusual a daily rise must be vs the previous 20 days.")
min_move = st.sidebar.slider("…and at least this % rise", 0.0, 20.0, 5.0, 1.0)
show_fomc = st.sidebar.checkbox("Mark FOMC decision days", value=False)
show_curated = st.sidebar.checkbox("Mark my curated events", value=True)
fred_key = st.sidebar.text_input("FRED API key (optional)", type="password",
                                 help="Free at fred.stlouisfed.org. Turns on CPI and jobs-report dates.")
refresh = st.sidebar.button("Refresh market data")


# ----------------------------------------------------------------- data
@st.cache_data(ttl=3600, show_spinner="Loading VIX and MOVE…")
def load(start_str: str, demo_on: bool, force: bool):
    if demo_on:
        return demo.demo_vol(start_str), "Demo data (synthetic)"
    return market_data.load_vol(start_str, force_refresh=force)


@st.cache_data(ttl=86400)
def load_events(key: str | None):
    return events.all_events(key or None)


try:
    raw, status = load(str(start), demo_mode, refresh)
except Exception as e:  # noqa: BLE001
    st.error(f"Couldn't download market data: {e}\n\nTurn on **Demo mode** in the sidebar to explore the dashboard offline.")
    st.stop()

ev, ev_warnings = load_events(fred_key)
feat = analytics.add_features(raw)
has_move = "MOVE_chg" in feat
spikes = analytics.match_events(analytics.find_spikes(feat, z_thresh, min_move), ev)

st.title("VIX & MOVE Volatility Tracker")
st.caption(
    f"{status} · {feat.index.min():%b %d, %Y} – {feat.index.max():%b %d, %Y} · "
    "VIX = expected S&P 500 volatility (equities) · MOVE = expected Treasury volatility (rates)"
)
for w in ev_warnings:
    st.sidebar.caption(w)


def add_event_marks(fig, rows: int, x0=None, x1=None):
    """Dotted vertical lines for events, plus invisible hover points carrying the labels."""
    sel = ev
    if x0 is not None:
        sel = sel[(sel["date"] >= x0) & (sel["date"] <= x1)]
    shown = []
    if show_fomc:
        shown.append((sel[sel["type"] == "FOMC"], C_FOMC))
    if show_curated:
        shown.append((sel[~sel["type"].isin(["FOMC", "CPI", "Jobs report"])], C_EVENT))
    if fred_key and show_fomc:
        shown.append((sel[sel["type"].isin(["CPI", "Jobs report"])], C_FOMC))
    for frame, color in shown:
        for d in frame["date"]:
            for r in range(1, rows + 1):
                fig.add_vline(x=d, line=dict(color=color, width=1, dash="dot"), row=r, col=1)
    if show_curated:
        cur = sel[~sel["type"].isin(["FOMC", "CPI", "Jobs report"])]
        top = feat["VIX"].reindex(cur["date"], method="nearest")
        fig.add_trace(
            go.Scatter(x=cur["date"], y=top.values, mode="markers", name="Curated event",
                       marker=dict(size=9, symbol="diamond", color=C_EVENT,
                                   line=dict(color="white", width=2)),
                       text=cur["label"], hovertemplate="%{text}<extra></extra>"),
            row=1, col=1,
        )


def style(fig, height):
    fig.update_layout(
        height=height, hovermode="x unified", margin=dict(l=10, r=10, t=80, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.06, x=0), plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor=C_GRID, zeroline=False)
    return fig


def vol_figure(data: pd.DataFrame, spike_rows: pd.DataFrame, x0=None, x1=None, height=640):
    rows = 3 if has_move else 1
    titles = ["VIX (equity volatility)", "MOVE (Treasury volatility)", "MOVE ÷ VIX — higher = rates are the bigger worry"][:rows]
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.06, subplot_titles=titles,
                        row_heights=[0.4, 0.4, 0.2][:rows] if rows == 3 else None)
    fig.add_trace(go.Scatter(x=data.index, y=data["VIX"], name="VIX", line=dict(color=C_VIX, width=2),
                             hovertemplate="%{y:.2f}"), row=1, col=1)
    if has_move:
        fig.add_trace(go.Scatter(x=data.index, y=data["MOVE"], name="MOVE", line=dict(color=C_MOVE, width=2),
                                 hovertemplate="%{y:.1f}"), row=2, col=1)
        fig.add_trace(go.Scatter(x=data.index, y=data["MOVE_VIX_ratio"], name="MOVE/VIX",
                                 line=dict(color=C_RATIO, width=2), hovertemplate="%{y:.2f}"), row=3, col=1)
    for col, row, color in (("VIX", 1, C_VIX), ("MOVE", 2, C_MOVE)):
        if col == "MOVE" and not has_move:
            continue
        s = spike_rows[spike_rows["spiked"].str.contains(col)] if not spike_rows.empty else spike_rows
        if s is not None and not s.empty:
            fig.add_trace(
                go.Scatter(x=s["date"], y=s[col], mode="markers", name=f"{col} spike",
                           marker=dict(size=9, color=color, line=dict(color="white", width=2)),
                           customdata=np.stack([s[f"{col}_chg"], s[f"{col}_z"]], axis=-1),
                           hovertemplate=f"{col} spike: +%{{customdata[0]:.1f}}% (z=%{{customdata[1]:.1f}})<extra></extra>"),
                row=row, col=1,
            )
    add_event_marks(fig, rows, x0, x1)
    return style(fig, height)


tab_over, tab_spikes, tab_study, tab_kalshi, tab_poly = st.tabs(
    ["Overview", "Spike log", "Event study", "Kalshi: macro surprises", "Polymarket: risk build-up"]
)

# ----------------------------------------------------------------- overview
with tab_over:
    last = feat.dropna(subset=["VIX"]).iloc[-1]
    prev = feat.dropna(subset=["VIX"]).iloc[-2]
    c = st.columns(4)
    c[0].metric("VIX", f"{last['VIX']:.2f}", f"{last['VIX'] - prev['VIX']:+.2f}", delta_color="inverse")
    if has_move and pd.notna(last.get("MOVE")):
        c[1].metric("MOVE", f"{last['MOVE']:.1f}", f"{last['MOVE'] - prev['MOVE']:+.1f}", delta_color="inverse")
        c[2].metric("MOVE ÷ VIX", f"{last['MOVE_VIX_ratio']:.2f}")
    else:
        c[1].metric("MOVE", "n/a")
    c[3].metric("VIX vs past year", f"{last['VIX_pctile']:.0f}th pct" if pd.notna(last.get("VIX_pctile")) else "n/a")

    st.plotly_chart(vol_figure(feat, spikes), key="overview")
    recent = spikes[spikes["date"] >= feat.index.max() - pd.Timedelta(days=90)]
    st.markdown(
        f"**{len(spikes)} spike days** found with your settings; **{len(recent)}** in the last 90 days. "
        "Dots mark spike days; diamonds mark your curated events (hover for the label)."
    )

# ----------------------------------------------------------------- spike log
with tab_spikes:
    if spikes.empty:
        st.info("No spikes with these settings. Lower the threshold in the sidebar.")
    else:
        log = spikes.sort_values("date", ascending=False).copy()
        st.dataframe(
            log[["date", "spiked", "VIX", "VIX_chg", "MOVE", "MOVE_chg", "led_by", "nearby_events"]],
            hide_index=True,
            column_config={
                "date": st.column_config.DateColumn("Date"),
                "spiked": "Spiked",
                "VIX_chg": st.column_config.NumberColumn("VIX Δ%", format="%.1f%%"),
                "MOVE_chg": st.column_config.NumberColumn("MOVE Δ%", format="%.1f%%"),
                "VIX": st.column_config.NumberColumn(format="%.2f"),
                "MOVE": st.column_config.NumberColumn(format="%.1f"),
                "led_by": st.column_config.TextColumn("Who moved first (3 days before)"),
                "nearby_events": st.column_config.TextColumn("Scheduled / curated events ±1 day", width="large"),
            },
        )
        st.download_button("Download spike log (CSV)", log.to_csv(index=False), "spike_log.csv")

        st.subheader("Look into one spike")
        pick = st.selectbox("Spike date", log["date"].dt.strftime("%Y-%m-%d").tolist())
        d = pd.Timestamp(pick)
        win = feat.loc[d - pd.Timedelta(days=45): d + pd.Timedelta(days=30)]
        st.plotly_chart(vol_figure(win, spikes[(spikes["date"] >= win.index.min()) & (spikes["date"] <= win.index.max())],
                                   win.index.min(), win.index.max(), height=520), key="zoom")
        row = log[log["date"] == d].iloc[0]
        st.markdown(f"**Events nearby:** {row['nearby_events'] or 'none on the calendar — likely an unscheduled shock'}")
        st.markdown(f"**Who moved first:** {row['led_by']}")
        st.link_button("Search news for this date", news.google_news_link(d))
        if not demo_mode and st.button("Pull headlines from GDELT"):
            try:
                h = news.headlines(d)
                if h.empty:
                    st.info("No GDELT articles. GDELT only covers about the last 3 months, so use the news link above for older dates.")
                else:
                    st.dataframe(h, hide_index=True, column_config={"url": st.column_config.LinkColumn("Link")})
            except Exception as e:  # noqa: BLE001
                st.warning(f"GDELT request failed: {e}")

# ----------------------------------------------------------------- event study
with tab_study:
    st.markdown("Do scheduled events actually move volatility? Average **absolute** daily % change on event days vs all other days.")
    types = [t for t in ["FOMC", "CPI", "Jobs report"] if (ev["type"] == t).any()]
    res = pd.DataFrame([analytics.event_study(feat, ev, t) for t in types])
    if res.empty:
        st.info("No event dates loaded.")
    else:
        idx_cols = ["VIX"] + (["MOVE"] if has_move else [])
        cols = st.columns(len(idx_cols))
        for col, idx_name in zip(cols, idx_cols):
            color = C_VIX if idx_name == "VIX" else C_MOVE
            fig = go.Figure()
            fig.add_bar(x=res["event_type"], y=res[f"{idx_name}_event_avg"], name="Event days",
                        marker=dict(color=color, cornerradius=4), hovertemplate="%{y:.2f}%<extra>Event days</extra>")
            fig.add_bar(x=res["event_type"], y=res[f"{idx_name}_other_avg"], name="Other days",
                        marker=dict(color=C_FOMC, cornerradius=4), hovertemplate="%{y:.2f}%<extra>Other days</extra>")
            fig.update_layout(title=f"{idx_name}: avg absolute daily move (%)", barmode="group", bargap=0.35, bargroupgap=0.08)
            col.plotly_chart(style(fig, 360), key=f"study_{idx_name}")
        for _, r in res.iterrows():
            parts = [f"VIX moved {r['VIX_event_avg']:.1f}% on average vs {r['VIX_other_avg']:.1f}% on other days"]
            if has_move:
                parts.append(f"MOVE {r['MOVE_event_avg']:.1f}% vs {r['MOVE_other_avg']:.1f}%")
            st.markdown(f"- **{r['event_type']}** ({int(r['n_event_days'])} days): " + "; ".join(parts) + ".")

# ----------------------------------------------------------------- kalshi
with tab_kalshi:
    st.markdown(
        "How surprised was the market? For each settled Kalshi event, the **surprise score** compares what traders priced "
        "the day before with what actually happened (0 = fully expected, 1 = total shock). Then we check whether bigger "
        "surprises came with bigger volatility moves."
    )
    series_choice = st.text_input("Kalshi series ticker", "KXFEDDECISION",
                                  help="Try KXFEDDECISION (Fed decisions) or CPI series. Use 'List economics series' to find tickers.")
    c1, c2 = st.columns(2)
    if c1.button("List economics series") and not demo_mode:
        try:
            s = kalshi.list_series()
            st.dataframe(s[s["title"].str.contains("Fed|CPI|inflation|rate|jobs|payroll", case=False, na=False)], hide_index=True)
        except Exception as e:  # noqa: BLE001
            st.warning(f"Kalshi request failed: {e}")
    if c2.button("Compute surprise scores", type="primary"):
        if demo_mode:
            st.session_state["kalshi"] = demo.demo_kalshi()
        else:
            bar = st.progress(0.0, "Pulling Kalshi prices…")
            try:
                st.session_state["kalshi"] = kalshi.surprise_table(series_choice, progress=lambda f, t: bar.progress(f, t[:60]))
            except Exception as e:  # noqa: BLE001
                st.warning(f"Kalshi request failed: {e}")
            bar.empty()
    ks = st.session_state.get("kalshi")
    if ks is not None and not ks.empty:
        day = feat[["VIX_chg"] + (["MOVE_chg"] if has_move else [])]
        ks = ks.merge(day, left_on="date", right_index=True, how="left")
        y_col, y_name, y_color = ("MOVE_chg", "MOVE", C_MOVE) if has_move else ("VIX_chg", "VIX", C_VIX)
        valid = ks.dropna(subset=[y_col])
        fig = go.Figure(go.Scatter(
            x=valid["surprise"], y=valid[y_col].abs(), mode="markers", name=y_name,
            marker=dict(size=10, color=y_color, line=dict(color="white", width=2)),
            text=valid["event"], hovertemplate="%{text}<br>Surprise %{x:.2f}<br>|Δ| %{y:.1f}%<extra></extra>"))
        fig.update_layout(title=f"Surprise score vs {y_name} absolute move that day")
        fig.update_xaxes(title="Surprise score (0 = expected, 1 = shock)", range=[0, 1])
        fig.update_yaxes(title=f"|{y_name} daily change| (%)")
        st.plotly_chart(style(fig, 420), key="kalshi_scatter")
        if len(valid) >= 5:
            corr = valid["surprise"].corr(valid[y_col].abs())
            st.markdown(f"**Correlation:** {corr:.2f} across {len(valid)} events "
                        f"({'bigger surprises tend to move ' + y_name + ' more' if corr > 0.3 else 'no strong link yet'}).")
        st.dataframe(ks, hide_index=True, column_config={
            "date": st.column_config.DateColumn("Date"),
            "surprise": st.column_config.ProgressColumn("Surprise", min_value=0, max_value=1, format="%.2f"),
            "VIX_chg": st.column_config.NumberColumn("VIX Δ%", format="%.1f%%"),
            "MOVE_chg": st.column_config.NumberColumn("MOVE Δ%", format="%.1f%%"),
        })

# ----------------------------------------------------------------- polymarket
with tab_poly:
    st.markdown(
        "Track how the odds of an unscheduled risk (tariffs, war, shutdown…) built up, against VIX. "
        "Prices are crowd probabilities, not facts — and thin markets are noisy, so check the volume."
    )
    q = st.text_input("Topic", "tariffs")
    if st.button("Search Polymarket", type="primary"):
        try:
            st.session_state["pm_results"] = demo.demo_polymarket_search() if demo_mode else polymarket.search(q)
        except Exception as e:  # noqa: BLE001
            st.warning(f"Polymarket request failed: {e}")
    results = st.session_state.get("pm_results")
    if results is not None and not results.empty:
        min_vol = st.slider("Minimum volume (USD)", 0, 5_000_000, 100_000, 50_000)
        pool = results[results["volume_usd"] >= min_vol]
        if pool.empty:
            st.info("No markets above that volume.")
        else:
            label = lambda i: f"{pool.loc[i, 'question']} — ${pool.loc[i, 'volume_usd']/1e6:.1f}M"  # noqa: E731
            chosen = st.selectbox("Market", pool.index.tolist(), format_func=label)
            m = pool.loc[chosen]
            try:
                prob = demo.demo_polymarket_history(m["yes_token"]) if demo_mode else polymarket.history(m["yes_token"])
            except Exception as e:  # noqa: BLE001
                prob = pd.Series(dtype=float)
                st.warning(f"Couldn't load price history: {e}")
            if prob.empty:
                st.info("No price history for this market.")
            else:
                lo, hi = prob.index.min() - pd.Timedelta(days=14), prob.index.max() + pd.Timedelta(days=14)
                win = feat.loc[lo:hi]
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                                    subplot_titles=["VIX", f"Polymarket: {m['question'][:80]} (Yes %)"])
                fig.add_trace(go.Scatter(x=win.index, y=win["VIX"], name="VIX", line=dict(color=C_VIX, width=2)), row=1, col=1)
                fig.add_trace(go.Scatter(x=prob.index, y=prob * 100, name="Yes probability",
                                         line=dict(color=C_PM, width=2), hovertemplate="%{y:.0f}%"), row=2, col=1)
                fig.update_yaxes(range=[0, 100], row=2, col=1)
                st.plotly_chart(style(fig, 540), key="pm_chart")
                sw = polymarket.biggest_swings(prob)
                sw = sw.merge(feat[["VIX_chg"]], left_on="date", right_index=True, how="left")
                st.markdown("**Biggest one-day odds swings** and what VIX did that day:")
                st.dataframe(sw, hide_index=True, column_config={
                    "date": st.column_config.DateColumn("Date"),
                    "prob_after": st.column_config.NumberColumn("Odds after", format="%.0f%%"),
                    "move_pts": st.column_config.NumberColumn("Swing (pts)", format="%+.0f"),
                    "VIX_chg": st.column_config.NumberColumn("VIX Δ%", format="%+.1f%%"),
                })
