# Methodology & Rationale

This document is the authoritative description of *how every number on the
dashboard is computed*. All formulas live in `src/engine/` and are validated by
hand-computed pytest cases in `tests/`. Notation: `dt = 1/252` (one trading day),
`i` = instrument, `t` = day, `pm` = portfolio manager.

---

## 0. Design principles

1. **Bottom-up, mark-to-market only.** PnL is never fabricated — it comes solely
   from `quantity × price change`. Because every level is a sum of the level
   below it, `Position → PM → Pod → Fund` reconciles *by construction*.
2. **Config-driven.** Every economic assumption lives in `config/assumptions.yaml`.
   The engine contains no hardcoded numbers.
3. **Auditable.** A set of reconciliation tie-outs (Section 7) is asserted in
   tests and shown live in the dashboard's Controls panel.

---

## 1. Prices — a factor model

Each instrument's daily log return is a market factor plus idiosyncratic noise:

```
r_{i,t} = beta_i * f_t + eps_{i,t}
f_t     ~ Normal(market.mu * dt,  market.sigma * sqrt(dt))      # shared factor
eps_{i,t} ~ Normal(alpha_i * dt,  idio_vol_i * sqrt(dt))        # idiosyncratic
price_{i,t} = price_{i,0} * exp( cumsum_t r_{i,t} )             # cumulated GBM
```

The **shared factor** `f_t` makes instruments co-move. That co-movement is what
makes **netting risk** (Section 6) non-trivial: when the market factor falls,
many pods lose together, so winners and losers do not cleanly cancel.

`beta_i`, `alpha_i`, `idio_vol_i` are drawn per instrument from per-asset-class
parameters in config (`asset_classes`).

---

## 2. Positions — skill-driven

Each PM trades a random subset of instruments. Target weights blend a
**skill-scaled signal** with noise:

```
signal_i = zscore( realized forward return of i over the window )
raw_i    = skill_pm * signal_i + noise_i,   noise_i ~ Normal(0, noise_scale)
weight_i = |raw_i| / Σ|raw|,   sign_i = sign(raw_i)
notional_i = (capital_pm * gross_leverage) * weight_i * sign_i
qty_{i,0}  = notional_i / price_{i,0}
```

Quantities then follow a mean-reverting random walk day to day, which creates
turnover (and therefore commission). A higher `skill` means a PM sits on the
right side of moves more often → more PnL. `skill ≈ 0` is noise (usually
underwater after costs); `skill < 0` is anti-skilled (loses money).

---

## 3. PnL — mark-to-market roll-up  (`src/engine/pnl.py`)

```
pos_pnl_{pm,i,t} = quantity_{pm,i,t-1} * (price_{i,t} - price_{i,t-1})
pm_gross_{pm,t}  = Σ_i pos_pnl_{pm,i,t}
pod_gross        = Σ pm_gross  (over PMs in pod)
fund_gross       = Σ pm_gross  (over all PMs)
```

The same per-position frame also yields the exposures the cost engine needs:

```
gross_exposure_{pm,t} = Σ_i |quantity_{i,t} * price_{i,t}|
short_notional_{pm,t} = Σ_i max(-quantity_{i,t} * price_{i,t}, 0)
traded_notional_{pm,t} = Σ_i |quantity_{i,t} - quantity_{i,t-1}| * price_{i,t}
```

**Worked example.** Hold 10 units; price moves 100 → 110. PnL = `10 × (110−100) = 100`;
gross exposure (prior day) = `|10 × 100| = 1000`. (See `tests/test_pnl.py`.)

---

## 4. Gross → Net → Eligible bridge  (`src/engine/costs.py`)

**Gross PnL has two components:**

```
trading_pnl     = Σ_i prev_qty × Δprice          (mark-to-market, bottom-up)
non_trading_pnl = other non-recurring income       (fee rebates, settlements, …; eod_income table)
gross_pnl       = trading_pnl + non_trading_pnl
```

**Tier 1 — trading costs** (market-facing; rates are annual, charged daily via `dt` on prior-day exposures):

```
financing_{pm,t}  = financing_rate * long_notional_{pm,t-1}  * dt    (longs are financed)
borrow_{pm,t}     = borrow_rate    * short_notional_{pm,t-1} * dt    (shorts pay borrow)
commission_{pm,t} = (commission_bps / 1e4) * traded_notional_{pm,t}
fx_{pm,t}         = fx_rate        * fx_notional_{pm,t-1}    * dt    (FX-class gross notional)
trading_cost      = financing + borrow + commission + fx
net_pnl           = gross_pnl − trading_cost
```

**Tier 2 — overhead costs** (fund structure; allocated to PMs by AUM share):

```
center_{pm,t}         = center_cost_bps_on_aum / 1e4 * pm_aum_{pm,t} * dt
capital_charge_{pm,t} = hurdle_rate * pm_aum_{pm,t} * dt              (cost of capital)
overhead_cost         = center + capital_charge
eligible_pnl          = net_pnl − overhead_cost
```

> **Incentive comp accrues on `eligible_pnl`**, not on `net_pnl`. Deducting center cost and
> capital charge before the high-water-mark calculation (Section 5) ensures PMs are only paid
> on profit that exceeds the fund's cost of running their book.

**Worked example.** Gross 100; long notional 700; short notional 300; traded 200; fx notional 100;
rates: `financing=0.030`, `borrow=0.015`, `commission_bps=1.5`, `fx_rate=0.010` (all annual):
`financing = 0.030/252×700 ≈ 0.083`, `borrow = 0.015/252×300 ≈ 0.018`,
`commission = 0.00015×200 = 0.030`, `fx = 0.010/252×100 ≈ 0.004` → `net_pnl ≈ 99.865`.
With `center = 0.08`, `capital_charge = 0.12` → `eligible_pnl ≈ 99.665`. (`tests/test_costs.py`.)

---

## 5. Compensation — high-water-mark crystallization  (`src/engine/payoff.py`)

Per PM, on cumulative **eligible** PnL, with a running high-water mark and **no clawback**.
Two structural features sit on top of the base rate:

- **Loss carryforward.** A negative `prior_year_pnl` becomes
  `loss_carryforward = max(0, −prior_year_pnl)` that must be earned back this year
  before any comp accrues (it raises the threshold).
- **Tiered (structural) payout.** The contractual `payout_ratio` is the *base*
  rate; a `comp_tiers` ladder adds marginal percentage points on higher bands of
  eligible profit (e.g. +3pp on $1M–$2M, +6pp above $2M).

```
cum_net_{pm,t}      = Σ_{s≤t} eligible_pnl_{pm,s}                      # accrues on eligible
peak_{pm,t}         = max(initial_hwm, max_{s≤t} cum_net)               # ratcheting HWM
hurdle_amt_{pm,t}   = hurdle_rate * pm_aum * (t * dt)                   # audit display only
profit_above_{pm,t} = max(0, peak - initial_hwm - loss_carryforward)
accrued_comp_{pm,t} = tiered(profit_above; base = payout_ratio, comp_tiers)
                    = Σ_tiers (base + add_pp) * (profit_above slice in that tier)
daily_comp_{pm,t}   = accrued_comp_t - accrued_comp_{t-1}   ( ≥ 0 )
total_comp          = Σ_pm accrued_comp_{pm,T}
effective_rate_pm   = total_comp_pm / profit_above_pm        # base ≤ effective ≤ base+top add_pp
```

> **Why `hurdle_amt` is not subtracted from `profit_above`:** the capital charge
> (`hurdle_rate × pm_aum × dt`) is already deducted daily inside `eligible_pnl` (Section 4).
> Subtracting it again in `profit_above` would double-count the hurdle. `hurdle_amt` is kept
> for audit transparency — it shows the time-scaled threshold on the comp page — but does not
> enter the computation.

`accrued_comp` is wrapped in a running max so it is **monotonically
non-decreasing** ("crystallized") — once comp is earned at a peak it does not
reverse. This models comp as a **GAAP liability that grows daily with PnL**, not
a year-end surprise.

**Worked examples** (`tests/test_payoff.py`):
- Eligible `[50, 50, −30]`, base 0.2, no tiers → cum `[50, 100, 70]`, peak `[50, 100, 100]`,
  accrued `[10, 20, 20]` — day 3 stays at 20 (no clawback).
- Profit above HWM of $3M with base 0.2 and the ladder above → comp
  `0.20×1M + 0.23×1M + 0.26×1M = 690,000` (effective rate 23%).
- A PM carrying a −$500k prior-year loss earns **0** until cumulative eligible recovers
  past $500k. An always-underwater PM earns **0** comp.

---

## 6. Netting risk  (`src/engine/attribution.py`)

When Pod A makes +100 and Pod B loses −100, **investors net 0** but the fund
**still owes A's payout**. Only finance can quantify this:

```
hypothetical_netted_comp = blended_payout * max(0, fund_cum_net
                              - Σ initial_HWM - Σ hurdle_amt_T)
netting_cost = max(0, total_comp - hypothetical_netted_comp)
```

`blended_payout` is the capital-weighted average payout ratio. The first term is
what the fund **actually owes** (sum of each winner's comp); the second is what
it **would owe** if the whole fund were a single netted book. The difference is
real dollars paid on profit the fund did not keep.

**Worked example** (`tests/test_attribution.py`): A = +100, B = −100, payout 0.2 →
`total_comp = 20` (only A), `fund_net = 0` → `hypothetical = 0` →
`netting_cost = 20`.

---

## 7. Investor economics & reconciliation  (`economics.py`, `recon.py`)

The fund-to-investor waterfall (all quantities over the simulated period):

```
fund_eligible        = Σ_pm eligible_pnl
fund_capital_charges = Σ_pm capital_charge               # collected from PM books, returned to investors
investor_net         = fund_eligible − mgmt_fee − base_comp − total_comp + fund_capital_charges
comp_expense_ratio   = total_comp / fund_eligible
```

> **Capital charge pass-through.** Capital charges are deducted from each PM's `eligible_pnl`
> (lowering the comp base), but flow into an investor pool — so they are added back to
> `investor_net`. The net effect is that investors earn the hurdle on their capital.
> `center_cost` is tracked separately for reporting and the R7 reconciliation check.

**Reconciliation tie-outs** (asserted in `tests/test_recon.py`, shown live in the
Controls panel):

| ID | Identity |
|----|----------|
| R1 | Fund trading PnL = Σ PM trading = Σ position gross (bottom-up MTM); fund non-trading = Σ eod_income; fund gross = trading + non-trading = Σ pod gross |
| R2 | `fund_net == Σ PM net == Σ Pod net` (after trading costs only) |
| R3 | `total_comp == Σ PM accrued_comp_T` |
| R4 | `investor_net == fund_eligible − mgmt_fee − base_comp − incentive_comp + capital_charges` |
| R5 | each `pod_net == Σ of its PMs' net` |
| R6 | `fund_net == Σ Team net` (the team taxonomy also ties out) |
| R7 | `Σ PM center_alloc == center_cost_total` (center pass-through balance) |

All-green means every figure on every page reconciles end-to-end and is safe to
show the CEO.

> **Two pod taxonomies.** PMs roll up two independent ways: by **strategy pod**
> (ECM, Quant, Macro, …) and by **team** (cross-strategy desks). Both partitions
> cover every PM exactly once, so the fund total ties out under either (R2/R5 for
> pods, R6 for teams). Pages with a *Strategy / Team* toggle use the same engine
> roll-up (`attribution.pnl_by_group`) keyed on `pod_id` or `team_id`.

---

## 8. Dynamic AUM  (`src/data_gen/generate.py`, `aum_history` table)

Fund AUM is not static. Each month-end, two forces change it:

1. **Performance-based reallocation (within-fund, zero-sum).** PMs are ranked by
   cumulative MTM return. The bottom `n` underperformers lose a random 5–12% of
   their AUM; that capital is redistributed to the top `n` outperformers. This
   models a fund that shifts capital toward its better books.

2. **Net investor flows (fund-level).** A random monthly net flow (subscriptions
   minus redemptions) scales linearly to the current fund total, drawn from a
   Normal distribution parameterised by `monthly_flow_mean_bps` and
   `monthly_flow_std_bps` in config. Positive flow goes to top performers;
   negative flow is absorbed by underperformers.

A **20% floor** (`floor_pct = 0.20 × initial_pm_aum`) prevents any PM from being
reduced to zero.

The resulting per-PM monthly snapshots are stored in the `aum_history` table
(`date, pm_id, pm_aum`). The loader forward-fills these to daily frequency so
every row in `pm_net_daily` has a `pm_aum` value. The cost engine uses this
time-varying `pm_aum` to compute `center` and `capital_charge` daily, making the
overhead deductions — and therefore `eligible_pnl` — dynamic rather than static.
The fund-level AUM curve is charted on the Home page.
