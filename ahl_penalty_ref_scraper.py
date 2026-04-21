#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AHL Penalty + Referee Scraper
==============================
Scrapes penalty data from the HockeyTech Play-by-Play feed and referee
assignments from the gameSummary feed, then joins them by game_id.

Why two feeds?
- gameCenterPlayByPlay  → has clean per-penalty events (takenBy, team, infraction, etc.)
- gameSummary           → has the officials/referee block (not present in PBP)

Output CSV columns:
  game_id, period, period_long, time, team_id, team_abbrev,
  player_id, player, jersey, position, infraction, minutes,
  is_power_play, is_bench, served_by_id, served_by,
  ref1, ref2, linesman1, linesman2

Usage:
  python ahl_penalty_ref_scraper.py --game_ids 1026478 1027801
  python ahl_penalty_ref_scraper.py --start_id 1026400 --end_id 1026450 --out_dir ./data
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

# ── API endpoints ────────────────────────────────────────────────────────────

BASE_URL = "https://lscluster.hockeytech.com/feed/index.php"
DEFAULT_KEY = "ccb91f29d6744675"
DEFAULT_CLIENT = "ahl"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json,text/javascript,*/*;q=0.9",
}

# ── Output columns ────────────────────────────────────────────────────────────

CSV_COLS = [
    "game_id", "period", "period_long", "time",
    "team_id", "team_abbrev",
    "player_id", "player", "jersey", "position",
    "infraction", "minutes",
    "is_power_play", "is_bench",
    "served_by_id", "served_by",
    "ref1", "ref2", "linesman1", "linesman2",
]

# ── JSONP stripping ───────────────────────────────────────────────────────────

# Matches: angular.callbacks._5(...) or angular.callbacks._6(...) etc.
_JSONP_RE = re.compile(r"^[^(]+\((.*)\)\s*;?\s*$", re.DOTALL)

def strip_jsonp(text: str) -> str:
    t = text.strip()
    m = _JSONP_RE.match(t)
    return m.group(1) if m else t

def parse_json(text: str) -> Optional[Any]:
    """Try plain JSON first, then strip JSONP wrapper and retry."""
    try:
        return json.loads(text)
    except Exception:
        try:
            return json.loads(strip_jsonp(text))
        except Exception:
            return None

# ── Generic fetcher with retry ────────────────────────────────────────────────

def fetch(params: Dict[str, str], retries: int = 3, timeout: float = 20.0,
          delay: float = 0.5, debug: bool = False) -> Optional[Any]:
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=timeout)
            if debug:
                q = "&".join(f"{k}={v}" for k, v in params.items())
                print(f"  GET {BASE_URL}?{q}", flush=True)
                print(f"  → HTTP {r.status_code}, {len(r.text)} bytes", flush=True)
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}"
                time.sleep(delay * attempt)
                continue
            data = parse_json(r.text)
            if data is not None:
                return data
            last_err = "JSON parse failed"
        except Exception as e:
            last_err = e
        time.sleep(delay * attempt)
    if debug:
        print(f"  !! All attempts failed: {last_err}", flush=True)
    return None

# ── Attempt matrix (mirrors ahl_boxscore_scraper.py logic) ───────────────────

def _attempt_matrix(game_id: int, view: str, key: str, client: str) -> List[Dict[str, str]]:
    """
    Build a list of param dicts to try in order. Tries:
      - site_id 3 and 1
      - with and without league_id
      - plain JSON, callback _5, callback _6
    This mirrors the robust approach in ahl_boxscore_scraper.py.
    """
    attempts = []
    for site_id in ("3", "1"):
        for with_league in (True, False):
            base = {
                "feed": "statviewfeed",
                "view": view,
                "game_id": str(game_id),
                "key": key,
                "client_code": client,
                "lang": "en",
                "site_id": site_id,
            }
            if with_league:
                base["league_id"] = ""
            # Plain
            attempts.append(dict(base))
            # JSONP callbacks
            for cb in ("_5", "_6"):
                p = dict(base)
                p["callback"] = f"angular.callbacks.{cb}"
                attempts.append(p)
    return attempts

# ── PBP feed → penalties ──────────────────────────────────────────────────────

def fetch_pbp(game_id: int, key: str, client: str, retries: int,
              timeout: float, delay: float, debug: bool) -> Optional[List[Dict]]:
    """
    Fetch gameCenterPlayByPlay. Returns the raw list of event dicts, or None.
    The PBP feed only works with the JSONP callback variant.
    """
    for cb in ("_5", "_6"):
        for site_id in ("3", "1"):
            for with_league in (True, False):
                params: Dict[str, str] = {
                    "feed": "statviewfeed",
                    "view": "gameCenterPlayByPlay",
                    "game_id": str(game_id),
                    "key": key,
                    "client_code": client,
                    "lang": "en",
                    "site_id": site_id,
                    "callback": f"angular.callbacks.{cb}",
                }
                if with_league:
                    params["league_id"] = ""
                data = fetch(params, retries=retries, timeout=timeout,
                             delay=delay, debug=debug)
                if isinstance(data, list) and data:
                    return data
    return None

def extract_penalties_from_pbp(game_id: int, events: List[Dict]) -> List[Dict[str, Any]]:
    """Parse penalty events out of the PBP list. Ref fields left blank (filled later)."""
    rows = []
    for ev in events:
        if ev.get("event") != "penalty":
            continue
        d = ev.get("details") or {}

        period = (d.get("period") or {})
        taken_by = d.get("takenBy") or {}
        served_by = d.get("servedBy") or {}
        against_team = d.get("againstTeam") or {}

        rows.append({
            "game_id": game_id,
            "period": period.get("shortName", ""),
            "period_long": period.get("longName", ""),
            "time": d.get("time", ""),
            "team_id": against_team.get("id", ""),
            "team_abbrev": against_team.get("abbreviation", ""),
            "player_id": taken_by.get("id", ""),
            "player": f"{taken_by.get('firstName', '')} {taken_by.get('lastName', '')}".strip(),
            "jersey": taken_by.get("jerseyNumber", ""),
            "position": taken_by.get("position", ""),
            "infraction": d.get("description", ""),
            "minutes": d.get("minutes", ""),
            "is_power_play": int(bool(d.get("isPowerPlay"))),
            "is_bench": int(bool(d.get("isBench"))),
            "served_by_id": served_by.get("id", ""),
            "served_by": f"{served_by.get('firstName', '')} {served_by.get('lastName', '')}".strip(),
            # Refs filled in below after gameSummary fetch
            "ref1": "",
            "ref2": "",
            "linesman1": "",
            "linesman2": "",
        })
    return rows

# ── gameSummary feed → officials ──────────────────────────────────────────────

def fetch_officials(game_id: int, key: str, client: str, retries: int,
                    timeout: float, delay: float, debug: bool
                    ) -> Tuple[str, str, str, str]:
    """
    Returns (ref1, ref2, linesman1, linesman2) from gameSummary.

    The AHL HockeyTech feed stores officials under data['referees'] (confirmed
    via DOM inspection: ng-repeat="referee in ::gameSummary.referees").
    Each entry has: { role: "Referee" | "Linesman", fn: "First", ln: "Last" }

    Falls back to empty strings on failure.
    """
    for params in _attempt_matrix(game_id, "gameSummary", key, client):
        data = fetch(params, retries=retries, timeout=timeout,
                     delay=delay, debug=debug)
        if not isinstance(data, dict):
            continue

        # Primary key confirmed from AHL site DOM: gameSummary.referees
        # Fallback to 'officials' in case other HockeyTech clients differ
        officials = data.get("referees") or data.get("officials") or []

        if debug and data:
            print(f"  gameSummary keys: {list(data.keys())}", flush=True)
            print(f"  referees raw: {officials}", flush=True)

        refs = []
        linesmen = []
        for o in officials:
            # Name fields: fn / ln (confirmed from DOM td ng-bind="::referee.role")
            name = f"{o.get('fn', '')} {o.get('ln', '')}".strip()
            if not name:
                # Some entries may use firstName/lastName instead
                name = f"{o.get('firstName', '')} {o.get('lastName', '')}".strip()
            role = (o.get("role") or "").strip()
            # Role string confirmed from DOM: "Referee" (capital R)
            if role == "Referee" or "referee" in role.lower():
                refs.append(name)
            elif role == "Linesman" or "linesman" in role.lower() or "lines" in role.lower():
                linesmen.append(name)

        # Positional fallback if role strings are missing/unexpected
        if not refs and not linesmen and officials:
            names = [f"{o.get('fn', '')} {o.get('ln', '')}".strip() for o in officials]
            refs = names[:2]
            linesmen = names[2:4]

        if refs or linesmen:
            return (
                refs[0] if len(refs) > 0 else "",
                refs[1] if len(refs) > 1 else "",
                linesmen[0] if len(linesmen) > 0 else "",
                linesmen[1] if len(linesmen) > 1 else "",
            )

    return ("", "", "", "")

# ── CSV output ────────────────────────────────────────────────────────────────

def write_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in CSV_COLS})

# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="AHL penalty + referee scraper (PBP + gameSummary)"
    )
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--game_ids", nargs="+", type=int,
                     help="One or more game IDs.")
    grp.add_argument("--start_id", type=int,
                     help="Start of game ID range (inclusive).")
    ap.add_argument("--end_id", type=int,
                    help="End of game ID range (inclusive). Used with --start_id.")
    ap.add_argument("--out_dir", default=".",
                    help="Output directory for CSVs. Default: .")
    ap.add_argument("--key", default=DEFAULT_KEY,
                    help=f"Feed key. Default: {DEFAULT_KEY}")
    ap.add_argument("--client_code", default=DEFAULT_CLIENT,
                    help=f"Client code. Default: {DEFAULT_CLIENT}")
    ap.add_argument("--delay", type=float, default=0.8,
                    help="Seconds between games. Default: 0.8")
    ap.add_argument("--retries", type=int, default=3,
                    help="HTTP retries per request. Default: 3")
    ap.add_argument("--timeout", type=float, default=20.0,
                    help="HTTP timeout seconds. Default: 20.0")
    ap.add_argument("--debug", action="store_true",
                    help="Print HTTP request details.")
    return ap.parse_args()


def expand_ids(args: argparse.Namespace) -> List[int]:
    if args.game_ids:
        return list(dict.fromkeys(int(g) for g in args.game_ids))
    end = args.end_id if args.end_id is not None else args.start_id
    if end < args.start_id:
        raise ValueError("--end_id must be >= --start_id")
    return list(range(args.start_id, end + 1))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    args = parse_args()
    game_ids = expand_ids(args)
    out_root = os.path.abspath(args.out_dir)
    os.makedirs(out_root, exist_ok=True)

    print(f"--- AHL Penalty + Ref Scraper ---")
    print(f"Games: {len(game_ids)} | out_dir: {out_root}")

    total_penalties = 0

    for i, gid in enumerate(game_ids, 1):
        print(f"\n[{i}/{len(game_ids)}] Game {gid}")

        # ── Step 1: PBP → penalties ──
        print(f"  Fetching play-by-play...", end=" ", flush=True)
        events = fetch_pbp(gid, args.key, args.client_code,
                           args.retries, args.timeout, args.delay, args.debug)
        if not events:
            print("FAILED (no PBP data)")
            csv_path = os.path.join(out_root, f"ahl_penalties_{gid}.csv")
            write_csv(csv_path, [])
            continue

        rows = extract_penalties_from_pbp(gid, events)
        print(f"{len(rows)} penalties found")

        # ── Step 2: gameSummary → officials ──
        print(f"  Fetching officials...", end=" ", flush=True)
        ref1, ref2, lin1, lin2 = fetch_officials(
            gid, args.key, args.client_code,
            args.retries, args.timeout, args.delay, args.debug
        )
        if ref1 or ref2:
            print(f"Refs: {ref1 or '—'}, {ref2 or '—'}  |  "
                  f"Linesmen: {lin1 or '—'}, {lin2 or '—'}")
        else:
            print("No official data found (will leave blank)")

        # ── Step 3: Stamp refs onto every penalty row ──
        for row in rows:
            row["ref1"] = ref1
            row["ref2"] = ref2
            row["linesman1"] = lin1
            row["linesman2"] = lin2

        # ── Step 4: Write CSV ──
        csv_path = os.path.join(out_root, f"ahl_penalties_{gid}.csv")
        write_csv(csv_path, rows)
        print(f"  → {csv_path}")
        total_penalties += len(rows)

        if i < len(game_ids):
            time.sleep(args.delay)

    print(f"\n--- Done. Total penalties written: {total_penalties} ---")


if __name__ == "__main__":
    main()