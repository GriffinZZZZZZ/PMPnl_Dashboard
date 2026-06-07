# PM PnL Dashboard

A polished, fast Streamlit dashboard for multi-pod portfolio management:
tracking PM trading performance through the full Gross→Net→Eligible pipeline,
accruing PM compensation as a liability, quantifying netting risk, and
reporting what investors actually net.

> **What this demonstrates:** not a pretty chart, but an *automation engineer's*
> deliverable — a one-command, reproducible, **unit-tested**, **config-driven**,
> **reconciled** pipeline that computes real money. It replaces a manual month-end
> process (~2–3 days) with **seconds** (`python run.py`).

📖 The *why* and the *how* live in [`docs/`](docs/):
[business context](docs/business_context.md) ·
[methodology & formulas](docs/methodology.md) ·
[data model](docs/data_model.md) ·
[assumptions & rationale](docs/assumptions.md).

---

## What you get

- **5-page dashboard** (Fund Overview, Pod & PM Drill-down, Attribution, PM Comp as Cost, SQL Data Explorer)
- **Tested calculation engine** — 59 pytest cases vs hand-computed values
- **Live Controls & Reconciliation panel** — Fund = ΣPod = ΣPM = ΣTeam, comp ties out, investor-net identity holds
- **Config-driven** — change one value in `config/assumptions.yaml`, everything recomputes
- **Structural comp** — contractual base payout + tiered marginal ladder + prior-year loss carryforward
- **Two pod taxonomies** — group by strategy pod or by cross-strategy team (a toggle on each page)
- **Decision tool** — a payout-ratio slider recomputes comp & investor net live, with the current ratio marked
- **Polished Altair charts** — zoom, tooltips, angled labels, a Gross→Net waterfall (pure-Python, bundled with Streamlit; no Plotly/matplotlib)
- **Dynamic AUM** — fund AUM evolves monthly via performance-based PM reallocation + net investor flows; the `aum_history` table feeds the `center` and `capital_charge` deductions daily and is charted on the Home page
- **Native theming** — refined dark & light themes in `config.toml`; charts, cards, and tables follow the theme automatically (switch via the app's ☰ → Settings)

---

## Architecture

```
config/assumptions.yaml ──┐
                          ▼
        src/data_gen/generate.py ──► data/pm_pnl.db  (SQLite)
                          │            (strategy_pods, portfolio_managers, security_master,
                          │             eod_prices, eod_positions, eod_income, aum_history)
                          ▼
        src/loader.py  ── compute_all() ──► src/engine/
                          │                   pnl → costs → payoff
                          │                   → attribution → economics → recon
                          ▼
        ┌─────────────────────────────────┐      run.py
        │ app/Home.py + app/pages/1,2,3,4 │   one command:
        │ (native st.* charts, theme CSS) │   generate→compute→reconcile→test
        └─────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Role in this project |
|---|---|---|
| **Web framework** | [Streamlit](https://streamlit.io) ≥ 1.40 | Multi-page app; `@st.cache_data` for computation caching; `@st.fragment` for isolated chart-level reruns (zoom without full-page rerun); `st.dataframe` + `column_config` for typed table rendering |
| **Charting** | [Altair](https://altair-viz.github.io) ≥ 5.0 (Vega-Lite) | All charts are declarative Vega-Lite specs: `show_line`, `show_area`, `show_stacked_area`, `bar`, `waterfall`, `scatter`, `show_dual`; interactive zoom + crosshair tooltip via Vega-Lite parameters; `labelExpr` for USD million-formatted axes |
| **Data manipulation** | [pandas](https://pandas.pydata.org) ≥ 2.0 | All engine transformations — pivot, groupby, cumsum, merge — are pure pandas DataFrames; no SQL in the calculation engine |
| **Numerics** | [NumPy](https://numpy.org) ≥ 1.24 | GBM price simulation, correlated factor-model returns for synthetic data generation |
| **Database** | SQLite (Python stdlib) | Zero-config embedded DB; single file `data/pm_pnl.db`; accessed via thin helpers in `src/db.py`; SQL Data Explorer page exposes it for ad-hoc queries |
| **Config** | [PyYAML](https://pyyaml.org) ≥ 6.0 | `config/assumptions.yaml` is the single source of truth for all economic parameters — payout ratios, hurdle rates, cost rates, pod/PM roster; no numbers hardcoded in engine modules |
| **Testing** | [pytest](https://pytest.org) ≥ 7.4 | 59 test cases; `conftest.py` seeds an in-memory SQLite DB with deterministic fixtures; each test validates engine output against hand-computed expected values |
| **Theming** | Streamlit native `config.toml` | Dark + light themes defined in `[theme.dark]` / `[theme.light]`; IBM Plex Sans (body), Fraunces (headings), IBM Plex Mono (code) loaded via Google Fonts; chart color tokens propagated via CSS `--st-*` variables read at runtime by `app/components/theme.py` |
| **Pipeline** | `run.py` (plain Python) | Single-command orchestrator: generate synthetic data → run engine → print R1–R7 reconciliation table → execute pytest; exits non-zero on any break; safe to run in CI |
| **Language** | Python 3.11+ | `__future__.annotations`, f-strings, walrus operator; no compiled extensions |

---

## Prerequisites

- **Python 3.11+** — verify with `python --version` (Mac: `python3 --version`)
- **~200 MB** free disk space for the virtual environment and generated database
- **Git** (to clone the repo)

---

## Install

**macOS / Linux**

```bash
git clone <repo-url>
cd pm_pnl_dashboard

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

**Windows (PowerShell)**

```powershell
git clone <repo-url>
cd pm_pnl_dashboard

python -m venv .venv
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

> **Windows — `python` opens the Microsoft Store?**
> Use the `py` launcher instead: `py -m venv .venv`, then `.venv\Scripts\Activate.ps1`.

> **Windows — PowerShell blocks script execution?**
> Run once as Administrator: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
> Then retry `.venv\Scripts\Activate.ps1`.

> **Mac — `python` not found?**
> Use `python3` and `pip3` throughout, or install Python via [python.org](https://www.python.org/downloads/) or `brew install python`.

---

## Run the pipeline (recommended first step)

Activate the virtual environment first (if not already active), then:

**macOS / Linux**
```bash
source .venv/bin/activate
python run.py
```

**Windows (PowerShell)**
```powershell
.venv\Scripts\Activate.ps1
python run.py
```

This runs the whole thing end-to-end and is safe to put in CI:

1. **generate** synthetic data → `data/pm_pnl.db` (SQLite)
2. **compute** all engine outputs
3. **reconcile** — prints the R1–R7 tie-out table; **exits non-zero if any break**
4. **test** — runs `pytest tests/`

On success it prints the command to launch the dashboard.

---

## Launch the dashboard

With the virtual environment active:

```bash
streamlit run app/Home.py
```

Streamlit opens a browser at `http://localhost:8501`. Use the left sidebar to move
between the five pages.

> **Session tip:** once the venv is activated in your terminal, `python`, `pip`,
> and `streamlit` all resolve to the venv automatically — no need to type the full
> path each time.

> If you launch the app *without* running the pipeline first, generate the data
> once with `python -m src.data_gen.generate`.

---

## How to use each page

Start on **Home** for the fund-level picture, then use **Pod & PM** to drill into
any selection. Use **Attribution** to find where PnL and costs come from, **PM Comp
as Cost** to understand the comp liability and what-if scenarios, and **SQL Explorer**
to verify any number against raw data.

The **date filter** in the left sidebar applies to all five pages simultaneously —
change it once and everything updates.

---

### 🏦 Home — Fund Overview

*The top-level snapshot. The first question it answers: is the fund making money, and can we trust the numbers?*

**KPI cards** across the top:
- **AUM** — total allocated capital at period end
- **Gross PnL** — trading + non-trading income before any costs
- **Net PnL** — after financing, borrow, commission, and FX
- **Return on AUM** — net PnL / AUM for the selected period
- **Eligible PnL** — net PnL after center overhead and capital charge (the PM comp base)
- **Incentive Comp Accrued** — total comp liability built up so far

**Fund Equity Curve** (below the KPIs):
Three lines — Gross, Net, Eligible — plotted cumulatively.
The gap between Gross and Net is the total cost drag.
The further gap down to Eligible is center overhead and capital charge.
- **Drag** on the chart to zoom into a date range; **double-click** to reset.
- **Hover** on any date for exact values per series.

**Fund AUM Over Time**: monthly AUM evolution driven by net investor flows
and performance-based PM reallocation. A flat or declining line means outflows
or underperformance-driven cuts are offsetting gains.

**All Portfolio Managers — PnL Over Time**: toggle between Gross / Net / Eligible
with the radio buttons; cumulative PnL per PM on one chart to see relative contributions.

**Pod & PM Leaderboard**: ranked by Net PnL, with columns for Eligible PnL,
Max Drawdown (% of capital), Comp, Comp/Eligible (progress bar 0–100%), and a
3-month sparkline trend. A PM deep in drawdown with a large prior-year loss will
show near-zero comp even if recent PnL is positive.

**Controls & Reconciliation panel** (bottom): the R1–R7 internal tie-out.
**All green = numbers are internally consistent and safe to trust.**
A red FAIL means an accounting identity broke — re-run the pipeline before
relying on any figures.

> Switch **light / dark** mode: app menu ☰ → Settings → Appearance.

---

### 🔍 Pod & PM Drill-down

*Deep-dive into a single pod, team, or PM. Answers: what drove this selection's PnL, what did it cost, and where does comp stand?*

**Step 1 — Select a scope** using the two dropdowns at the top:
- **Pod / Team** — choose a strategy pod (e.g., Equity L/S), a cross-strategy team, or "All pods"
- **PM** — narrow to one PM or keep "All PMs in selection"

Everything below updates instantly for that selection.

**Allocated Capital Over Time**: shows how this PM's AUM changed as the investment
committee reallocated capital month by month.

**Equity Curve + Drawdown** (two charts):
- Cumulative Gross / Net / Eligible for the selection. Drag to zoom, hover for values.
- Drawdown as % of allocated capital relative to the High-Water Mark.
  A value of –5 means the book is 5% below its peak eligible PnL.

**Gross → Net → Eligible → Investor Bridge** (waterfall + table side by side):
The waterfall shows every deduction in sequence — each step reduces the starting
Trading PnL until you arrive at what investors actually net.
The table on the right lists every line in income-statement format:
deductions are indented in red, bold rows are subtotals (Gross, Net, Eligible, Investor Net).
Use this to explain precisely why a PM's comp base is lower than their gross book.

**Strategy & Position Attribution**:
- Bar chart of Gross PnL broken down by strategy tag.
- Top & bottom 10 positions table: ticker, which PM holds it, position return (%), and absolute PnL.
  Sorting is by absolute PnL — the biggest winners and biggest losers are at the top and bottom.

**High-Water Mark, Cumulative Eligible & Accrued Comp**:
- Line chart: HWM (the running peak of eligible PnL) vs cumulative eligible PnL.
  Comp only accrues when the blue line rises above the orange line (new peak).
- Area chart: accrued comp liability over time.
- If a PM has an unrecovered prior-year loss, a **loss carryforward callout** appears —
  the PM must earn back that amount before any comp accrues this year.

---

### 🧭 Attribution

*Breaks down where PnL, cost, and risk come from across every dimension. Answers: which pods, strategies, asset classes, and positions drove performance — and what did it cost?*

**PnL Attribution** (top section, four charts):
- Net PnL by **Strategy Pod** and by **Team** — bars show absolute PnL; orange dots show Return on Capital on a second axis. A pod with large PnL but low return used a lot of capital to get there.
- Gross PnL by **Strategy** and by **Asset Class** — same layout. Use these to spot which strategies and asset classes are carrying the fund.

**Non-trading Income** (middle section):
Summary metrics show how Trading PnL, Non-trading PnL, and Gross PnL relate.
The horizontal bar chart breaks non-trading income by category (Tax Reclaim, Fee Rebate, Legal Settlement, Corporate Action, Interest True-up).

**Position Analysis** (two tables side by side):
- **Top & Bottom 10 by PnL** — includes the PM who holds each position, the position's return (%), and its absolute Gross PnL contribution. Use this to identify idiosyncratic winners/losers.
- **Top 10 by NMV / AUM** — concentration risk. A position at 8% NMV/AUM dominates the book; any adverse move has outsized impact. High concentration + high vol = elevated tail risk.

**Cost Attribution** (bottom section):
- **Radio button** at the top selects the breakdown level: Strategy Pod / Team / PM.
- **Stacked bar chart** showing each cost component (Financing, Borrow, Commission, FX, Center, Capital Charge) stacked per group. Hover a segment for the exact dollar amount.
- **Cost detail table** alongside: lists each cost line and the **Cost / Gross PnL** ratio. A low ratio means returns come from revenue, not just cost control. A ratio above 1.0 means the group lost money net of its own costs.

**Risk vs Return** (scatter plot, bottom):
One point per PM. X-axis = annualized volatility; Y-axis = annualized return on capital.
The dashed reference line = Sharpe ratio of 1.0. Points above it have Sharpe > 1.
Hover any point for PM name, exact return, volatility, and Sharpe ratio.

---

### 💰 PM Comp as Cost

*Treats PM incentive compensation as an accrued liability. Answers: how much is comp costing the fund, which PMs are earning above their contractual rate, and what happens to investor net if we renegotiate payout ratios?*

**Comp Expense by Pod** — stacked bar showing each pod's total incentive comp for the period.

**Comp by PM** — for each PM: accrued comp amount, contractual payout ratio, and realized effective rate (effective = accrued comp / eligible PnL).
- Effective rate **above** contractual = the tiered comp ladder triggered on outsized profit (the PM had an exceptional year).
- Effective rate **below** contractual = the PM has an unrecovered prior-year loss; comp is partially held back.

**Netting Risk Callout**: when long-biased and short-biased PMs sit in the same pod, their positions partially offset — this reduces gross notional and therefore financing/borrow costs at the fund level. But this benefit can mask individual PM underperformance (a losing short-biased PM is "hidden" by a winning long-biased PM in the same pod). The callout quantifies the netting benefit in dollar terms.

**Accrued Comp Over Time** — area chart of cumulative accrued comp vs cumulative Net PnL. The ratio shows what fraction of the period's net profit is spoken for as comp liability.

**Payout-Ratio Sensitivity Tool** (interactive slider):
- Move the slider to a hypothetical **uniform payout ratio** (applies the same rate to all PMs).
- The **total comp** and **investor net** instantly recalculate for that scenario.
- The **sensitivity curve** below shows investor net across the full slider range; the current actual blended rate is marked with a vertical line.
- Use this to evaluate the fund-level impact of tightening or loosening PM contracts.

> Moving the slider left (lower payout) increases investor net but reduces PM retention incentive.
> Moving it right shows how quickly comp expense can grow if payout terms are more generous.

---

### 🗄️ SQL Data Explorer

*A live query console against the underlying database. Use it to verify that any number on any other page traces directly to source rows — closing the audit loop.*

**Table browser**: select a table from the dropdown to preview the first 100 rows instantly.

Available tables:
| Table | Contents |
|---|---|
| `strategy_pods` | Pod definitions and allocated capital |
| `portfolio_managers` | PM roster, payout terms, skill, prior-year PnL |
| `security_master` | Instrument metadata: ticker, asset class, strategy tag |
| `eod_prices` | Daily closing prices per instrument |
| `eod_positions` | Daily PM positions (quantity, notional) |
| `eod_income` | Non-trading income events per PM |
| `aum_history` | Monthly per-PM AUM after reallocation |

**SQL editor**: type any SQLite-dialect query; results appear as a scrollable, sortable dataframe.

Example queries to get started:

```sql
-- Largest single-day PnL moves across all PMs
SELECT date, pm_id, gross_pnl
FROM pm_net_daily
ORDER BY ABS(gross_pnl) DESC
LIMIT 20;

-- AUM history for one PM over the year
SELECT date, pm_aum
FROM aum_history
WHERE pm_id = 'PM_ECM_1'
ORDER BY date;

-- All non-trading income events above $500k
SELECT date, pm_id, category, amount
FROM eod_income
WHERE ABS(amount) > 500000
ORDER BY date DESC;

-- Cost breakdown totals by PM
SELECT pm_id,
       SUM(financing) AS financing,
       SUM(borrow)    AS borrow,
       SUM(commission) AS commission
FROM pm_net_daily
GROUP BY pm_id
ORDER BY SUM(financing) DESC;
```

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

### 🏦 Fund Overview
KPI cards, the Gross-vs-Net fund equity curve, the Pod & PM leaderboard, and the live
Controls & Reconciliation panel.

![Fund Overview](docs/images/01_Home.png)

### 🔍 Pod & PM Drill-down
Per-selection KPIs, equity curve, and the Gross → Net → Investor bridge.

![Pod and PM Drill-down](docs/images/02_Pod_and_PM.png)

### 🧭 Attribution
Net PnL by pod, Gross PnL by strategy and asset class, and top contributors/detractors.

![Attribution](docs/images/03_Attribution.png)

### 💰 PM Comp as Cost
Comp expense by pod/PM, the comp/net ratio, netting-risk callout, accrued comp
liability over time, and the `payout_ratio` sensitivity tool.

![PM Comp as Cost](docs/images/04_PM_Comp_as_Cost.png)

### 🗄️ SQL Data Explorer
Live query console against `data/pm_pnl.db` — browse raw tables, run ad-hoc SQL,
close the audit loop between dashboard numbers and source data.

![SQL Data Explorer](docs/images/05_SQL_Data_Explorer.png)

> To regenerate these after a UI change: run the app, then re-capture each page into
> `docs/images/` (filenames `01_Home.png` through `05_SQL_Data_Explorer.png`).

---

## Testing

```bash
pytest tests/ -q
```

59 tests validate the engine against hand-computed values: MTM roll-up, the
Gross→Net→Eligible bridge, HWM crystallization (including an underwater PM earning
**0** comp), the tiered comp ladder, prior-year loss carryforward, netting cost,
non-trading income, dynamic AUM history, and every reconciliation tie-out (R1–R7).

---

## Troubleshooting / FAQ

**`FileNotFoundError: Missing data tables ...`**
The database hasn't been generated yet. Run the pipeline first:
```bash
python run.py          # Mac / Linux (venv active)
python run.py          # Windows PowerShell (venv active)
```
Or generate data only: `python -m src.data_gen.generate`.

---

**`ModuleNotFoundError: No module named 'src'` / `'app'`**
Two common causes:
1. **Wrong directory** — run all commands from the repo root (`pm_pnl_dashboard/`), not a subdirectory.
2. **Venv not active** — activate it first:
   - Mac/Linux: `source .venv/bin/activate`
   - Windows: `.venv\Scripts\Activate.ps1`

---

**Windows: `.venv\Scripts\Activate.ps1` is blocked by execution policy**
Run once in PowerShell (no admin needed):
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Then retry activation.

---

**Windows: `python` opens the Microsoft Store instead of running**
Use the `py` launcher:
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

**Mac: `python: command not found`**
Use `python3`:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
Or install Python via [python.org](https://www.python.org/downloads/) or `brew install python`.

---

**The dashboard is empty or stale after I changed the config.**
Streamlit caches computed results. Press **R** in the browser (or app menu → *Rerun*)
to reload; for a hard reset, use *Clear cache* from the app menu. `run.py` always
regenerates from scratch and clears the cache automatically.

---

**Numbers look wrong / the fund is losing money after editing config.**
The fund's profitability is driven by per-PM `skill` and cost rates in the config.
Extreme edits (very high financing rate, all-negative skill) will produce losses —
that is the model working correctly, not a bug. See [assumptions & rationale](docs/assumptions.md).

---

**Can I use a different number of PMs/pods/instruments?**
Yes — edit the `pods`/`pms` lists and `n_instruments` in `config/assumptions.yaml` and re-run.
Keep each pod's PM `allocated_capital` values summing to the pod's `allocated_capital`
or reconciliation check R2 will fail.

---

**Reconciliation shows a red FAIL.**
An accounting identity broke — numbers are not safe to trust. Re-run the pipeline;
if it persists, a config or engine change violated an invariant. See
[methodology §7](docs/methodology.md).

---

## Project layout

```
pm_pnl_dashboard/
├─ README.md                              # this file
├─ run.py                                 # one-command pipeline: generate → compute → reconcile → test
├─ requirements.txt                       # Python dependencies
│
├─ config/
│  └─ assumptions.yaml                   # all economic parameters — payout ratios, hurdles,
│                                        #   cost rates, pod/PM roster (no numbers in engine code)
├─ .streamlit/
│  └─ config.toml                        # native dark + light theme; chart palette; fonts
│
├─ data/
│  └─ pm_pnl.db                          # generated SQLite database (created by run.py)
│
├─ docs/
│  ├─ business_context.md               # motivation, roles, and what each calculation means
│  ├─ methodology.md                    # formula derivations and reconciliation identities (R1–R7)
│  ├─ data_model.md                     # table schemas and column definitions
│  ├─ assumptions.md                    # every config parameter, its value, and its rationale
│  └─ images/                           # page screenshots (01_Home.png … 04_PM_Comp_as_Cost.png)
│
├─ src/
│  ├─ config.py                          # YAML loader + blended payout-ratio helper
│  ├─ db.py                              # SQLite helpers: query(), execute()
│  ├─ loader.py                          # compute_all() — cached orchestration of the full engine
│  ├─ data_gen/
│  │  └─ generate.py                    # synthetic data: factor-model prices, PM positions,
│  │                                    #   AUM history with monthly reallocation
│  └─ engine/
│     ├─ pnl.py                         # mark-to-market roll-up → gross / net / eligible daily PnL
│     ├─ costs.py                        # financing, borrow, commission, FX, center, capital charge;
│     │                                 #   bridge_components() for the waterfall
│     ├─ payoff.py                       # HWM crystallisation, tiered comp ladder, loss carryforward
│     ├─ attribution.py                  # PnL by pod / team / strategy / asset class;
│     │                                 #   top-bottom positions; concentration table
│     ├─ economics.py                    # fund-level aggregations: AUM, investor net, expense ratios
│     └─ recon.py                        # R1–R7 reconciliation checks (Fund = ΣPod = ΣPM = ΣTeam)
│
├─ app/
│  ├─ Home.py                            # page 1 — Fund Overview (KPIs, equity curve, leaderboard,
│  │                                    #   AUM time-series, controls & recon panel)
│  ├─ pages/
│  │  ├─ 1_PM_Book_Drilldown.py         # page 2 — Pod & PM drill-down: KPIs, equity curve,
│  │  │                                 #   Gross→Net→Investor waterfall, attribution, HWM/comp
│  │  ├─ 2_PnL_Attribution.py           # page 3 — PnL by strategy / asset class; position analysis;
│  │  │                                 #   cost breakdown; risk-vs-return scatter
│  │  ├─ 3_Comp_and_Netting_Risk.py     # page 4 — comp expense, netting risk callout,
│  │  │                                 #   accrued comp over time, payout-ratio sensitivity slider
│  │  └─ 4_SQL_Data_Explorer.py         # page 5 — live SQL console against pm_pnl.db
│  └─ components/
│     ├─ charts.py                       # Altair chart builders: show_line, show_area,
│     │                                 #   show_stacked_area, bar, waterfall, scatter, show_dual …
│     ├─ controls.py                     # date filter sidebar + reconciliation panel renderer
│     ├─ kpi.py                          # kpi_card(), kpi_row(), fmt_money(), fmt_pct()
│     └─ theme.py                        # color tokens, page_header(), section(), setup_page()
│
└─ tests/
   ├─ conftest.py                        # shared fixtures: in-memory DB, seeded engine outputs
   ├─ test_pnl.py                        # MTM roll-up, gross/net/eligible bridge
   ├─ test_costs.py                      # financing, borrow, commission, FX, center
   ├─ test_payoff.py                     # HWM crystallisation, tiered ladder, loss carryforward
   ├─ test_attribution.py               # contribution breakdowns, concentration
   ├─ test_economics.py                 # investor net, expense ratios
   ├─ test_income.py                    # non-trading income booking
   ├─ test_aum_history.py              # dynamic AUM reallocation
   ├─ test_recon.py                     # R1–R7 tie-outs
   └─ test_db.py                        # SQLite helper tests
```
