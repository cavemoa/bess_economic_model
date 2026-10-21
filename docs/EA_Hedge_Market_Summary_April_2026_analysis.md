# Hedge-market implications for the SFD2201 CAES model

Source: [Electricity Authority, *Hedge market summary – April 2026* (11 May 2026)](https://www.ea.govt.nz/documents/9907/Hedge_market_summary_-_April_2026.pdf).

## Purpose and interpretation

The report is useful for improving the model's treatment of **forward energy prices, peak shaping and hedgeability**. It is not evidence for an additional standalone CAES capacity payment. In particular, the report covers ASX futures and over-the-counter (OTC) electricity hedges; it does not publish a market price for dependable MW, storage capacity, reserve availability or long-duration firming.

The present model is a historic, perfect-foresight merchant dispatch at SFD2201. That is a useful operating back-test, but it is not a 40-year forward-price forecast or a contracted-revenue case. The hedge report helps define those cases more rigorously.

The report itself notes that it uses hedge-disclosure data which the Authority has not independently reviewed for accuracy. It should therefore be used as a transparent market indicator and scenario input, not as a bankable price forecast.

## Key findings from the report

| Finding | What the report says | Modelling implication |
|---|---|---|
| Forward energy-price level fell in April | June 2026 ASX baseload futures declined by $75/MWh at Ōtāhuhu and $72/MWh at Benmore; September contracts declined by about $50/MWh. Higher hydro and thermal storage were cited as likely contributors. | Do not use one high-price historic year as the sole future energy-price case. Add a lower forward-price case. |
| Future prices were expected to decline over the next three years | The report attributes this to prospective new generation, with Huntly firming options also cited as a contributor to lower long-dated winter prices. | Test merchant CAES under lower seasonal price levels and, separately, under compressed spreads. Lower average price does not automatically imply lower storage value, so both drivers must be varied. |
| Peak-shaped power has a premium | In the final April standardised super-peak session, price premiums over ASX baseload were 32% at Ōtāhuhu and 22% at Benmore. OTC monthly/quarterly super-peak CFDs averaged 40% premium in the North Island and 24% in the South Island. | A super-peak hedge is a plausible portfolio product to test. The premium is a hedge-price shape, not extra merchant revenue to add to spot arbitrage. |
| Super-peak products cover defined windows | The standardised product applies from 7:00–10:30 and 17:00–21:00. | A two-hour CAES cannot sell 50 MW continuously across the whole 7.5-hour daily super-peak window. It must be modelled as a limited-volume shaped hedge, with an explicit dispatch/SoC obligation. |
| Super-peak liquidity is limited | Only 18.5 MW of standardised super-peak product traded in April's sessions. OTC super-peak CFDs totalled 17 GWh in April; shaped products were only 5% of 1.6 TWh OTC volume. | A 50 MW CAES must not be assumed able to hedge all of its output at the quoted premium. Apply a volume cap, liquidity haircut, and/or use a bilateral counterparty case. |
| Hedge markets transfer risk rather than create value mechanically | CFDs settle the difference between a contracted price and the average spot price in the effective period. | Model hedge settlement together with physical CAES dispatch. A contract replaces some exposed spot revenue; it is not a second sale of the same MWh. |
| Ōtāhuhu and Benmore are reference points | ASX North Island futures are referenced to Ōtāhuhu, while the CAES model is at SFD2201. | Add explicit SFD2201-to-Ōtāhuhu basis risk. Do not apply an Ōtāhuhu hedge price directly to SFD2201 output. |

## What this changes in the current assumptions

### 1. Move from one historic revenue case to a market-view range

The existing December 2024–November 2025 back-test should remain the **historic operating benchmark**. It should not be treated as the central 40-year forward revenue forecast.

Add at least three merchant-energy cases:

1. **Historic spot benchmark** — the present model, with final SFD2201 prices.
2. **Forward-level case** — preserve a selected historic intraday/seasonal shape but scale each future quarter to a published ASX/OTC baseload forward level, after applying SFD2201 basis.
3. **Low-spread case** — reduce the high-minus-low half-hourly price spread as well as lowering the quarterly price level. This represents additional flexible supply, new renewable generation and competing storage reducing arbitrage opportunities.

The second and third cases should be reported separately. Storage value comes primarily from the shape and volatility of prices, not the absolute annual average price. A lower baseload forward price could increase or decrease CAES margin depending on when the lower prices occur.

### 2. Treat super-peak hedging as a contract overlay, not a revenue adder

The report makes shaped hedges a credible scenario to investigate, particularly because the North Island OTC super-peak premium was 40% relative to equivalent ASX baseload in April. But the correct economics are:

```text
portfolio cashflow with CAES and hedge
= physical SFD2201 energy cashflow
+ CFD settlement at the hedge reference node
− SFD2201-to-reference-node basis settlement/exposure
− lost merchant opportunity from maintaining the delivery obligation
− collateral, trading, imbalance and contract-administration costs
```

It is incorrect to add `40% × existing CAES energy revenue` to the merchant result. A hedge fixes or reshapes price exposure for a defined MW and time window; it does not create a second physical output.

### 3. Recognise that the report does not validate the $158k/MW-year calibration

The earlier $158k/MW-year calculation is the annual contracted value needed to close the current 50 MW / 2-hour CAES NPV gap. The hedge report does not provide a capacity-market or availability-payment price against which that number can be judged.

It can, however, help value a specific hedge-backed product. For example, a counterparty may value a two-hour evening super-peak energy hedge because it reduces its price exposure. The value to CAES is then the incremental portfolio-cost reduction, not an assumed generic capacity payment.

### 4. Use lower financing risk only after modelling the contract

A credible multi-year, creditworthy, shaped contract could justify testing a lower real discount rate than a fully merchant CAES case. The report alone does not justify that change: its observed standardised super-peak volume is small, and it reports only one month's pricing and liquidity.

Use a merchant rate and a contracted-revenue rate as distinct scenarios, with the contract's duration, volume, counterparty, collateral and termination conditions explicitly represented.

## Recommended model additions

### A. Forward-price and basis module

Add a `forward_price_case` section to the simulation configuration. It should accept quarterly baseload prices at the appropriate ASX/OTC reference node and transform a historic SFD2201 profile without destroying its daily pattern.

```yaml
forward_price_case:
  enabled: false
  reference_node: OTA2201
  target_quarterly_baseload_nzd_per_mwh:
    "2026-Q3": null
    "2026-Q4": null
  sfd_basis_method: historic_monthly_distribution
  intraday_shape_method: preserve_historic_shape
  spread_case: base # base | compressed | expanded
```

Inputs should come from an auditable ASX or disclosed OTC data extract, rather than values visually estimated from a chart. Outputs should state the assumed reference price, SFD basis distribution and final synthetic SFD2201 price statistics.

### B. Super-peak hedge overlay

Represent a hedge as a financial contract plus a physical availability obligation. This allows the optimiser to decide whether retaining stored energy for a hedge period is preferable to an uncontracted merchant discharge.

```yaml
super_peak_hedge:
  enabled: false
  reference_node: OTA2201
  contract_mw: 10.0
  contract_price_nzd_per_mwh: null
  effective_months: [5, 6, 7, 8, 9]
  windows_nz:
    - "07:00-10:30"
    - "17:00-21:00"
  duration_limit_hours: 2.0
  sfd_basis_method: historic_monthly_distribution
  counterparty_and_collateral_cost_nzd_per_year: 0.0
```

The first sensitivity should use modest contract volumes—such as 5, 10 and 20 MW—not 50 MW. April's 18.5 MW standardised super-peak trade volume is a warning that a full-asset standard-product hedge is not an evidenced assumption.

### C. Contracted firming module

Keep the generic capacity/availability payment as a separate module, because it is commercially different from a CFD:

```yaml
contracted_firming:
  enabled: false
  contracted_capacity_mw: 50.0
  required_duration_hours: 2.0
  payment_nzd_per_mw_year: 0.0
  eligible_months: [5, 6, 7, 8, 9]
  eligible_hours_nz: [7, 8, 17, 18, 19]
  availability_target: 0.95
  non_delivery_penalty_nzd_per_mwh: 0.0
```

The solver should reserve enough **AC-deliverable** energy and power during eligible intervals. For CAES this needs to use the actual charge/discharge efficiency, SoC limits, compressor/turbine response times and any reserve commitments—not merely the nameplate `50 MW / 2-hour` label.

### D. Output additions

For every hedge or contracted-firming run, report:

- merchant energy and reserve revenue;
- CFD settlement and local basis effect;
- gross contract/availability payment;
- lost merchant margin caused by the obligation;
- contract administration, collateral and expected penalty costs;
- net portfolio value versus the merchant-only counterfactual;
- contracted MW, annual MWh, average utilisation and non-delivery intervals.

This makes double counting visible and keeps the output suitable for screening rather than presenting a hedge premium as automatic project revenue.

## Prioritised next steps

1. Build the **SFD2201-to-Ōtāhuhu basis and forward-price module** first. It directly improves the forward-energy assumption used in every CAES scenario.
2. Add a **small-volume super-peak CFD overlay** with 5/10/20 MW cases. Use it to value a shaped hedge, not to assume a 50 MW market outlet.
3. Add the **contracted-firming module** only once the likely counterparty and product are defined. Use the $157.7k/MW-year result as a break-even comparison point, not an assumed price.
4. Run the resulting cases across 2, 8, 10 and 12-hour CAES durations. A two-hour asset can service only a narrow part of the super-peak/firming requirement; longer-duration CAES may be more relevant for a portfolio product.

## Bottom line

The report supports a more disciplined distinction between:

- **merchant storage value** from SFD2201 spot and reserve markets;
- **forward/hedged energy value** at a reference node after local basis risk; and
- **bilateral firming value**, which must be separately contracted and dispatch-feasible.

It does not support adding a generic 22–40% super-peak premium, or a generic capacity payment, to current CAES merchant revenue. Its strongest practical contribution is to provide a transparent framework for creating conservative forward-price, shaped-hedge and liquidity scenarios.
