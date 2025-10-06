
# streamlit_app.py — Paste Analyzer with stronger header scan + redundancy + check-figures
# Version: v1.4.2

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple, Set
import streamlit as st
import pandas as pd
from statistics import mode, StatisticsError

@dataclass
class Participant:
    rank: Optional[int]
    name: str
    current_points: float
    picks: List[Tuple[str, int]]  # (TEAM_OR_DASH, CONF)

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

RANK_RE  = re.compile(r"^(\d{1,2})(st|nd|rd|th)$", re.I)
TEAM_RE  = re.compile(r"^[A-Za-z]{2,4}$")
PICK_INLINE_RE = re.compile(r"^\s*([A-Z]{2,4}|-)\s*\(\s*(\d{1,2})\s*\)\s*$")
NUMS_LINE_2INTS_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s*$")
CONF_ONLY_RE = re.compile(r"^\s*\(\s*(\d{1,2})\s*\)\s*$")

IS_FINAL = re.compile(r"\bfinal\b", re.I)
IS_LIVE  = re.compile(r"\b(q[1-4]|1st|2nd|3rd|4th|ot)\b|\b\d{1,2}:\d{2}\b", re.I)
IS_TIME  = re.compile(r"(?:(Mon|Tue|Tues|Wed|Thu|Thur|Fri|Sat|Sun)|Today|Tonight)\s+\d{1,2}:\d{2}\s*[AaPp]\.?\s*[Mm]\.?(?:\s*(ET|CT|MT|PT))?\b", re.I)
IS_CODE  = re.compile(r"^[A-Za-z]{2,4}\s*-\s*[A-Za-z]{2,4}$")
NOISE_RE = re.compile(r"^(TIE|[–—-])$", re.I)

def _clean_lines(raw: str) -> List[str]:
    raw = raw.replace("\xa0", " ")
    lines = [ln.strip() for ln in raw.replace("\r", "").split("\n")]
    return [ln for ln in lines if ln]

def _looks_like_participant_block(lines: List[str], i: int) -> bool:
    n = len(lines)
    if i >= n or not RANK_RE.match(lines[i]):
        return False
    if i + 2 >= n:
        return False
    name_line = lines[i+1]
    points_line = lines[i+2]
    if TEAM_RE.match(name_line) or IS_TIME.search(name_line) or IS_CODE.match(name_line):
        return False
    if not (NUMS_LINE_2INTS_RE.match(points_line) or re.search(r"\d", points_line)):
        return False
    return True

def parse_games_block(lines: List[str]) -> Tuple[int, Set[str], List[Tuple[str,str]], List[str]]:
    pregame_teams: Set[str] = set()
    pregame_pairs: List[Tuple[str,str]] = []
    pregame_headers: List[str] = []
    i, n = 0, len(lines)

    # Primary scan
    while i < n:
        if _looks_like_participant_block(lines, i):
            break

        line = lines[i]

        if IS_FINAL.search(line) or IS_LIVE.search(line):
            if i + 2 < n and TEAM_RE.match(lines[i+1]) and TEAM_RE.match(lines[i+2]):
                i += 5 if i + 4 < n else 3
            else:
                i += 1
            continue

        if IS_TIME.search(line):
            # Look ahead up to 5 lines for TEAM/TEAM
            found = []
            for j in range(i+1, min(i+6, n)):
                tok = lines[j]
                if TEAM_RE.match(tok) and tok != "-":
                    found.append(norm_team(tok))
                    if len(found) == 2:
                        a,b = found[0], found[1]
                        pregame_pairs.append((a,b))
                        pregame_teams.update([a,b])
                        pregame_headers.append(line)
                        break
            i += 1
            continue

        if IS_CODE.match(line):
            a, b = [norm_team(t) for t in re.split(r"-", line)]
            pregame_pairs.append((a,b))
            pregame_teams.update([a, b])
            pregame_headers.append(line)
            i += 1
            continue

        if line.upper() == "TIE" and i >= 2 and TEAM_RE.match(lines[i-2]) and TEAM_RE.match(lines[i-1]):
            a = norm_team(lines[i-2]); b = norm_team(lines[i-1])
            pregame_pairs.append((a,b))
            pregame_teams.update([a, b])
            pregame_headers.append("TIE")
            i += 1
            continue

        i += 1

    start_idx = i

    # Redundant mini-scan in the header region (0..start_idx) for any missed "time + TEAM/TEAM"
    if start_idx > 0 and not pregame_pairs:
        for k in range(0, start_idx):
            if IS_TIME.search(lines[k]) and k + 2 < start_idx:
                if TEAM_RE.match(lines[k+1]) and TEAM_RE.match(lines[k+2]):
                    a = norm_team(lines[k+1]); b = norm_team(lines[k+2])
                    pregame_pairs.append((a,b))
                    pregame_teams.update([a,b])
                    pregame_headers.append(lines[k])

    # Deduplicate pairs
    if pregame_pairs:
        uniq = set()
        pairs_dedup = []
        for a,b in pregame_pairs:
            key = tuple(sorted((a,b)))
            if key not in uniq:
                uniq.add(key)
                pairs_dedup.append((a,b))
        pregame_pairs = pairs_dedup

    return start_idx, pregame_teams, pregame_pairs, pregame_headers

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
    used = {c for _, c in p.picks}
    return sum(c for c in range(1, max_conf + 1) if c not in used)

def pts_remaining_for_entry(p: Participant, remaining_teams: Set[str]) -> int:
    return sum(conf for (team, conf) in p.picks if team != "-" and norm_team(team) in remaining_teams)

def pts_remaining_by_count_diff(your: Participant, others: List[Participant]) -> int:
    other_counts = [len(p.picks) for p in others if p.picks]
    if not other_counts:
        return 0
    try:
        base = mode(other_counts)
    except StatisticsError:
        other_counts.sort()
        base = other_counts[len(other_counts)//2]
    diff = max(0, len(your.picks) - base)
    if diff == 0:
        return 0
    tail = your.picks[-diff:]
    return sum(conf for (team, conf) in tail if team != "-")

# ---------------- UI ----------------
st.set_page_config(page_title="CBS Pick 'Em — Analyzer", layout="wide")
st.title("🏈 CBS Pick 'Em — Analyzer")
st.caption("Header detection + manual override + fallback. Now with check-figures and redundant time scanner.")

raw = st.text_area("Paste the visible text from your Weekly Standings page (include the scoreboard at the top):", height=420)
override_max = st.number_input("Optional: Override Max Confidence (leave 0 to auto)", 0, 30, 0, 1)

if st.button("Analyze", type="primary"):
    if not raw.strip():
        st.error("Please paste the standings text first.")
    else:
        try:
            lines = _clean_lines(raw)
            start_idx, pregame_teams, pregame_pairs, pregame_headers = parse_games_block(lines)
            parts = parse_participants(lines, start_idx)
            if not parts:
                st.warning("No participants parsed. Double-check your paste.")
            else:
                names = [p.name for p in parts]
                your_name = st.selectbox("Your entry (optional):", ["(none)"] + names, index=0)

                all_confs = [conf for p in parts for (_, conf) in p.picks]
                auto_max = max(all_confs) if all_confs else 0
                max_conf = override_max if override_max > 0 else auto_max

                # Manual override for remaining teams
                all_team_tokens = sorted({norm_team(t) for p in parts for (t, _) in p.picks if t != "-"})
                manual_teams = st.multiselect(
                    "Manual override — Remaining matchup teams (optional)",
                    options=all_team_tokens,
                    default=sorted(pregame_teams),
                    help="If header detection missed your last game, pick the two teams here. Used only for YOUR entry."
                )
                manual_set = set(manual_teams)

                # ---- Check-figures ----
                games_left = max(0, len(pregame_pairs))
                completed_games = max(0, (max_conf if max_conf else 0) - games_left)
                c1, c2, c3 = st.columns(3)
                with c1: st.metric("Week Size (Max Confidence)", max_conf)
                with c2: st.metric("Completed Games", completed_games)
                with c3: st.metric("Games Left", games_left)

                # --- Build table ---
                you_obj = next((p for p in parts if p.name == your_name), None) if your_name != "(none)" else None
                others = [p for p in parts if you_obj and p is not you_obj]

                rows = []
                for p in parts:
                    pts_rem = pts_remaining_missing_numbers(p, max_conf)

                    if you_obj and p is you_obj:
                        remaining_set = manual_set if manual_set else pregame_teams
                        pts_try = pts_remaining_for_entry(p, remaining_set)
                        if pts_try == 0:
                            pts_try = pts_remaining_by_count_diff(p, others)
                        pts_rem = pts_try

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

                st.divider()
                st.subheader("Standings with Remaining Ceiling")
                st.dataframe(df, use_container_width=True, hide_index=True)

                with st.expander("Debug — headers/codes & your picks"):
                    st.write("**PRE-GAME header/code lines detected:**")
                    if pregame_headers:
                        for h in pregame_headers:
                            st.write(f"• {h}")
                    else:
                        st.write("_none (did the paste include the scoreboard header?)_")
                    st.write(f"**Detected PRE-GAME pairs:** {pregame_pairs}")
                    if your_name != "(none)" and you_obj:
                        st.write(f"**Your picks (normalized):** {[(t, c) for (t, c) in you_obj.picks]}")

        except Exception as e:
            st.error(f"Parsing failed: {e}")

st.divider()
st.caption("Version: v1.4.2")
