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

## 4. Gross → Net bridge — trading costs  (`src/engine/costs.py`)

Config rates are **annual**; charged daily on the **prior day's** exposure via `dt`:

```
financing_{pm,t}  = financing_rate * gross_exposure_{pm,t-1} * dt
borrow_{pm,t}     = borrow_rate    * short_notional_{pm,t-1} * dt
commission_{pm,t} = (commission_bps / 1e4) * traded_notional_{pm,t}
pm_net_{pm,t}     = pm_gross_{pm,t} - financing - borrow - commission
```

> **Center cost is NOT in `pm_net`.** Center cost is a *fund overhead*, deducted
> once at the fund level (Section 5). PM compensation is paid on `pm_net`, so a
> PM is never charged for overhead they do not control. This is the key modeling
> decision that keeps the reconciliation identities exact.

**Worked example.** Gross 100; gross exposure 1000; short notional 500; traded 200;
`financing_rate=0.252`, `borrow_rate=0.504`, `commission_bps=10`:
`financing = 0.252/252×1000 = 1.0`, `borrow = 0.504/252×500 = 1.0`,
`commission = 0.001×200 = 0.2` → `pm_net = 100 − 2.2 = 97.8`. (`tests/test_costs.py`.)

---

## 5. Compensation — high-water-mark crystallization  (`src/engine/payoff.py`)

Per PM, on cumulative net PnL, with a running high-water mark and **no clawback**.
Two structural features sit on top of the base rate:

- **Loss carryforward.** A negative `prior_year_pnl` becomes
  `loss_carryforward = max(0, −prior_year_pnl)` that must be earned back this year
  before any comp accrues (it raises the threshold).
- **Tiered (structural) payout.** The contractual `payout_ratio` is the *base*
  rate; a `comp_tiers` ladder adds marginal percentage points on higher bands of
  eligible profit (e.g. +3pp on $1M–$2M, +6pp above $2M).

```
cum_net_{pm,t}      = Σ_{s≤t} pm_net_{pm,s}
peak_{pm,t}         = max(initial_HWM, max_{s≤t} cum_net)          # ratcheting HWM
hurdle_amt_{pm,t}   = hurdle_rate * allocated_capital * (t * dt)   # time-scaled, small/0
profit_above_{pm,t} = max(0, peak - initial_HWM - hurdle_amt - loss_carryforward)
accrued_comp_{pm,t} = tiered(profit_above; base = payout_ratio, comp_tiers)
                    = Σ_tiers (base + add_pp) * (profit_above slice in that tier)
daily_comp_{pm,t}   = accrued_comp_t - accrued_comp_{t-1}   ( ≥ 0 )
total_comp          = Σ_pm accrued_comp_{pm,T}
effective_rate_pm   = total_comp_pm / profit_above_pm        # base ≤ effective ≤ base+top add_pp
```

`accrued_comp` is wrapped in a running max so it is **monotonically
non-decreasing** ("crystallized") — once comp is earned at a peak it does not
reverse. This models comp as a **GAAP liability that grows daily with PnL**, not
a year-end surprise.

**Worked examples** (`tests/test_payoff.py`):
- Net `[50, 50, −30]`, base 0.2, no hurdle/tiers → cum `[50,100,70]`, peak `[50,100,100]`,
  accrued `[10, 20, 20]` — day 3 stays at 20 (no clawback).
- Profit above HWM of $3M with base 0.2 and the ladder above → comp
  `0.20×1M + 0.23×1M + 0.26×1M = 690,000` (effective rate 23%).
- A PM carrying a −$500k prior-year loss earns **0** until cumulative net recovers
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

```
fund_net_pnl       = Σ_pm pm_net
center_cost_annual = center_cost_bps / 1e4 * AUM
center_cost_total  = center_cost_annual * (n_business_days * dt)   # accrued over period
investor_net       = fund_net_pnl - total_comp - center_cost_total
comp_expense_ratio = total_comp / fund_net_pnl
```

**Reconciliation tie-outs** (asserted in `tests/test_recon.py`, shown live in the
Controls panel):

| ID | Identity |
|----|----------|
| R1 | `fund_gross == Σ PM gross == Σ Pod gross` |
| R2 | `fund_net == Σ PM net == Σ Pod net` |
| R3 | `total_comp == Σ PM accrued_comp_T` |
| R4 | `investor_net == fund_net − total_comp − center_cost_total` |
| R5 | each `pod_net == Σ of its PMs' net` |
| R6 | `fund_net == Σ Team net` (the second, team taxonomy also ties out) |

All-green means every figure on every page reconciles end-to-end and is safe to
show the CEO.

> **Two pod taxonomies.** PMs roll up two independent ways: by **strategy pod**
> (ECM, Quant, Macro, …) and by **team** (cross-strategy desks). Both partitions
> cover every PM exactly once, so the fund total ties out under either (R2/R5 for
> pods, R6 for teams). Pages with a *Strategy / Team* toggle use the same engine
> roll-up (`attribution.pnl_by_group`) keyed on `pod_id` or `team_id`.
