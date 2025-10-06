# app.py — CBS Pick 'Em Paste Analyzer (no HTML, no login, works on Streamlit Cloud & streamliter)
# Computes Points Remaining as the sum of MISSING confidence numbers 1..max_conf
# Treats "- (N)" as a used confidence point (no points available there).

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple, Set

import streamlit as st
import pandas as pd

# -----------------------------
# Data structures
# -----------------------------
@dataclass
class Participant:
    rank: Optional[int]
    name: str
    current_points: float
    picks: List[Tuple[str, int]]  # (TEAM_ABBR_OR_DASH, CONF)

# -----------------------------
# Parsing helpers
# -----------------------------
RANK_RE = re.compile(r"^(\d{1,2})(st|nd|rd|th)$", re.I)

# Allow inline picks like "LAR (14)" OR "- (10)"
PICK_INLINE_RE = re.compile(r"^\s*([A-Z]{2,4}|-)\s*\(\s*(\d{1,2})\s*\)\s*$")

NUMS_LINE_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s*$")  # e.g., "72    441"
TEAM_RE = re.compile(r"^[A-Z]{2,4}$")  # used for optional scoreboard parsing

def _clean_lines(raw: str) -> List[str]:
    lines = [ln.strip() for ln in raw.replace("\r", "").split("\n")]
    return [ln for ln in lines if ln is not None and ln.strip() != ""]

def parse_participants(lines: List[str], start_idx: int) -> List[Participant]:
    """
    Parse participants:
      Rank -> Name -> Points line (use FIRST integer as current week points) -> Picks
      Picks are:
        • Inline: "TEAM (N)" OR "- (N)"
        • Two-line: TEAM or "-" on one line, then "(N)" on the next line
      Stops at the next rank or EOF.
    """
    participants: List[Participant] = []
    i = start_idx
    n = len(lines)

    while i < n:
        m_rank = RANK_RE.match(lines[i])
        if not m_rank:
            i += 1
            continue

        rank = int(m_rank.group(1))
        i += 1
        if i >= n:
            break

        name = lines[i]
        i += 1
        if i >= n:
            break

        current_points = 0.0
        if i < n:
            m_nums = NUMS_LINE_RE.match(lines[i])
            if m_nums:
                current_points = float(m_nums.group(1))
                i += 1
            else:
                # try single numeric on that line
                maybe_num = re.sub(r"[^\d\.]", "", lines[i])
                if maybe_num:
                    try:
                        current_points = float(maybe_num)
                    except Exception:
                        current_points = 0.0
                i += 1

        picks: List[Tuple[str, int]] = []
        while i < n and not RANK_RE.match(lines[i]):
            line = lines[i]

            # Inline form: "LAR (14)" OR "- (10)"
            m_pick = PICK_INLINE_RE.match(line)
            if m_pick:
                team = m_pick.group(1)
                conf = int(m_pick.group(2))
                picks.append((team, conf))
                i += 1
                continue

            # Two-line form: TEAM or "-" on one line, "(N)" on the next line
            if (TEAM_RE.match(line) or line == "-") and (i + 1) < n:
                m_conf = re.match(r"^\s*\(\s*(\d{1,2})\s*\)\s*$", lines[i+1])
                if m_conf:
                    team = line
                    conf = int(m_conf.group(1))
                    picks.append((team, conf))
                    i += 2
                    continue

            # Skip junk like "TIE", "KC-JAC", lone hyphens without a following "(N)", etc.
            i += 1

        participants.append(Participant(rank=rank, name=name, current_points=current_points, picks=picks))

    return participants

# Points Remaining = sum of MISSING 1..max_conf (treat "-" picks as used)
def compute_points_remaining_from_missing(participant: Participant, max_conf: int) -> int:
    used = {conf for _, conf in participant.picks}  # includes '-' picks
    missing = [c for c in range(1, max_conf + 1) if c not in used]
    return sum(missing)

def compute_table(participants: List[Participant], max_conf: int) -> pd.DataFrame:
    rows = []
    for p in participants:
        pts_remaining = compute_points_remaining_from_missing(p, max_conf)
        total_possible = p.current_points + pts_remaining
        rows.append({
            "Name": p.name,
            "Current Standing": p.rank,
            "Current Points": p.current_points,
            "Points Remaining": pts_remaining,
            "Total Points Possible": total_possible
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(
            by=["Total Points Possible", "Current Points"],
            ascending=[False, False],
            kind="mergesort"
        ).reset_index(drop=True)
    return df

# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="CBS Pick 'Em – Paste Analyzer", layout="wide")
st.title("🏈 CBS Pick 'Em – Paste Analyzer (Missing-Points Method, handles '- (N)')")

st.write(
    "Paste the **raw text** copied from the CBS **Weekly Standings** page. "
    "This computes **Points Remaining** as the sum of **unused** confidence numbers 1..MaxConf, "
    "and treats **`- (N)`** as a used pick (no points available there)."
)

raw_text = st.text_area(
    "Paste the standings text here",
    height=380,
    placeholder="Copy the visible text from the Weekly Standings page and paste it here..."
)

# Optional: allow manual override of max confidence if you want to force 16, etc.
override_max = st.number_input(
    "Optional: Override Max Confidence (leave 0 to auto-detect)",
    min_value=0, max_value=30, value=0, step=1,
    help="If set, replaces the auto-detected max."
)

if st.button("Analyze", type="primary"):
    if not raw_text.strip():
        st.error("Please paste the standings text first.")
    else:
        try:
            lines = _clean_lines(raw_text)

            # Find where participants start: first rank token
            i = 0
            while i < len(lines) and not RANK_RE.match(lines[i]):
                i += 1

            participants = parse_participants(lines, i)

            if not participants:
                st.info("No participants parsed. Double-check your paste.")
            else:
                all_confs = [conf for p in participants for (_, conf) in p.picks]
                auto_max = max(all_confs) if all_confs else 0
                max_conf = override_max if override_max > 0 else auto_max

                df = compute_table(participants, max_conf)

                left, right = st.columns([1, 2])
                with left:
                    st.metric("Week Size (Max Confidence)", max_conf)
                with right:
                    st.caption("Points Remaining = sum of unused confidence numbers 1..MaxConf "
                               "(including '-' picks as used).")

                st.divider()
                st.subheader("Standings with Remaining Ceiling")
                st.dataframe(df, use_container_width=True, hide_index=True)

                # Optional per-player breakdown for debugging
                with st.expander("Per-player used/missing breakdown (debug)"):
                    for p in participants:
                        used = sorted({c for _, c in p.picks})
                        missing = [c for c in range(1, max_conf + 1) if c not in used]
                        st.write(f"**{p.name}** — used: {used} | missing: {missing} | "
                                 f"Pts Rem: {sum(missing)} | Total: {p.current_points + sum(missing)}")

        except Exception as e:
            st.error(f"Parsing failed: {e}")
            st.info("Make sure you pasted the visible text and that picks appear like TEAM (N) or - (N).")
