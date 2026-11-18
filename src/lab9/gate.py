"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    rows, base_rows = pr.get("rows") or [], base.get("rows") or []
    # 1. a metric that is NaN or infinite cannot be compared with a threshold (nan < min is False)
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v}")
    # 2. row accounting: items x seeds, no duplicates, same (item, seed) set as the baseline
    man = pr.get("manifest") or {}
    want = int(man.get("items", 0)) * len(man.get("seeds") or [])
    if len(rows) != want:
        problems.append(f"{len(rows)} rows, manifest says {man.get('items')} items x {len(man.get('seeds') or [])} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(set(keys)) != len(keys):
        problems.append(f"{len(keys) - len(set(keys))} duplicated (item, seed) row(s)")
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(keys) != base_keys:
        problems.append(f"(item, seed) set differs from the baseline's: {len(set(keys) - base_keys)} extra, "
                        f"{len(base_keys - set(keys))} missing")
    # 3. a crashed grader: reported failures, or a graded metric that is None in a row
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), first: {pr['evaluator_failures'][0]}")
    graded = [m["id"] for m in spec["metrics"] if base_rows and all(m["id"] in r for r in base_rows)]
    for m in graded:
        none_rows = sum(1 for r in rows if r.get(m) is None)
        if none_rows:
            problems.append(f"{none_rows} row(s) with no value for graded metric {m}")
    # 4. reported metrics must be what the rows say (a hand-edited metric block)
    try:
        ids = [m for m in graded if all(m in r for r in rows)]
        again = aggregate([{**r, "cost": r.get("cost", 0.0)} for r in rows], ids, k_values=spec.get("pass_k", []))
        for k, v in (pr.get("metrics") or {}).items():
            w = again.get(k)
            if k != "cost_per_success" and isinstance(v, (int, float)) and isinstance(w, (int, float))                     and math.isfinite(v) and abs(v - w) > 1e-3:
                problems.append(f"metric {k} reported {v} but its rows give {w}")
    except (KeyError, TypeError, ZeroDivisionError):
        pass                                                   # malformed rows are reported by the checks above
    # 5. relabelling an item out of a slice hides its regression from the slice gate
    tags = lambda rs: {r.get("item_id"): sorted(r.get("slices") or []) for r in rs}
    pt, bt = tags(rows), tags(base_rows)
    moved = sorted(i for i in pt.keys() & bt.keys() if pt[i] != bt[i])
    if moved:
        problems.append(f"slice tags changed for {', '.join(map(str, moved[:5]))}")
    # 6. ratchet: on the same eval-set version a threshold may only get stricter
    if base_spec is not None and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        problems += _ratchet(spec, base_spec)
    return problems


def _loosened(new: dict, old: dict, what: str) -> list[str]:
    out = []
    th_new, th_old = new.get("threshold", new), old.get("threshold", old)
    if "min" in th_old and ("min" not in th_new or th_new["min"] < th_old["min"]):
        out.append(f"{what}: min {th_old['min']} -> {th_new.get('min')}")
    if "max" in th_old and ("max" not in th_new or th_new["max"] > th_old["max"]):
        out.append(f"{what}: max {th_old['max']} -> {th_new.get('max')}")
    if "max_increase" in th_old and ("max_increase" not in th_new or th_new["max_increase"] > th_old["max_increase"]):
        out.append(f"{what}: max_increase {th_old['max_increase']} -> {th_new.get('max_increase')}")
    if th_old.get("no_significant_drop") and not th_new.get("no_significant_drop"):
        out.append(f"{what}: no_significant_drop removed")
    if old.get("blocking") and not new.get("blocking"):
        out.append(f"{what}: blocking -> non-blocking")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    out = []
    now = {m["id"]: m for m in spec["metrics"]}
    for m in base_spec["metrics"]:
        if m["id"] not in now:
            out.append(f"ratchet: metric {m['id']} removed")
        else:
            out += [f"ratchet: {x}" for x in _loosened(now[m["id"]], m, f"metric {m['id']}")]
    now_s = {(x["name"], x.get("metric")): x for x in spec.get("slices") or []}
    for x in base_spec.get("slices") or []:
        key = (x["name"], x.get("metric"))
        if key not in now_s:
            out.append(f"ratchet: slice {x['name']}/{x.get('metric')} removed")
        else:
            out += [f"ratchet: {y}" for y in _loosened(now_s[key], x, f"slice {x['name']}/{x.get('metric')}")]
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    bs = spec.get("bootstrap", {})
    blocked, lines = [], []
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, name), per_item(base, metric, name)
        verdict, note = "ok", ""
        val = sum(a.values()) / len(a) if a else None
        if val is None:
            verdict = "missing"                                   # no rows left in the slice: nothing is proven
        else:
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if sl.get("no_significant_drop") and len(keys) >= 2:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        blocking = sl.get("blocking", True)
        if verdict != "ok" and blocking:
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if blocking else "warn")
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<34} {val if val is None else round(val, 4)!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
