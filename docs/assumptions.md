# Model Assumptions & Rationale

This document explains every configurable parameter in `config/assumptions.yaml`,
the reasoning behind each choice, and guidance on how to change them safely.

All values feed the synthetic data generator (`src/data_gen/generate.py`) and the
calculation engine (`src/engine/`). Nothing economic is hardcoded in the engine —
changing a value here and rerunning `python run.py` is all that is needed.

---

## 1. Simulation Parameters

| Parameter | Value | Rationale |
|---|---|---|
| `seed` | `20240601` | Fixed random seed ensures fully reproducible outputs across runs. Change it to generate a different synthetic history while keeping the same structural properties. |
| `n_business_days` | `252` | One standard US trading year. Enough history to show drawdowns, HWM crystallisation, and tiered comp triggers without the dataset becoming unwieldy. |
| `n_instruments` | `50` | Sufficient for realistic cross-sectional dispersion and meaningful concentration metrics, while keeping data generation fast (~seconds). |
| `calendar_start` | `2025-01-02` | First business day of 2025 (Jan 1 is a holiday). The calendar runs forward `n_business_days` trading days from this date, so the dataset covers the full calendar year. |

---

## 2. Trading Cost Rates

All rates are **annual**; the engine divides by `dt = 1/252` to charge them daily on the prior day's exposure.

| Parameter | Value | Rationale |
|---|---|---|
| `financing_rate` | `3.0% p.a.` | Prime brokerage financing on gross notional (long + short). Reflects a mid-market institutional rate for a fund of this size. Typical range: 2–5% depending on asset class and credit terms. |
| `borrow_rate` | `1.5% p.a.` | Stock-borrow cost charged only on short notional. Blended across easy-to-borrow (≈0.5%) and harder-to-borrow names. Funds with larger short books or concentrated shorts may see 3–8% on specific names. |
| `commission_bps` | `1.5 bps` | Commission charged on traded notional (`|Δqty| × price`). Reflects electronic execution; full-service or less liquid names typically 3–10 bps. |
| `fx_rate` | `1.0% p.a.` | Annual FX conversion cost applied to positions in the `FX` asset class only. Covers bid-ask on currency forwards and basis risk. |

**Changing cost rates:** Raising `financing_rate` or `borrow_rate` will widen the Gross→Net gap and reduce eligible PnL and comp. This is the most direct way to stress-test how sensitive comp expense is to execution quality.

---

## 3. Non-Trading Income

One-off items (tax reclaims, fee rebates, legal settlements, corporate actions, interest true-ups) that are not mark-to-market trading PnL. They are stored in `eod_income` and flow into Gross PnL, so they reach the PM comp base (Eligible PnL) like any other book income.

| Parameter | Value | Rationale |
|---|---|---|
| `annual_events_per_pm` | `6` | Roughly one non-trading event every two months per PM — realistic for an active book with periodic corporate actions and fee reconciliations. |
| `amount_mean` | `$150,000` | Lognormal median event size. Reflects typical mid-size one-off items; the lognormal distribution allows occasional large events (e.g., a sizable tax reclaim). |
| `amount_sigma` | `0.8` | Lognormal shape parameter. A value of 0.8 produces meaningful size dispersion: most events are small, a few are large. |
| `negative_prob` | `15%` | Share of events that are charges rather than income (e.g., a legal settlement paid out, a fee true-up owed). Keeps the non-trading line broadly positive but not implausibly clean. |

---

## 4. Center Cost

Fund-level overhead (operations, technology, compliance, rent, back-office) that is not attributable to any single PM.

| Parameter | Value | Rationale |
|---|---|---|
| `bps_on_aum` | `35 bps (0.35% p.a.)` | Mid-range for a fund of ~$1.6B AUM. Smaller funds (<$500M) often run 50–80 bps; larger funds ($5B+) can run as low as 15–20 bps via economies of scale. The 35 bps figure is realistic for a ~10-PM operation with institutional infrastructure. |

Center cost accrues daily (`× dt`) and is deducted from Investor Net — it is never charged inside PM Net PnL, so it does not affect PM comp calculations.

---

## 5. Management Fee

The "2" in the classic "2 and 20" fee structure. Charged on AUM annually and accrued daily.

| Parameter | Value | Rationale |
|---|---|---|
| `bps_on_aum` | `200 bps (2.0% p.a.)` | The long-standing industry standard management fee rate. Some newer or smaller managers charge 1–1.5%; established multi-PM platforms have maintained 2%. Deducted from Investor Net (fund-level cost, not from PM eligible PnL). |

---

## 6. Incentive Compensation Tiers

Each PM has a contractual base `payout_ratio` (share of profit above HWM paid as comp). On top of that, a marginal tier ladder rewards outperformance:

| Tier | Profit Above HWM (this period) | Marginal Add-on |
|---|---|---|
| Tier 1 | $0 – $1,000,000 | Base rate only (+0 pp) |
| Tier 2 | $1,000,000 – $2,000,000 | Base rate + 3 pp |
| Tier 3 | Above $2,000,000 | Base rate + 6 pp |

**Rationale:** Tiered comp aligns PM incentives with fund profitability — a PM generating outsized alpha earns more per marginal dollar, creating a retention mechanism for top performers. The $1M / $2M tier thresholds are illustrative and sized relative to this synthetic fund's profit magnitudes. Raise them proportionally if you scale up the fund's AUM.

**Loss carryforward:** If a PM had a negative `prior_year_pnl`, that loss must be fully recovered before any comp accrues in the current year. This is standard HWM convention and prevents paying comp on "recovery" PnL that merely offsets prior losses.

---

## 7. Market Factor Model

Daily returns for each instrument follow a single-factor model:

```
r_{i,t} = β_i × f_t + ε_{i,t}

f_t   ~ N(μ_market × dt,  σ_market × √dt)   (shared market factor)
ε_{i,t} ~ N(α_i × dt,    idio_vol_i × √dt)   (idiosyncratic component)
```

| Parameter | Value | Rationale |
|---|---|---|
| `market.mu` | `6% p.a.` | Long-run US equity market real return. Used as the baseline drift for the shared factor. |
| `market.sigma` | `16% p.a.` | Approximately one standard deviation of annual US equity market returns over the past 30 years (historical range: 12–22%). Produces realistic day-to-day volatility at the fund level. |

The shared factor creates cross-instrument co-movement, which is what makes **netting risk** non-trivial: long and short positions partially cancel, reducing net notional and financing cost, but this benefit can mask individual PM underperformance.

---

## 8. Asset Class Parameters

Per-asset-class calibration of the factor model. Each instrument is assigned to one asset class; its beta, idiosyncratic vol, and alpha parameters are drawn from the class parameters below.

| Asset Class | Beta (β) | Idio Vol | Alpha Dispersion | Universe Weight | Rationale |
|---|---|---|---|---|---|
| Equity | 1.10 | 18% | 10% | 40% | High market sensitivity, meaningful idiosyncratic vol; largest universe share reflecting equity L/S dominance in a typical multi-PM fund. |
| Rates | 0.25 | 6% | 4% | 15% | Low equity beta (rates move on their own factors), low idio vol (liquid, efficient market), narrow alpha dispersion. |
| Credit | 0.55 | 9% | 6% | 15% | Moderate beta (credit spreads partially track equities), moderate idio vol (issuer-specific events). |
| Commodity | 0.70 | 24% | 12% | 15% | Moderate equity beta, high idio vol (supply shocks, weather, geopolitics), wide alpha dispersion (fundamental mis-pricings common). |
| FX | 0.35 | 10% | 5% | 15% | Lower equity beta, moderate vol; FX alpha is typically narrow and mean-reverting. |

---

## 9. Position Model

Controls how PM positions are sized and how strongly they track the skill signal.

| Parameter | Value | Rationale |
|---|---|---|
| `gross_leverage_min` | `1.8×` | Minimum gross leverage (gross notional / AUM). A fund running 1.8× has 90% long and 90% short (for example), a common lower bound for actively traded L/S books. |
| `gross_leverage_max` | `2.6×` | Maximum gross leverage. Multi-PM platforms typically cap individual PM books at 2.5–3× to control financing costs and drawdown risk. |
| `noise_scale` | `1.0` | Idiosyncratic positioning noise relative to the skill signal. A value of 1.0 means noise and signal are roughly equal in magnitude, producing realistic return dispersion — skilled PMs outperform on average but not every day. |

**PM `skill` parameter:** Each PM has a `skill` value that controls how well their target weights align with realized forward returns. `skill > 0` = net positive alpha (profitable after costs at sufficient magnitude); `skill ≈ 0` = noise-level returns (likely underwater after costs); `skill < 0` = anti-skilled (consistent losses). Negative-skill PMs are intentional — they demonstrate HWM loss carryforward mechanics and zero comp accrual.

---

## 10. Dynamic AUM Reallocation

Each month an investment committee reviews PM performance and adjusts capital. Fund-level AUM also drifts via net investor subscriptions and redemptions.

| Parameter | Value | Rationale |
|---|---|---|
| `monthly_flow_mean_bps` | `+50 bps/month` | Average net investor inflow of ~0.5%/month. Represents a fund in a modest growth phase; change to negative to model redemption pressure. |
| `monthly_flow_std_bps` | `150 bps` | Month-to-month flow volatility (±~1.5%); captures the lumpiness of institutional subscriptions and redemptions. |
| `reallocation_range` | `5–12%` | Fraction of a PM's AUM moved per reallocation event. Keeps reallocation meaningful but not abrupt (a 10% cut on a $200M book = $20M shift). |
| `n_reallocated` | `3` | Number of top + bottom PMs whose capital is adjusted each month (e.g., top 3 gain AUM, bottom 3 lose AUM). |

---

## 11. PM Roster

11 portfolio managers across 5 pods. All names are anonymized to three-letter codes.

| PM | Pod | AUM | Payout | Hurdle | Skill | Prior-Year Loss | Base Salary | Design Intent |
|---|---|---|---|---|---|---|---|---|
| AAA | Equity L/S | $200M | 18% | 1% | 2.0 | $0 | $750k | Strong performer; demonstrates tiered comp ladder triggering |
| BBB | Equity L/S | $160M | 16% | 1% | 0.9 | $0 | $500k | Marginal performer; may or may not cover costs in a given year |
| CCC | Equity L/S | $120M | 20% | 2% | –0.4 | –$1M | $350k | Underwater PM; shows loss carryforward + zero comp accrual |
| DDD | Quant | $200M | 15% | 1% | 1.8 | $0 | $700k | Strong quant; lower payout reflecting systematic strategy margins |
| EEE | Quant | $180M | 17% | 1% | 0.1 | –$800k | $400k | Near-zero skill + prior loss; demonstrates extended recovery period |
| FFF | Macro | $160M | 18% | 2% | 1.2 | $0 | $600k | Solid macro PM; higher hurdle reflects discretionary strategy premium |
| GGG | Macro | $140M | 19% | 2% | –0.6 | –$1M | $350k | Struggling macro; shows full loss carryforward mechanics |
| HHH | Credit | $140M | 16% | 1% | 1.5 | $0 | $650k | Consistent credit PM; demonstrates credit asset-class attribution |
| III | Credit | $110M | 17% | 1% | 0.6 | –$1.5M | $450k | Moderate skill + largest prior loss; slowest comp recovery |
| JJJ | Event | $120M | 20% | 2% | 1.6 | $0 | $800k | Top event-driven PM; highest payout + highest base salary |
| KKK | Event | $100M | 18% | 2% | 0.3 | $0 | $400k | Borderline event PM; illustrates marginal profitability |

**Rationale for payout ratio range (15–20%):** Industry range for PM-level incentive comp at a multi-PM platform is typically 15–25% of eligible PnL, with higher rates for discretionary PMs in niche strategies (event, macro) and lower rates for systematic strategies where the infrastructure investment is significant. The 20% ceiling here avoids the 20% "carry-style" headline number while still producing visible comp expense.

**Rationale for hurdle rates (1–2%):** Low hurdles by design — the capital charge (which already deducts a hurdle-equivalent amount from eligible PnL daily) effectively embeds a performance threshold. The per-PM `hurdle_rate` here is a secondary display parameter only; double-counting is avoided in the engine.

---

## Changing Assumptions Safely

1. Edit `config/assumptions.yaml`.
2. Run `python run.py` — this regenerates the database, recomputes the engine, prints the reconciliation table, and runs all 59 tests.
3. If `run.py` exits 0, the numbers are internally consistent. If a reconciliation check fails (red FAIL), the changed parameters violated an accounting identity — review the change.
4. Refresh the dashboard: press **R** in the browser or use the app menu → *Rerun*.

**Parameters that are safe to change freely:** `seed`, `n_business_days`, cost rates, non-trading income parameters, center cost, management fee, comp tier thresholds, market mu/sigma, AUM dynamics.

**Parameters that require care:** PM `allocated_capital` values must sum to the pod's `allocated_capital`. If you add or remove PMs, ensure the pod total is preserved — otherwise reconciliation check R2 (Pod = ΣPM) will fail.
