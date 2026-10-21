# MBIE / Sense Partners: alternative future electricity price paths - implications for the SFD2201 CAES model

Source: [Sense Partners and Phylleos, *Economic and industry impacts of alternative future electricity price paths: A GSM-NZ dynamic CGE analysis*, final report to MBIE, 6 August 2025](https://www.mbie.govt.nz/dmsdocument/31690-sense-partners-economic-and-industry-impacts-of-alternative-future-electricity-price-paths). The [MBIE review-of-electricity-market-performance page](https://www.mbie.govt.nz/building-and-energy/energy-and-natural-resources/energy-consultations-and-reviews/review-of-electricity-market-performance/review-of-electricity-market-performance-and-release-of-the-governments-energy-package) provides the publication context.

## Executive conclusion

This is a useful report for setting **plausible economy-wide wholesale price-level scenarios for 2026-2030** and for framing why firm, affordable electricity matters to industrial customers. It is not a forecast, a nodal price study, an electricity-market dispatch model, or evidence of a storage capacity payment.

For the SFD2201 CAES model, its strongest message is that the historic 2024-25 operating year should not be extrapolated unchanged for 40 years. A future case should separately specify:

1. the annual wholesale price level;
2. the half-hourly and seasonal price shape, including charge/discharge spreads;
3. SFD2201's basis relative to any national or hub reference price;
4. reserve prices and reserve deliverability; and
5. any bilateral firming, hedge, or capacity contract.

The Sense Partners scenarios inform only the first item. A higher average price is not automatically better for CAES. If all prices rise by the same amount while the timing of prices is unchanged, a round-trip-loss storage asset can have *lower* energy-arbitrage margin because it buys more MWh than it sells. The report gives no basis for assuming that its high-price case also contains larger intraday spreads or more reserve revenue.

## What the report does

Sense Partners uses GSM-NZ, a dynamic computable general equilibrium (CGE) model with 79 industries. It projects a business-as-usual economy to 2040, imposes alternative electricity-price paths for 2026-2030, and examines the resulting economy-wide and industry impacts. Prices after 2030 are endogenous to the CGE model.

The purpose is macroeconomic and industrial-impact analysis. It asks how the wider economy changes if electricity prices are lower or higher than the selected baseline. It is deliberately not a study of a particular policy, power-station build, fuel supply solution, transmission constraint, or market design.

For its alternative cases, the model changes an all-input productivity variable across eight generation industries (hydro, geothermal, wind, solar, coal, gas, oil and biomass). The authors state that this is a way to deliver the selected price paths without making assumptions about generation cost structures or the cause of the change. That design is suitable for the report's macroeconomic purpose, but it means the scenarios do not describe hourly scarcity, dispatch, regional congestion, hydro conditions, reserve procurement, or the operational value of storage.

## Electricity price paths used in the report

All values below are real NZD per MWh in the report's price basis.

| Scenario | 2026-2030 price description | How it is constructed / interpreted | Relevance to CAES |
|---|---:|---|---|
| Baseline | Declines from about $220/MWh in 2025 to about $175/MWh in 2030 | Based on the average settlement prices over the year to Q4 2025 for futures expiring 12, 18, 24 and 30 months ahead, with the 12-to-24-month decline extrapolated | A useful reference for an aggregate price-level path, but not a SFD2201 forward curve. |
| Low | Averages $133/MWh over 2026-2030 | Draws on a cited Jarden analysis, generation investment in the pipeline, and an assumed long-run generation cost of about $105/MWh | A lower price-level stress case. It does not say what happens to charging versus discharging spreads. |
| High | Averages $250/MWh over 2026-2030, about 30% above baseline in every year | Intended to represent worsening capacity constraints and fuel shortages | A scarcity/affordability stress case, not evidence that a CAES asset earns $250/MWh when discharging. |

The report explicitly says that the baseline and alternative paths are **not forecasts** and do not analyse particular policy or regulatory settings. The annual values should therefore be used as transparent scenario anchors, not as a market forecast to put directly into an investment model.

## Principal macroeconomic findings

The report's headline results are material and are useful context for an offtaker or policy discussion:

| Result | Low-price scenario | High-price scenario |
|---|---:|---:|
| Real GDP effect in 2030 versus baseline | +$10.3bn (+1.8%) | -$3.2bn (-0.7%) |
| Real GDP effect in 2040 versus baseline | +$5.1bn (+0.8%) | -$2.3bn (-0.5%) |
| Main transmission mechanism | Improved profitability, investment, employment and export competitiveness | Lower profitability and investment, then lower employment, wages and household spending |
| Most price-sensitive industries | Primary metals, pulp and paper, chemicals, and non-metallic minerals benefit most | The same sectors are most adversely affected |

The report also runs illustrative sensitivity tests. A one-off +/-2% price change in 2025 is estimated to change real GDP in 2035 by roughly +/-$0.33bn (about 0.06%). A recurring +/-2% annual change in the price path has much larger effects: about +$3.76bn (+0.57%) / -$3.88bn (-0.59%) in 2035, and +$15.55bn (+1.44%) / -$13.55bn (-1.32%) in 2050.

Those figures are conditional on GSM-NZ's structure and behavioural assumptions; the authors are clear that they are not econometrically estimated elasticities. They should not be used as an NPV sensitivity, a demand forecast, or a storage-revenue multiplier.

## What the report can firm up for this project

### 1. The model needs a forward price-level range

The current CAES screening model dispatches against a single historic year at SFD2201 (December 2024 to November 2025) and extrapolates annual operating cash flow through the project life. That remains a useful historical operating benchmark, but not a complete long-run merchant case.

This report provides a defensible reason to show a price-level range around a forward central case rather than a single historic outcome. The range should be labelled as a **macro scenario range**, not as a CAES revenue forecast:

- lower price-level case: report low scenario (five-year average $133/MWh real);
- forward-informed central case: a documented SFD2201 forward/basis case, with the report's baseline trajectory as a reasonableness check; and
- high price-level case: report high scenario (five-year average $250/MWh real).

The report only defines the 2026-2030 period. It does not support assuming $133, $175, or $250/MWh indefinitely for a 40-year asset life. The existing annualisation and margin-fade approach needs either an explicit post-2030 long-run case or a separate terminal-value convention.

### 2. Price affordability is commercially relevant to firming products

The report's macro results support the proposition that large electricity users may value price stability and dependable supply. Electricity-intensive exporters are particularly exposed to high energy costs and limited ability to substitute away from electricity. This is useful context for testing a bilateral renewable-firming, shaped-energy, or availability product for CAES.

It does **not** establish the price, term, volume, credit quality, or dispatch obligation of such a contract. The current illustrative break-even calibration for the 50 MW / 2-hour central CAES case (about $7.9m/year, or $158k/MW-year, of non-fading incremental firming value) remains a question for a specific counterparty and contract design, not a conclusion from this report.

### 3. Real-dollar consistency matters

The report's price paths are real. The CAES finance configuration is also explicitly a pre-tax, ungeared, real-NZD screening model with an 8% real discount rate. Any use of the report in the model should therefore:

1. identify the report's real-dollar base year and the price basis of the historic SFD2201 data;
2. deflate or inflate all energy, reserve, capex and operating-cost series to one common real-dollar basis; and
3. keep the discount rate real only after the cash flows are real.

Mixing real 2026 CAES cost assumptions with nominal historic spot prices would give a misleading NPV even if the optimiser is operating correctly.

## What the report cannot support

| Missing element | Why it matters to the CAES model | Appropriate source or modelling treatment |
|---|---|---|
| Half-hourly price shape and volatility | CAES earns from the difference between charging and discharge intervals, not the annual average price alone | Preserve/scenario-test historic SFD2201 shapes; use forward shaped products or a market model if available. |
| SFD2201 basis | The report is an aggregate national wholesale price exercise, not a Stratford-node price forecast | Calculate historic SFD2201 basis against the selected reference node and apply a separate basis distribution. |
| Reserve prices, volumes and availability | FIR/SIR are a material illustrative stacked revenue stream in the model | Use Electricity Authority / System Operator reserve data, with independent price and availability cases. |
| Capacity or firming-payment value | The report quantifies no payment for dependable MW or stored MWh | Model a named bilateral product with eligibility, availability, non-delivery, opportunity cost and counterparty terms. |
| Storage competition and price cannibalisation | Future batteries, flexible demand and CAES can compress spreads | Apply explicit spread-compression and reserve-price/volume haircuts. |
| Project finance conditions | A macro price scenario does not set debt terms, WACC, contractability or construction risk | Maintain separate merchant and contracted discount-rate cases, supported by a financing case. |

## Why average wholesale price is not CAES arbitrage revenue

For a simplified cycle that delivers one MWh and has round-trip efficiency `eta`, the energy-only gross margin is approximately:

```text
margin per MWh discharged = discharge price - (charge price / eta) - variable O&M
```

If every charging and discharge price rises by the same amount `dP`, while their timing and spread do not change, the change in margin is:

```text
change in margin per MWh discharged = dP x (1 - 1 / eta)
```

Because `eta` is below one, this is negative. The 50 MW / 2-hour A-CAES configuration has charge and discharge efficiencies of about 81.24% each, implying about 66% round-trip efficiency. Holding the operating pattern fixed, a uniform price-level increase raises the cost of the charging MWh more than the revenue from the discharged MWh.

This is a deliberately simplified illustration. In reality, the optimiser may change its operating hours; high-price conditions may coincide with wider scarcity spreads; and reserve or contract income may change. The crucial point is that none of those effects follows from an annual average price path. They must be modelled explicitly and independently.

## Recommended scenario architecture

Use the Sense Partners study as one layer of a future-market case, rather than replacing the historic half-hourly price series with a single average.

```text
future SFD2201 price series
    = annual wholesale price level
    + SFD2201 local basis
    + seasonal / time-of-day shape
    + scarcity and volatility component
```

The components should be reported separately. A practical configuration could look like this:

```yaml
future_market_case:
  enabled: false
  currency_basis: real_nzd_2026
  source: MBIE Sense Partners 2025 - price-level scenario only
  price_level_case: baseline # low | baseline | high
  period_start: 2026
  period_end: 2030

  annual_wholesale_target:
    method: documented_external_curve_or_report_path
    # Transcribe an auditable annual path before enabling.
    # Report anchors: low average = 133; high average = 250 NZD/MWh real.

  sfd2201_basis:
    method: historic_monthly_distribution
    reference_node: null

  intraday_shape:
    source_year: 2024-12_to_2025-11
    method: preserve_historic_profile
    spread_multiplier: 1.0
    scarcity_event_multiplier: 1.0

  reserve_market:
    method: separate_historic_or_forward_case
    price_multiplier: 1.0
    availability_multiplier: 1.0
```

The `annual_wholesale_target` must be in the same real-dollar basis as the finance model. Do not infer annual values from the report chart by eye for a final model input; record their source and transformation in the run metadata.

### A conservative first set of runs

Run each price level with at least three independent shape cases:

| Price level | Spread / volatility case | Interpretation |
|---|---|---|
| Low | Historic shape | Lower energy price level, with historic timing retained only as a mechanical benchmark |
| Low | Compressed spread | New generation and flexible supply reduce both price level and arbitrage opportunity |
| Baseline | Historic shape | Current back-test transformed to a documented forward level and SFD basis |
| High | Historic shape | Higher level only; shows the pure efficiency effect without assuming extra scarcity value |
| High | Expanded scarcity spread | A separate, explicitly optimistic case in which constraints create wider charge/discharge spreads |

For every case, hold reserve prices constant initially. Then test reserve price and availability separately. Combining higher energy prices, wider spreads, higher reserve prices and a capacity payment in one unlabelled case would obscure the driver of NPV and risk double counting scarcity value.

## Contracted firming: how this report informs, but does not price, the case

The report strengthens the qualitative reason to investigate a contract with an electricity-intensive customer: sustained high prices can impair profitability, investment and competitiveness. A CAES facility may have value if it transforms intermittent renewable output into a defined delivery profile or reduces a customer's exposure to specified high-price periods.

The correct next analytical question is not "what capacity payment does the report imply?" It is:

> What verified portfolio-cost reduction does a creditworthy counterparty receive from 50 MW, 100 MWh of CAES at SFD2201 under a stated delivery and non-delivery regime?

Model that as a separate product with all of the following visible:

- contracted MW, MWh, eligible months and delivery windows;
- whether the product is energy, availability, a CFD, a reliability option, or a renewable PPA firming sleeve;
- charge-energy procurement and local basis exposure;
- state-of-charge reservation and the merchant margin sacrificed to meet the obligation;
- availability target, testing, outage allowance and non-delivery penalties;
- counterparty, collateral, term and annual escalation; and
- any reduction in the discount rate justified by the signed contract, separate from merchant cash flow.

The NPV gap calculation can remain a useful output: it tells us the net annual contract value required after opportunity cost and penalties. It must not be treated as a market quote.

## Prioritised next steps for the model

1. **Create a real-price normalisation check.** Document the dollar date of historic SFD2201 prices, CAES capital costs, operating costs and reserve prices. Convert all to a common real NZD basis before altering long-run assumptions.

2. **Add an explicit future-price transformation module.** Begin with a historical SFD2201 half-hourly profile, apply an auditable annual target and historic basis treatment, then report the resulting annual average, peak/off-peak spreads, negative-price hours and CAES revenue.

3. **Separate price level from shape.** Apply the report's low/baseline/high levels, then independently vary intraday and seasonal spread multipliers. This is the key sensitivity for a 66%-round-trip-efficiency CAES system.

4. **Retain a historic merchant benchmark.** Continue to show the unmodified December 2024-November 2025 case beside all forward cases. It is evidence of what the optimiser could have earned in that year, not a forecast.

5. **Add a contracted-firming overlay only after defining the product.** Test its net incremental value against the existing break-even requirement, rather than inserting a generic capacity payment.

6. **Report revenue bridges.** For each scenario, plot or tabulate energy-arbitrage revenue, charging energy cost, FIR revenue, SIR revenue, variable O&M, fixed O&M, contract settlement/availability revenue and capital cost separately. That will make clear whether a positive result is driven by merchant spreads, reserves, or contracted value.

## Bottom line

The report is strong evidence that the project should be assessed across more than one long-run electricity-price environment and that firming could have commercial relevance to electricity-intensive customers. It does not justify changing the CAES revenue forecast by a fixed percentage, assuming a high annual price translates to high arbitrage margin, or adding a generic capacity payment.

For this model, use it to define **price-level bounds and a future-period discipline**. Continue to derive actual CAES value from node-specific half-hourly spreads, reserve rules, efficiency, degradation/availability, and explicitly modelled contracts.
