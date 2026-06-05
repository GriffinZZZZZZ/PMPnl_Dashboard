# Data Model

All tables are generated deterministically (fixed seed) by
`src/data_gen/generate.py` and written to `data/*.parquet`. PnL and costs are
**derived in the engine**, never stored, so the raw data stays auditable.

## Entity relationships

```
Fund
 └─ Pod            (strategy bucket: Equity L/S, Quant, Macro, Credit, Event)
     └─ PM         (1–3 PMs per pod, each runs a sub-book with its own payout terms)
         └─ Positions   (daily quantity per instrument; long & short)

Instrument ──< Prices    (one daily price series per instrument)
PM, Instrument ──< Positions   (one daily quantity series per PM × instrument)
```

Join keys: `pods.pod_id → pms.pod_id`, `pms.pm_id → positions.pm_id`,
`instruments.ticker → prices.ticker` and `→ positions.ticker`.

## Tables

### `pods.parquet`
| field | type | description |
|-------|------|-------------|
| `pod_id` | str | primary key (e.g. `POD_ECM`) |
| `name` | str | display name (e.g. "Equity L/S") |
| `strategy_type` | str | strategy description |
| `allocated_capital` | float | USD capital allocated to the pod |

### `pms.parquet`
| field | type | description |
|-------|------|-------------|
| `pm_id` | str | primary key (e.g. `PM_ECM_1`) |
| `pod_id` | str | foreign key → `pods.pod_id` |
| `name` | str | PM display name |
| `allocated_capital` | float | USD capital for this PM (pod = Σ its PMs) |
| `payout_ratio` | float | share of profit above HWM+hurdle paid to the PM |
| `hurdle_rate` | float | annual return threshold on capital (time-scaled in the engine) |
| `initial_HWM` | float | starting high-water mark on cumulative net PnL (USD) |
| `skill` | float | alignment of positions with realized returns (see methodology §2) |

### `instruments.parquet`
| field | type | description |
|-------|------|-------------|
| `ticker` | str | primary key |
| `asset_class` | str | Equity / Rates / Credit / Commodity / FX |
| `sector` | str | sub-classification |
| `strategy_tag` | str | `asset_class-sector` attribution tag |
| `beta` | float | sensitivity to the shared market factor |
| `alpha` | float | idiosyncratic annual drift |
| `idio_vol` | float | idiosyncratic annual volatility |

### `prices.parquet`  (long format)
| field | type | description |
|-------|------|-------------|
| `date` | datetime | business day |
| `ticker` | str | foreign key → `instruments.ticker` |
| `price` | float | simulated close price |

### `positions.parquet`  (long format)
| field | type | description |
|-------|------|-------------|
| `date` | datetime | business day |
| `pm_id` | str | foreign key → `pms.pm_id` |
| `ticker` | str | foreign key → `instruments.ticker` |
| `qty` | float | signed units held (negative = short) |

## Scale (default config)
~5 pods · ~11 PMs · 50 instruments · 252 business days
→ ~12.6k price rows, ~33k position rows.
