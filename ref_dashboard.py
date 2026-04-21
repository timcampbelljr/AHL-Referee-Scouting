"""
AHL Referee Analysis Dashboard
================================
Drop any number of ahl_penalties_*.csv files into the /Refs folder,
then run:  streamlit run ref_dashboard.py

Expected CSV columns (output of ahl_penalty_ref_scraper.py):
  game_id, period, period_long, time, team_id, team_abbrev,
  player_id, player, jersey, position, infraction, minutes,
  is_power_play, is_bench, served_by_id, served_by,
  ref1, ref2, linesman1, linesman2
"""

import glob
import io
import os
from datetime import datetime

import pandas as pd
import streamlit as st

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
)

# ── PDF generation ─────────────────────────────────────────────────────────────

NAVY   = colors.HexColor("#1a2744")
GOLD   = colors.HexColor("#f0c040")
LIGHT  = colors.HexColor("#f5f5f5")
WHITE  = colors.white
GREEN  = colors.HexColor("#c8f7c5")
YELLOW = colors.HexColor("#fff3b0")
RED_BG = colors.HexColor("#ffd6d6")
GREEN_TXT  = colors.HexColor("#1a6b16")
YELLOW_TXT = colors.HexColor("#7a5c00")
RED_TXT    = colors.HexColor("#8b0000")

def _pct_color(val):
    if val >= 70:
        return GREEN, GREEN_TXT
    elif val >= 35:
        return YELLOW, YELLOW_TXT
    return RED_BG, RED_TXT

def _tight_label(ppg, median, sd):
    """
    1 SD above median = Tight (calls everything).
    1 SD below median = Loose (lets it go).
    Everything in between = Average.
    """
    if ppg >= median + sd:
        return "Tight"
    elif ppg <= median - sd:
        return "Loose"
    return "Average"

def _th(txt):
    return Paragraph(txt, ParagraphStyle("th", fontSize=9, fontName="Helvetica-Bold", textColor=GOLD))

def _td(txt):
    return Paragraph(str(txt), ParagraphStyle("td", fontSize=9, alignment=1))

def _tdl(txt):
    return Paragraph(str(txt), ParagraphStyle("tdl", fontSize=9, alignment=0))

def _pv(txt, fg):
    return Paragraph(str(txt), ParagraphStyle("pv", fontSize=8, textColor=fg, fontName="Helvetica-Bold", alignment=1))

def build_ref_pdf(ref_names, summary, pct_df, df_stacked, league_median_ppg):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.6*inch, rightMargin=0.6*inch,
        topMargin=0.6*inch, bottomMargin=0.6*inch,
    )
    styles = getSampleStyleSheet()
    section_style = ParagraphStyle("sec", parent=styles["Normal"],
        fontSize=11, fontName="Helvetica-Bold", textColor=NAVY, spaceBefore=10, spaceAfter=4)
    small_style = ParagraphStyle("sm", parent=styles["Normal"],
        fontSize=8, textColor=colors.HexColor("#888888"), spaceBefore=2)
    title_style  = ParagraphStyle("tit", parent=styles["Normal"],
        fontSize=16, fontName="Helvetica-Bold", textColor=WHITE, spaceAfter=2)
    gold_style   = ParagraphStyle("gld", parent=styles["Normal"],
        fontSize=9, textColor=GOLD)

    story = []
    ref_median = summary["pen_per_game"].median()
    ref_sd     = summary["pen_per_game"].std(ddof=1) if len(summary) > 1 else 0

    # Cover banner
    banner = Table([[
        Paragraph("AHL Referee Scouting Report", title_style),
        Paragraph(f"Generated {datetime.now().strftime('%B %d, %Y')}", gold_style),
    ]], colWidths=[4.5*inch, 2.7*inch])
    banner.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,-1), NAVY),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0),(-1,-1), 12),
        ("RIGHTPADDING", (0,0),(-1,-1), 12),
        ("TOPPADDING",   (0,0),(-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1), 10),
        ("ALIGN",        (1,0),(1,0),   "RIGHT"),
    ]))
    story.append(banner)
    story.append(Spacer(1, 14))

    for idx, ref_name in enumerate(ref_names):
        if idx > 0:
            story.append(PageBreak())

        row   = summary[summary["ref"] == ref_name].iloc[0]
        df_r  = df_stacked[df_stacked["_ref"] == ref_name]
        games = row["games"]
        tight = _tight_label(row["pen_per_game"], ref_median, ref_sd)
        sign  = "+" if row["pen_per_game"] >= league_median_ppg else ""
        delta = round(row["pen_per_game"] - league_median_ppg, 2)
        has_pct = games >= 3

        # Ref header
        rh = Table([[Paragraph(f"{ref_name}   |   {tight}", title_style)]],
                   colWidths=[7.2*inch])
        rh.setStyle(TableStyle([
            ("BACKGROUND",   (0,0),(-1,-1), NAVY),
            ("LEFTPADDING",  (0,0),(-1,-1), 12),
            ("TOPPADDING",   (0,0),(-1,-1), 8),
            ("BOTTOMPADDING",(0,0),(-1,-1), 8),
        ]))
        story.append(rh)
        story.append(Spacer(1, 8))

        # Quick metrics
        metrics = [
            ("Games",      str(games)),
            ("Pen / Game", str(row["pen_per_game"])),
            ("PIM / Game", str(row["pim_per_game"])),
            ("PP Rate",    f"{row['pp_pct']}%"),
            ("vs Avg",     f"{sign}{delta}"),
        ]
        mh = [Paragraph(m[0], ParagraphStyle("mh", fontSize=8, textColor=GOLD, fontName="Helvetica-Bold", alignment=1)) for m in metrics]
        mv = [Paragraph(m[1], ParagraphStyle("mv", fontSize=14, fontName="Helvetica-Bold", textColor=WHITE, alignment=1)) for m in metrics]
        mt = Table([mh, mv], colWidths=[1.44*inch]*5)
        mt.setStyle(TableStyle([
            ("BACKGROUND",   (0,0),(-1,-1), NAVY),
            ("ALIGN",        (0,0),(-1,-1), "CENTER"),
            ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
            ("TOPPADDING",   (0,0),(-1,-1), 6),
            ("BOTTOMPADDING",(0,0),(-1,-1), 6),
            ("LINEAFTER",    (0,0),(3,-1),  0.5, colors.HexColor("#2e4070")),
        ]))
        story.append(mt)
        story.append(Spacer(1, 12))

        # Total calls + percentiles
        story.append(Paragraph("Total Calls", section_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=NAVY, spaceAfter=4))

        tc_defs = [("Games","games",None),("Pen/G","pen_per_game","pen_per_game"),
                   ("PIM/G","pim_per_game","pim_per_game"),("PP%","pp_pct","pp_pct"),
                   ("Bench%","bench_pct",None)]
        tc_h = [_th("Official")] + [_th(d[0]) for d in tc_defs]
        tc_v = [_tdl(ref_name)] + [_td(row[d[1]]) for d in tc_defs]
        tc_p = [Paragraph("Percentile", ParagraphStyle("ptd", fontSize=8, textColor=colors.HexColor("#555")))]
        pct_bg_cmds = []
        for ci, (_, _, pk) in enumerate(tc_defs, start=1):
            if pk and has_pct and ref_name in pct_df.index and f"{pk}_pct" in pct_df.columns:
                v = int(pct_df.loc[ref_name, f"{pk}_pct"])
                bg, fg = _pct_color(v)
                tc_p.append(_pv(v, fg))
                pct_bg_cmds.append(("BACKGROUND", (ci,2),(ci,2), bg))
            else:
                tc_p.append(Paragraph("—", ParagraphStyle("nd", fontSize=8, textColor=colors.HexColor("#888"), alignment=1)))
        tc_t = Table([tc_h, tc_v, tc_p], colWidths=[1.8*inch,0.75*inch,0.85*inch,0.85*inch,0.75*inch,0.85*inch])
        tc_ts = TableStyle([
            ("BACKGROUND",   (0,0),(-1,0), NAVY),
            ("BACKGROUND",   (0,1),(-1,1), WHITE),
            ("BACKGROUND",   (0,2),(-1,2), LIGHT),
            ("ALIGN",        (0,0),(-1,-1),"CENTER"),
            ("VALIGN",       (0,0),(-1,-1),"MIDDLE"),
            ("GRID",         (0,0),(-1,-1), 0.4, colors.HexColor("#dddddd")),
            ("TOPPADDING",   (0,0),(-1,-1), 4),
            ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ])
        for cmd in pct_bg_cmds:
            tc_ts.add(*cmd)
        tc_t.setStyle(tc_ts)
        story.append(tc_t)
        story.append(Spacer(1, 10))

        # Infraction categories + percentiles
        story.append(Paragraph("Infraction Categories / Game", section_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=NAVY, spaceAfter=4))

        cat_defs = [("Stick","stick_per_game"),("Body","body_per_game"),
                    ("Trapping","trap_per_game"),("Misconduct","misc_per_game")]
        cat_h = [_th("Official")] + [_th(d[0]) for d in cat_defs]
        cat_v = [_tdl(ref_name)] + [_td(row[d[1]]) for d in cat_defs]
        cat_p = [Paragraph("Percentile", ParagraphStyle("ptd", fontSize=8, textColor=colors.HexColor("#555")))]
        cat_bg = []
        for ci, (_, k) in enumerate(cat_defs, start=1):
            if has_pct and ref_name in pct_df.index and f"{k}_pct" in pct_df.columns:
                v = int(pct_df.loc[ref_name, f"{k}_pct"])
                bg, fg = _pct_color(v)
                cat_p.append(_pv(v, fg))
                cat_bg.append(("BACKGROUND",(ci,2),(ci,2),bg))
            else:
                cat_p.append(Paragraph("—", ParagraphStyle("nd", fontSize=8, textColor=colors.HexColor("#888"), alignment=1)))
        cat_t = Table([cat_h, cat_v, cat_p], colWidths=[1.8*inch,1.35*inch,1.35*inch,1.35*inch,1.35*inch])
        cat_ts = TableStyle([
            ("BACKGROUND",   (0,0),(-1,0), NAVY),
            ("BACKGROUND",   (0,1),(-1,1), WHITE),
            ("BACKGROUND",   (0,2),(-1,2), LIGHT),
            ("ALIGN",        (0,0),(-1,-1),"CENTER"),
            ("VALIGN",       (0,0),(-1,-1),"MIDDLE"),
            ("GRID",         (0,0),(-1,-1),0.4,colors.HexColor("#dddddd")),
            ("TOPPADDING",   (0,0),(-1,-1),4),
            ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ])
        for cmd in cat_bg:
            cat_ts.add(*cmd)
        cat_t.setStyle(cat_ts)
        story.append(cat_t)
        story.append(Spacer(1, 10))

        # Period breakdown
        story.append(Paragraph("Period Breakdown", section_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=NAVY, spaceAfter=4))
        p_data = df_r.groupby("period").size().reindex([1,2,3,4], fill_value=0)
        ph = [_th("Official")] + [_th(f"P{int(p)}/G") for p in p_data.index] + [_th("P3/P1")]
        pv = [_tdl(ref_name)]
        pv += [_td(round(v/games, 2) if games else 0) for v in p_data.values]
        p3r = row["p3_ratio"]
        pv.append(_td(p3r if p3r is not None else "—"))
        pt = Table([ph, pv], colWidths=[1.8*inch,0.9*inch,0.9*inch,0.9*inch,0.9*inch,0.9*inch])
        pt.setStyle(TableStyle([
            ("BACKGROUND",   (0,0),(-1,0), NAVY),
            ("BACKGROUND",   (0,1),(-1,1), WHITE),
            ("ALIGN",        (0,0),(-1,-1),"CENTER"),
            ("VALIGN",       (0,0),(-1,-1),"MIDDLE"),
            ("GRID",         (0,0),(-1,-1),0.4,colors.HexColor("#dddddd")),
            ("TOPPADDING",   (0,0),(-1,-1),4),
            ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ]))
        story.append(pt)
        story.append(Paragraph("P3/P1 < 1.0 = swallows whistle late game", small_style))
        story.append(Spacer(1, 10))

        # Top infractions + teams side by side
        story.append(Paragraph("Top Infractions & Teams Called Against", section_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=NAVY, spaceAfter=4))

        top_inf = (df_r.groupby("infraction").size()
                   .sort_values(ascending=False).head(8).reset_index(name="count"))
        top_inf["per_game"] = (top_inf["count"] / games).round(2)

        team_d = (df_r.groupby("team_abbrev")
                  .agg(total=("infraction","count"), pim=("minutes","sum"))
                  .sort_values("total", ascending=False).reset_index())
        team_d["per_game"]     = (team_d["total"] / games).round(2)
        team_d["pim_per_game"] = (team_d["pim"]   / games).round(2)

        inf_rows = [[_th("Infraction"), _th("Total"), _th("/Game")]]
        for _, r in top_inf.iterrows():
            inf_rows.append([_tdl(r["infraction"]), _td(r["count"]), _td(r["per_game"])])
        inf_t = Table(inf_rows, colWidths=[2.3*inch,0.7*inch,0.7*inch])
        inf_t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0), NAVY),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[WHITE,LIGHT]),
            ("ALIGN",         (1,0),(-1,-1),"CENTER"),
            ("GRID",          (0,0),(-1,-1),0.4,colors.HexColor("#dddddd")),
            ("TOPPADDING",    (0,0),(-1,-1),3),
            ("BOTTOMPADDING", (0,0),(-1,-1),3),
        ]))

        team_rows = [[_th("Team"), _th("Total"), _th("Pen/G"), _th("PIM/G")]]
        for _, r in team_d.iterrows():
            team_rows.append([_td(r["team_abbrev"]),_td(r["total"]),_td(r["per_game"]),_td(r["pim_per_game"])])
        team_t = Table(team_rows, colWidths=[0.9*inch,0.7*inch,0.75*inch,0.75*inch])
        team_t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0), NAVY),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[WHITE,LIGHT]),
            ("ALIGN",         (0,0),(-1,-1),"CENTER"),
            ("GRID",          (0,0),(-1,-1),0.4,colors.HexColor("#dddddd")),
            ("TOPPADDING",    (0,0),(-1,-1),3),
            ("BOTTOMPADDING", (0,0),(-1,-1),3),
        ]))

        side = Table([[inf_t, Spacer(0.2*inch, 1), team_t]])
        side.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP")]))
        story.append(side)

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    story.append(Paragraph(
        "Data source: AHL / HockeyTech  |  Built with ahl_penalty_ref_scraper.py",
        ParagraphStyle("foot", fontSize=7, textColor=colors.HexColor("#999999"), spaceBefore=4),
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AHL Ref Dashboard",
    page_icon="🏒",
    layout="wide",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .dash-header {
        background: #1a2744; color: #f0c040;
        padding: 14px 24px; border-radius: 8px;
        font-size: 22px; font-weight: 700;
        margin-bottom: 1.2rem; letter-spacing: .5px;
    }
    .ref-header {
        background: #1a2744; color: #f0c040;
        padding: 8px 14px; border-radius: 6px;
        font-size: 15px; font-weight: 700;
        margin-bottom: 10px; text-align: center;
    }
    .section-title {
        color: #1a2744; font-size: 15px; font-weight: 700;
        border-bottom: 2px solid #1a2744;
        padding-bottom: 3px; margin-bottom: 8px;
    }
    .stat-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .stat-table th {
        background: #1a2744; color: #f0c040;
        padding: 5px 8px; text-align: center;
    }
    .stat-table td {
        padding: 5px 8px; text-align: center;
        border-bottom: 1px solid #e0e0e0;
    }
    .stat-table tr.data-row { background: #ffffff; }
    .stat-table tr.pct-row  { background: #f5f5f5; font-style: italic; }
    .pct-high { background: #c8f7c5 !important; color: #1a6b16; font-weight: 600; }
    .pct-mid  { background: #fff3b0 !important; color: #7a5c00; font-weight: 600; }
    .pct-low  { background: #ffd6d6 !important; color: #8b0000; font-weight: 600; }
    .pct-none { color: #888; }
    .badge { display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:700; }
    .badge-loose { background:#c8f7c5; color:#1a6b16; }
    .badge-avg   { background:#fff3b0; color:#7a5c00; }
    .badge-tight { background:#ffd6d6; color:#8b0000; }
    .metric-card {
        background: #f8f9fa; border: 1px solid #dee2e6;
        border-radius: 8px; padding: 10px 12px; text-align: center;
        margin-bottom: 6px;
    }
    .metric-card .val { font-size: 22px; font-weight: 700; color: #1a2744; }
    .metric-card .lbl { font-size: 10px; color: #666; margin-top: 2px; }
</style>
""", unsafe_allow_html=True)

# ── Load data ─────────────────────────────────────────────────────────────────
# Add as many folder names as you need — all CSVs across all folders are combined.
DATA_DIRS = [
    os.path.join(os.path.dirname(__file__), "Refs"),
    os.path.join(os.path.dirname(__file__), "Refs_prev"),
]

@st.cache_data
def load_data(data_dirs: tuple) -> pd.DataFrame:
    # Collect all CSV files across all folders
    files = []
    for d in data_dirs:
        if os.path.isdir(d):
            files.extend(glob.glob(os.path.join(d, "ahl_penalties_*.csv")))
    if not files:
        return pd.DataFrame()

    # Deduplicate at the file level — if the same game_id CSV exists in
    # multiple folders, only load it once (first one wins).
    seen_game_ids = set()
    dfs = []
    for f in files:
        try:
            # Extract game_id from filename: ahl_penalties_1028894.csv -> 1028894
            basename = os.path.basename(f)
            gid = int(basename.replace("ahl_penalties_", "").replace(".csv", ""))
            if gid in seen_game_ids:
                continue
            seen_game_ids.add(gid)
            dfs.append(pd.read_csv(f))
        except Exception:
            pass

    if not dfs:
        return pd.DataFrame()
    df = pd.concat(dfs, ignore_index=True)
    df["minutes"]       = pd.to_numeric(df["minutes"], errors="coerce").fillna(0)
    df["is_power_play"] = df["is_power_play"].fillna(0).astype(int)
    df["is_bench"]      = df["is_bench"].fillna(0).astype(int)
    df["period"]        = pd.to_numeric(df["period"], errors="coerce")
    for col in ["ref1", "ref2", "infraction", "team_abbrev", "player", "position"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
    return df

df_all = load_data(tuple(DATA_DIRS))

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<div class="dash-header">🏒 AHL Referee Analysis Dashboard</div>', unsafe_allow_html=True)

if df_all.empty:
    st.warning(
        "No data found. Add `ahl_penalties_*.csv` files to the **`Refs/`** or "
        "**`Refs_prev/`** folder and refresh."
    )
    st.stop()

# ── Build per-ref summary ─────────────────────────────────────────────────────
@st.cache_data
def build_summary(df: pd.DataFrame):
    stacked = pd.concat([
        df.assign(_ref=df["ref1"]),
        df.assign(_ref=df["ref2"]),
    ], ignore_index=True)
    stacked = stacked[stacked["_ref"] != ""]

    rows = []
    for ref_name, grp in stacked.groupby("_ref"):
        games     = grp["game_id"].nunique()
        pens      = len(grp)
        pim       = grp["minutes"].sum()
        pp_pct    = grp["is_power_play"].mean() * 100 if pens else 0
        bench_pct = grp["is_bench"].mean() * 100 if pens else 0
        stick     = grp["infraction"].str.contains("High-stick|Slash|Hook|Interfer", case=False).sum()
        body      = grp["infraction"].str.contains("Rough|Fight|Cross|Charg|Board",  case=False).sum()
        misc      = grp["infraction"].str.contains("Misc|Unsport|Instig|Conduct",    case=False).sum()
        trap      = grp["infraction"].str.contains("Trip|Hold|Obstruct",             case=False).sum()
        p1        = (grp["period"] == 1).sum()
        p3        = (grp["period"] == 3).sum()
        rows.append({
            "ref":            ref_name,
            "games":          games,
            "total_pen":      pens,
            "pen_per_game":   round(pens  / games, 2) if games else 0,
            "pim_per_game":   round(pim   / games, 2) if games else 0,
            "pp_pct":         round(pp_pct, 1),
            "bench_pct":      round(bench_pct, 1),
            "stick_per_game": round(stick / games, 2) if games else 0,
            "body_per_game":  round(body  / games, 2) if games else 0,
            "misc_per_game":  round(misc  / games, 2) if games else 0,
            "trap_per_game":  round(trap  / games, 2) if games else 0,
            "p3_ratio":       round(p3 / p1, 2) if p1 > 0 else None,
        })
    return pd.DataFrame(rows), stacked

summary, df_stacked = build_summary(df_all)

# ── Percentile table ──────────────────────────────────────────────────────────
STAT_COLS = [
    "pen_per_game", "pim_per_game", "pp_pct",
    "stick_per_game", "body_per_game", "misc_per_game", "trap_per_game",
]
pct_df = summary.copy().set_index("ref")
for col in STAT_COLS:
    pct_df[f"{col}_pct"] = pct_df[col].rank(pct=True).mul(100).round(0).astype(int)

league_median_ppg = round(summary["pen_per_game"].median(), 2)

# ── Sidebar — two independent selectors ──────────────────────────────────────
all_refs = sorted(summary["ref"].unique())

with st.sidebar:
    st.markdown("### 🏒 Referee A")
    ref_a = st.selectbox("Referee A", all_refs, index=0, label_visibility="collapsed")

    st.markdown("### 🏒 Referee B")
    default_b = min(1, len(all_refs) - 1)
    ref_b = st.selectbox("Referee B", all_refs, index=default_b, label_visibility="collapsed")

    st.markdown("---")
    st.markdown("### 📁 Data")
    st.metric("Games loaded", df_all["game_id"].nunique())
    n_files = sum(len(glob.glob(os.path.join(d, "ahl_penalties_*.csv"))) for d in DATA_DIRS if os.path.isdir(d))
    st.metric("CSV files", n_files)
    median_games = int(summary["games"].median()) if not summary.empty else 0
    st.metric("Median games / ref", median_games)
    loaded = [os.path.basename(d) for d in DATA_DIRS if os.path.isdir(d)]
    st.caption("Folders: " + ", ".join(f"`{d}`" for d in loaded))
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("### 📄 Export PDF")
    pdf_mode = st.radio(
        "Include in report",
        ["Both refs", "Referee A only", "Referee B only"],
        label_visibility="collapsed",
    )
    if st.button("⬇️ Generate PDF"):
        if pdf_mode == "Referee A only":
            refs_for_pdf = [ref_a]
        elif pdf_mode == "Referee B only":
            refs_for_pdf = [ref_b]
        else:
            refs_for_pdf = [ref_a, ref_b]
        with st.spinner("Building PDF..."):
            pdf_bytes = build_ref_pdf(
                ref_names=refs_for_pdf,
                summary=summary,
                pct_df=pct_df,
                df_stacked=df_stacked,
                league_median_ppg=league_median_ppg,
            )
        names_slug = "_vs_".join(r.split()[-1] for r in refs_for_pdf)
        st.download_button(
            label="📥 Download PDF",
            data=pdf_bytes,
            file_name=f"AHL_Ref_Report_{names_slug}.pdf",
            mime="application/pdf",
        )

# ── Rendering helpers ─────────────────────────────────────────────────────────
def pct_badge(ref_name: str, col: str) -> str:
    if ref_name not in pct_df.index:
        return '<span class="pct-none">—</span>'
    ref_games = summary.loc[summary["ref"] == ref_name, "games"].iloc[0]
    if ref_games < 3:
        return '<span class="pct-none">—</span>'
    pct_col = f"{col}_pct"
    if pct_col not in pct_df.columns:
        return '<span class="pct-none">—</span>'
    val = int(pct_df.loc[ref_name, pct_col])
    cls = "pct-high" if val >= 70 else ("pct-mid" if val >= 35 else "pct-low")
    return f'<span class="{cls}">{val}</span>'

def tightness_badge(ppg: float) -> str:
    """1 SD above median = Tight, 1 SD below median = Loose, else Average."""
    median = summary["pen_per_game"].median()
    sd     = summary["pen_per_game"].std(ddof=1) if len(summary) > 1 else 0
    if ppg >= median + sd:
        return '<span class="badge badge-tight">Tight</span>'
    elif ppg <= median - sd:
        return '<span class="badge badge-loose">Loose</span>'
    return '<span class="badge badge-avg">Average</span>'

def render_ref_column(ref_name: str):
    """Render all stats for one referee into the current Streamlit column."""
    row   = summary[summary["ref"] == ref_name].iloc[0]
    df_r  = df_stacked[df_stacked["_ref"] == ref_name].copy()
    games = row["games"]

    # Name header + badge
    badge = tightness_badge(row["pen_per_game"])
    st.markdown(
        f'<div class="ref-header">{ref_name} &nbsp; {badge}</div>',
        unsafe_allow_html=True,
    )

    # Quick metric cards
    mc1, mc2, mc3, mc4 = st.columns(4)
    sign  = "+" if row["pen_per_game"] >= league_median_ppg else ""
    delta = round(row["pen_per_game"] - league_median_ppg, 2)
    for col_obj, val, lbl in [
        (mc1, row["games"],        "Games"),
        (mc2, row["pen_per_game"], "Pen / Game"),
        (mc3, row["pim_per_game"], "PIM / Game"),
        (mc4, f"{sign}{delta}",    f"vs Avg ({league_median_ppg})"),
    ]:
        col_obj.markdown(
            f'<div class="metric-card"><div class="val">{val}</div>'
            f'<div class="lbl">{lbl}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Total calls table + percentiles
    st.markdown('<div class="section-title">Total Calls</div>', unsafe_allow_html=True)
    cols_display = {
        "Games":  ("games",        False),
        "Pen/G":  ("pen_per_game", True),
        "PIM/G":  ("pim_per_game", True),
        "PP%":    ("pp_pct",       True),
        "Bench%": ("bench_pct",    True),
    }
    header   = "".join(f"<th>{c}</th>" for c in cols_display)
    vals_row = "".join(f"<td>{row[k]}</td>" for _, (k, _) in cols_display.items())
    pct_row  = "".join(
        f"<td>{pct_badge(ref_name, k) if sp else '<span class=\"pct-none\">—</span>'}</td>"
        for _, (k, sp) in cols_display.items()
    )
    st.markdown(f"""
    <table class="stat-table">
      <tr><th>Official</th>{header}</tr>
      <tr class="data-row"><td><b>{ref_name}</b></td>{vals_row}</tr>
      <tr class="pct-row"><td>Percentile</td>{pct_row}</tr>
    </table>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Infraction categories + percentiles
    st.markdown('<div class="section-title">Infraction Categories / Game</div>', unsafe_allow_html=True)
    cat_cols = {
        "Stick":      ("stick_per_game", True),
        "Body":       ("body_per_game",  True),
        "Trapping":   ("trap_per_game",  True),
        "Misconduct": ("misc_per_game",  True),
    }
    cat_header  = "".join(f"<th>{c}</th>" for c in cat_cols)
    cat_vals    = "".join(f"<td>{row[k]}</td>" for _, (k, _) in cat_cols.items())
    cat_pct_row = "".join(
        f"<td>{pct_badge(ref_name, k) if sp else '<span class=\"pct-none\">—</span>'}</td>"
        for _, (k, sp) in cat_cols.items()
    )
    st.markdown(f"""
    <table class="stat-table">
      <tr><th>Official</th>{cat_header}</tr>
      <tr class="data-row"><td><b>{ref_name}</b></td>{cat_vals}</tr>
      <tr class="pct-row"><td>Percentile</td>{cat_pct_row}</tr>
    </table>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Period breakdown
    st.markdown('<div class="section-title">Period Breakdown</div>', unsafe_allow_html=True)
    p_data   = df_r.groupby("period").size().reindex([1, 2, 3, 4], fill_value=0)
    p_header = "".join(f"<th>P{int(p)}/G</th>" for p in p_data.index)
    p_vals   = "".join(
        f"<td>{round(v / games, 2) if games else 0}</td>" for v in p_data.values
    )
    p3_ratio = row["p3_ratio"]
    st.markdown(f"""
    <table class="stat-table">
      <tr><th>Official</th>{p_header}<th>P3/P1</th></tr>
      <tr class="data-row"><td><b>{ref_name}</b></td>{p_vals}
        <td>{p3_ratio if p3_ratio is not None else "—"}</td>
      </tr>
    </table>
    <small style="color:#888">P3/P1 &lt; 1.0 = swallows whistle late</small>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Top infractions
    st.markdown('<div class="section-title">Top Infractions Called</div>', unsafe_allow_html=True)
    top_inf = (
        df_r.groupby("infraction").size()
        .sort_values(ascending=False)
        .head(8)
        .reset_index(name="count")
    )
    top_inf["per_game"] = (top_inf["count"] / games).round(2)
    inf_rows = "".join(
        f"<tr class='data-row'><td style='text-align:left'>{r['infraction']}</td>"
        f"<td>{r['count']}</td><td>{r['per_game']}</td></tr>"
        for _, r in top_inf.iterrows()
    )
    st.markdown(f"""
    <table class="stat-table">
      <tr><th style="text-align:left">Infraction</th><th>Total</th><th>/Game</th></tr>
      {inf_rows}
    </table>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Teams called against
    st.markdown('<div class="section-title">Teams Called Against</div>', unsafe_allow_html=True)
    team_data = (
        df_r.groupby("team_abbrev")
        .agg(total=("infraction", "count"), pim=("minutes", "sum"))
        .sort_values("total", ascending=False)
        .reset_index()
    )
    team_data["per_game"]     = (team_data["total"] / games).round(2)
    team_data["pim_per_game"] = (team_data["pim"]   / games).round(2)
    team_rows = "".join(
        f"<tr class='data-row'><td><b>{r['team_abbrev']}</b></td>"
        f"<td>{r['total']}</td><td>{r['per_game']}</td>"
        f"<td>{r['pim']}</td><td>{r['pim_per_game']}</td></tr>"
        for _, r in team_data.iterrows()
    )
    st.markdown(f"""
    <table class="stat-table">
      <tr><th>Team</th><th>Total</th><th>Pen/G</th><th>PIM</th><th>PIM/G</th></tr>
      {team_rows}
    </table>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Game log
    with st.expander(f"📋 Full penalty log — {ref_name}"):
        log_cols = ["game_id", "period", "time", "team_abbrev", "player",
                    "infraction", "minutes", "is_power_play", "is_bench"]
        st.dataframe(
            df_r[log_cols].sort_values(["game_id", "period", "time"]).reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
        )

# ── Two-column comparison layout ──────────────────────────────────────────────
col_a, spacer, col_b = st.columns([10, 0.3, 10])

with col_a:
    render_ref_column(ref_a)

with spacer:
    st.markdown(
        '<div style="border-left:2px solid #1a2744;min-height:900px;margin:0 auto;"></div>',
        unsafe_allow_html=True,
    )

with col_b:
    render_ref_column(ref_b)

# ── All refs comparison table ─────────────────────────────────────────────────
st.markdown("---")
with st.expander("📊 All Referees Comparison"):
    display_cols = {
        "Referee":  "ref",
        "Games":    "games",
        "Pen/G":    "pen_per_game",
        "PIM/G":    "pim_per_game",
        "PP%":      "pp_pct",
        "Stick/G":  "stick_per_game",
        "Body/G":   "body_per_game",
        "P3 Ratio": "p3_ratio",
    }
    compare_df = summary[list(display_cols.values())].copy()
    compare_df.columns = list(display_cols.keys())
    compare_df = compare_df.sort_values("Pen/G", ascending=False)

    def highlight_selected(row):
        if row["Referee"] == ref_a:
            return ["background-color: #d0e8ff"] * len(row)
        if row["Referee"] == ref_b:
            return ["background-color: #ffd6f0"] * len(row)
        return [""] * len(row)

    st.dataframe(
        compare_df.style.apply(highlight_selected, axis=1).format({
            "Pen/G":    "{:.2f}",
            "PIM/G":    "{:.2f}",
            "PP%":      "{:.1f}",
            "Stick/G":  "{:.2f}",
            "Body/G":   "{:.2f}",
            "P3 Ratio": lambda x: f"{x:.2f}" if x else "—",
        }),
        use_container_width=True,
        hide_index=True,
    )
    st.caption("Blue = Referee A · Pink = Referee B")

st.markdown("---")
st.caption("Data source: AHL / HockeyTech · Built with ahl_penalty_ref_scraper.py")
