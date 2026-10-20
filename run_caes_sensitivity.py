"""Run A-CAES duration and investment-cost sensitivities at SFD2201."""

from __future__ import annotations

import argparse
import json
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bess_model.configuration import load_study_config
from bess_model.data import configured_period_label, load_market_data, write_manifest
from bess_model.dispatch import solve_energy_dispatch
from bess_model.finance import calculate_project_npv


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _case_path(simulation_path: Path, reference: str) -> Path:
    path = Path(reference)
    return path if path.is_absolute() else (simulation_path.parent / path).resolve()


def _write_duration_chart(results: pd.DataFrame, output_path: Path) -> None:
    pivot = results.pivot(index="cost_case_id", columns="duration_hours", values="npv_nzd") / 1_000_000.0
    fig, axis = plt.subplots(figsize=(9, 4.8))
    image = axis.imshow(pivot.to_numpy(), cmap="RdYlGn", aspect="auto")
    axis.set_xticks(range(len(pivot.columns)), [f"{value:g} h" for value in pivot.columns])
    axis.set_yticks(range(len(pivot.index)), pivot.index)
    axis.set_xlabel("Nameplate duration at 100 MW")
    axis.set_title("A-CAES NPV sensitivity at SFD2201 (NZD million)")
    for y, row in enumerate(pivot.to_numpy()):
        for x, value in enumerate(row):
            axis.text(x, y, f"{value:,.0f}", ha="center", va="center", fontsize=9)
    fig.colorbar(image, ax=axis, label="NPV (NZD million)")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _write_tornado_chart(tornado: pd.DataFrame, base_npv: float, output_path: Path) -> None:
    chart = tornado.sort_values("range_nzd", ascending=True).reset_index(drop=True)
    fig, axis = plt.subplots(figsize=(10, max(3.8, 0.8 * len(chart) + 1.4)))
    y = range(len(chart))
    axis.barh(y, chart["low_delta_nzd"] / 1_000_000.0, color="#d62728", label="Low assumption")
    axis.barh(y, chart["high_delta_nzd"] / 1_000_000.0, color="#2ca02c", label="High assumption")
    axis.axvline(0.0, color="black", linewidth=0.8)
    axis.set_yticks(list(y), chart["parameter"])
    axis.set_xlabel("Change from central 10-hour NPV (NZD million)")
    axis.set_title(f"A-CAES 10-hour NPV tornado (central NPV {base_npv / 1_000_000:,.1f}m NZD)")
    axis.grid(axis="x", alpha=0.25)
    axis.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _npv(intervals: pd.DataFrame, config: dict[str, Any]) -> float:
    return float(calculate_project_npv(intervals, config)[1]["npv_nzd"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/acaes_sfd2201_annual_sensitivity.yaml")
    args = parser.parse_args()
    simulation_path = Path(args.config)
    if not simulation_path.is_absolute():
        simulation_path = PROJECT_ROOT / simulation_path
    simulation_path = simulation_path.resolve()
    raw_simulation = _read_yaml(simulation_path)
    central_config = load_study_config(simulation_path)
    sensitivity = raw_simulation["sensitivity"]
    durations = [float(value) for value in sensitivity["duration_hours"]]
    cost_paths = [_case_path(simulation_path, reference) for reference in sensitivity["cost_case_files"]]
    period_label = configured_period_label(central_config["data"])
    output_dir = PROJECT_ROOT / central_config["reporting"]["output_dir"] / period_label
    output_dir.mkdir(parents=True, exist_ok=True)
    market, manifest = load_market_data(central_config, PROJECT_ROOT)

    results: list[dict[str, Any]] = []
    solved: dict[tuple[float, str], tuple[dict[str, Any], pd.DataFrame, dict[str, Any]]] = {}
    power_mw = float(central_config["asset"].get("discharge_power_mw", central_config["asset"].get("power_mw")))
    for duration in durations:
        for cost_path in cost_paths:
            config = load_study_config(
                simulation_path, cost_path, {"nominal_energy_mwh": duration * power_mw}
            )
            started = time.perf_counter()
            intervals, dispatch_meta = solve_energy_dispatch(market, config)
            seconds = time.perf_counter() - started
            finance_meta = calculate_project_npv(intervals, config)[1]
            case_id = config["cost_case"]["cost_case_id"]
            results.append(
                {
                    "system_id": config["system"]["id"],
                    "technology": config["system"]["technology"],
                    "cost_case_id": case_id,
                    "duration_hours": duration,
                    "discharge_power_mw": power_mw,
                    "nominal_energy_mwh": duration * power_mw,
                    "model_period_variable_margin_nzd": float(intervals["variable_margin_nzd"].sum()),
                    "model_period_net_cashflow_nzd": float(intervals["net_cashflow_nzd"].sum()),
                    "annualised_variable_margin_nzd": float(finance_meta["annualised_variable_margin_nzd"]),
                    "annual_fixed_opex_nzd": float(finance_meta["annual_fixed_opex_nzd"]),
                    "project_capex_nzd": float(finance_meta["project_capex_nzd"]),
                    "npv_nzd": float(finance_meta["npv_nzd"]),
                    "equivalent_full_cycles": float(intervals["discharge_mwh"].sum()) / float(dispatch_meta["usable_energy_mwh"]),
                    "mip_gap": dispatch_meta["mip_gap"],
                    "solve_seconds": seconds,
                    "dispatch_basis": "cost-case-specific optimal energy-only dispatch",
                }
            )
            solved[(duration, case_id)] = (config, intervals, finance_meta)
            print(f"Solved {case_id} at {duration:g} h in {seconds:.1f}s; NPV {finance_meta['npv_nzd'] / 1_000_000:,.2f}m NZD", flush=True)

    result_frame = pd.DataFrame(results).sort_values(["cost_case_id", "duration_hours"])
    result_frame.to_csv(output_dir / "duration_cost_sensitivity.csv", index=False, float_format="%.6f")
    _write_duration_chart(result_frame, output_dir / "duration_cost_npv.png")

    central_id, central_duration = central_config["cost_case"]["cost_case_id"], 10.0 if 10.0 in durations else durations[len(durations) // 2]
    base_config, base_intervals, base_finance = solved[(central_duration, central_id)]
    low_config, _, _ = solved[(central_duration, "acaes_salt_low")]
    high_config, _, _ = solved[(central_duration, "acaes_salt_high")]
    base_npv = float(base_finance["npv_nzd"])
    tornado_rows: list[dict[str, Any]] = []
    for component, label in [
        ("power_island_capex_nzd", "Power-island capital cost"),
        ("storage_capex_nzd", "Cavern / thermal-storage capital cost"),
        ("interconnection_capex_nzd", "Interconnection capital cost"),
    ]:
        low_variant, high_variant = deepcopy(base_config), deepcopy(base_config)
        central_value = float(base_config["cost_case"]["capital_breakdown_nzd"][component])
        low_variant["finance"]["project_capex_nzd"] += float(low_config["cost_case"]["capital_breakdown_nzd"][component]) - central_value
        high_variant["finance"]["project_capex_nzd"] += float(high_config["cost_case"]["capital_breakdown_nzd"][component]) - central_value
        tornado_rows.append({"parameter": label, "low_npv_nzd": _npv(base_intervals, low_variant), "high_npv_nzd": _npv(base_intervals, high_variant)})
    low_variant, high_variant = deepcopy(base_config), deepcopy(base_config)
    low_variant["operating_costs"]["fixed_opex_annual_nzd"] = low_config["operating_costs"]["fixed_opex_annual_nzd"]
    high_variant["operating_costs"]["fixed_opex_annual_nzd"] = high_config["operating_costs"]["fixed_opex_annual_nzd"]
    tornado_rows.append({"parameter": "Fixed O&M", "low_npv_nzd": _npv(base_intervals, low_variant), "high_npv_nzd": _npv(base_intervals, high_variant)})
    # Variable O&M can change dispatch, so solve two controlled variants rather than
    # using the all-in low/high cost-case NPVs.
    low_variant, high_variant = deepcopy(base_config), deepcopy(base_config)
    low_variant["operating_costs"]["discharge_variable_cost_per_mwh"] = low_config["operating_costs"]["discharge_variable_cost_per_mwh"]
    high_variant["operating_costs"]["discharge_variable_cost_per_mwh"] = high_config["operating_costs"]["discharge_variable_cost_per_mwh"]
    low_vom_intervals, _ = solve_energy_dispatch(market, low_variant)
    high_vom_intervals, _ = solve_energy_dispatch(market, high_variant)
    tornado_rows.append({"parameter": "Variable O&M", "low_npv_nzd": _npv(low_vom_intervals, low_variant), "high_npv_nzd": _npv(high_vom_intervals, high_variant)})
    tornado = pd.DataFrame(tornado_rows)
    tornado["low_delta_nzd"] = tornado["low_npv_nzd"] - base_npv
    tornado["high_delta_nzd"] = tornado["high_npv_nzd"] - base_npv
    tornado["range_nzd"] = tornado[["low_delta_nzd", "high_delta_nzd"]].max(axis=1) - tornado[["low_delta_nzd", "high_delta_nzd"]].min(axis=1)
    tornado = tornado.sort_values("range_nzd", ascending=False)
    tornado.to_csv(output_dir / "npv_tornado.csv", index=False, float_format="%.6f")
    _write_tornado_chart(tornado, base_npv, output_dir / "npv_tornado.png")
    summary = {
        "scope": "Historic, perfect-foresight, energy-only A-CAES screening sensitivity; no reserve revenue.",
        "period": period_label,
        "node": central_config["data"]["node"],
        "duration_definition": "Nominal storage MWh divided by 100 MW discharge power; the A-CAES SoC window is 0-100%.",
        "cost_case_treatment": "Each duration and low/central/high cost case is independently re-optimised.",
        "central_tornado_case": {"duration_hours": central_duration, "npv_nzd": base_npv},
    }
    (output_dir / "sensitivity_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_manifest(manifest, output_dir / "data_manifest.json")
    print(json.dumps(summary, indent=2))
    print(f"\nOutputs written to: {output_dir}")


if __name__ == "__main__":
    main()
