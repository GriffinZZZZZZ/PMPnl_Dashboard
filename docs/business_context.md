# Business Context — why a multi-Pod fund's finance team needs this

## The setup

A **multi-Pod (multi-manager / "platform") hedge fund** allocates capital to many
semi-autonomous portfolio managers (PMs), grouped into pods by strategy. Each PM
runs their own book and is paid a contractual **share of the profit they generate**
(a payout ratio), subject to a high-water mark and sometimes a hurdle.

This payout structure is **asymmetric**: the fund pays the PM for gains, but the
fund — not the PM — absorbs the losses. That asymmetry, multiplied across a dozen
PMs whose results partly cancel, is the central economic problem this dashboard
exists to manage.

## Why FINANCE owns this (not the PMs, not the CIO)

The finance team owns the **fund-company's own P&L and balance sheet**. On that
P&L, **PM compensation is the largest and most volatile line item**. Finance must
therefore be able to:

1. **Accrue comp as a liability (GAAP).** Comp is not a year-end calculation; it
   is a liability that grows daily with PnL and must be booked as it accrues.
2. **Own the Gross → Net bridge.** Financing, borrow/short fees, commissions, and
   center-cost allocation turn a PM's headline (gross) number into the fund's
   real (net) number. PM payout is paid on **net**, so every cost line is real
   dollars out the door.
3. **Quantify netting risk.** When Pod A makes +100 and Pod B loses −100,
   investors net 0, but the fund may still owe Pod A's payout. Only finance —
   looking across all pods at once — can compute this exposure.
4. **Report investor net economics.** What LPs actually keep after all costs and
   comp is a finance number, not a trading number.
5. **Run decision-support what-ifs.** Before a board meeting, finance must be
   able to answer "what happens to investor net if we cut payout ratios 5pp?" or
   "what does netting risk look like if we add a new macro PM?" — live, not days
   later after rebuilding the spreadsheet.
6. **Exercise independent control.** Finance independently marks and costs what
   PMs claim, and proves it reconciles.

## The manual process this replaces

Historically this is a **manual month-end reconciliation**: a finance analyst
pulls prime-broker statements, exports OMS positions, and maintains comp
spreadsheets, then hand-stitches them together. It is slow (days), error-prone
(broken spreadsheet links, stale marks), and impossible to audit or re-run with
different assumptions.

## Before → after (the finance-automation-engineer value)

| | Manual process | This system |
|---|---|---|
| **Time** | ~2–3 days of stitching per month-end | seconds (`python run.py`) |
| **Reproducibility** | one-off spreadsheets, hard to re-run | deterministic, fixed-seed, one command |
| **Correctness** | trust the analyst's formulas | unit-tested vs hand-computed cases |
| **Auditability** | manual spot-checks | live reconciliation tie-outs (all-green or red) |
| **What-ifs** | rebuild the spreadsheet | move a slider / edit one config value |
| **Assumptions** | buried in cells | one `config/assumptions.yaml` |

The point is not a prettier chart — an analyst can make charts. The point is that
a **finance automation engineer** turns a slow, error-prone, manually-stitched
process into a fast, reproducible, auditable, unit-tested system that finance can
trust to compute real money.
