"""One-command pipeline: generate -> compute -> reconcile -> test.

Replaces the real-world month-end stitching of prime-broker statements, OMS
positions, and comp spreadsheets with a single reproducible command::

    python run.py

Exits non-zero if any reconciliation tie-out or unit test fails, so it is safe
to wire into CI. On success it prints the command to launch the dashboard.
"""
from __future__ import annotations

import subprocess
import sys

# Windows consoles default to GBK; force UTF-8 so Unicode in output doesn't crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import datetime
import time

from src.config import load_config
from src.data_gen.generate import generate_all
from src.db import write_manifest
from src.engine import recon
from src.loader import compute_all


def _section(title: str) -> None:
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def _git_ref() -> str | None:
    """Return current git commit short hash, or None if not in a git repo."""
    try:
        import subprocess as _sp
        r = _sp.run(["git", "rev-parse", "--short", "HEAD"],
                    capture_output=True, text=True, timeout=3)
        return r.stdout.strip() or None
    except Exception:
        return None


def main() -> int:
    t0 = time.time()
    cfg = load_config()

    _section("1/4  GENERATE synthetic data")
    tables = generate_all(cfg)
    for name, df in tables.items():
        print(f"  {name:12s}: {len(df):>8,d} rows")

    _section("2/4  COMPUTE engine outputs")
    results = compute_all()
    print(f"  AUM           : {results['aum']:>16,.0f}")
    print(f"  Fund Trading  : {results['fund_trading']:>16,.0f}")
    print(f"  Fund Non-trad : {results['fund_non_trading']:>16,.0f}")
    print(f"  Fund Gross    : {results['fund_gross']:>16,.0f}")
    print(f"  Fund Net      : {results['fund_net']:>16,.0f}")
    print(f"  Total Comp    : {results['total_comp']:>16,.0f}")
    print(f"  Center Cost   : {results['center_cost']:>16,.0f}")
    print(f"  Investor Net  : {results['investor_net']:>16,.0f}")
    print(f"  Netting Cost  : {results['netting_cost']:>16,.0f}")

    _section("3/4  RECONCILE control tie-outs")
    checks = recon.run_checks(results, cfg)
    print(recon.to_frame(checks).to_string(index=False))
    recon_ok = recon.all_passed(checks)
    write_manifest({
        "run_at":       datetime.datetime.utcnow().isoformat(),
        "git_ref":      _git_ref(),
        "n_prices":     len(tables["eod_prices"]),
        "n_positions":  len(tables["eod_positions"]),
        "n_income":     len(tables["eod_income"]),
        "recon_pass":   int(recon_ok),
        "n_checks":     len(checks),
        "pipeline_sec": round(time.time() - t0, 2),
    })
    if not recon_ok:
        print("\n  RECONCILIATION FAILED — numbers do not tie out.")
        return 1
    print("\n  All reconciliation tie-outs PASS.")

    _section("4/4  TEST engine (pytest)")
    proc = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"])
    if proc.returncode != 0:
        print("\n  TESTS FAILED.")
        return proc.returncode

    _section("PIPELINE COMPLETE")
    print("  Launch the dashboard with:\n\n      streamlit run app/Home.py\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
