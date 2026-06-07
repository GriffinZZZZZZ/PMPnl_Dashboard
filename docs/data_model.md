# Data Model

All tables are generated deterministically (fixed seed) by
`src/data_gen/generate.py` and written to `data/pm_pnl.db` (SQLite). PnL and costs are
**derived in the engine**, never stored, so the raw data stays auditable.

## Entity relationships

```
Fund
 └─ strategy_pods      (strategy bucket: Equity L/S, Quant, Macro, Credit, Event)
     └─ portfolio_managers  (1–3 PMs per pod, each with its own payout terms)
         └─ eod_positions   (daily quantity per instrument; long & short)

security_master ──< eod_prices     (one daily price series per instrument)
portfolio_managers, security_master ──< eod_positions   (daily quantity per PM × instrument)
portfolio_managers ──< eod_income  (sparse non-trading income events per PM)
portfolio_managers ──< aum_history (monthly PM AUM snapshots; ffilled to daily by the loader)
```

Join keys:
`strategy_pods.pod_id → portfolio_managers.pod_id`,
`portfolio_managers.pm_id → eod_positions.pm_id`,
`security_master.ticker → eod_prices.ticker` and `→ eod_positions.ticker`,
`portfolio_managers.pm_id → eod_income.pm_id`,
`portfolio_managers.pm_id → aum_history.pm_id`.

## Tables

### `strategy_pods`
| field | type | description |
|-------|------|-------------|
| `pod_id` | str | primary key (e.g. `POD_ECM`) |
| `pod_name` | str | display name (e.g. "Equity L/S") |
| `strategy_type` | str | strategy description (e.g. "Equity Long-Short") |
| `pod_aum` | float | USD capital allocated to the pod (= Σ its PMs' `pm_aum`) |

### `portfolio_managers`
| field | type | description |
|-------|------|-------------|
| `pm_id` | str | primary key (e.g. `PM_ECM_1`) |
| `pod_id` | str | foreign key → `strategy_pods.pod_id` |
| `team_id` | str | second taxonomy FK → teams config (e.g. `TEAM_ALPHA`) |
| `pm_name` | str | PM display name (anonymized to codes) |
| `pm_aum` | float | initial USD capital for this PM |
| `payout_ratio` | float | contractual base share of profit above HWM paid to the PM |
| `hurdle_rate` | float | annual return threshold on capital; capital charge = `hurdle_rate × pm_aum × dt` |
| `initial_hwm` | float | starting high-water mark on cumulative eligible PnL (USD) |
| `base_salary` | float | fixed annual cash compensation (USD/yr); accrues daily, deducted from Investor Net |
| `skill` | float | alignment of positions with realized returns (see methodology §2) |
| `loss_carryforward` | float | `max(0, −prior_year_pnl)`; PM must earn this back before comp accrues |

Note: `prior_year_pnl` is consumed to derive `loss_carryforward` at generation time and is not stored.

### `security_master`
| field | type | description |
|-------|------|-------------|
| `ticker` | str | primary key (e.g. `EQU001`) |
| `asset_class` | str | Equity / Rates / Credit / Commodity / FX |
| `sector` | str | sub-classification (e.g. "Tech", "IG") |
| `strategy_tag` | str | `asset_class-sector` attribution tag |
| `beta` | float | sensitivity to the shared market factor |
| `alpha` | float | idiosyncratic annual drift |
| `idiosyncratic_vol` | float | idiosyncratic annual volatility |

### `eod_prices`  (long format)
| field | type | description |
|-------|------|-------------|
| `date` | datetime | business day |
| `ticker` | str | foreign key → `security_master.ticker` |
| `close_price` | float | simulated end-of-day price |

### `eod_positions`  (long format)
| field | type | description |
|-------|------|-------------|
| `date` | datetime | business day |
| `pm_id` | str | foreign key → `portfolio_managers.pm_id` |
| `ticker` | str | foreign key → `security_master.ticker` |
| `quantity` | float | signed units held (negative = short) |

### `eod_income`  (long format, sparse)
| field | type | description |
|-------|------|-------------|
| `date` | datetime | business day the item is booked |
| `pm_id` | str | foreign key → `portfolio_managers.pm_id` |
| `category` | str | item type: Tax Reclaim / Fee Rebate / Legal Settlement / Corporate Action / Interest True-up |
| `amount` | float | USD amount (positive = income, negative = charge) |

Most days have no row for a given PM; the engine aggregates these into `non_trading_pnl` which rolls into `gross_pnl`.

### `aum_history`  (monthly snapshots)
| field | type | description |
|-------|------|-------------|
| `date` | datetime | snapshot date (first business day of simulation + each business month-end) |
| `pm_id` | str | foreign key → `portfolio_managers.pm_id` |
| `pm_aum` | float | USD capital allocated to this PM at the snapshot date |

The loader forward-fills these monthly snapshots to daily frequency. The cost engine uses the resulting time-varying `pm_aum` to compute `center` and `capital_charge` each day (see methodology §4 and §8).

## Scale (default config)
~5 pods · ~11 PMs · 50 instruments · 252 business days · ~13 AUM snapshots per PM
→ ~12.6k price rows · ~138k position rows · ~66 income events · ~143 AUM history rows.
