"""Leave-one-out backtest of the entry's model over a case file's comparables.

Each comparable launch with a usable release-day curve takes a turn as the pseudo-target:
the model sees its hour-1 viewers as the case's `known` print and every other comparable as
its library, forecasts hours 2..24, and is scored with the contest's pinball loss on the log
scale against the launch's actual hours. The house persistence baseline is scored on the
same folds. This is a proxy for the practice/final grades (whose answers only the server
holds), not the grade itself.

    python3 tools/backtest.py <case.in> [--json]
"""

import importlib.util
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("entry_main", ROOT / "main.py")
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)

Z = entry.Z
LEVELS = entry.LEVELS


def pinball(rows, actual):
    """Mean pinball loss on the log scale; rows: {hour: [q x5]}, actual: {hour: viewers}."""
    total, n = 0.0, 0
    for h, y in actual.items():
        if h == 1 or h not in rows:
            continue
        ly = math.log(max(1.0, y))
        for tau, q in zip(LEVELS, rows[h]):
            d = ly - math.log(q)
            total += 2 * max(tau * d, (tau - 1) * d)
            n += 1
    return total / n if n else float("nan")


def baseline_rows(p1, hours):
    return {
        h: [entry.round2(p1 * math.exp(z * 0.15 * math.sqrt(h - 1))) for z in Z]
        for h in hours
    }


def fold_losses(case):
    """[(name, is_rolling, model_loss, baseline_loss)] for every usable comparable."""
    comps = case["comparables"]
    out = []
    for i, target in enumerate(comps):
        actual = entry.day_hours(target)
        if actual is None:
            continue
        pseudo = {
            "levels": LEVELS,
            "day_start": target["day_start"],
            "known": [{"hour": 1, "viewers": actual[1]}],
            "forecast": [{"hour": h} for h in range(2, 25)],
            "history_hourly": [
                {"from": r["from"], "viewers": r["viewers"]} for r in target["hourly"]
            ],
            "comparables": [c for j, c in enumerate(comps) if j != i],
        }
        mine = entry.forecast_case(pseudo, target["name"])
        my_rows = {row["hour"]: row["q"] for row in mine["hours"]}
        base_rows = baseline_rows(max(1.0, actual[1]), range(2, 25))
        unlock = (target.get("unlock") or "").lower()
        rolling = "midnight local" in unlock or "rolling" in unlock
        out.append((target["name"], rolling, pinball(my_rows, actual), pinball(base_rows, actual)))
    return out


def grid(case):
    """Coarse calibration grid over the model's constants, on rolling folds and all folds."""
    import itertools
    folds_cache = {}
    best = []
    for shrink, k, s, tau in itertools.product(
            (0.6, 0.75, 0.9, 1.0), (0.85, 1.0, 1.15), (1.2, 1.8, 3.0), (0.9,)):
        entry.CENTRE_SHRINK, entry.SPREAD_K, entry.SCALE_S, entry.RAMP_TAU = shrink, k, s, tau
        folds = fold_losses(case)
        roll = [f for f in folds if f[1]]
        rm = sum(f[2] for f in roll) / len(roll)
        am = sum(f[2] for f in folds) / len(folds)
        rb = sum(f[3] for f in roll) / len(roll)
        best.append((rm, am, shrink, k, s, tau))
        print(f"shrink={shrink:<5} K={k:<5} S={s:<4} rolling model={rm:.4f} (baseline {rb:.4f})  all={am:.4f}")
    best.sort()
    print("\nbest by rolling folds:", best[0])


def main():
    case_path = Path(sys.argv[1])
    if "--grid" in sys.argv:
        grid(json.loads(case_path.read_text(encoding="utf-8")))
        return
    case = json.loads(case_path.read_text(encoding="utf-8"))
    comps = case["comparables"]
    results = []
    for i, target in enumerate(comps):
        actual = entry.day_hours(target)
        if actual is None:
            continue
        pseudo = {
            "levels": LEVELS,
            "day_start": target["day_start"],
            "known": [{"hour": 1, "viewers": actual[1]}],
            "forecast": [{"hour": h} for h in range(2, 25)],
            "history_hourly": [
                {"from": r["from"], "viewers": r["viewers"]}
                for r in target["hourly"]
                if r["from"] < target["day_start"][:11] + "01:00:00Z" or r["from"] < target["day_start"]
            ],
            "comparables": [c for j, c in enumerate(comps) if j != i],
        }
        mine = entry.forecast_case(pseudo, target["name"])
        my_rows = {row["hour"]: row["q"] for row in mine["hours"]}
        base_rows = baseline_rows(max(1.0, actual[1]), range(2, 25))
        results.append({
            "name": target["name"],
            "weight": entry.comparable_weight(target),
            "peak": max(actual.values()),
            "model": pinball(my_rows, actual),
            "baseline": pinball(base_rows, actual),
            "model_median": my_rows,
            "actual": actual,
        })
    results.sort(key=lambda r: r["model"])
    for r in results:
        print(f"{r['name'][:42]:44s} w={r['weight']:.2f} peak={r['peak']:>9,.0f} "
              f"model={r['model']:.4f} baseline={r['baseline']:.4f}")
    mm = sum(r["model"] for r in results) / len(results)
    mb = sum(r["baseline"] for r in results) / len(results)
    print(f"\n{len(results)} folds  model mean loss = {mm:.4f}   baseline mean loss = {mb:.4f}")
    if "--json" in sys.argv:
        slim = [{k: r[k] for k in ("name", "weight", "peak", "model", "baseline")} for r in results]
        print(json.dumps({"folds": slim, "model_mean": mm, "baseline_mean": mb}, indent=1))


if __name__ == "__main__":
    main()
