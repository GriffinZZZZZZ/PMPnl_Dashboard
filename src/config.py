"""Centralized loader for ``config/assumptions.yaml``.

Every economic assumption (payout ratios, hurdles, financing/borrow/commission
rates, center-cost, GBM parameters, pod/PM rosters) lives in the YAML file so
that the engine contains *no* hardcoded numbers. Both the data generator and
the calculation engine import :func:`load_config` from here.
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

# Repository root = two levels up from this file (src/config.py -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "assumptions.yaml"
DATA_DIR = REPO_ROOT / "data"
DB_PATH = DATA_DIR / "pm_pnl.db"


@functools.lru_cache(maxsize=8)
def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load and cache the assumptions YAML as a plain dict.

    Args:
        path: Optional override path. Defaults to ``config/assumptions.yaml``.

    Returns:
        The parsed configuration dictionary.
    """
    cfg_path = Path(path) if path is not None else CONFIG_PATH
    with open(cfg_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def blended_payout_ratio(cfg: dict[str, Any]) -> float:
    """Capital-weighted average payout ratio across all PMs.

    Used as the reference rate in the netting-risk calculation: the rate the
    fund *would* pay if comp were charged only on the fund's net result.
    """
    pms = cfg["pms"]
    total_cap = sum(pm["allocated_capital"] for pm in pms)
    if total_cap == 0:
        return 0.0
    return sum(pm["payout_ratio"] * pm["allocated_capital"] for pm in pms) / total_cap
