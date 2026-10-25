"""Full data collection (Phase 5) and the data-quality report.

`collect run` = for every usable program (or a subset): the search methods (+ merged confirmation
and validation) and the single-edit knowledge base, all resumable. Screening and confirmed
measurements both land in results/dataset.sqlite.

`collect quality` reports the three counts SEPARATELY (programs, valid program-input pairs,
usable records), failure rates, per-program noise, the share of candidates with a measurable
difference, and writes a dataset version tag (hash of corpus, config, LLVM, -O3 pipeline and
code) to results/dataset_version.json.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from .config import Config
from .db import Store
from .toolchain import Toolchain


def code_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted((root / "nc").glob("*.py")):
        h.update(p.name.encode() + p.read_bytes())
    return h.hexdigest()[:16]


def quality(store: Store, manifest: dict[str, dict], cfg: Config, tc: Toolchain, root: Path,
            write: bool = True) -> str:
    ok = {k: v for k, v in manifest.items() if v.get("status") == "ok"}
    with_data = {r["program_id"] for r in store.rows("SELECT DISTINCT program_id FROM runs")}
    st = Counter(r["status"] for r in store.rows(
        "SELECT status FROM candidates WHERE method NOT IN ('baseline')"))
    total = sum(st.values()) or 1
    timed = store.rows("SELECT COUNT(*) n FROM measurements WHERE stage='screen'")[0]["n"]
    conf = store.rows("SELECT COUNT(*) n, SUM(ci_lo > 1.0 OR ci_hi < 1.0) sig FROM measurements "
                      "WHERE stage IN ('confirm','confirm_min','validate','passkb_confirm')")[0]
    big = store.rows("SELECT COUNT(*) n FROM measurements WHERE stage='screen' AND (speedup >= 1.02 OR speedup <= 0.98)")[0]["n"]
    # A/A controls: every attempt (a noisy first attempt is repeated by design and discarded) vs. the
    # ACCEPTED attempt of each measurement (the last one), which is what the stored labels rely on.
    ctrl, accepted = {}, {}
    for r in store.rows("SELECT program_id, speedup, note FROM measurements WHERE stage IN ('control','control_validate') "
                        "AND speedup IS NOT NULL ORDER BY id"):
        dev = abs(r["speedup"] - 1) * 100
        ctrl.setdefault(r["program_id"], []).append(dev)
        try:
            ctx = json.loads(r["note"]).get("stage", "confirm") if r["note"] else "confirm"
        except ValueError:
            ctx = "confirm"
        accepted.setdefault(r["program_id"], {})[ctx] = dev        # later attempts overwrite earlier ones
    noisy_any = sorted(p for p, v in ctrl.items() if max(v) > cfg.control_max_dev_pct)
    noisy = sorted(p for p, v in accepted.items() if max(v.values()) > cfg.control_max_dev_pct)
    wrong_by_prog = Counter(r["program_id"] for r in store.rows("SELECT program_id FROM candidates WHERE status='wrong_output'"))
    fam = Counter(v["family"] for v in ok.values())
    lines = [
        "== Dataset quality ==",
        f"Programs usable in corpus: {len(ok)} in {len(fam)} families | with search data: {len(with_data & set(ok))}",
        f"Valid program-input pairs: {len(ok)} (one scaled input per program)",
        f"Usable records: {st.get('ok', 0)} built+verified candidates, {timed} screening measurements, "
        f"{conf['n'] or 0} confirmed/validated measurements",
        "",
        "Candidate status (failure rate):",
    ]
    for k, v in st.most_common():
        lines.append(f"  {k:<16s} {v:>7d}  {v / total * 100:5.1f}%")
    lines += [
        "",
        f"Measurable difference: {big / max(timed, 1) * 100:.0f}% of screened binaries differ from -O3 by >= 2% (screening); "
        f"{(conf['sig'] or 0) / max(conf['n'] or 1, 1) * 100:.0f}% of confirmed measurements have a CI excluding 1.0",
        f"Noise: A/A control worst deviation per program, median {sorted(max(v) for v in ctrl.values())[len(ctrl) // 2] if ctrl else float('nan'):.2f}%, "
        f"programs above {cfg.control_max_dev_pct}% in an ACCEPTED measurement: {len(noisy)} {noisy[:8]} "
        f"(in any attempt, incl. repeated/discarded ones: {len(noisy_any)})",
        f"Programs with wrong-output candidates (UB-sensitive or miscompile; never selected): {len(wrong_by_prog)} "
        f"{dict(wrong_by_prog.most_common(5))}",
    ]
    issues = []
    if st.get("wrong_output", 0) / total > 0.05:
        issues.append("wrong_output > 5% of candidates")
    if len(noisy) > 0.1 * max(len(ctrl), 1):
        issues.append(f"{len(noisy)} programs with a noisy accepted A/A control (>10% of programs)")
    if (st.get("timeout", 0) + st.get("crash", 0)) / total > 0.05:
        issues.append("crash+timeout > 5%")
    if len(fam) < 15:
        issues.append(f"only {len(fam)} families: held-out-family estimates will be very wide")
    lines.append("")
    lines.append("QUALITY: " + ("CLEAN" if not issues else "ISSUES -> " + "; ".join(issues)))
    if write:
        tag_src = json.dumps({"programs": sorted((k, v.get("ref_output_hash"), v.get("cflags"), v.get("time_spec"))
                                                 for k, v in ok.items()),
                              "cfg": {k: getattr(cfg, k) for k in ("reps", "warmup", "settle_s", "screen_reps",
                                                                    "screen_halving", "screen_keep", "screen_abort",
                                                                    "timing_cpu", "isolate_sibling", "march")},
                              "llvm": tc.version(), "o3": tc.pipeline_string("O3"), "code": code_hash(root)},
                             sort_keys=True, default=str)
        tag = hashlib.sha256(tag_src.encode()).hexdigest()[:12]
        out = {"version": tag, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "machine_id": cfg.machine_id,
               "llvm": tc.version(), "code_hash": code_hash(root), "programs": len(ok), "families": len(fam),
               "program_input_pairs": len(ok), "records_ok": st.get("ok", 0), "screen_measurements": timed,
               "confirmed_measurements": conf["n"] or 0, "issues": issues}
        p = root / cfg.results_dir / "dataset_version.json"
        p.write_text(json.dumps(out, indent=2))
        lines.append(f"Dataset version tag {tag} -> {p}")
    return "\n".join(lines)
