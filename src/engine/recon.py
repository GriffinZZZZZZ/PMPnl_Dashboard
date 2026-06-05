"""Reconciliation / control tie-outs.

These checks are the line between a trustworthy system and a toy. They are
asserted in ``run.py`` and the pytest suite, and rendered live as green/red in
the dashboard's Controls panel.

    R1  Fund Gross == sum(Pod Gross) == sum(PM Gross)
    R2  Fund Net   == sum(Pod Net)   == sum(PM Net)
    R3  Total Comp == sum(PM accrued_comp_T)
    R4  Investor Net == Fund Net - Total Comp - Center Cost (accrued)
    R5  Each Pod Net == sum of its PMs' Net
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.engine.attribution import pnl_by_pod
from src.engine.economics import center_cost_total
from src.engine.payoff import total_comp_by_pm

TOL = 1e-6


@dataclass
class Check:
    """One reconciliation tie-out result."""

    name: str
    expected: float
    actual: float

    @property
    def diff(self) -> float:
        return self.actual - self.expected

    @property
    def passed(self) -> bool:
        # Relative tolerance for large dollar magnitudes, absolute floor for tiny ones.
        scale = max(1.0, abs(self.expected), abs(self.actual))
        return abs(self.diff) <= TOL * scale


def run_checks(results: dict, cfg: dict) -> list[Check]:
    """Compute all R1-R4 checks from the engine result bundle.

    Args:
        results: dict produced by the loader's ``compute_all`` containing at least
            ``pm_net_daily``, ``pms``, ``payoff_daily``, ``fund_net``,
            ``total_comp``, ``investor_net``.
        cfg: parsed config (for center cost).

    Returns:
        A list of :class:`Check`.
    """
    pm_net_daily = results["pm_net_daily"]
    pms = results["pms"]
    fund_gross = results["fund_gross"]
    fund_net = results["fund_net"]
    total_comp = results["total_comp"]
    investor_net = results["investor_net"]
    pod = pnl_by_pod(pm_net_daily, pms)

    checks: list[Check] = []

    # R1 — Fund Gross vs sum of PM / Pod gross (bottom-up MTM ties by construction).
    checks.append(Check("R1a  Fund Gross == Sum(PM Gross)", fund_gross, float(pm_net_daily["gross_pnl"].sum())))
    checks.append(Check("R1b  Fund Gross == Sum(Pod Gross)", fund_gross, float(pod["gross_pnl"].sum())))

    # R2 — Fund Net vs sum of PM / Pod net.
    checks.append(Check("R2a  Fund Net == Sum(PM Net)", fund_net, float(pm_net_daily["net_pnl"].sum())))
    checks.append(Check("R2b  Fund Net == Sum(Pod Net)", fund_net, float(pod["net_pnl"].sum())))

    # R3 — Total comp vs sum of per-PM accrued comp.
    sum_pm_comp = float(total_comp_by_pm(results["payoff_daily"])["total_comp"].sum())
    checks.append(Check("R3   Total Comp == Sum(PM Comp)", total_comp, sum_pm_comp))

    # R4 — Investor net identity (center cost accrued over the period).
    cc = center_cost_total(cfg)
    checks.append(Check("R4   Investor Net identity", fund_net - total_comp - cc, investor_net))

    # R5 — Each pod net == sum of its PMs' net.
    pm_with_pod = pm_net_daily.merge(pms[["pm_id", "pod_id"]], on="pm_id", how="left")
    per_pod_from_pm = pm_with_pod.groupby("pod_id")["net_pnl"].sum()
    max_pod_diff = 0.0
    for pod_id, expected in pod.set_index("pod_id")["net_pnl"].items():
        actual = float(per_pod_from_pm.get(pod_id, 0.0))
        max_pod_diff = max(max_pod_diff, abs(actual - expected))
    checks.append(Check("R5   Pod Net == Sum(its PM Net)", 0.0, max_pod_diff))

    return checks


def all_passed(checks: list[Check]) -> bool:
    """True iff every check passes."""
    return all(c.passed for c in checks)


def to_frame(checks: list[Check]) -> pd.DataFrame:
    """Render checks as a tidy DataFrame for display/printing."""
    return pd.DataFrame(
        [
            {
                "Check": c.name,
                "Expected": c.expected,
                "Actual": c.actual,
                "Diff": c.diff,
                "Status": "PASS" if c.passed else "FAIL",
            }
            for c in checks
        ]
    )
