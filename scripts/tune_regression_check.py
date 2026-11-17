"""Tune-mode regression check: does tune still rank candidates exactly as before?

For a few programs, rebuilds tune's candidate pool (RL proposals + library) from the MANIFEST-verified files
and ranks it with the frozen surrogate, using the STORED program features (deterministic: the live command
measures scan features by running the program, which varies slightly). The first run saves the top-8 ranking;
later runs compare against it and print IDENTICAL or DIFFERENT. No timing; nothing is written to the main DB.
Run: .venv/bin/python scripts/tune_regression_check.py [--save]
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nc import rl, tunelock                                    # noqa: E402
from nc.config import load_config                              # noqa: E402
from nc.corpus import load_manifest                            # noqa: E402
from nc.db import Store                                        # noqa: E402
from nc.deploy import library                                  # noqa: E402
from nc.features import leaf_names, program_features           # noqa: E402
from nc.model import Surrogate                                 # noqa: E402
from nc.search import ProgramSearch                            # noqa: E402
from nc.toolchain import Toolchain                             # noqa: E402

PROGRAMS = ["polybench/3mm", "ss/Shootout-C++/fibo", "ms/Benchmarks/Ptrdist/ft"]
REF = Path("results/models/tune/regression_reference.json")

cfg = load_config("config.toml")
tc = Toolchain(cfg)
files = tunelock.load_verified(cfg.db_path)                    # refuses on any hash mismatch
man = load_manifest(Path(cfg.corpus_dir) / "manifest.jsonl")
main = Store(cfg.db_path)
pf = program_features(main)
sur = Surrogate(files["surrogate"])
meta = json.loads(files["rl_policy_meta"].read_text())
out = {}
with tempfile.TemporaryDirectory() as d:
    scratch = Store(Path(d) / "scratch.sqlite")
    for pid in PROGRAMS:
        ps = ProgramSearch(tc, cfg, scratch, man[pid], log=lambda *a: None)
        names = leaf_names(ps.tree)
        lib = library(main, ps, set(sur.meta["train_programs"]), 300, Path(cfg.results_dir))
        env = rl.PassEnv(sur, names, meta["actions"], {p: pf[p] for p in sur.meta["train_programs"] if p in pf},
                         meta.get("horizon", 4))
        env.pf[pid] = pf[pid]
        props = rl.propose(env, rl.load_policy(files["rl_policy"], env), pid, 24, 0)
        pool = props + lib
        sc = sur.predict(pf[pid], pool, names)
        order = sorted(range(len(pool)), key=lambda i: -sc[i])[:8]
        out[pid] = [{"genome": pool[i].to_json(), "score": round(float(sc[i]), 6),
                     "source": "RL" if i < len(props) else "library"} for i in order]
if "--save" in sys.argv or not REF.exists():
    REF.write_text(json.dumps(out, indent=1))
    print(f"reference saved: {REF}")
ref = json.loads(REF.read_text())
same = all([x["genome"] for x in ref[p]] == [x["genome"] for x in out[p]] for p in PROGRAMS)
for p in PROGRAMS:
    print(f"{p:32s} top-8 sources {[x['source'] for x in out[p]]}  "
          f"{'IDENTICAL' if [x['genome'] for x in ref[p]] == [x['genome'] for x in out[p]] else 'DIFFERENT'}")
print("TUNE REGRESSION CHECK:", "IDENTICAL top-8 order on all programs" if same else "DIFFERENT -> investigate")
sys.exit(0 if same else 1)
