"""
AHL Referee Analysis Dashboard
================================
Drop any number of ahl_penalties_*.csv files into the /refs folder,
then run:  streamlit run ref_dashboard.py

Expected CSV columns (output of ahl_penalty_ref_scraper.py):
  game_id, period, period_long, time, team_id, team_abbrev,
  player_id, player, jersey, position, infraction, minutes,
  is_power_play, is_bench, served_by_id, served_by,
  ref1, ref2, linesman1, linesman2
"""

import glob
import os

import numpy as np
import pandas as pd
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AHL Ref Dashboard",
    page_icon="🏒",
    layout="wide",
)

# ── Custom CSS (mirrors the photo aesthetic: navy/gold, tight tables) ─────────
st.markdown("""
<style>
    /* Header bar */
    .dash-header {
        background: #1a2744;
        color: #f0c040;
        padding: 14px 24px;
        border-radius: 8px;
        font-size: 22px;
        font-weight: 700;
        margin-bottom: 1.2rem;
        letter-spacing: .5px;
    }
    /* Section title */
    .section-title {
        color: #1a2744;
        font-size: 17px;
        font-weight: 700;
        border-bottom: 2px solid #1a2744;
        padding-bottom: 4px;
        margin-bottom: 10px;
    }
    /* Stat table */
    .stat-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .stat-table th {
        background: #1a2744; color: #f0c040;
        padding: 5px 10px; text-align: center;
    }
    .stat-table td { padding: 5px 10px; text-align: center; border-bottom: 1px solid #e0e0e0; }
    .stat-table tr.data-row { background: #ffffff; }
    .stat-table tr.pct-row  { background: #f5f5f5; font-style: italic; }
    /* Percentile coloring */
    .pct-high  { background: #c8f7c5 !important; color: #1a6b16; font-weight: 600; }
    .pct-mid   { background: #fff3b0 !important; color: #7a5c00; font-weight: 600; }
    .pct-low   { background: #ffd6d6 !important; color: #8b0000; font-weight: 600; }
    .pct-none  { color: #888; }
    /* Tightness badge */
    .badge {
        display: inline-block; padding: 2px 10px; border-radius: 12px;
        font-size: 12px; font-weight: 700;
    }
    .badge-loose  { background: #c8f7c5; color: #1a6b16; }
    .badge-avg    { background: #fff3b0; color: #7a5c00; }
    .badge-tight  { background: #ffd6d6; color: #8b0000; }
    /* Metric card */
    .metric-card {
        background: #f8f9fa; border: 1px solid #dee2e6;
        border-radius: 8px; padding: 12px 16px; text-align: center;
    }
    .metric-card .val { font-size: 26px; font-weight: 700; color: #1a2744; }
    .metric-card .lbl { font-size: 11px; color: #666; margin-top: 2px; }
</style>
""", unsafe_allow_html=True)

# ── Load data ─────────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "refs")

@st.cache_data
def load_data(data_dir: str) -> pd.DataFrame:
    files = glob.glob(os.path.join(data_dir, "ahl_penalties_*.csv"))
    if not files:
        return pd.DataFrame()
    dfs = []
    for f in files:
        try:
            dfs.append(pd.read_csv(f))
        except Exception:
            pass
    if not dfs:
        return pd.DataFrame()
    df = pd.concat(dfs, ignore_index=True)
    df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0)
    df["is_power_play"] = df["is_power_play"].fillna(0).astype(int)
    df["is_bench"] = df["is_bench"].fillna(0).astype(int)
    df["period"] = pd.to_numeric(df["period"], errors="coerce")
    for col in ["ref1", "ref2", "infraction", "team_abbrev", "player", "position"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
    return df

df_all = load_data(DATA_DIR)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<div class="dash-header">🏒 AHL Referee Analysis Dashboard</div>', unsafe_allow_html=True)

if df_all.empty:
    st.warning(
        f"No data found. Add `ahl_penalties_*.csv` files to the **`refs/`** folder "
        f"(expected at `{DATA_DIR}`) and refresh."
    )
    st.stop()

# ── Build per-ref summary ─────────────────────────────────────────────────────
def ref_stats(df: pd.DataFrame, ref_col: str) -> pd.DataFrame:
    """Aggregate stats for each name appearing in ref_col."""
    rows = []
    for ref_name, grp in df.groupby(ref_col):
        if not ref_name:
            continue
        games = grp["game_id"].nunique()
        pens = len(grp)
        pim = grp["minutes"].sum()
        pp_pct = grp["is_power_play"].mean() * 100 if len(grp) else 0
        bench_pct = grp["is_bench"].mean() * 100 if len(grp) else 0

        # Infraction category rates (per game)
        stick  = grp["infraction"].str.contains("High-stick|Slash|Hook|Interfer", case=False).sum()
        body   = grp["infraction"].str.contains("Rough|Fight|Cross|Charg|Board", case=False).sum()
        misc   = grp["infraction"].str.contains("Misc|Unsport|Instig|Conduct", case=False).sum()
        trap   = grp["infraction"].str.contains("Trip|Hold|Obstruct", case=False).sum()

        # Period 3 tilt: P3 calls vs P1 calls ratio (late-game leniency signal)
        p1 = (grp["period"] == 1).sum()
        p3 = (grp["period"] == 3).sum()
        p3_ratio = round(p3 / p1, 2) if p1 > 0 else None

        # Home/away differential
        # We don't have explicit home/away per-penalty, but we can use
        # the two teams per game: team called more often = away bias candidate
        # (rough proxy — real version needs game-level home team mapping)

        rows.append({
            "ref": ref_name,
            "games": games,
            "total_pen": pens,
            "pen_per_game": round(pens / games, 2) if games else 0,
            "pim_per_game": round(pim / games, 2) if games else 0,
            "pp_pct": round(pp_pct, 1),
            "bench_pct": round(bench_pct, 1),
            "stick_per_game": round(stick / games, 2) if games else 0,
            "body_per_game": round(body / games, 2) if games else 0,
            "misc_per_game": round(misc / games, 2) if games else 0,
            "trap_per_game": round(trap / games, 2) if games else 0,
            "p3_ratio": p3_ratio,
        })
    return pd.DataFrame(rows)

# Stack ref1 and ref2 together so each ref appears once
df_ref1 = df_all[df_all["ref1"] != ""].copy()
df_ref2 = df_all[df_all["ref2"] != ""].copy()
df_ref2 = df_ref2.rename(columns={"ref1": "_ref1_orig", "ref2": "ref1"})

df_stacked = pd.concat([
    df_all.assign(_ref_col=df_all["ref1"]),
    df_all.assign(_ref_col=df_all["ref2"]),
], ignore_index=True)
df_stacked = df_stacked[df_stacked["_ref_col"] != ""]

summary = ref_stats(df_stacked, "_ref_col")

# ── Percentile helper ─────────────────────────────────────────────────────────
STAT_COLS = [
    "pen_per_game", "pim_per_game", "pp_pct",
    "stick_per_game", "body_per_game", "misc_per_game", "trap_per_game",
]

def percentile_rank(series: pd.Series, val: float) -> int | None:
    if len(series) < 3:
        return None
    return int(round(pd.Series(series).rank(pct=True)[series[series == val].index[0]] * 100))

pct_df = summary.copy().set_index("ref")
for col in STAT_COLS:
    pct_df[f"{col}_pct"] = pct_df[col].rank(pct=True).mul(100).round(0).astype(int)

# ── Sidebar: ref selector ─────────────────────────────────────────────────────
all_refs = sorted(summary["ref"].unique())

with st.sidebar:
    st.markdown("### 🏒 Choose Referee")
    chosen_ref = st.selectbox("Referee", all_refs, label_visibility="collapsed")
    st.markdown("---")
    st.markdown("### 📁 Data")
    n_games = df_all["game_id"].nunique()
    n_files = len(glob.glob(os.path.join(DATA_DIR, "ahl_penalties_*.csv")))
    st.metric("Games loaded", n_games)
    st.metric("CSV files", n_files)
    st.caption(f"Source: `refs/` folder")
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()
        st.rerun()

# ── Pull this ref's data ──────────────────────────────────────────────────────
ref_row = summary[summary["ref"] == chosen_ref].iloc[0]
df_ref = df_stacked[df_stacked["_ref_col"] == chosen_ref].copy()

def pct_badge(val, min_games=3):
    """Return colored HTML for a percentile value."""
    if val is None or ref_row["games"] < min_games:
        return '<span class="pct-none">—</span>'
    if val >= 70:
        return f'<span class="pct-high">{int(val)}</span>'
    elif val >= 35:
        return f'<span class="pct-mid">{int(val)}</span>'
    else:
        return f'<span class="pct-low">{int(val)}</span>'

def tightness_badge(ppg):
    league_avg = summary["pen_per_game"].mean()
    diff = ppg - league_avg
    if ppg <= league_avg * 0.8:
        return '<span class="badge badge-tight">Tight game</span>', "#8b0000"
    elif ppg >= league_avg * 1.2:
        return '<span class="badge badge-loose">Loose game</span>', "#1a6b16"
    else:
        return '<span class="badge badge-avg">Average</span>', "#7a5c00"

badge_html, _ = tightness_badge(ref_row["pen_per_game"])
league_avg_ppg = round(summary["pen_per_game"].mean(), 2)

# ── Layout: ref name + quick metrics ─────────────────────────────────────────
st.markdown(f'<div class="section-title">Referee: {chosen_ref} &nbsp; {badge_html}</div>',
            unsafe_allow_html=True)

c1, c2, c3, c4, c5 = st.columns(5)
def mcard(col, val, label):
    col.markdown(
        f'<div class="metric-card"><div class="val">{val}</div>'
        f'<div class="lbl">{label}</div></div>',
        unsafe_allow_html=True
    )

mcard(c1, ref_row["games"], "Games")
mcard(c2, ref_row["pen_per_game"], "Pen / Game")
mcard(c3, ref_row["pim_per_game"], "PIM / Game")
mcard(c4, f'{ref_row["pp_pct"]}%', "PP Rate")
sign = "+" if ref_row["pen_per_game"] >= league_avg_ppg else ""
delta = round(ref_row["pen_per_game"] - league_avg_ppg, 2)
mcard(c5, f'{sign}{delta}', f'vs Avg ({league_avg_ppg})')

st.markdown("<br>", unsafe_allow_html=True)

# ── Section 1: Total calls table ──────────────────────────────────────────────
col_left, col_right = st.columns([1, 1], gap="large")

with col_left:
    st.markdown('<div class="section-title">Total Calls</div>', unsafe_allow_html=True)

    cols_display = {
        "Games": ("games", False),
        "Pen/G": ("pen_per_game", True),
        "PIM/G": ("pim_per_game", True),
        "PP%": ("pp_pct", True),
        "Bench%": ("bench_pct", True),
    }

    header = "".join(f"<th>{c}</th>" for c in cols_display)
    vals   = "".join(f"<td>{ref_row[k]}</td>" for c, (k, _) in cols_display.items())

    has_pct = ref_row["games"] >= 3
    pcts = []
    for c, (k, show_pct) in cols_display.items():
        if show_pct and has_pct and k in pct_df.columns:
            pct_col = f"{k}_pct"
            pval = pct_df.loc[chosen_ref, pct_col] if pct_col in pct_df.columns else None
            pcts.append(pct_badge(pval))
        else:
            pcts.append('<span class="pct-none">—</span>')
    pct_row = "".join(f"<td>{p}</td>" for p in pcts)

    st.markdown(f"""
    <table class="stat-table">
      <tr><th>Official</th>{header}</tr>
      <tr class="data-row"><td><b>{chosen_ref}</b></td>{vals}</tr>
      <tr class="pct-row"><td>Percentile</td>{pct_row}</tr>
    </table>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Infraction category breakdown
    st.markdown('<div class="section-title">Infraction Categories / Game</div>', unsafe_allow_html=True)

    cat_cols = {
        "Stick": ("stick_per_game", True),
        "Body": ("body_per_game", True),
        "Trapping": ("trap_per_game", True),
        "Misconduct": ("misc_per_game", True),
    }
    cat_header = "".join(f"<th>{c}</th>" for c in cat_cols)
    cat_vals   = "".join(f"<td>{ref_row[k]}</td>" for c, (k, _) in cat_cols.items())
    cat_pcts   = []
    for c, (k, sp) in cat_cols.items():
        if sp and has_pct:
            pct_col = f"{k}_pct"
            pval = pct_df.loc[chosen_ref, pct_col] if pct_col in pct_df.columns else None
            cat_pcts.append(pct_badge(pval))
        else:
            cat_pcts.append('<span class="pct-none">—</span>')
    cat_pct_row = "".join(f"<td>{p}</td>" for p in cat_pcts)

    st.markdown(f"""
    <table class="stat-table">
      <tr><th>Official</th>{cat_header}</tr>
      <tr class="data-row"><td><b>{chosen_ref}</b></td>{cat_vals}</tr>
      <tr class="pct-row"><td>Percentile</td>{cat_pct_row}</tr>
    </table>
    """, unsafe_allow_html=True)

with col_right:
    st.markdown('<div class="section-title">Period Breakdown</div>', unsafe_allow_html=True)

    p_data = df_ref.groupby("period").size().reindex([1, 2, 3, 4], fill_value=0)
    games = ref_row["games"]
    p_header = "".join(f"<th>P{int(p)}/G</th>" for p in p_data.index)
    p_vals   = "".join(f"<td>{round(v/games,2) if games else 0}</td>" for v in p_data.values)

    st.markdown(f"""
    <table class="stat-table">
      <tr><th>Official</th>{p_header}<th>P3/P1 Ratio</th></tr>
      <tr class="data-row"><td><b>{chosen_ref}</b></td>{p_vals}
        <td>{ref_row["p3_ratio"] if ref_row["p3_ratio"] is not None else "—"}</td>
      </tr>
    </table>
    <small style="color:#888">P3/P1 &lt; 1.0 = swallows whistle late game</small>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Top infractions called
    st.markdown('<div class="section-title">Top Infractions Called</div>', unsafe_allow_html=True)

    top_inf = (df_ref.groupby("infraction").size()
               .sort_values(ascending=False)
               .head(8)
               .reset_index(name="count"))
    top_inf["per_game"] = (top_inf["count"] / games).round(2)

    inf_rows = ""
    for _, r in top_inf.iterrows():
        inf_rows += f"<tr class='data-row'><td style='text-align:left'>{r['infraction']}</td><td>{r['count']}</td><td>{r['per_game']}</td></tr>"

    st.markdown(f"""
    <table class="stat-table">
      <tr><th style="text-align:left">Infraction</th><th>Total</th><th>Per Game</th></tr>
      {inf_rows}
    </table>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Section 2: Teams called against ──────────────────────────────────────────
st.markdown('<div class="section-title">Teams Called Against</div>', unsafe_allow_html=True)

team_data = (df_ref.groupby("team_abbrev")
             .agg(total=("infraction","count"), pim=("minutes","sum"))
             .sort_values("total", ascending=False)
             .reset_index())
team_data["per_game"] = (team_data["total"] / games).round(2)
team_data["pim_per_game"] = (team_data["pim"] / games).round(2)

team_rows = ""
for _, r in team_data.iterrows():
    team_rows += (f"<tr class='data-row'><td><b>{r['team_abbrev']}</b></td>"
                  f"<td>{r['total']}</td><td>{r['per_game']}</td>"
                  f"<td>{r['pim']}</td><td>{r['pim_per_game']}</td></tr>")

st.markdown(f"""
<table class="stat-table" style="max-width:600px">
  <tr><th>Team</th><th>Total Penalties</th><th>Pen/Game</th><th>Total PIM</th><th>PIM/Game</th></tr>
  {team_rows}
</table>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Section 3: All refs comparison ───────────────────────────────────────────
with st.expander("📊 All Referees Comparison"):
    display_cols = {
        "Referee": "ref",
        "Games": "games",
        "Pen/G": "pen_per_game",
        "PIM/G": "pim_per_game",
        "PP%": "pp_pct",
        "Stick/G": "stick_per_game",
        "Body/G": "body_per_game",
        "P3 Ratio": "p3_ratio",
    }
    compare_df = summary[list(display_cols.values())].copy()
    compare_df.columns = list(display_cols.keys())
    compare_df = compare_df.sort_values("Pen/G", ascending=False)

    def highlight_ref(row):
        return ["background-color: #fff3b0" if row["Referee"] == chosen_ref else "" for _ in row]

    st.dataframe(
        compare_df.style.apply(highlight_ref, axis=1).format({
            "Pen/G": "{:.2f}", "PIM/G": "{:.2f}", "PP%": "{:.1f}",
            "Stick/G": "{:.2f}", "Body/G": "{:.2f}", "P3 Ratio": lambda x: f"{x:.2f}" if x else "—"
        }),
        use_container_width=True,
        hide_index=True,
    )

# ── Section 4: Game log ───────────────────────────────────────────────────────
with st.expander(f"📋 Full penalty log — {chosen_ref}"):
    log_cols = ["game_id", "period", "time", "team_abbrev", "player",
                "infraction", "minutes", "is_power_play", "is_bench"]
    st.dataframe(
        df_ref[log_cols].sort_values(["game_id", "period", "time"]).reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
    )

st.markdown("---")
st.caption("Data source: AHL / HockeyTech · Built with ahl_penalty_ref_scraper.py")
