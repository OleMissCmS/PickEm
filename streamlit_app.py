
# streamlit_app.py — Paste Analyzer with robust PRE-GAME logic + manual override
# Everyone: Missing Numbers method
# Your entry: PRE-GAME (from scoreboard headers/codes) OR manual override of remaining teams
# Treats "- (N)" as used
# Requires: streamlit, pandas
# Version: v1.1.1

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

# ---------- team normalization ----------
TEAM_ALIASES = {
    "JAC": "JAX", "JAX": "JAX",
    "WSH": "WAS", "WAS": "WAS",
    "LA": "LAR", "LAR": "LAR", "STL": "LAR",
    "SD": "LAC", "LAC": "LAC",
    "OAK": "LV", "LVR": "LV", "LV": "LV",
    "ARZ": "ARI", "ARI": "ARI", "AZ": "ARI",
    "TAM": "TB", "TBB": "TB", "TB": "TB",
    "GNB": "GB", "GB": "GB",
    "KAN": "KC", "KCC": "KC", "KC": "KC",
    "NWE": "NE", "NE": "NE",
    "NOS": "NO", "NO": "NO",
    "SFO": "SF", "SF": "SF",
    "CLV": "CLE", "CLE": "CLE",
    "HST": "HOU", "HOU": "HOU",
    "BLT": "BAL", "BAL": "BAL",
    "NYG": "NYG", "NYJ": "NYJ",
    "SEA": "SEA", "BUF": "BUF", "MIA": "MIA",
    "MIN": "MIN", "PHI": "PHI", "PIT": "PIT",
    "DET": "DET", "CHI": "CHI", "DAL": "DAL",
    "TEN": "TEN", "ATL": "ATL", "CAR": "CAR",
}

def norm_team(tok: str) -> str:
    if not tok or tok == "-":
        return tok
    t = re.sub(r"[^A-Za-z]", "", tok.upper())
    return TEAM_ALIASES.get(t, t)

# ---------- regexes ----------
RANK_RE  = re.compile(r"^(\d{1,2})(st|nd|rd|th)$", re.I)
TEAM_RE  = re.compile(r"^[A-Za-z]{2,4}$")
PICK_INLINE_RE = re.compile(r"^\s*([A-Z]{2,4}|-)\s*\(\s*(\d{1,2})\s*\)\s*$")
NUMS_LINE_2INTS_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s*$")
CONF_ONLY_RE = re.compile(r"^\s*\(\s*(\d{1,2})\s*\)\s*$")

# Scoreboard status detectors
IS_FINAL = re.compile(r"\bfinal\b", re.I)
IS_LIVE  = re.compile(r"\b(q[1-4]|1st|2nd|3rd|4th|ot)\b|\b\d{1,2}:\d{2}\b", re.I)
# PRE-GAME time header: weekday / Today / Tonight + time am/pm
IS_TIME  = re.compile(r"(?:(Mon|Tue|Tues|Wed|Thu|Thur|Fri|Sat|Sun)|Today|Tonight)\s+\d{1,2}:\d{2}\s*[AaPp][Mm]\b", re.I)
# Matchup code like KC-JAX
IS_CODE  = re.compile(r"^[A-Za-z]{2,4}\s*-\s*[A-Za-z]{2,4}$")
# Simple noise tokens often between lines
NOISE_RE = re.compile(r"^(TIE|[–—-])$", re.I)

def _clean_lines(raw: str) -> List[str]:
    lines = [ln.strip() for ln in raw.replace("\r", "").split("\n")]
    return [ln for ln in lines if ln]

def _look_ahead_two_teams(lines: List[str], start: int, window: int = 8) -> Optional[Tuple[str, str]]:
    """Scan next up-to-`window` lines for the first two team codes (skip noise)."""
    found = []
    n = len(lines)
    for j in range(start + 1, min(start + 1 + window, n)):
        tok = lines[j].strip()
        if NOISE_RE.match(tok):
            continue
        if TEAM_RE.match(tok) and tok != "-":
            found.append(norm_team(tok))
            if len(found) == 2:
                return found[0], found[1]
    return None

def parse_games_block(lines: List[str]) -> Tuple[int, Set[str], List[str]]:
    """
    Returns:
      start_idx: index of first rank line (e.g., '1st')
      pregame_teams: set of normalized team codes in PRE-GAME matchups
      pregame_headers: raw header lines that triggered PRE-GAME (for debug)
    PRE-GAME triggers (any of):
      • time header (Mon/Tonight/etc)
      • matchup code like 'KC-JAX'
      • 'TIE' line with two team lines just above
    """
    pregame_teams: Set[str] = set()
    pregame_headers: List[str] = []
    i, n = 0, len(lines)

    while i < n and not RANK_RE.match(lines[i]):
        line = lines[i]

        # FINAL or LIVE -> skip if teams present, else step
        if IS_FINAL.search(line) or IS_LIVE.search(line):
            if i + 2 < n and TEAM_RE.match(lines[i+1]) and TEAM_RE.match(lines[i+2]):
                i += 5 if i + 4 < n else 3  # status + team + team (+scores)
            else:
                i += 1
            continue

        # TIME header: look ahead for the first two team codes
        if IS_TIME.search(line):
            pair = _look_ahead_two_teams(lines, i, window=8)
            if pair:
                a, b = pair
                pregame_teams.update([a, b])
                pregame_headers.append(line)
            i += 1
            continue

        # MATCHUP code like KC-JAX
        if IS_CODE.match(line):
            a, b = [norm_team(t) for t in re.split(r"-", line)]
            pregame_teams.update([a, b])
            pregame_headers.append(line)
            i += 1
            continue

        # 'TIE' under two team lines → treat as PRE-GAME pair
        if line.upper() == "TIE" and i >= 2 and TEAM_RE.match(lines[i-2]) and TEAM_RE.match(lines[i-1]):
            a = norm_team(lines[i-2]); b = norm_team(lines[i-1])
            pregame_teams.update([a, b])
            pregame_headers.append("TIE")
            i += 1
            continue

        # unknown/noise
        i += 1

    # move exactly to first rank line
    while i < n and not RANK_RE.match(lines[i]):
        i += 1

    return i, pregame_teams, pregame_headers

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
                picks.append((norm_team(m_inline.group(1)), int(m_inline.group(2))))
                i += 1; continue

            if (TEAM_RE.match(line) or line == "-") and (i + 1) < n:
                m_conf = CONF_ONLY_RE.match(lines[i+1])
                if m_conf:
                    picks.append((norm_team(line), int(m_conf.group(1))))
                    i += 2; continue

            i += 1

        parts.append(Participant(rank=rank, name=name, current_points=current_points, picks=picks))
    return parts

def pts_remaining_missing_numbers(p: Participant, max_conf: int) -> int:
    used = {c for _, c in p.picks}  # '-' counts as used
    return sum(c for c in range(1, max_conf + 1) if c not in used)

def pts_remaining_for_entry(p: Participant, remaining_teams: Set[str]) -> int:
    # Only sum confidences where the TEAM is in remaining_teams; ignore '-' picks
    return sum(conf for (team, conf) in p.picks if team != "-" and norm_team(team) in remaining_teams)

# --------------- UI ---------------
st.set_page_config(page_title="CBS Pick 'Em — Paste Analyzer", layout="wide")
st.title("🏈 CBS Pick 'Em — Paste Analyzer (PRE-GAME + manual override)")
st.caption("Everyone uses **Missing Numbers**. Your selected entry uses **PRE-GAME** from headers/codes "
           "or a **manual remaining teams** override. Live/Final games do not count as remaining.")

raw = st.text_area("Paste the visible text from your Weekly Standings page:", height=380)
override_max = st.number_input("Optional: Override Max Confidence (leave 0 to auto)", 0, 30, 0, 1)

if st.button("Analyze", type="primary"):
    if not raw.strip():
        st.error("Please paste the standings text first.")
    else:
        try:
            lines = _clean_lines(raw)
            start_idx, pregame_teams, pregame_headers = parse_games_block(lines)
            parts = parse_participants(lines, start_idx)
            if not parts:
                st.warning("No participants parsed. Double-check your paste.")
            else:
                # Choose your entry
                names = [p.name for p in parts]
                your_name = st.selectbox("Your entry (optional):", ["(none)"] + names, index=0)

                # Week size = max confidence seen (overrideable)
                all_confs = [conf for p in parts for (_, conf) in p.picks]
                auto_max = max(all_confs) if all_confs else 0
                max_conf = override_max if override_max > 0 else auto_max

                # Manual override for remaining teams (pre-populated with detected PRE-GAME teams)
                all_team_tokens = sorted({norm_team(t) for p in parts for (t, _) in p.picks if t != "-"})
                manual_teams = st.multiselect(
                    "Manual override — Remaining matchup teams (optional)",
                    options=all_team_tokens,
                    default=sorted(pregame_teams),
                    help="If the header detection missed your last game, pick the two teams here. "
                         "Used only for YOUR entry."
                )
                manual_set = set(manual_teams)

                # Build table
                rows = []
                for p in parts:
                    pts_rem = pts_remaining_missing_numbers(p, max_conf)
                    if your_name != "(none)" and p.name == your_name:
                        remaining = manual_set if manual_set else pregame_teams
                        pts_rem = pts_remaining_for_entry(p, remaining)
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
                left, mid, right = st.columns([1, 2, 2])
                with left: st.metric("Week Size (Max Confidence)", max_conf)
                with mid:
                    st.caption("Detected PRE-GAME teams (normalized): " + (", ".join(sorted(pregame_teams)) if pregame_teams else "none"))
                with right:
                    if your_name != "(none)":
                        st.caption(f"Remaining teams used for **{your_name}**: " + (", ".join(sorted(manual_set if manual_set else pregame_teams)) or "none"))

                st.divider()
                st.subheader("Standings with Remaining Ceiling")
                st.dataframe(df, use_container_width=True, hide_index=True)

                # Debug expander
                with st.expander("Debug — headers/codes & your picks"):
                    st.write("**PRE-GAME header/code lines detected:**")
                    if pregame_headers:
                        for h in pregame_headers:
                            st.write(f"• {h}")
                    else:
                        st.write("_none (did the paste include the scoreboard header?)_")

                    if your_name != "(none)":
                        you = next((p for p in parts if p.name == your_name), None)
                        if you:
                            st.write(f"**Your picks (normalized):** {[(t, c) for (t, c) in you.picks]}")
                            st.write(f"**Remaining teams applied:** {sorted(manual_set if manual_set else pregame_teams)}")
                            pre_pts = pts_remaining_for_entry(you, manual_set if manual_set else pregame_teams)
                            st.write(f"**Points Remaining for {your_name}: {pre_pts}")

        except Exception as e:
            st.error(f"Parsing failed: {e}")
            st.info("Make sure the scoreboard header section is included (time lines, matchup codes, or TIE).")

st.divider()
st.caption("Version: v1.1.1")
