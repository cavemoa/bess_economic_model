"""Create a 50 MW / 2-hour A-CAES power-island/storage-cost NPV contour."""

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
from matplotlib.colors import TwoSlopeNorm
import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bess_model.configuration import load_study_config
from bess_model.cost_frontier import build_npv_cost_surface
from bess_model.data import configured_period_label, load_market_data, write_manifest
from bess_model.dispatch import solve_energy_dispatch, solve_fir_sir_price_taker_dispatch
from bess_model.finance import calculate_project_npv
from bess_model.reporting import build_daily_pnl


VARIABLE_COST_COLUMNS = [
    "discharge_variable_cost_nzd",
    "frequency_keeping_cost_nzd",
    "trading_import_cost_nzd",
    "trading_export_cost_nzd",
    "ir_allocation_cost_nzd",
]

REVENUE_COMPONENTS = [
    ("energy_export_revenue_nzd", "Energy export", "#1f77b4"),
    ("fir_charge_interruptible_load_revenue_nzd", "FIR interruptible load", "#17becf"),
    ("sir_charge_interruptible_load_revenue_nzd", "SIR interruptible load", "#2ca02c"),
    ("fir_generation_reserve_revenue_nzd", "FIR generation reserve", "#9467bd"),
    ("sir_generation_reserve_revenue_nzd", "SIR generation reserve", "#e377c2"),
]


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _axis_values(settings: dict[str, Any], name: str) -> np.ndarray:
    try:
        minimum = float(settings["min"])
        maximum = float(settings["max"])
        points = int(settings["points"])
    except KeyError as error:
        raise ValueError(f"cost_frontier.{name} requires min, max and points.") from error
    if minimum < 0.0 or maximum <= minimum or points < 2:
        raise ValueError(f"cost_frontier.{name} must have non-negative min, greater max and at least two points.")
    return np.linspace(minimum, maximum, points)


def _solve_operating_case(market: Any, config: dict[str, Any], operating_case: str) -> tuple[Any, dict[str, Any]]:
    if operating_case == "energy_only":
        return solve_energy_dispatch(market, config)
    if operating_case == "configured_reserve_stack":
        if not config.get("reserve_price_taker", {}).get("enabled", False):
            raise ValueError("configured_reserve_stack requires reserve_price_taker.enabled: true in the system YAML.")
        return solve_fir_sir_price_taker_dispatch(market, config)
    raise ValueError("cost_frontier.operating_case must be energy_only or configured_reserve_stack.")


def _reference_path(config_path: Path, reference: str) -> Path:
    """Resolve a file reference written relative to the simulation YAML."""
    path = Path(reference)
    return path if path.is_absolute() else (config_path.parent / path).resolve()


def _npv(intervals: pd.DataFrame, config: dict[str, Any]) -> float:
    return float(calculate_project_npv(intervals, config)[1]["npv_nzd"])


def _write_contour(
    npv_surface_nzd: np.ndarray,
    power_costs: np.ndarray,
    storage_costs: np.ndarray,
    break_even: Any,
    currency_code: str,
    operating_case: str,
    output_path: Path,
) -> None:
    npv_million = npv_surface_nzd / 1_000_000.0
    minimum, maximum = float(npv_million.min()), float(npv_million.max())
    levels = np.linspace(minimum, maximum, 31) if maximum > minimum else np.array([minimum - 1.0, maximum + 1.0])
    fig, axis = plt.subplots(figsize=(10, 7))
    norm = TwoSlopeNorm(vmin=minimum, vcenter=0.0, vmax=maximum) if minimum < 0.0 < maximum else None
    filled = axis.contourf(power_costs, storage_costs, npv_million, levels=levels, cmap="RdYlGn", norm=norm)
    colourbar = fig.colorbar(filled, ax=axis)
    colourbar.set_label("NPV (NZD million)")
    valid = break_even[
        (break_even["break_even_power_island_cost_per_kw"] >= power_costs.min())
        & (break_even["break_even_power_island_cost_per_kw"] <= power_costs.max())
    ]
    if not valid.empty:
        axis.plot(
            valid["break_even_power_island_cost_per_kw"],
            valid["storage_cost_per_kwh"],
            color="black",
            linewidth=2.2,
            label="NPV = 0 break-even frontier",
        )
        axis.legend(loc="upper right")
    else:
        axis.text(
            0.02,
            0.02,
            "No zero-NPV frontier inside the requested cost range",
            transform=axis.transAxes,
            bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "0.4"},
        )
    axis.set_xlabel(f"Power-island capital cost ({currency_code}/kW)")
    axis.set_ylabel(f"Storage capital cost ({currency_code}/kWh)")
    axis.set_title(f"50 MW / 2-hour A-CAES NPV cost frontier at SFD2201 ({operating_case})")
    axis.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _write_tornado_chart(tornado: pd.DataFrame, base_npv: float, output_path: Path) -> None:
    """Write a one-at-a-time low/central/high NPV tornado chart."""
    chart = tornado.sort_values("range_nzd", ascending=True).reset_index(drop=True)
    fig, axis = plt.subplots(figsize=(10, max(3.8, 0.8 * len(chart) + 1.4)))
    y = range(len(chart))
    axis.barh(y, chart["low_delta_nzd"] / 1_000_000.0, color="#2ca02c", label="Low cost")
    axis.barh(y, chart["high_delta_nzd"] / 1_000_000.0, color="#d62728", label="High cost")
    axis.axvline(0.0, color="black", linewidth=0.8)
    axis.set_yticks(list(y), chart["parameter"])
    axis.set_xlabel("Change from central NPV (NZD million)")
    axis.set_title(f"50 MW / 2-hour A-CAES NPV tornado (central NPV {base_npv / 1_000_000:,.1f}m NZD)")
    axis.grid(axis="x", alpha=0.25)
    axis.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _build_cumulative_revenue_daily(intervals: pd.DataFrame) -> pd.DataFrame:
    """Aggregate operating cashflows daily and add transparent cumulative measures."""
    daily = build_daily_pnl(intervals)
    revenue_columns = [column for column, _, _ in REVENUE_COMPONENTS if column in daily.columns]
    daily["gross_revenue_nzd"] = daily[revenue_columns].sum(axis=1)
    daily["after_energy_purchases_nzd"] = daily["gross_revenue_nzd"] + daily["energy_import_cashflow_nzd"]
    daily["variable_operating_costs_nzd"] = daily[VARIABLE_COST_COLUMNS].sum(axis=1)
    cumulative_columns = [
        *revenue_columns,
        "gross_revenue_nzd",
        "energy_import_cashflow_nzd",
        "after_energy_purchases_nzd",
        "variable_operating_costs_nzd",
        "variable_margin_nzd",
        "fixed_opex_cost_nzd",
        "net_cashflow_nzd",
    ]
    for column in cumulative_columns:
        daily[f"cumulative_{column}"] = daily[column].cumsum()
    return daily


def _write_cumulative_revenue_chart(daily: pd.DataFrame, output_path: Path) -> None:
    """Plot cumulative historic revenue sources and operating cashflow in NZD."""
    dates = pd.to_datetime(daily["TradingDate"])
    active_components = [
        (column, label, colour)
        for column, label, colour in REVENUE_COMPONENTS
        if column in daily.columns and daily[column].abs().sum() > 1e-8
    ]
    fig, axes = plt.subplots(2, 1, figsize=(14, 9), sharex=True, height_ratios=[1.1, 1])

    axes[0].stackplot(
        dates,
        *[daily[f"cumulative_{column}"] for column, _, _ in active_components],
        labels=[label for _, label, _ in active_components],
        colors=[colour for _, _, colour in active_components],
        alpha=0.85,
    )
    axes[0].plot(dates, daily["cumulative_gross_revenue_nzd"], color="black", linewidth=1.2, label="Gross revenue")
    axes[0].set_title("50 MW / 2-hour A-CAES at SFD2201: cumulative historic revenue")
    axes[0].set_ylabel("Cumulative revenue (NZD)")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend(loc="upper left", ncol=3, fontsize=8)

    axes[1].plot(
        dates,
        daily["cumulative_gross_revenue_nzd"],
        color="black",
        linewidth=1.4,
        label="Gross revenue",
    )
    axes[1].plot(
        dates,
        daily["cumulative_after_energy_purchases_nzd"],
        color="#ff7f0e",
        linewidth=1.2,
        label="After energy purchases",
    )
    axes[1].plot(
        dates,
        daily["cumulative_variable_margin_nzd"],
        color="#1f77b4",
        linewidth=1.35,
        label="Variable margin",
    )
    axes[1].plot(
        dates,
        daily["cumulative_net_cashflow_nzd"],
        color="#7f3c8d",
        linewidth=1.35,
        label="After fixed O&M",
    )
    axes[1].axhline(0.0, color="black", linewidth=0.7)
    axes[1].set_ylabel("Cumulative cashflow (NZD)")
    axes[1].set_xlabel("Trading date")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend(loc="upper left", ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _build_tornado(
    market: pd.DataFrame,
    central_config: dict[str, Any],
    central_intervals: pd.DataFrame,
    central_npv: float,
    low_config: dict[str, Any],
    high_config: dict[str, Any],
    operating_case: str,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Evaluate single-input low/high NPV cases around the central frontier point.

    Capital and fixed-O&M changes do not alter the optimal hourly operation, so they
    reuse the central dispatch.  Variable O&M enters the dispatch objective and is
    therefore re-optimised at its low and high values.
    """
    rows: list[dict[str, Any]] = []
    for component, label in [
        ("power_island_capex_nzd", "Power-island capital cost"),
        ("storage_capex_nzd", "Cavern / thermal-storage capital cost"),
        ("interconnection_capex_nzd", "Interconnection capital cost"),
    ]:
        low_variant, high_variant = deepcopy(central_config), deepcopy(central_config)
        central_value = float(central_config["cost_case"]["capital_breakdown_nzd"][component])
        low_variant["finance"]["project_capex_nzd"] += (
            float(low_config["cost_case"]["capital_breakdown_nzd"][component]) - central_value
        )
        high_variant["finance"]["project_capex_nzd"] += (
            float(high_config["cost_case"]["capital_breakdown_nzd"][component]) - central_value
        )
        rows.append(
            {
                "parameter": label,
                "low_npv_nzd": _npv(central_intervals, low_variant),
                "high_npv_nzd": _npv(central_intervals, high_variant),
                "dispatch_treatment": "central dispatch reused",
            }
        )

    low_variant, high_variant = deepcopy(central_config), deepcopy(central_config)
    low_variant["operating_costs"]["fixed_opex_annual_nzd"] = low_config["operating_costs"]["fixed_opex_annual_nzd"]
    high_variant["operating_costs"]["fixed_opex_annual_nzd"] = high_config["operating_costs"]["fixed_opex_annual_nzd"]
    rows.append(
        {
            "parameter": "Fixed O&M",
            "low_npv_nzd": _npv(central_intervals, low_variant),
            "high_npv_nzd": _npv(central_intervals, high_variant),
            "dispatch_treatment": "central dispatch reused",
        }
    )

    # Variable O&M changes the dispatch objective, including any recharge and
    # reserve-release decisions, so both endpoints are separately optimised.
    low_variant, high_variant = deepcopy(central_config), deepcopy(central_config)
    low_variant["operating_costs"]["discharge_variable_cost_per_mwh"] = low_config["operating_costs"][
        "discharge_variable_cost_per_mwh"
    ]
    high_variant["operating_costs"]["discharge_variable_cost_per_mwh"] = high_config["operating_costs"][
        "discharge_variable_cost_per_mwh"
    ]
    started = time.perf_counter()
    low_intervals, _ = _solve_operating_case(market, low_variant, operating_case)
    low_solve_seconds = time.perf_counter() - started
    started = time.perf_counter()
    high_intervals, _ = _solve_operating_case(market, high_variant, operating_case)
    high_solve_seconds = time.perf_counter() - started
    rows.append(
        {
            "parameter": "Variable O&M",
            "low_npv_nzd": _npv(low_intervals, low_variant),
            "high_npv_nzd": _npv(high_intervals, high_variant),
            "dispatch_treatment": "low/high endpoint re-optimised",
        }
    )

    tornado = pd.DataFrame(rows)
    tornado["low_delta_nzd"] = tornado["low_npv_nzd"] - central_npv
    tornado["high_delta_nzd"] = tornado["high_npv_nzd"] - central_npv
    tornado["range_nzd"] = (
        tornado[["low_delta_nzd", "high_delta_nzd"]].max(axis=1)
        - tornado[["low_delta_nzd", "high_delta_nzd"]].min(axis=1)
    )
    return tornado.sort_values("range_nzd", ascending=False), {
        "low_variable_om_solve_seconds": low_solve_seconds,
        "high_variable_om_solve_seconds": high_solve_seconds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/acaes_sfd2201_50mw_2h_cost_frontier.yaml")
    args = parser.parse_args()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    config_path = config_path.resolve()
    raw_config = _read_yaml(config_path)
    config = load_study_config(config_path)
    settings = raw_config["cost_frontier"]
    power_costs = _axis_values(settings["power_island_cost_per_kw"], "power_island_cost_per_kw")
    storage_costs = _axis_values(settings["storage_cost_per_kwh"], "storage_cost_per_kwh")
    operating_case = str(settings["operating_case"])
    interconnection_cost = float(settings["interconnection_cost_per_kw"])
    if interconnection_cost < 0.0:
        raise ValueError("cost_frontier.interconnection_cost_per_kw must be non-negative.")

    period_label = configured_period_label(config["data"])
    output_dir = PROJECT_ROOT / config["reporting"]["output_dir"] / period_label
    output_dir.mkdir(parents=True, exist_ok=True)
    market, manifest = load_market_data(config, PROJECT_ROOT)
    started = time.perf_counter()
    intervals, dispatch_meta = _solve_operating_case(market, config, operating_case)
    solve_seconds = time.perf_counter() - started
    cashflows, finance_meta = calculate_project_npv(intervals, config)
    operating_present_value_nzd = float(finance_meta["npv_nzd"] + finance_meta["project_capex_nzd"])
    power_mw = float(config["asset"].get("discharge_power_mw", config["asset"].get("power_mw")))
    energy_mwh = float(config["asset"]["nominal_energy_mwh"])
    currency = config["cost_case"]["source_currency"]
    currency_code = str(currency.get("code", "NZD")).upper()
    currency_to_nzd = float(config["cost_case"]["currency_to_nzd_multiplier"])
    grid, break_even, surface = build_npv_cost_surface(
        operating_present_value_nzd,
        power_mw,
        energy_mwh,
        currency_to_nzd,
        interconnection_cost,
        power_costs,
        storage_costs,
    )
    grid["currency_code"] = currency_code
    break_even["currency_code"] = currency_code
    break_even["within_requested_power_cost_range"] = break_even["break_even_power_island_cost_per_kw"].between(
        float(power_costs.min()), float(power_costs.max())
    )
    grid.to_csv(output_dir / "cost_frontier_grid.csv", index=False, float_format="%.6f")
    break_even.to_csv(output_dir / "cost_frontier_break_even.csv", index=False, float_format="%.6f")
    cashflows.to_csv(output_dir / "frontier_operating_case_cashflows.csv", index=False, float_format="%.6f")
    daily_revenue = _build_cumulative_revenue_daily(intervals)
    daily_revenue.to_csv(output_dir / "cumulative_revenue_daily.csv", index=False, float_format="%.6f")
    _write_cumulative_revenue_chart(daily_revenue, output_dir / "cumulative_revenue.png")
    _write_contour(
        surface,
        power_costs,
        storage_costs,
        break_even,
        currency_code,
        operating_case,
        output_dir / "cost_frontier_npv.png",
    )
    tornado_settings = settings.get("tornado")
    tornado_summary: dict[str, Any] | None = None
    if tornado_settings is not None:
        try:
            low_path = _reference_path(config_path, str(tornado_settings["low_cost_case_file"]))
            high_path = _reference_path(config_path, str(tornado_settings["high_cost_case_file"]))
        except KeyError as error:
            raise ValueError("cost_frontier.tornado requires low_cost_case_file and high_cost_case_file.") from error
        low_config = load_study_config(config_path, low_path)
        high_config = load_study_config(config_path, high_path)
        if low_config["cost_case"]["source_currency"].get("code") != currency.get("code") or high_config["cost_case"][
            "source_currency"
        ].get("code") != currency.get("code"):
            raise ValueError("Tornado cost cases must use the central cost case's source currency.")
        print("Solving low/high variable-O&M tornado endpoints...", flush=True)
        tornado, tornado_timings = _build_tornado(
            market,
            config,
            intervals,
            float(finance_meta["npv_nzd"]),
            low_config,
            high_config,
            operating_case,
        )
        tornado.to_csv(output_dir / "cost_frontier_tornado.csv", index=False, float_format="%.6f")
        _write_tornado_chart(tornado, float(finance_meta["npv_nzd"]), output_dir / "cost_frontier_tornado.png")
        tornado_summary = {
            "central_npv_nzd": float(finance_meta["npv_nzd"]),
            "low_cost_case_id": low_config["cost_case"]["cost_case_id"],
            "high_cost_case_id": high_config["cost_case"]["cost_case_id"],
            "variable_om_endpoint_solve_seconds": tornado_timings,
            "dispatch_treatment": {
                "capital_and_fixed_om": "Central operating dispatch is reused because these inputs do not affect its optimisation.",
                "variable_om": "Low and high endpoints are independently re-optimised.",
            },
        }
    summary = {
        "scope": "Historic, perfect-foresight A-CAES operating case with a vectorised capital-cost NPV frontier.",
        "period": period_label,
        "node": config["data"]["node"],
        "operating_case": operating_case,
        "dispatch_case": dispatch_meta["dispatch_case"],
        "solve_seconds": solve_seconds,
        "system": config["system"],
        "currency": currency,
        "currency_to_nzd_multiplier": currency_to_nzd,
        "interconnection_cost_per_kw": interconnection_cost,
        "annualised_variable_margin_nzd": finance_meta["annualised_variable_margin_nzd"],
        "annual_fixed_opex_nzd": finance_meta["annual_fixed_opex_nzd"],
        "operating_present_value_before_capex_nzd": operating_present_value_nzd,
        "grid_points": int(len(grid)),
        "positive_npv_grid_points": int((grid["npv_nzd"] > 0.0).sum()),
        "break_even_power_island_cost_at_zero_storage": float(break_even.iloc[0]["break_even_power_island_cost_per_kw"]),
        "break_even_power_island_cost_at_max_storage": float(break_even.iloc[-1]["break_even_power_island_cost_per_kw"]),
        "tornado": tornado_summary,
    }
    (output_dir / "cost_frontier_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_manifest(manifest, output_dir / "data_manifest.json")
    print(json.dumps(summary, indent=2))
    print(f"\nOutputs written to: {output_dir}")


if __name__ == "__main__":
    main()
