"""Run the SFD2201 historical BESS energy-arbitrage model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bess_model.configuration import load_study_config
from bess_model.data import configured_period_label, load_market_data, write_manifest
from bess_model.dispatch import solve_energy_dispatch, solve_fir_sir_price_taker_dispatch
from bess_model.finance import calculate_project_npv
from bess_model.reporting import build_daily_pnl, build_monthly_pnl, build_scenario_comparison, write_outputs


def _scenario_summary(
    intervals: Any,
    daily: Any,
    dispatch_meta: dict[str, Any],
    finance_meta: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    imported = float(intervals["charge_mwh"].sum())
    exported = float(intervals["discharge_mwh"].sum())
    usable_energy = dispatch_meta["usable_energy_mwh"]
    return {
        "energy_imported_mwh": imported,
        "energy_exported_mwh": exported,
        "fir_offered_mw_hours": float(intervals["fir_offer_mw"].sum() * 0.5),
        "sir_offered_mw_hours": float(intervals["sir_offer_mw"].sum() * 0.5),
        "equivalent_full_cycles": exported / usable_energy if usable_energy else None,
        "weighted_average_buy_price_nzd_per_mwh": (
            float((intervals["charge_mwh"] * intervals["sfd_price_nzd_per_mwh"]).sum() / imported) if imported else None
        ),
        "weighted_average_sell_price_nzd_per_mwh": (
            float((intervals["discharge_mwh"] * intervals["sfd_price_nzd_per_mwh"]).sum() / exported) if exported else None
        ),
        "model_period_variable_margin_nzd": float(intervals["variable_margin_nzd"].sum()),
        "model_period_net_cashflow_nzd": float(intervals["net_cashflow_nzd"].sum()),
        "model_period_fir_reserve_revenue_nzd": float(intervals["fir_reserve_revenue_nzd"].sum()),
        "model_period_sir_reserve_revenue_nzd": float(intervals["sir_reserve_revenue_nzd"].sum()),
        "best_day_net_cashflow_nzd": float(daily["net_cashflow_nzd"].max()),
        "worst_day_net_cashflow_nzd": float(daily["net_cashflow_nzd"].min()),
        **dispatch_meta,
        **finance_meta,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/base_case.yaml", help="Path relative to the project root or absolute path")
    args = parser.parse_args()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    config = load_study_config(config_path)

    period_label = configured_period_label(config["data"])
    output_dir = PROJECT_ROOT / config["reporting"]["output_dir"] / period_label
    market, manifest = load_market_data(config, PROJECT_ROOT)
    energy_intervals, energy_dispatch_meta = solve_energy_dispatch(market, config)
    energy_daily = build_daily_pnl(energy_intervals)
    energy_monthly = build_monthly_pnl(energy_intervals)
    energy_finance, energy_finance_meta = calculate_project_npv(energy_intervals, config)

    energy_summary = _scenario_summary(
        energy_intervals, energy_daily, energy_dispatch_meta, energy_finance_meta, config
    )
    summary = {
        "scope": "Historical, perfect-foresight, price-taker storage screening model.",
        "period": period_label,
        "node": config["data"]["node"],
        "intervals": int(len(energy_intervals)),
        "system": config.get("system", {"technology": "battery"}),
        "cost_case": config.get("cost_case"),
        "energy_only": energy_summary,
    }

    reserve_intervals = reserve_daily = reserve_monthly = reserve_finance = scenario_comparison = None
    if config.get("reserve_price_taker", {}).get("enabled", False):
        reserve_intervals, reserve_dispatch_meta = solve_fir_sir_price_taker_dispatch(market, config)
        reserve_daily = build_daily_pnl(reserve_intervals)
        reserve_monthly = build_monthly_pnl(reserve_intervals)
        reserve_finance, reserve_finance_meta = calculate_project_npv(reserve_intervals, config)
        reserve_summary = _scenario_summary(
            reserve_intervals, reserve_daily, reserve_dispatch_meta, reserve_finance_meta, config
        )
        scenario_comparison = build_scenario_comparison(
            energy_intervals, reserve_intervals, energy_finance_meta, reserve_finance_meta
        )
        directional_reserve = "charging_interruptible_load" in config.get("reserve_price_taker", {})
        reserve_limitations = [
            "Historic final FIR/SIR prices are treated as unaffected by a 100 MW storage offer.",
            "Actual System Operator approval, offer envelopes, clearing quantities, risk allocation and activation energy are not modelled.",
        ]
        if directional_reserve:
            reserve_limitations.insert(
                1,
                "Charging FIR/SIR is an illustrative interruptible-load capability and generation reserve is limited to the YAML envelope.",
            )
            reserve_limitations.insert(
                2,
                "Common charging-response capacity can earn both FIR and SIR only because the configured illustrative stacking rule permits it.",
            )
        else:
            reserve_limitations.insert(
                1,
                "One certified response capacity is assumed to earn both FIR and SIR availability revenue.",
            )
        summary.update(
            {
                "scope": (
                    "Historical, perfect-foresight price-taker comparison. The FIR/SIR case is an "
                    "illustrative upper bound, not a clearing or investment forecast."
                ),
                "reserve_case_limitations": reserve_limitations,
                "fir_sir_price_taker": reserve_summary,
                "incremental_fir_sir_price_taker_vs_energy_only": {
                    row["metric"]: float(row["incremental_fir_sir_vs_energy_only"])
                    for _, row in scenario_comparison.iterrows()
                },
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(manifest, output_dir / "data_manifest.json")
    write_outputs(
        energy_intervals,
        energy_daily,
        energy_monthly,
        energy_finance,
        reserve_intervals,
        reserve_daily,
        reserve_monthly,
        reserve_finance,
        summary,
        scenario_comparison,
        output_dir,
    )
    print(json.dumps(summary, indent=2))
    print(f"\nOutputs written to: {output_dir}")


if __name__ == "__main__":
    main()
from bess_model.configuration import load_study_config
