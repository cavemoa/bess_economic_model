# SFD2201 storage economic model

This project models storage at the Stratford pricing node (`SFD2201`) using historic final New Zealand wholesale prices. It includes a 100 MW / 200 MWh BESS reference case and an energy-only adiabatic compressed-air energy-storage (A-CAES) screening case. BESS compares **energy-only, price-taking, perfect-foresight** dispatch with a deliberately optimistic **FIR/SIR price-taker** case.

SciPy's `milp` interface uses the HiGHS mixed-integer optimiser. A binary operating-mode variable prevents simultaneous charging and discharging.

## Run

```powershell
python -m unittest discover -s tests -v
python run_model.py --config config/base_case.yaml
# Full historic-year back-test (December 2024 to November 2025)
python run_model.py --config config/annual_complete_2024-12_to_2025-11.yaml
# Full-year A-CAES duration and cost sensitivity (100 MW x 8, 10 and 12 hours)
python run_caes_sensitivity.py --config config/acaes_sfd2201_annual_sensitivity.yaml
```

The standard test suite completes quickly. The cached historic BESS regressions are deliberately opt-in because they solve the June and annual HiGHS MILPs:

```powershell
$env:RUN_HISTORICAL_REGRESSION='1'
python -m unittest discover -s tests -p test_historical_regression.py -v
```

## Configuration structure

The former all-in-one BESS assumptions are now composed from three files:

- `config/base_case.yaml` and `config/annual_complete_2024-12_to_2025-11.yaml` are simulation definitions: historic period, node, finance, solver and reporting.
- `config/systems/` holds reusable technical systems, including charge/discharge power, storage capacity, SoC limits, efficiency and any reserve modelling.
- `config/cost_cases/` holds independent capital and operating-cost cases. A power-and-energy capital model prevents A-CAES power-island and cavern/thermal-storage cost assumptions from being double counted.

`config/acaes_sfd2201_annual_sensitivity.yaml` references `acaes_salt.yaml` and the low, central and high A-CAES cost cases. It treats duration as nameplate MWh divided by 100 MW of discharge power. The configured A-CAES has a full 0--100% SoC window, so 8, 10 and 12 hours correspond to 800, 1,000 and 1,200 MWh respectively.

The first run downloads official public price data into `data/raw/2026-06/`. Subsequent runs use the local cache. Outputs are created in `outputs/2026-06/`:

- `scenario_comparison.csv` - scenario totals, including the incremental FIR/SIR result
- `interval_results_energy_only.csv` and `interval_results_fir_sir_price_taker.csv` - every settlement-period decision and cashflow
- `daily_pnl_energy_only.csv` and `daily_pnl_fir_sir_price_taker.csv` - daily revenue/cost tables
- `monthly_pnl_energy_only.csv` and `monthly_pnl_fir_sir_price_taker.csv` - monthly revenue/cost tables for multi-month runs
- `daily_pnl.png` - three stacked subplots: energy-only, reserve case and incremental revenue sources
- `monthly_pnl.png` - the same revenue comparison aggregated by month
- `dispatch_and_soc.png` - four subplots: energy dispatch, FIR/SIR offers, reserve prices and state of charge
- `project_cashflows_energy_only.csv` and `project_cashflows_fir_sir_price_taker.csv` - annualised-June NPV scenarios
- `summary.json` and `data_manifest.json` - scenario assumptions, results and input provenance

The legacy files without a scenario suffix (`interval_results.csv`, `daily_pnl.csv` and `project_cashflows.csv`) remain the energy-only case.

`config/annual_complete_2024-12_to_2025-11.yaml` runs one continuous 12-month MILP over the latest fully complete historic period available from the Electricity Authority monthly archive. State of charge carries across calendar-month boundaries, while the configured terminal SoC remains equal to the initial SoC. Its finance annualisation factor is one because the input period is already a full year.

The A-CAES run writes to `outputs/acaes_salt/2024-12_to_2025-11/`:

- `duration_cost_sensitivity.csv` - independently optimised 3 x 3 duration/cost matrix.
- `duration_cost_npv.png` - NPV heatmap in NZD million.
- `npv_tornado.csv` and `npv_tornado.png` - isolated low/high NPV effects for power-island, storage, interconnection, fixed O&M and variable O&M assumptions. Variable O&M endpoints are separately re-optimised; the other bars are finance-only changes because they cannot change dispatch.
- `sensitivity_summary.json` and `data_manifest.json` - scope and data provenance.

## Model boundaries

Energy revenue uses final `SFD2201` prices. The reserve scenario uses final North Island FIR/SIR availability prices and co-optimises charging, discharging, inverter headroom and stored energy. Reserve availability revenue is `offered MW x final price x 0.5 hour`.

The default `reserve_price_taker` case assumes one certified response capacity can receive FIR and SIR payments at the same time (`product_stacking: common_response_capacity`). It holds enough post-dispatch stored energy for a one-minute FIR or 15-minute SIR response, and limits reserve plus scheduled discharge to inverter power. These assumptions are intentionally optimistic: historic prices are unaffected by the BESS, activation energy, final offer envelopes, actual clearing quantities and reserve cost allocation are not modelled. Do not treat this case as an investment forecast.

The `finance` section in [config/base_case.yaml](config/base_case.yaml) is a **pre-tax, ungeared, real-NZD scenario**, not a Stratford investment quote. In particular, its capex and fixed O&M values are placeholders for sensitivity analysis until connection works, BBCs, insurance, O&M and augmentation assumptions are supplied.

The A-CAES low/central/high cases are likewise published-range screening assumptions expressed in USD and converted using an explicit, configurable 1.65 NZD/USD real-2026 conversion. They are not a geotechnical, EPC, connection or consent estimate. The initial A-CAES model does not include FIR/SIR revenue because it has no evidenced System Operator response envelope.

## Assumptions to replace when project evidence is available

- AC-to-AC round-trip efficiency, usable SoC window and warranty throughput
- actual SFD connection works, Transpower connection charges and benefit-based charges
- asset management, insurance, telemetry, market access and trading fees
- applicable frequency-keeping and instantaneous-reserve cost allocation rates
- System Operator-approved charge-to-discharge reserve response envelope
- development timetable, tax, financing, augmentation and residual value

## Next module

Replace the price-taker reserve result with a vSPD counterfactual market-impact case using the BESS's System Operator-approved charge-to-discharge reserve response envelope.
