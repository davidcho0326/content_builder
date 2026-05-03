"""Diversity-aware selector helpers for v2 reference query.

Three stages:
  A. handle_dedup        — same account.handle keeps highest-scored row only
  B. stratified_pick     — slot allocation by target mood × location distribution
  C. axis_clash_filter   — drop near-duplicates that share ≥4/5 axis values
                            and refill from next-best candidate

Pure helpers, no I/O. mood_query / mood_query_product wrap these for v1↔v2.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Callable, Iterable, Optional

# Axis keys used for clash detection (5 marketing axes).
CLASH_AXES = ("pose", "expression", "gaze", "mood", "location")


def _axis_value(rec: dict, axis: str) -> Optional[str]:
    """Pull one canonical value per axis, lowercased; None if absent."""
    if axis == "pose":
        v = (rec.get("model") or {}).get("pose")
    elif axis == "expression":
        v = (rec.get("model") or {}).get("expression")
    elif axis == "gaze":
        v = (rec.get("model") or {}).get("gaze direction")
    elif axis == "mood":
        v = (rec.get("background") or {}).get("mood")
    elif axis == "location":
        v = (rec.get("background") or {}).get("location")
    else:
        return None
    if isinstance(v, list):
        v = v[0] if v else None
    return str(v).strip().lower() if v else None


def handle_dedup(scored: list[tuple[float, list[str], dict]]
                 ) -> list[tuple[float, list[str], dict]]:
    """Keep the highest-scored row per account.handle. Preserves original order."""
    best: dict[str, tuple[float, list[str], dict]] = {}
    order: list[str] = []
    for s, reasons, rec in scored:
        h = (rec.get("account") or {}).get("handle") or f"_no_handle_{id(rec)}"
        if h not in best or s > best[h][0]:
            if h not in best:
                order.append(h)
            best[h] = (s, reasons, rec)
    return [best[h] for h in order]


def _allocate_slots(target: dict[str, float], k: int) -> dict[str, int]:
    """Largest-remainder rounding: distribute k slots over a probability dict.

    Empty/degenerate target → all slots in a special key '*' (no constraint).
    """
    if not target:
        return {"*": k}
    total = sum(target.values()) or 1.0
    probs = {kk: vv / total for kk, vv in target.items() if vv > 0}
    if not probs:
        return {"*": k}
    raw = {kk: vv * k for kk, vv in probs.items()}
    floors = {kk: int(math.floor(vv)) for kk, vv in raw.items()}
    used = sum(floors.values())
    remainder = sorted(probs.keys(),
                        key=lambda kk: (raw[kk] - floors[kk], probs[kk]),
                        reverse=True)
    i = 0
    while used < k and remainder:
        kk = remainder[i % len(remainder)]
        floors[kk] += 1
        used += 1
        i += 1
    return floors


def stratified_pick(scored: list[tuple[float, list[str], dict]],
                    target_mood: dict[str, float],
                    target_loc: dict[str, float],
                    k: int) -> list[tuple[float, list[str], dict]]:
    """Allocate k slots primarily by mood, secondarily fill location coverage.

    Strategy: mood slots first (largest-remainder rounding). Within each mood
    bucket, sort by score and walk top-down preferring still-uncovered locations
    according to target_loc. Falls back to score-only when buckets are exhausted.
    """
    if not scored:
        return []

    # Sort scored by score desc once.
    scored = sorted(scored, key=lambda t: -t[0])

    # Bucket by mood value.
    by_mood: dict[str, list[tuple[float, list[str], dict]]] = defaultdict(list)
    for tup in scored:
        mv = _axis_value(tup[2], "mood") or "_unknown_"
        by_mood[mv].append(tup)

    mood_quota = _allocate_slots(target_mood, k)

    chosen: list[tuple[float, list[str], dict]] = []
    seen_ids: set[int] = set()
    loc_target_keys = list(target_loc.keys())
    loc_covered: Counter[str] = Counter()

    def _take_from(pool: list[tuple[float, list[str], dict]], n: int):
        nonlocal loc_covered
        picked = 0
        # Pass 1: prefer rows whose location is still under-covered relative to target.
        for tup in pool:
            if picked >= n:
                break
            if id(tup[2]) in seen_ids:
                continue
            loc_v = _axis_value(tup[2], "location")
            if loc_v and loc_v in target_loc:
                target_quota = max(1, int(round(target_loc[loc_v] * k)))
                if loc_covered[loc_v] >= target_quota:
                    continue
            chosen.append(tup)
            seen_ids.add(id(tup[2]))
            if loc_v:
                loc_covered[loc_v] += 1
            picked += 1
        # Pass 2: fill remaining slots ignoring location constraint.
        for tup in pool:
            if picked >= n:
                break
            if id(tup[2]) in seen_ids:
                continue
            chosen.append(tup)
            seen_ids.add(id(tup[2]))
            loc_v = _axis_value(tup[2], "location")
            if loc_v:
                loc_covered[loc_v] += 1
            picked += 1
        return picked

    # Walk mood buckets in target-priority order, then everything else.
    mood_order = sorted(mood_quota.keys(),
                         key=lambda m: -target_mood.get(m, 0))
    deficit = 0
    for mv in mood_order:
        if mv == "*":
            continue
        want = mood_quota[mv]
        pool = by_mood.get(mv, [])
        got = _take_from(pool, want)
        deficit += (want - got)

    # If unconstrained ('*' target) or buckets short, fill by global score.
    remaining = k - len(chosen) + 0  # ensure positive
    if remaining > 0 or mood_quota.get("*"):
        _take_from(scored, max(remaining, mood_quota.get("*", 0)))

    return chosen[:k]


def _clash_count(a: dict, b: dict) -> int:
    """How many of CLASH_AXES match between two records."""
    n = 0
    for axis in CLASH_AXES:
        va = _axis_value(a, axis)
        vb = _axis_value(b, axis)
        if va and vb and va == vb:
            n += 1
    return n


def axis_clash_filter(picked: list[tuple[float, list[str], dict]],
                      candidates: list[tuple[float, list[str], dict]],
                      *, threshold: int = 4,
                      max_iter: int = 6) -> list[tuple[float, list[str], dict]]:
    """Drop near-duplicates (≥threshold axes match) keeping higher-score row.

    Refill from `candidates` (already sorted desc) skipping any whose record
    objects are already present.
    """
    if not picked:
        return picked
    out = list(picked)
    seen = {id(t[2]) for t in out}
    iteration = 0
    while iteration < max_iter:
        iteration += 1
        clash_pair = None
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                if _clash_count(out[i][2], out[j][2]) >= threshold:
                    clash_pair = (i, j)
                    break
            if clash_pair:
                break
        if not clash_pair:
            break
        i, j = clash_pair
        # Drop the lower-scored member.
        drop_idx = j if out[i][0] >= out[j][0] else i
        seen.discard(id(out[drop_idx][2]))
        out.pop(drop_idx)
        # Refill: walk candidates in score order, take first one that doesn't
        # itself trigger a clash with current `out`.
        for cand in candidates:
            if id(cand[2]) in seen:
                continue
            if any(_clash_count(cand[2], t[2]) >= threshold for t in out):
                continue
            out.append(cand)
            seen.add(id(cand[2]))
            break
        else:
            # No usable refill; stop.
            break
    return out


def select_v2(scored_all: list[tuple[float, list[str], dict]],
              target_mood: dict[str, float],
              target_loc: dict[str, float],
              k: int,
              *, clash_threshold: int = 4) -> list[tuple[float, list[str], dict]]:
    """Compose 3-stage filter end to end and return final K rows."""
    if not scored_all:
        return []
    # Stage A — handle dedup
    deduped = handle_dedup(scored_all)
    deduped.sort(key=lambda t: -t[0])
    # Stage B — stratified pick
    picked = stratified_pick(deduped, target_mood, target_loc, k)
    # Stage C — axis-clash filter (refill pool = deduped, score-sorted)
    final = axis_clash_filter(picked, deduped,
                               threshold=clash_threshold)
    # Re-sort final by score desc for stable presentation.
    final.sort(key=lambda t: -t[0])
    return final[:k]


__all__ = [
    "handle_dedup",
    "stratified_pick",
    "axis_clash_filter",
    "select_v2",
    "CLASH_AXES",
]
