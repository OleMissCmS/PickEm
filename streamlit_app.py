
# streamlit_app.py — Paste Analyzer with PRE-GAME logic for your entry
# - Everyone: Missing Numbers method
# - Your entry: PRE-GAME (from scoreboard headers)
# - Treats "- (N)" as used
# Requires: streamlit, pandas

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple, Set
import streamlit as st
import pandas as pd

@dataclass
class Participant:
    rank: Optional[int]
    name: str
    current_points: float
    picks: List[Tuple[str, int]]  # (TEAM_OR_DASH, CONF)

# ---------- regexes ----------
RANK_RE = re.compile(r"^(\d{1,2})(st|nd|rd|th)$", re.I)
TEAM_RE = re.compile(r"^[A-Za-z]{2,4}$")
PICK_INLINE_RE = re.compile(r"^\s*([A-Z]{2,4}|-)\s*\(\s*(\d{1,2})\s*\)\s*$")
NUMS_LINE_2INTS_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s*$")
CONF_ONLY_RE = re.compile(r"^\s*\(\s*(\d{1,2})\s*\)\s*$")

# Status detectors for the scoreboard header lines
IS_FINAL = re.compile(r"\bfinal\b", re.I)
IS_LIVE = re.compile(r"\b(q[1-4]|1st|2nd|3rd|4th|ot)\b|\b\d{1,2}:\d{2}\b", re.I)
IS_TIME = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b.*\b(AM|PM)\b", re.I)

def _clean_lines(raw: str) -> List[str]:
    lines = [ln.strip() for ln in raw.replace("\r", "").split("\n")]
    return [ln for ln in lines if ln]

def parse_games_block(lines: List[str]) -> Tuple[int, Set[str]]:
    """
    Read the scoreboard block (before first rank) and return:
      - start index of participants
      - set of TEAM abbreviations appearing in PRE-GAME (not started) matchups
    Heuristics:
      FINAL/FINAL OT -> decided (skip)
      Lines with Q1/Q2/Q3/Q4/OT or mm:ss -> LIVE (skip)
      Lines like 'Mon 7:15 PM' -> PRE-GAME; next two lines are teams
    """
    pregame_teams: Set[str] = set()
    i, n = 0, len(lines)

    # Walk until we reach the first rank line
    while i < n and not RANK_RE.match(lines[i]):
        line = lines[i]

        if IS_FINAL.search(line) or IS_LIVE.search(line):
            # Try to jump past status + TEAM + TEAM + SCORE + SCORE when present
            if i + 4 < n and TEAM_RE.match(lines[i+1]) and TEAM_RE.match(lines[i+2]):
                i += 5
            else:
                i += 1

        elif IS_TIME.search(line):
            # PRE-GAME: take next two TEAM lines (if present)
            if i + 2 < n and TEAM_RE.match(lines[i+1]) and TEAM_RE.match(lines[i+2]):
                t1, t2 = lines[i+1].upper(), lines[i+2].upper()
                pregame_teams.update([t1, t2])
                # After time + teams, CBS may show noise lines ("TIE", matchup code, "-"); just advance by 3
                i += 3
            else:
                i += 1

        else:
            # Unknown header/noise; move on
            i += 1

    # Ensure we're exactly at the first rank
    while i < n and not RANK_RE.match(lines[i]):
        i += 1

    return i, pregame_teams

def parse_participants(lines: List[str], start_idx: int) -> List[Participant]:
    parts: List[Participant] = []
    i, n = start_idx, len(lines)

    while i < n:
        m_rank = RANK_RE.match(lines[i])
        if not m_rank:
            i += 1
            continue
        rank = int(m_rank.group(1)); i += 1
        if i >= n: break

        name = lines[i]; i += 1
        if i >= n: break

        current_points = 0.0
        m2 = NUMS_LINE_2INTS_RE.match(lines[i]) if i < n else None
        if m2:
            current_points = float(m2.group(1)); i += 1
        else:
            maybe = re.sub(r"[^\d\.]", "", lines[i]) if i < n else ""
            if maybe:
                try: current_points = float(maybe)
                except: current_points = 0.0
            i += 1

        picks: List[Tuple[str, int]] = []
        while i < n and not RANK_RE.match(lines[i]):
            line = lines[i]

            m_inline = PICK_INLINE_RE.match(line)
            if m_inline:
                picks.append((m_inline.group(1), int(m_inline.group(2))))
                i += 1; continue

            if (TEAM_RE.match(line) or line == "-") and (i + 1) < n:
                m_conf = CONF_ONLY_RE.match(lines[i+1])
                if m_conf:
                    picks.append((line, int(m_conf.group(1))))
                    i += 2; continue

            i += 1

        parts.append(Participant(rank=rank, name=name, current_points=current_points, picks=picks))
    return parts

def pts_remaining_missing_numbers(p: Participant, max_conf: int) -> int:
    used = {c for _, c in p.picks}  # '-' counts as used
    return sum(c for c in range(1, max_conf + 1) if c not in used)

def pts_remaining_pregame_only(p: Participant, pregame_teams: Set[str]) -> int:
    # Only sum confidences whose TEAM is in PRE-GAME set; ignore '-' picks
    return sum(conf for (team, conf) in p.picks if team != "-" and team.upper() in pregame_teams)

# --------------- UI ---------------
st.set_page_config(page_title="CBS Pick 'Em — Paste Analyzer", layout="wide")
st.title("🏈 CBS Pick 'Em — Paste Analyzer")
st.caption("Everyone uses **Missing Numbers**. Your selected entry uses **PRE-GAME** (from scoreboard headers). "
           "Live games (Q1/3:21/etc.) and Final games do **not** count as remaining.")

raw = st.text_area("Paste the visible text from your Weekly Standings page:", height=380)
override_max = st.number_input("Optional: Override Max Confidence (leave 0 to auto)", 0, 30, 0, 1)

if st.button("Analyze", type="primary"):
    if not raw.strip():
        st.error("Please paste the standings text first.")
    else:
        try:
            lines = _clean_lines(raw)
            start_idx, pregame_teams = parse_games_block(lines)
            parts = parse_participants(lines, start_idx)
            if not parts:
                st.warning("No participants parsed. Double-check your paste.")
            else:
                # Choose your entry (used for PRE-GAME method)
                names = [p.name for p in parts]
                your_name = st.selectbox("Your entry (optional):", ["(none)"] + names, index=0)

                # Week size = max confidence seen (overrideable)
                all_confs = [conf for p in parts for (_, conf) in p.picks]
                auto_max = max(all_confs) if all_confs else 0
                max_conf = override_max if override_max > 0 else auto_max

                # Build table
                rows = []
                for p in parts:
                    pts_rem = pts_remaining_missing_numbers(p, max_conf)
                    if your_name != "(none)" and p.name == your_name:
                        pts_rem = pts_remaining_pregame_only(p, pregame_teams)
                    rows.append({
                        "Name": p.name,
                        "Current Standing": p.rank,
                        "Current Points": p.current_points,
                        "Points Remaining": pts_rem,
                        "Total Points Possible": p.current_points + pts_rem,
                    })

                df = pd.DataFrame(rows).sort_values(
                    by=["Total Points Possible", "Current Points"],
                    ascending=[False, False],
                    kind="mergesort"
                ).reset_index(drop=True)

                # Header
                left, right = st.columns([1, 2])
                with left: st.metric("Week Size (Max Confidence)", max_conf)
                with right:
                    st.caption("PRE-GAME detected teams: " + (", ".join(sorted(pregame_teams)) if pregame_teams else "none"))

                st.divider()
                st.subheader("Standings with Remaining Ceiling")
                st.dataframe(df, use_container_width=True, hide_index=True)

                # Debug expander (helps verify your row)
                with st.expander("Debug — per-player details"):
                    for p in parts:
                        used = sorted({c for _, c in p.picks})
                        missing = [c for c in range(1, max_conf + 1) if c not in used]
                        miss_sum = sum(missing)
                        pre_sum = pts_remaining_pregame_only(p, pregame_teams)
                        me_flag = " ← YOU" if your_name != "(none)" and p.name == your_name else ""
                        st.write(f"**{p.name}**{me_flag} — used: {used} | missing: {missing} (sum={miss_sum}) | PRE-GAME sum={pre_sum}")

        except Exception as e:
            st.error(f"Parsing failed: {e}")
            st.info("Make sure the scoreboard header is included so PRE-GAME lines like 'Mon 7:15 PM' are present.")
