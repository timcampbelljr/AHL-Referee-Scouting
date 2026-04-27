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

# ── Global constants ─────────────────────────────────────────────────────────────
# Minimum games before a ref's stats are considered reliable for analysis
RELIABILITY_THRESHOLD = 5
BIAS_MIN_GAMES = 3  # Min games for bias — lower bar, directional read only

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

def build_ref_pdf(ref_names, summary, pct_df, df_stacked, league_median_ppg, team_baseline):
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
        story.append(Paragraph(
            "Percentile = how this ref ranks vs all refs in dataset. "
            "Green 70+ = top tier  |  Yellow 35-69 = middle  |  Red 0-34 = bottom. "
            f"Requires {RELIABILITY_THRESHOLD}+ games to display.",
            small_style,
        ))
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
        story.append(Paragraph(
            "Higher percentile = calls more of that infraction type than most refs. "
            "e.g. Stick 90th = calls stick infractions more than 90% of officials.",
            small_style,
        ))
        story.append(Spacer(1, 10))

        # Period breakdown
        story.append(Paragraph("Period Breakdown", section_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=NAVY, spaceAfter=4))
        p_data = df_r.groupby("period").size().reindex([1,2,3,4], fill_value=0)
        ph = [_th("Official")] + [_th(f"P{int(p)}/G") for p in p_data.index] + [_th("P3/P1")]
        pv = [_tdl(ref_name)]
        pv += [_td(round(v/games, 2) if games else 0) for v in p_data.values]
        p3r = row["p3_ratio"]
        pv.append(_td(f"{p3r:.3f}" if p3r is not None else "—"))
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

        def _ths(txt):
            return Paragraph(txt, ParagraphStyle("ths", fontSize=7, fontName="Helvetica-Bold", textColor=GOLD))
        def _tds(txt):
            return Paragraph(str(txt), ParagraphStyle("tds", fontSize=7, alignment=1))
        def _tdls(txt):
            return Paragraph(str(txt), ParagraphStyle("tdls", fontSize=7, alignment=0))

        team_d = (df_r.groupby("team_abbrev")
                  .agg(total=("infraction","count"), pim=("minutes","sum"))
                  .reset_index())

        def _team_med_pdf(team, col):
            g = df_r[df_r["team_abbrev"] == team]
            if col == "pen":
                return round(g.groupby("game_id").size().median(), 2)
            return round(g.groupby("game_id")[col].sum().median(), 2)

        team_d["g_together"]  = team_d["team_abbrev"].apply(
            lambda t: df_r[df_r["team_abbrev"] == t]["game_id"].nunique())
        team_d["per_game"]    = team_d["team_abbrev"].apply(lambda t: _team_med_pdf(t, "pen"))
        team_d["pim_per_game"]= team_d["team_abbrev"].apply(lambda t: _team_med_pdf(t, "minutes"))

        def _bias_pdf(row):
            team = row["team_abbrev"]
            if row["g_together"] < BIAS_MIN_GAMES or team not in team_baseline.index:
                return None
            return round(row["per_game"] - team_baseline.loc[team, "season_ppg"], 2)
        team_d["bias"] = team_d.apply(_bias_pdf, axis=1)
        team_d = team_d.sort_values("g_together", ascending=False)

        def _bias_cell_pdf(val):
            if val is None:
                return Paragraph("—", ParagraphStyle("nd", fontSize=7, textColor=colors.HexColor("#aaa"), alignment=1))
            color = RED_TXT if val > 0 else GREEN_TXT
            sign  = "+" if val > 0 else ""
            return Paragraph(f"{sign}{val}", ParagraphStyle("bv", fontSize=7, textColor=color, fontName="Helvetica-Bold", alignment=1))

        inf_rows = [[_th("Infraction"), _th("Total"), _th("/Game")]]
        for _, r in top_inf.iterrows():
            inf_rows.append([_tdl(r["infraction"]), _td(r["count"]), _td(r["per_game"])])
        inf_t = Table(inf_rows, colWidths=[2.0*inch, 0.6*inch, 0.6*inch])
        inf_t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0), NAVY),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[WHITE,LIGHT]),
            ("ALIGN",         (1,0),(-1,-1),"CENTER"),
            ("GRID",          (0,0),(-1,-1),0.4,colors.HexColor("#dddddd")),
            ("TOPPADDING",    (0,0),(-1,-1),2),
            ("BOTTOMPADDING", (0,0),(-1,-1),2),
        ]))

        team_rows = [[_ths("Team"), _ths("G"), _ths("Pen/G"), _ths("PIM/G"), _ths("Bias")]]
        for _, r in team_d.iterrows():
            team_rows.append([
                _tds(r["team_abbrev"]),
                _tds(r["g_together"]),
                _tds(r["per_game"]),
                _tds(r["pim_per_game"]),
                _bias_cell_pdf(r["bias"]),
            ])
        team_t = Table(team_rows, colWidths=[0.55*inch, 0.35*inch, 0.55*inch, 0.55*inch, 0.5*inch])
        team_ts = TableStyle([
            ("BACKGROUND",    (0,0),(-1,0), NAVY),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[WHITE,LIGHT]),
            ("ALIGN",         (0,0),(-1,-1),"CENTER"),
            ("GRID",          (0,0),(-1,-1),0.4,colors.HexColor("#dddddd")),
            ("TOPPADDING",    (0,0),(-1,-1),2),
            ("BOTTOMPADDING", (0,0),(-1,-1),2),
        ])
        team_t.setStyle(team_ts)

        side = Table([[inf_t, Spacer(0.15*inch, 1), team_t]])
        side.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP")]))
        story.append(side)
        story.append(Paragraph(
            f"Bias = ref median pen/G vs team - team season median pen/G  |  "
            f"red = harder on team  |  green = easier  |  "
            f"shown for {BIAS_MIN_GAMES}+ games together",
            small_style,
        ))

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

    /* ── Projection section ── */
    .proj-header {
        background: linear-gradient(135deg, #1a2744 0%, #2e4070 100%);
        color: #f0c040; padding: 16px 24px; border-radius: 10px;
        font-size: 20px; font-weight: 700; margin-bottom: 1rem;
        letter-spacing: .5px;
    }
    .proj-card {
        background: #1a2744; color: white;
        border-radius: 10px; padding: 14px 10px; text-align: center;
        margin-bottom: 8px;
    }
    .proj-card .pval { font-size: 28px; font-weight: 800; color: #f0c040; }
    .proj-card .plbl { font-size: 11px; color: #aab8d0; margin-top: 3px; }
    .proj-card .psub { font-size: 10px; color: #90a0c0; margin-top: 4px; }
    .range-bar {
        display: flex; align-items: center; gap: 12px;
        background: #f0f4fa; border-radius: 8px; padding: 12px 20px;
        margin: 8px 0;
    }
    .range-low  { color: #1a6b16; font-weight: 700; font-size: 18px; }
    .range-mid  { color: #1a2744; font-weight: 800; font-size: 24px; flex: 1; text-align: center; }
    .range-high { color: #8b0000; font-weight: 700; font-size: 18px; }
    .period-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 6px; }
    .period-table th {
        background: #1a2744; color: #f0c040;
        padding: 6px 10px; text-align: center; font-size: 12px;
    }
    .period-table td {
        padding: 6px 10px; text-align: center;
        border-bottom: 1px solid #e8eaf0;
    }
    .period-table tr:nth-child(even) td { background: #f5f7fb; }
    .team-proj-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 6px; }
    .team-proj-table th {
        background: #1a2744; color: #f0c040;
        padding: 6px 10px; text-align: center; font-size: 12px;
    }
    .team-proj-table td {
        padding: 7px 10px; text-align: center;
        border-bottom: 1px solid #e8eaf0;
    }
    .methodology-box {
        background: #f8f9fb; border-left: 3px solid #1a2744;
        border-radius: 0 6px 6px 0; padding: 12px 16px;
        font-size: 11px; color: #444; line-height: 1.7;
    }
</style>
""", unsafe_allow_html=True)

# ── Load data ─────────────────────────────────────────────────────────────────
DATA_DIRS = [
    os.path.join(os.path.dirname(__file__), "Refs"),
    os.path.join(os.path.dirname(__file__), "Refs_prev"),
]

@st.cache_data
def load_data(data_dirs: tuple) -> pd.DataFrame:
    files = []
    for d in data_dirs:
        if os.path.isdir(d):
            files.extend(glob.glob(os.path.join(d, "ahl_penalties_*.csv")))
    if not files:
        return pd.DataFrame()

    seen_game_ids = set()
    dfs = []
    for f in files:
        try:
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


# ── Offsetting pair detection ─────────────────────────────────────────────────
@st.cache_data
def flag_offsetting_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """
    Marks rows that are part of same-time offsetting minor pairs so the
    projector can exclude them from PP-relevant calculations.

    Logic: within each (game_id, period, time) group, if two rows belong to
    *different* teams, are both minors (minutes <= 2), and both have
    is_power_play == 0, they offset each other (4v4 situation).
    We tag every such row with is_offsetting = True.

    Rows that don't meet ALL criteria — e.g. a minor + a major at the same
    time, or a bench minor that produces a PP — are left as is_offsetting = False.
    """
    df = df.copy()
    df["is_offsetting"] = False

    groups = df.groupby(["game_id", "period", "time"])
    for _, grp in groups:
        if len(grp) < 2:
            continue
        teams = grp["team_abbrev"].unique()
        if len(teams) < 2:
            continue
        # Candidate offsetting rows: minor penalty, no PP produced
        candidates = grp[
            (grp["minutes"] <= 2) &
            (grp["is_power_play"] == 0) &
            (grp["is_bench"] == 0)
        ]
        # Need at least one candidate from each of two different teams
        if candidates["team_abbrev"].nunique() < 2:
            continue
        df.loc[candidates.index, "is_offsetting"] = True

    return df


df_all = flag_offsetting_pairs(df_all)

# Flag fighting penalties — refs have no discretion on these calls
df_all["is_fighting"] = df_all["infraction"].str.contains(
    r"Fight|Instig|Aggress", case=False, regex=True
)

# Clean view for projector: strip offsetting pairs AND fighting penalties.
# Both are non-discretionary — they tell us nothing about a ref's calling tendencies.
df_proj = df_all[~df_all["is_offsetting"] & ~df_all["is_fighting"]].copy()

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
        game_pp    = grp.groupby("game_id")["is_power_play"].sum()
        game_pen   = grp.groupby("game_id").size()
        game_pp_rate = (game_pp / game_pen * 100)
        pp_pct    = round(game_pp_rate.median(), 1) if len(game_pp_rate) else 0
        game_bench = grp.groupby("game_id")["is_bench"].sum()
        game_bench_rate = (game_bench / game_pen * 100)
        bench_pct = round(game_bench_rate.median(), 1) if len(game_bench_rate) else 0
        def _median_per_game(g, pattern):
            counts = g.groupby("game_id")["infraction"].apply(
                lambda x: x.str.contains(pattern, case=False).sum()
            )
            return counts.median() if len(counts) else 0
        stick = _median_per_game(grp, "High-stick|Slash|Hook|Interfer")
        body  = _median_per_game(grp, "Rough|Cross|Charg|Board")
        misc  = _median_per_game(grp, "Misc|Unsport|Fight")
        trap  = _median_per_game(grp, "Trip|Hold|Obstruct")
        period_int = pd.to_numeric(grp["period"], errors="coerce")
        p1_total   = (period_int == 1).sum()
        p3_total   = (period_int == 3).sum()
        p3_ratio   = round(p3_total / p1_total, 3) if p1_total > 0 else 1.000

        # Per-period median per game (used for projector period splits)
        per_period = {}
        for p in [1, 2, 3]:
            pg = grp[pd.to_numeric(grp["period"], errors="coerce") == p]
            per_period[f"p{p}_median"] = round(pg.groupby("game_id").size().median(), 3) if games else 0

        rows.append({
            "ref":            ref_name,
            "games":          games,
            "reliable":       games >= RELIABILITY_THRESHOLD,
            "total_pen":      pens,
            "pen_per_game":   round(grp.groupby("game_id").size().median(), 2) if games else 0,
            "pim_per_game":   round(grp.groupby("game_id")["minutes"].sum().median(), 2) if games else 0,
            "pp_pct":         round(pp_pct, 1),
            "bench_pct":      round(bench_pct, 1),
            "stick_per_game": round(stick, 2),
            "body_per_game":  round(body,  2),
            "misc_per_game":  round(misc,  2),
            "trap_per_game":  round(trap,  2),
            "p3_ratio":       p3_ratio,
            **per_period,
        })
    return pd.DataFrame(rows), stacked

summary, df_stacked = build_summary(df_all)

# Projector stacked view — offsetting pairs removed
@st.cache_data
def build_proj_stacked(df: pd.DataFrame) -> pd.DataFrame:
    stacked = pd.concat([
        df.assign(_ref=df["ref1"]),
        df.assign(_ref=df["ref2"]),
    ], ignore_index=True)
    return stacked[stacked["_ref"] != ""]

proj_stacked = build_proj_stacked(df_proj)

# ── Percentile table ──────────────────────────────────────────────────────────
STAT_COLS = [
    "pen_per_game", "pim_per_game", "pp_pct",
    "stick_per_game", "body_per_game", "misc_per_game", "trap_per_game",
]
pct_df = summary.copy().set_index("ref")
for col in STAT_COLS:
    pct_df[f"{col}_pct"] = pct_df[col].rank(pct=True).mul(100).round(0).astype(int)

league_median_ppg = round(summary["pen_per_game"].median(), 2)

# ── Team season pen/game baseline ────────────────────────────────────────────
@st.cache_data
def build_team_baseline(df: pd.DataFrame) -> pd.DataFrame:
    per_game = (
        df.groupby(["team_abbrev", "game_id"])
        .size().reset_index(name="pen")
    )
    team_stats = (
        per_game.groupby("team_abbrev")
        .agg(
            season_ppg=("pen", "median"),
            games=("game_id", "nunique"),
        )
        .reset_index()
    )
    team_stats["season_ppg"] = team_stats["season_ppg"].round(2)
    return team_stats.set_index("team_abbrev")

team_baseline = build_team_baseline(df_all)

# Projector uses a clean baseline (offsetting pairs stripped)
proj_team_baseline = build_team_baseline(df_proj)

# ── Sidebar ───────────────────────────────────────────────────────────────────
all_refs = sorted(summary["ref"].unique())

with st.sidebar:
    st.markdown("### 🏒 Referee A")
    ref_a = st.selectbox("Referee A", all_refs, index=0, label_visibility="collapsed")

    st.markdown("### 🏒 Referee B")
    default_b = min(1, len(all_refs) - 1)
    ref_b = st.selectbox("Referee B", all_refs, index=default_b, label_visibility="collapsed")

    st.markdown("---")
    st.markdown("### 🔍 Game Scouting Snapshot")

    @st.cache_data
    def build_game_labels(df: pd.DataFrame) -> dict:
        labels = {}
        for gid, grp in df.groupby("game_id"):
            teams = sorted(grp["team_abbrev"].dropna().unique())
            if len(teams) >= 2:
                label = f"{teams[0]} vs {teams[1]}  (#{gid})"
            elif len(teams) == 1:
                label = f"{teams[0]}  (#{gid})"
            else:
                label = f"Game #{gid}"
            labels[label] = gid
        return dict(sorted(labels.items(), key=lambda x: x[1], reverse=True))

    game_labels = build_game_labels(df_all)
    selected_label = st.selectbox("Select Game", list(game_labels.keys()), label_visibility="collapsed")
    selected_game  = game_labels.get(selected_label)

    if selected_game:
        game_data = df_all[df_all["game_id"] == selected_game]
        crew = []
        if not game_data.empty:
            crew = [game_data["ref1"].iloc[0], game_data["ref2"].iloc[0]]
            crew = [r for r in crew if r and str(r).strip()]
        game_teams = sorted(game_data["team_abbrev"].dropna().unique()) if not game_data.empty else []

        if crew:
            ref_median = summary["pen_per_game"].median()
            ref_sd     = summary["pen_per_game"].std(ddof=1) if len(summary) > 1 else 0

            for official in crew:
                o_row = summary[summary["ref"] == official]
                if o_row.empty:
                    continue
                o_stats      = o_row.iloc[0]
                reliable_tag = "" if o_stats["reliable"] else " ⚠️"
                style        = _tight_label(o_stats["pen_per_game"], ref_median, ref_sd)
                p3r          = o_stats["p3_ratio"]
                p3r_str      = f"{p3r:.3f}" if p3r is not None else "—"
                whistle      = "Swallows whistle late" if (p3r or 1) < 1.0 else "Active in 3rd"
                style_color  = "#8b0000" if style == "Tight" else ("#1a6b16" if style == "Loose" else "#7a5c00")
                ppg          = o_stats["pen_per_game"]

                df_ref_all = df_stacked[df_stacked["_ref"] == official]
                bias_lines = []
                for team in game_teams:
                    df_rt      = df_ref_all[df_ref_all["team_abbrev"] == team]
                    g_together = df_rt["game_id"].nunique()
                    if g_together == 0:
                        bias_lines.append(f"{team}: no history")
                        continue
                    ref_ppg_vs = round(df_rt.groupby("game_id").size().median(), 2)
                    if team in team_baseline.index:
                        baseline = team_baseline.loc[team, "season_ppg"]
                        bias_val = round(ref_ppg_vs - baseline, 2)
                        sign     = "+" if bias_val > 0 else ""
                        color    = "#8b0000" if bias_val > 0 else "#1a6b16"
                        sample   = "" if g_together >= RELIABILITY_THRESHOLD else " ⚠️"
                        bias_lines.append(
                            f"{team}: <span style='color:{color};font-weight:700'>{sign}{bias_val}</span>"
                            f" ({g_together}G){sample}"
                        )
                    else:
                        bias_lines.append(f"{team}: no baseline")

                bias_html = "<br>".join(bias_lines) if bias_lines else "No team data"

                st.markdown(
                    f"**{official}**{reliable_tag}<br>"
                    f"Style: <span style='color:{style_color};font-weight:700'>{style}</span> &nbsp;|&nbsp; "
                    f"Late game: {whistle} (P3/P1: {p3r_str})<br>"
                    f"Median pen/G: {ppg}<br>"
                    f"<span style='font-size:11px;color:#555'>Bias vs teams in this game:</span><br>"
                    f"<span style='font-size:12px'>{bias_html}</span>",
                    unsafe_allow_html=True,
                )
                st.markdown("---")
        else:
            st.caption("No crew data for this game.")

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
                team_baseline=team_baseline,
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
    if ref_games < RELIABILITY_THRESHOLD:
        return '<span class="pct-none">—</span>'
    pct_col = f"{col}_pct"
    if pct_col not in pct_df.columns:
        return '<span class="pct-none">—</span>'
    val = int(pct_df.loc[ref_name, pct_col])
    cls = "pct-high" if val >= 70 else ("pct-mid" if val >= 35 else "pct-low")
    return f'<span class="{cls}">{val}</span>'

def tightness_badge(ppg: float) -> str:
    median = summary["pen_per_game"].median()
    sd     = summary["pen_per_game"].std(ddof=1) if len(summary) > 1 else 0
    if ppg >= median + sd:
        return '<span class="badge badge-tight">Tight</span>'
    elif ppg <= median - sd:
        return '<span class="badge badge-loose">Loose</span>'
    return '<span class="badge badge-avg">Average</span>'

def render_ref_column(ref_name: str):
    row   = summary[summary["ref"] == ref_name].iloc[0]
    df_r  = df_stacked[df_stacked["_ref"] == ref_name].copy()
    games = row["games"]

    badge = tightness_badge(row["pen_per_game"])
    reliable_warn = "" if row.get("reliable", True) else " &nbsp; ⚠️ Low sample"
    st.markdown(
        f'<div class="ref-header">{ref_name} &nbsp; {badge}{reliable_warn}</div>',
        unsafe_allow_html=True,
    )

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
    <small style="color:#888">
      <b>Percentile</b> = how this ref ranks vs all refs in your dataset for that stat.
      <span style="background:#c8f7c5;color:#1a6b16;padding:1px 5px;border-radius:3px;font-weight:600">70+</span> top tier &nbsp;
      <span style="background:#fff3b0;color:#7a5c00;padding:1px 5px;border-radius:3px;font-weight:600">35–69</span> middle &nbsp;
      <span style="background:#ffd6d6;color:#8b0000;padding:1px 5px;border-radius:3px;font-weight:600">0–34</span> bottom &nbsp;
      &mdash; requires {RELIABILITY_THRESHOLD}+ games to show.
    </small>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

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
    <small style="color:#888">
      Higher pen/G percentile = calls more of that infraction type than most refs.
      A 90th percentile in Stick means this ref calls stick infractions more than 90% of officials.
    </small>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

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
        <td>{f"{p3_ratio:.3f}" if p3_ratio is not None else "—"}</td>
      </tr>
    </table>
    <small style="color:#888">P3/P1 &lt; 1.0 = swallows whistle late</small>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

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

    st.markdown('<div class="section-title">Teams Called Against</div>', unsafe_allow_html=True)
    team_games_ref = df_r.groupby("team_abbrev")["game_id"].nunique().rename("ref_games")
    team_data = (
        df_r.groupby("team_abbrev")
        .agg(total=("infraction", "count"), pim=("minutes", "sum"))
        .reset_index()
        .join(team_games_ref, on="team_abbrev")
    )
    def _team_median(team_abbrev, col):
        grp = df_r[df_r["team_abbrev"] == team_abbrev]
        if col == "pen":
            return round(grp.groupby("game_id").size().median(), 2)
        return round(grp.groupby("game_id")[col].sum().median(), 2)
    team_data["per_game"]     = team_data["team_abbrev"].apply(lambda t: _team_median(t, "pen"))
    team_data["pim_per_game"] = team_data["team_abbrev"].apply(lambda t: _team_median(t, "minutes"))
    def _bias(row):
        team = row["team_abbrev"]
        if row["ref_games"] < BIAS_MIN_GAMES or team not in team_baseline.index:
            return None
        return round(row["per_game"] - team_baseline.loc[team, "season_ppg"], 2)
    team_data["bias"] = team_data.apply(_bias, axis=1)
    team_data = team_data.sort_values("ref_games", ascending=False)

    def _bias_cell(val):
        import math
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return "<td>—</td>"
        color = "#8b0000" if val > 0 else "#1a6b16"
        sign  = "+" if val > 0 else ""
        return f"<td style='color:{color};font-weight:600'>{sign}{val}</td>"

    team_rows = "".join(
        f"<tr class='data-row'><td><b>{r['team_abbrev']}</b></td>"
        f"<td>{r['ref_games']}</td><td>{r['per_game']}</td>"
        f"<td>{r['pim_per_game']}</td>{_bias_cell(r['bias'])}</tr>"
        for _, r in team_data.iterrows()
    )
    st.markdown(f"""
    <table class="stat-table">
      <tr><th>Team</th><th>Games Reffed</th><th>Pen/G</th><th>PIM/G</th><th>Bias</th></tr>
      {team_rows}
    </table>
    <small style="color:#888">
      Bias = ref pen/g vs team &minus; team season pen/g &nbsp;|&nbsp;
      red = harder on team &nbsp;|&nbsp; green = easier &nbsp;|&nbsp;
      bias shown for {BIAS_MIN_GAMES}+ games together (lower bar than overall reliability — treat small samples as directional only)
    </small>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

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
            "P3 Ratio": lambda x: f"{x:.3f}" if x else "—",
        }),
        use_container_width=True,
        hide_index=True,
    )
    st.caption("Blue = Referee A · Pink = Referee B")
    st.markdown(
        "<small style='color:#888'>"
        "<b>Percentile note:</b> Each stat is ranked across all refs in your dataset. "
        "A Pen/G percentile of 80 means this ref calls more penalties per game than 80% of officials. "
        "For infraction categories, higher = calls more of that type. "
        f"Only refs with {RELIABILITY_THRESHOLD}+ games are ranked — others show —."
        "</small>",
        unsafe_allow_html=True,
    )

# ── Team View ─────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown('<div class="dash-header">🏒 Team View — Referee Bias by Team</div>', unsafe_allow_html=True)

all_teams = sorted(df_all["team_abbrev"].dropna().unique())
chosen_team = st.selectbox("Choose a team", all_teams)

if chosen_team:
    baseline_ppg = team_baseline.loc[chosen_team, "season_ppg"] if chosen_team in team_baseline.index else None
    total_team_games = int(team_baseline.loc[chosen_team, "games"]) if chosen_team in team_baseline.index else 0

    tc1, tc2 = st.columns(2)
    tc1.markdown(
        f'<div class="metric-card"><div class="val">{total_team_games}</div>'
        f'<div class="lbl">Season games (in dataset)</div></div>',
        unsafe_allow_html=True,
    )
    tc2.markdown(
        f'<div class="metric-card"><div class="val">{baseline_ppg}</div>'
        f'<div class="lbl">Season pen/game baseline</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    bias_rows = []
    for _, ref_row in summary.iterrows():
        ref_name = ref_row["ref"]
        df_r = df_stacked[df_stacked["_ref"] == ref_name]
        df_rt = df_r[df_r["team_abbrev"] == chosen_team]
        g_together = df_rt["game_id"].nunique()
        if g_together == 0:
            continue
        ppg_vs_team = round(df_rt.groupby("game_id").size().median(), 2) if g_together else 0
        bias = round(ppg_vs_team - baseline_ppg, 2) if baseline_ppg is not None else None
        bias_rows.append({
            "Referee":       ref_name,
            "G Together":    g_together,
            "Pen/G vs Team": ppg_vs_team,
            "Season Pen/G":  baseline_ppg,
            "Bias":          bias,
            "_reliable":     g_together >= BIAS_MIN_GAMES,
        })

    if not bias_rows:
        st.info(f"No data found for {chosen_team}.")
    else:
        bias_df = pd.DataFrame(bias_rows).sort_values(["G Together", "Bias"], ascending=[False, False])

        def _bias_color(val, reliable):
            if not reliable or val is None:
                return "<td><span style='color:#aaa;font-size:11px'>min 3G</span></td>"
            color = "#8b0000" if val > 0 else "#1a6b16"
            sign  = "+" if val > 0 else ""
            return f"<td style='color:{color};font-weight:700'>{sign}{val}</td>"

        def _ref_cell(name, reliable):
            style = "color:#aaa" if not reliable else ""
            return f"<td style='{style}'><b>{name}</b></td>"

        t_rows = "".join(
            f"<tr class='data-row'>{_ref_cell(r['Referee'], r['_reliable'])}"
            f"<td>{r['G Together']}</td>"
            f"<td>{r['Pen/G vs Team']}</td>"
            f"<td>{r['Season Pen/G']}</td>"
            f"{_bias_color(r['Bias'], r['_reliable'])}</tr>"
            for _, r in bias_df.iterrows()
        )
        st.markdown(f"""
        <table class="stat-table">
          <tr>
            <th style="text-align:left">Referee</th>
            <th>Reffed {chosen_team}</th>
            <th>Pen/G vs {chosen_team}</th>
            <th>{chosen_team} Season Pen/G</th>
            <th>Bias</th>
          </tr>
          {t_rows}
        </table>
        <small style="color:#888">
          Sorted hardest → easiest &nbsp;|&nbsp; red = harder on {chosen_team} than season avg &nbsp;|&nbsp;
          green = easier &nbsp;|&nbsp; grey = fewer than 3 games together (unreliable)
        </small>
        """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════════
# ── GAME PENALTY PROJECTOR ────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════════

st.markdown("---")
st.markdown('<div class="proj-header">🎯 Game Penalty Projector</div>', unsafe_allow_html=True)
st.markdown(
    "Select a referee crew and the two teams for an upcoming game. "
    "The projector blends both refs' penalty tendencies — weighting the higher-volume "
    "ref more — then adjusts using each ref's known historical bias against the specific teams.",
)
st.markdown("<br>", unsafe_allow_html=True)

# ── Independent selectors ────────────────────────────────────────────────────
pcol1, pcol2, pcol3, pcol4 = st.columns(4)
with pcol1:
    st.markdown("**Referee 1**")
    proj_ref1 = st.selectbox(
        "Proj Ref 1", all_refs, index=0, key="proj_ref1", label_visibility="collapsed"
    )
with pcol2:
    st.markdown("**Referee 2**")
    proj_ref2 = st.selectbox(
        "Proj Ref 2", all_refs, index=min(1, len(all_refs) - 1),
        key="proj_ref2", label_visibility="collapsed"
    )
with pcol3:
    st.markdown("**Home Team**")
    proj_home = st.selectbox(
        "Proj Home", all_teams, index=0, key="proj_home", label_visibility="collapsed"
    )
with pcol4:
    st.markdown("**Away Team**")
    proj_away = st.selectbox(
        "Proj Away", all_teams, index=min(1, len(all_teams) - 1),
        key="proj_away", label_visibility="collapsed"
    )

st.markdown("<br>", unsafe_allow_html=True)


# ── Core projection functions ────────────────────────────────────────────────

def get_ref_bias_vs_team(ref_name, team):
    """
    Returns (bias_value, games_together) using the offsetting-stripped data.
    bias = ref's clean median pen/game vs that team − team's clean season baseline.
    Excludes same-time opposite-team minor pairs (4v4 situations) so the bias
    reflects penalties that actually produced or could produce PP opportunities.
    Returns (None, 0) if no shared history or no team baseline.
    """
    df_r  = proj_stacked[proj_stacked["_ref"] == ref_name]
    df_rt = df_r[df_r["team_abbrev"] == team]
    g     = df_rt["game_id"].nunique()
    if g == 0 or team not in proj_team_baseline.index:
        return None, 0
    ref_ppg_vs = df_rt.groupby("game_id").size().median()
    bias = round(ref_ppg_vs - proj_team_baseline.loc[team, "season_ppg"], 2)
    return bias, g


def compute_projection(ref1, ref2, team_home, team_away):
    """
    Weighted blend of two refs' clean (offsetting-stripped) medians,
    then apply averaged team bias computed on the same clean data.
    The ref with the higher clean pen/game median gets a proportionally larger weight.
    """
    # Use clean per-game stats for each ref from proj_stacked
    def _clean_ref_stats(ref_name):
        grp = proj_stacked[proj_stacked["_ref"] == ref_name]
        if grp.empty:
            # Fall back to raw summary if ref has no clean data (edge case)
            row = summary[summary["ref"] == ref_name].iloc[0]
            return row["pen_per_game"], row["pim_per_game"], row["pp_pct"] / 100.0, {}
        games = grp["game_id"].nunique()
        ppg = grp.groupby("game_id").size().median() if games else 0
        pim = grp.groupby("game_id")["minutes"].sum().median() if games else 0
        # PP% on clean data: PP calls / total clean calls per game
        game_pp  = grp.groupby("game_id")["is_power_play"].sum()
        game_pen = grp.groupby("game_id").size()
        pp_rate  = (game_pp / game_pen).median() if len(game_pp) else 0
        # Per-period medians on clean data
        per_period = {}
        for p in [1, 2, 3]:
            pg = grp[pd.to_numeric(grp["period"], errors="coerce") == p]
            per_period[p] = pg.groupby("game_id").size().median() if games else 0
        return ppg, pim, pp_rate, per_period

    ppg1, pim1, pp1, period1 = _clean_ref_stats(ref1)
    ppg2, pim2, pp2, period2 = _clean_ref_stats(ref2)

    # Weight by clean penalty volume: higher-median ref gets bigger say
    total_ppg = ppg1 + ppg2
    w1 = (ppg1 / total_ppg) if total_ppg > 0 else 0.5
    w2 = (ppg2 / total_ppg) if total_ppg > 0 else 0.5

    base_ppg = w1 * ppg1 + w2 * ppg2
    base_pim = w1 * pim1 + w2 * pim2
    base_pp  = w1 * pp1  + w2 * pp2

    # Bias per team: average both refs' biases where data exists
    teams = [team_home, team_away]
    team_detail = {}
    total_bias  = 0.0

    for team in teams:
        b1, g1 = get_ref_bias_vs_team(ref1, team)
        b2, g2 = get_ref_bias_vs_team(ref2, team)
        available = [b for b in [b1, b2] if b is not None]
        blended   = round(sum(available) / len(available), 3) if available else None
        team_detail[team] = {
            "bias_ref1": b1, "games_ref1": g1,
            "bias_ref2": b2, "games_ref2": g2,
            "blended_bias": blended,
        }
        if blended is not None:
            total_bias += blended

    proj_total = max(0.0, round(base_ppg + total_bias, 2))

    # Confidence range: ±1 blended std dev of clean per-game penalty counts
    def _ref_std(ref_name):
        per_game = proj_stacked[proj_stacked["_ref"] == ref_name].groupby("game_id").size()
        return per_game.std(ddof=1) if len(per_game) > 1 else 1.0

    std1 = _ref_std(ref1)
    std2 = _ref_std(ref2)
    # Quadrature sum: the two refs are independent so their variances add,
    # giving a combined SD that properly reflects the full game's variability
    # rather than the weighted average (which always understates the spread).
    blended_std = round((std1 ** 2 + std2 ** 2) ** 0.5, 3)

    proj_low  = max(0.0, round(proj_total - blended_std, 1))
    proj_high = max(0.0, round(proj_total + blended_std, 1))

    # PIM: scale by same total bias (each penalty ~ 2 min, bias in penalty units)
    proj_pim  = max(0.0, round(base_pim + total_bias * 2.0, 2))

    # PP opportunities: projected total × blended PP%
    proj_pp_total = round(proj_total * base_pp, 2)

    # Per-team PP opportunities (penalties called *against* the opponent)
    pp_by_team = {}
    for team in teams:
        tb = team_detail[team]["blended_bias"] or 0.0
        team_pen_proj = max(0.0, (base_ppg / 2) + tb)
        pp_by_team[team] = round(team_pen_proj * base_pp, 2)

    # Per-period split: blend each ref's historical clean period fractions
    def _period_fracs(per_period_dict, ppg):
        if ppg == 0:
            return {1: 1/3, 2: 1/3, 3: 1/3}
        s = sum(per_period_dict.values())
        return {p: (v / s if s > 0 else 1/3) for p, v in per_period_dict.items()}

    fracs1 = _period_fracs(period1, ppg1)
    fracs2 = _period_fracs(period2, ppg2)
    period_proj = {
        p: round(proj_total * (w1 * fracs1.get(p, 1/3) + w2 * fracs2.get(p, 1/3)), 2)
        for p in [1, 2, 3]
    }

    return {
        "proj_total":     proj_total,
        "proj_low":       proj_low,
        "proj_high":      proj_high,
        "proj_pim":       proj_pim,
        "proj_pp_total":  proj_pp_total,
        "pp_by_team":     pp_by_team,
        "period_proj":    period_proj,
        "team_detail":    team_detail,
        "base_ppg":       round(base_ppg, 3),
        "w1":             round(w1, 3),
        "w2":             round(w2, 3),
        "ppg1":           round(ppg1, 2),
        "ppg2":           round(ppg2, 2),
        "blended_std":    round(blended_std, 3),
        "total_bias_adj": round(total_bias, 3),
        "base_pp_pct":    round(base_pp * 100, 1),
    }


proj = compute_projection(proj_ref1, proj_ref2, proj_home, proj_away)

# ── Headline metric cards ────────────────────────────────────────────────────
st.markdown("#### Projected Totals for This Game")
hc1, hc2, hc3, hc4 = st.columns(4)

bias_sign = "+" if proj["total_bias_adj"] >= 0 else ""

hc1.markdown(
    f'<div class="proj-card">'
    f'<div class="plbl">Total Penalties</div>'
    f'<div class="pval">{proj["proj_total"]}</div>'
    f'<div class="psub">Range {proj["proj_low"]} – {proj["proj_high"]}</div>'
    f'</div>',
    unsafe_allow_html=True,
)
hc2.markdown(
    f'<div class="proj-card">'
    f'<div class="plbl">Total PIM</div>'
    f'<div class="pval">{proj["proj_pim"]}</div>'
    f'<div class="psub">penalty minutes</div>'
    f'</div>',
    unsafe_allow_html=True,
)
hc3.markdown(
    f'<div class="proj-card">'
    f'<div class="plbl">PP Opportunities</div>'
    f'<div class="pval">{proj["proj_pp_total"]}</div>'
    f'<div class="psub">at {proj["base_pp_pct"]}% PP rate</div>'
    f'</div>',
    unsafe_allow_html=True,
)
hc4.markdown(
    f'<div class="proj-card">'
    f'<div class="plbl">Bias Adjustment</div>'
    f'<div class="pval">{bias_sign}{proj["total_bias_adj"]}</div>'
    f'<div class="psub">from team history</div>'
    f'</div>',
    unsafe_allow_html=True,
)

st.markdown("<br>", unsafe_allow_html=True)

# ── Confidence range ─────────────────────────────────────────────────────────
st.markdown("#### Confidence Range")
st.markdown(
    f'<div class="range-bar">'
    f'<div><span style="font-size:11px;color:#888">LOW</span><br>'
    f'<span class="range-low">{proj["proj_low"]}</span></div>'
    f'<div style="flex:1;text-align:center;color:#ccc;font-size:20px">————————————</div>'
    f'<div><span style="font-size:11px;color:#888">PROJECTED</span><br>'
    f'<span class="range-mid">{proj["proj_total"]}</span></div>'
    f'<div style="flex:1;text-align:center;color:#ccc;font-size:20px">————————————</div>'
    f'<div><span style="font-size:11px;color:#888">HIGH</span><br>'
    f'<span class="range-high">{proj["proj_high"]}</span></div>'
    f'</div>'
    f'<small style="color:#888">±1 blended std dev of both refs\' per-game penalty distributions '
    f'(blended SD: {proj["blended_std"]})</small>',
    unsafe_allow_html=True,
)

st.markdown("<br>", unsafe_allow_html=True)

# ── Period breakdown + PP by team ────────────────────────────────────────────
left_col, right_col = st.columns(2)

with left_col:
    st.markdown("#### Per-Period Breakdown")
    share_rows = ""
    for p in [1, 2, 3]:
        pval  = proj["period_proj"][p]
        share = round(pval / proj["proj_total"] * 100, 1) if proj["proj_total"] > 0 else "—"
        share_rows += f"<tr><td><b>Period {p}</b></td><td>{pval}</td><td>{share}%</td></tr>"
    st.markdown(f"""
    <table class="period-table">
      <tr><th>Period</th><th>Proj. Penalties</th><th>Share</th></tr>
      {share_rows}
    </table>
    <small style="color:#888">
      Based on each ref's historical per-period distribution, blended by weight
    </small>
    """, unsafe_allow_html=True)

with right_col:
    st.markdown("#### PP Opportunities by Team")
    pp_rows = "".join(
        f"<tr><td style='text-align:left;font-weight:700'>{team}</td>"
        f"<td>{proj['pp_by_team'].get(team, '—')}</td></tr>"
        for team in [proj_home, proj_away]
    )
    st.markdown(f"""
    <table class="period-table">
      <tr><th style="text-align:left">Team</th><th>Proj. PP Opps</th></tr>
      {pp_rows}
    </table>
    <small style="color:#888">
      PP opps = penalties projected against the opponent × blended PP% ({proj["base_pp_pct"]}%).<br>
      Team-specific bias adjustments are factored into each team's penalty projection.
    </small>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Team bias detail ──────────────────────────────────────────────────────────
st.markdown("#### Team Bias Detail")

r1_short = proj_ref1.split()[-1]
r2_short = proj_ref2.split()[-1]

bias_detail_rows = ""
for team in [proj_home, proj_away]:
    td = proj["team_detail"][team]
    season_ppg = team_baseline.loc[team, "season_ppg"] if team in team_baseline.index else "—"

    def _fmt_bias(bias, games):
        if bias is None:
            return "<span style='color:#aaa'>— (no data)</span>"
        sign  = "+" if bias > 0 else ""
        color = "#8b0000" if bias > 0 else "#1a6b16"
        flag  = f" ({games}G)" if games >= BIAS_MIN_GAMES else f" ({games}G) ⚠️"
        return f"<span style='color:{color};font-weight:700'>{sign}{bias}</span><span style='font-size:10px;color:#888'>{flag}</span>"

    def _fmt_blended(bias):
        if bias is None:
            return "<span style='color:#aaa'>—</span>"
        sign  = "+" if bias > 0 else ""
        color = "#8b0000" if bias > 0 else "#1a6b16"
        return f"<span style='color:{color};font-weight:800;font-size:14px'>{sign}{bias}</span>"

    bias_detail_rows += (
        f"<tr>"
        f"<td style='text-align:left;font-weight:700;font-size:14px'>{team}</td>"
        f"<td>{season_ppg}</td>"
        f"<td>{_fmt_bias(td['bias_ref1'], td['games_ref1'])}</td>"
        f"<td>{_fmt_bias(td['bias_ref2'], td['games_ref2'])}</td>"
        f"<td>{_fmt_blended(td['blended_bias'])}</td>"
        f"</tr>"
    )

st.markdown(f"""
<table class="team-proj-table">
  <tr>
    <th style="text-align:left">Team</th>
    <th>Season Pen/G</th>
    <th>{r1_short} Bias</th>
    <th>{r2_short} Bias</th>
    <th>Blended Bias</th>
  </tr>
  {bias_detail_rows}
</table>
<small style="color:#888">
  Bias = ref's median pen/G vs team − team season pen/G &nbsp;|&nbsp;
  <span style="color:#8b0000;font-weight:600">red = ref historically harder on that team</span> &nbsp;|&nbsp;
  <span style="color:#1a6b16;font-weight:600">green = easier</span> &nbsp;|&nbsp;
  ⚠️ fewer than {BIAS_MIN_GAMES} games together — treat as directional only &nbsp;|&nbsp;
  blended = average of the two refs' biases where data exists
</small>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Methodology expander ──────────────────────────────────────────────────────
with st.expander("📐 How this projection works"):
    st.markdown(f"""
    <div class="methodology-box">
    <b>Offsetting pair & fighting filters</b><br>
    Before any projection math runs, two categories of non-discretionary penalties
    are removed from the projector's input data:<br>
    &nbsp;&nbsp;• <b>Offsetting minors</b> — same time, opposite teams, is_power_play = 0 (4v4 situations)<br>
    &nbsp;&nbsp;• <b>Fighting penalties</b> — Fighting, Instigating, Aggressor (refs have no choice)<br>
    Both still appear in the main dashboard and penalty logs — they just don't feed
    the projection. All stats below are computed on this clean dataset.<br><br>

    <b>Step 1 — Weighted blend of ref medians</b><br>
    Each ref's clean median pen/game is the base. The higher-median ref gets a
    proportionally larger weight (their median ÷ the sum of both medians), so their
    tendencies drive the estimate more when there's a meaningful difference.<br>
    &nbsp;&nbsp;• <b>{proj_ref1}</b>: {proj['ppg1']} pen/G (clean) → weight <b>{proj['w1']:.1%}</b><br>
    &nbsp;&nbsp;• <b>{proj_ref2}</b>: {proj['ppg2']} pen/G (clean) → weight <b>{proj['w2']:.1%}</b><br>
    &nbsp;&nbsp;• Blended base: <b>{proj['base_ppg']}</b> pen/game<br><br>

    <b>Step 2 — Team bias adjustments</b><br>
    For each team, we look at how each ref's clean median pen/game against them compares
    to that team's clean season average. Both refs' biases are averaged (where data exists)
    to get a blended bias per team. The sum of both teams' blended biases is added
    to the base projection.<br>
    &nbsp;&nbsp;• Total bias adjustment applied: <b>{"+" if proj["total_bias_adj"] >= 0 else ""}{proj["total_bias_adj"]}</b><br><br>

    <b>Step 3 — Confidence range</b><br>
    Each ref's standard deviation of clean per-game penalty counts is combined using
    quadrature (√(SD₁² + SD₂²)) rather than a weighted average — because the two refs
    are independent, their variances add. A weighted average always lands between the
    two individual SDs and understates the true spread of a two-ref game.
    Low = projection − combined SD, High = projection + combined SD.<br>
    &nbsp;&nbsp;• Combined SD: <b>{proj['blended_std']}</b><br><br><br><br>

    <b>Step 4 — PIM, PP opportunities, and period splits</b><br>
    PIM uses the blended clean PIM/game rate with the same bias scaling (each penalty ≈ 2 min).
    PP opportunities = projected total penalties × blended clean PP%. Per-team PP opps use
    each team's bias-adjusted penalty projection. Period splits use each ref's
    historical share of clean calls per period, blended by the same weights.
    </div>
    """, unsafe_allow_html=True)


st.markdown("---")
st.caption("Data source: AHL / HockeyTech · Built with ahl_penalty_ref_scraper.py")
