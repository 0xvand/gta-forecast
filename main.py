"""gta6-twitch-ccu-forecast-01 entry: an hour-by-hour quantile forecast of a launch day's
Twitch category viewers, built from the release-day curves of past comparable launches.

Model (see METHOD.md for the full write-up and the evidence behind it):

  The case gives one hard fact, hour 1's print p, plus a library of comparable launches,
  each with its whole release day as hourly category averages. A launch day's shape is far
  more alike across launches than its size, so the forecast is built in ratio space:

    1. Every usable comparable contributes its release-day curve as log ratios to its own
       hour 1, log(viewers_h / viewers_1), for h = 1..24.
    2. Each comparable is weighted twice over. By launch shape: this contest's target is a
       console-only, single-player game unlocking at midnight local time, rolling around
       the world, so rolling midnight-local unlocks and console-only launches weigh most,
       fixed-hour simultaneous global unlocks and early-access-contaminated launches
       least. And by regime: the comparable's viewer ramp over the twelve hours before
       its hour 1, in log space relative to its hour 1, is compared with the case's own
       ramp over the same window; the closer the two ramps, the more the comparable
       counts. This separates launches that were already hot at hour 1 (the game had
       unlocked region by region before the UTC day began) from launches that only
       unlocked hours into the UTC day and ramped from near zero, whose ratio curves
       would otherwise swamp the median.
    3. The median forecast for hour h is p * exp(weighted median of the log ratios at h).
    4. The spread at h is the weighted dispersion of the log ratios at h across
       comparables (floored, and scaled by a constant calibrated by leave-one-out
       backtest, in tools/backtest.py), turned into the five quantiles with the
       normal's z values.

  The program is a pure function of the case file: no randomness, no clock, no network,
  so two runs on the same case write the same bytes. Standard library only.

Run by the grader as `python3 -P -s /bot/main.py` with the case alone in /input; outside
the container, MAKEFUN_INPUT_DIR and MAKEFUN_OUTPUT_DIR stand in for /input and /output.
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, in case a sibling module ships.
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.644854, -0.674490, 0.0, 0.674490, 1.644854]

# Comparable weights, by launch shape (calibrated in tools/backtest.py; see METHOD.md).
W_ROLLING = 1.6        # unlock text says midnight local / rolling
W_SIMULTANEOUS = 0.45  # one fixed-hour global unlock for everyone
W_UNVERIFIED = 0.8     # unlock text does not say how it unlocked
W_EARLY_ACCESS = 0.55  # a paid early-access window preceded the "release" day
W_CONSOLE_ONLY = 1.3   # no PC in the platform list (the target is console-only)
W_MULTIPLAYER = 0.7    # multiplayer / live-service / free-to-play launches
MULTIPLAYER_HINTS = (
    "call of duty", "battlefield", "marvel rivals", "helldivers",
    "arc raiders", "marathon", "halo infinite",
)

RAMP_TAU = 1.4         # log units of ramp distance that cost a comparable a factor e
SCALE_S = 1.0          # log units of hour-1 size distance that cost a factor e
CENTRE_SHRINK = 1.0    # median log ratio used as-is (backtest: shrinkage did not help)
SPREAD_K = 0.8         # multiplier on the cross-comparable dispersion (backtest-calibrated)
SPREAD_FLOOR = 0.12    # log units; no hour is forecast more surely than this
MIN_DAY_HOURS = 20     # a comparable needs at least this many of its day's 24 hours
RAMP_HOURS = 12        # hours before hour 1 that make up the regime ramp


def parse_ts(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def round2(x):
    """Round half up to 2 decimals; whole numbers come back as ints, as the starter writes."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if float(value).is_integer() else value


def fill_hours(raw, lo, hi):
    """{hour: viewers} for lo..hi from the present subset raw, log-interpolated inside,
    nearest value at the edges; None when raw is empty."""
    if not raw:
        return None
    present = sorted(raw)
    out = {}
    for h in range(lo, hi + 1):
        if h in raw:
            out[h] = raw[h]
            continue
        before = max((k for k in present if k < h), default=None)
        after = min((k for k in present if k > h), default=None)
        if before is not None and after is not None:
            frac = (h - before) / (after - before)
            out[h] = math.exp(math.log(raw[before]) + frac * (math.log(raw[after]) - math.log(raw[before])))
        elif before is not None:
            out[h] = raw[before]
        else:
            out[h] = raw[after]
    return out


def day_hours(comp):
    """The comparable's release-day viewers by hour 1..24, or None when it cannot anchor.

    A comparable anchors only when its own hour 1 exists and is positive and at least
    MIN_DAY_HOURS of the day's hours are present; missing hours are filled as in fill_hours.
    """
    try:
        start = parse_ts(comp["day_start"])
    except (KeyError, ValueError):
        return None
    raw = {}
    for row in comp.get("hourly", []):
        try:
            at = parse_ts(row["from"])
        except (KeyError, ValueError):
            continue
        delta = (at - start).total_seconds()
        if 0 <= delta < 24 * 3600:
            viewers = row.get("viewers")
            if viewers is not None and viewers > 0:
                raw[int(delta // 3600) + 1] = float(viewers)
    if raw.get(1) is None or len(raw) < MIN_DAY_HOURS:
        return None
    return fill_hours(raw, 1, 24)


def ramp_of_points(points, start):
    """Log viewers relative to hour 1 at offsets -RAMP_HOURS..-1 before a day starting at
    `start`, from (timestamp, viewers) points; None when too few of the window is present."""
    raw = {}
    for at, viewers in points:
        if viewers is None or viewers <= 0:
            continue
        offset = int((at - start).total_seconds() // 3600)
        if -RAMP_HOURS <= offset <= -1:
            raw[offset] = float(viewers)
    if len(raw) < RAMP_HOURS // 2:
        return None
    filled = fill_hours(raw, -RAMP_HOURS, -1)
    return filled


def comparable_ramp(comp, day):
    """A comparable's pre-hour-1 ramp, in log space relative to its own hour 1."""
    try:
        start = parse_ts(comp["day_start"])
    except (KeyError, ValueError):
        return None
    points = []
    for row in comp.get("hourly", []):
        try:
            points.append((parse_ts(row["from"]), row.get("viewers")))
        except (KeyError, ValueError):
            continue
    filled = ramp_of_points(points, start)
    if filled is None:
        return None
    base = math.log(day[1])
    return {k: math.log(v) - base for k, v in filled.items()}


def case_ramp(case, p1):
    """The case's own pre-hour-1 ramp from its history_hourly, relative to hour 1's print."""
    try:
        start = parse_ts(case["day_start"])
    except (KeyError, ValueError):
        return None
    points = []
    for row in case.get("history_hourly", []):
        try:
            points.append((parse_ts(row["from"]), row.get("viewers")))
        except (KeyError, ValueError):
            continue
    filled = ramp_of_points(points, start)
    if filled is None:
        return None
    base = math.log(p1)
    return {k: math.log(v) - base for k, v in filled.items()}


def ramp_distance(a, b):
    """Mean absolute difference of two ramps over their shared offsets; None if <4 shared."""
    shared = [k for k in a if k in b]
    if len(shared) < 4:
        return None
    return sum(abs(a[k] - b[k]) for k in shared) / len(shared)


def comparable_weight(comp):
    """How much a comparable's launch shape matches this contest's target."""
    unlock = (comp.get("unlock") or "").lower()
    platforms = (comp.get("platforms") or "")
    name = (comp.get("name") or "").lower()
    weight = 1.0
    if "midnight local" in unlock or "rolling" in unlock:
        weight *= W_ROLLING
    elif "simultaneous" in unlock or "single global unlock" in unlock:
        weight *= W_SIMULTANEOUS
    else:
        weight *= W_UNVERIFIED
    if "early access" in unlock:
        weight *= W_EARLY_ACCESS
    if "pc" not in platforms.lower():
        weight *= W_CONSOLE_ONLY
    if any(hint in name for hint in MULTIPLAYER_HINTS):
        weight *= W_MULTIPLAYER
    return weight


def extract_curves(case, p1):
    """[(log-ratio curve {hour: log r_h}, weight)] for every usable comparable of a case,
    each weight carrying both the launch-shape match and the ramp-regime match."""
    target_ramp = case_ramp(case, p1)
    curves = []
    for comp in case.get("comparables", []):
        day = day_hours(comp)
        if day is None:
            continue
        base = math.log(day[1])
        curve = {h: math.log(day[h]) - base for h in range(1, 25)}
        weight = comparable_weight(comp)
        weight *= math.exp(-abs(base - math.log(p1)) / SCALE_S)
        if target_ramp is not None:
            comp_ramp = comparable_ramp(comp, day)
            if comp_ramp is not None:
                dist = ramp_distance(target_ramp, comp_ramp)
                if dist is not None:
                    weight *= math.exp(-dist / RAMP_TAU)
        curves.append((curve, weight))
    return curves


def weighted_median(pairs):
    ordered = sorted(pairs, key=lambda pair: pair[0])
    total = sum(w for _, w in ordered)
    acc = 0.0
    for value, w in ordered:
        acc += w
        if acc >= total / 2:
            return value
    return ordered[-1][0]


def weighted_std(pairs, centre):
    total = sum(w for _, w in pairs)
    var = sum(w * (value - centre) ** 2 for value, w in pairs) / total
    return math.sqrt(var)


def forecast_quantiles(p1, curves, hours_wanted):
    """The five quantiles of each wanted hour, given hour 1's print and the curve library."""
    rows = {}
    for h in hours_wanted:
        pairs = [(curve[h], w) for curve, w in curves if h in curve]
        if not pairs:
            centre, spread = 0.0, 0.15 * math.sqrt(h - 1)
        else:
            centre = weighted_median(pairs) * CENTRE_SHRINK
            spread = max(SPREAD_FLOOR, weighted_std(pairs, centre) * SPREAD_K)
        quantiles = []
        for z in Z:
            q = p1 * math.exp(centre + z * spread)
            q = min(max(q, 1e-6), 1e9)
            quantiles.append(q)
        for i in range(1, len(quantiles)):
            quantiles[i] = max(quantiles[i], quantiles[i - 1])
        rows[h] = [round2(q) for q in quantiles]
    return rows


def forecast_case(case, name):
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1.0, float(first["viewers"]))
    curves = extract_curves(case, p1)
    wanted = [row["hour"] for row in case["forecast"]]
    rows = forecast_quantiles(p1, curves, wanted)
    return {"hours": [{"hour": h, "q": rows[h]} for h in sorted(rows)]}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
