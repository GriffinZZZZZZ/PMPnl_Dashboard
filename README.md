# PM PnL Dashboard — Multi-Pod Hedge Fund Finance

A polished, fast Streamlit dashboard that a multi-Pod hedge fund's **finance team**
uses to translate raw PM trading performance into the fund's own economics:
accruing PM compensation as a liability, owning the Gross→Net bridge, quantifying
netting risk, and reporting what investors actually net.

> **What this demonstrates:** not a pretty chart, but a *finance automation
> engineer's* deliverable — a one-command, reproducible, **unit-tested**,
> **config-driven**, **reconciled** pipeline that finance can trust to compute
> real money. It replaces a manual month-end stitch of prime-broker statements +
> OMS positions + comp spreadsheets (~2–3 days) with **seconds** (`python run.py`).

📖 The *why* and the *how* live in [`docs/`](docs/):
[business context](docs/business_context.md) ·
[methodology & formulas](docs/methodology.md) ·
[data model](docs/data_model.md).

---

## What you get

- **4-page dashboard** (Fund Overview, Pod & PM drill-down, Attribution, PM Comp as Cost)
- **Tested calculation engine** — 19 pytest cases vs hand-computed values
- **Live Controls & Reconciliation panel** — Fund = ΣPod = ΣPM, comp ties out, investor-net identity holds
- **Config-driven** — change one value in `config/assumptions.yaml`, everything recomputes
- **Decision tool** — a `payout_ratio` slider recomputes comp & investor net live
- **Native Streamlit charts only** (no Plotly/Altair/matplotlib)

---

## Architecture

```
config/assumptions.yaml ──┐
                          ▼
        src/data_gen/generate.py ──► data/*.parquet
                          │            (pods, pms, instruments, prices, positions)
                          ▼
        src/loader.py  ── compute_all() ──► src/engine/
                          │                   pnl → costs → payoff
                          │                   → attribution → economics → recon
                          ▼
        ┌───────────────────────────────┐      run.py
        │ app/Home.py + app/pages/1,2,3  │   one command:
        │ (native st.* charts, theme CSS)│   generate→compute→reconcile→test
        └───────────────────────────────┘
```

---

## Prerequisites

- **Python 3.11+**
- ~200 MB disk for the virtual environment and generated parquet data

---

## Install

```bash
# from the repo root
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Run the pipeline (recommended first step)

```bash
python run.py
```

This runs the whole thing end-to-end and is safe to put in CI:

1. **generate** synthetic data → `data/*.parquet`
2. **compute** all engine outputs
3. **reconcile** — prints the R1–R5 tie-out table; **exits non-zero if any break**
4. **test** — runs `pytest tests/`

On success it prints the command to launch the dashboard.

---

## Launch the dashboard

```bash
streamlit run app/Home.py
```

Streamlit opens a browser at `http://localhost:8501`. Use the left sidebar to move
between the four pages.

> If you launch the app *without* running the pipeline first, generate the data
> once with `python -m src.data_gen.generate`.

---

## How to use each page

### 🏦 Home — Fund Overview
The CEO/LP landing page. KPI cards (AUM, Gross, Net, **PM Comp Expense**, Investor
Net), the fund equity curve (Gross vs Net — the gap *is* the cost bridge), a Pod &
PM leaderboard with inline sparklines and a comp/net progress bar, and the **Controls
& Reconciliation** panel. **All-green = trustworthy.**

### 🔍 Pod & PM — Drill-down
Pick a **Pod**, then a **PM** (or "All PMs in pod") from the two selectors. You get
that selection's KPIs, equity curve, the **Gross → Net → Investor bridge** (costs and
comp shown as negative deductions, with running subtotals), strategy/position
attribution, and the **High-Water Mark vs cumulative net** with the accrued-comp
liability.

### 🧭 Attribution
Where PnL, cost, and loss come from: Net PnL by pod, Gross PnL by strategy and asset
class, top contributors/detractors, total cost by type, and a **risk-vs-return
scatter** (each point a PM, colored by pod).

### 💰 PM Comp as Cost  *(the finance centerpiece)*
Comp expense by pod and PM, the comp/net expense ratio, the **accrued comp liability
over time**, the **netting-risk** callout (comp paid on offset gains), and the
**decision tool**: a `payout_ratio` slider that **recomputes comp and investor net
live**, plus a sensitivity curve across payout ratios.

---

## Editing assumptions (config-driven)

Everything economic lives in [`config/assumptions.yaml`](config/assumptions.yaml):
payout ratios, hurdles, financing/borrow/commission rates, center cost, GBM/factor
parameters, and the pod/PM rosters. **No numbers are hardcoded in the engine.**

Try it: change a PM's `payout_ratio`, then re-run:

```bash
python run.py            # pipeline + reconciliation reflect the change
streamlit run app/Home.py
```

No code edits required — that is the "system, not a one-off script" proof point.

---

## Screenshots

Screenshots are not committed (they would go stale). To capture your own once the
app is running, navigate each page and save images into `docs/images/`. Each page is
described under [How to use each page](#how-to-use-each-page) above.

---

## Testing

```bash
pytest tests/ -q
```

19 tests validate the engine against hand-computed values: MTM roll-up, the
Gross→Net bridge, HWM crystallization (including an underwater PM earning **0**
comp), netting cost, and every reconciliation tie-out.

---

## Troubleshooting / FAQ

**`FileNotFoundError: Missing data tables ...`**
Generate the data first: `python -m src.data_gen.generate` (or just `python run.py`).

**`ModuleNotFoundError: No module named 'src'` / `'app'`**
Run commands from the **repo root** with the virtualenv activated. The app pages add
the repo root to `sys.path` automatically; the pipeline relies on the working dir.

**The dashboard is empty or stale after I changed the config.**
Streamlit caches computed results. Press **"R"** (or use the menu → *Rerun*) to
rerun; for a hard refresh, *Clear cache* from the app menu. `run.py` always
regenerates from scratch.

**The fund is losing money / numbers look off after editing config.**
The synthetic fund's profitability is driven by per-PM `skill` and cost rates in the
config. Extreme edits (very high financing rate, all-negative skill) will make it
unprofitable — that is the model working, not a bug.

**Can I use a different number of PMs/pods/instruments?**
Yes — edit the `pods`/`pms` lists and `n_instruments` in the config and re-run. Keep
each pod's PM capital summing to the pod's `allocated_capital` for a clean read.

**Reconciliation shows a red FAIL.**
That means an identity broke — the numbers are not safe to trust. Re-run the pipeline;
if it persists, a config or engine change violated an invariant. See
[methodology §7](docs/methodology.md).

---

## Project layout

```
pm_pnl_dashboard/
├─ README.md                  # this file (how to run & use)
├─ docs/                      # methodology, data model, business context
├─ config/assumptions.yaml    # all economic assumptions (config-driven)
├─ run.py                     # one-command pipeline
├─ requirements.txt
├─ .streamlit/config.toml     # dark financial theme
├─ src/
│  ├─ config.py               # YAML loader + blended payout
│  ├─ data_gen/generate.py    # synthetic data (factor model + skill)
│  ├─ engine/                 # pnl, costs, payoff, attribution, economics, recon
│  └─ loader.py               # cached loaders + compute_all()
├─ app/
│  ├─ Home.py                 # Fund Overview
│  ├─ pages/                  # 1 Pod & PM · 2 Attribution · 3 PM Comp as Cost
│  └─ components/             # theme (CSS), kpi cards, controls panel
└─ tests/                     # pytest engine correctness
```
