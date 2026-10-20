"""Write scenario tables, charts and auditable comparisons."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


OPERATING_COST_COLUMNS = [
    "discharge_variable_cost_nzd",
    "frequency_keeping_cost_nzd",
    "trading_import_cost_nzd",
    "trading_export_cost_nzd",
    "ir_allocation_cost_nzd",
]

BASE_CASHFLOW_COMPONENTS = [
    ("energy_export_revenue_nzd", "Energy export revenue", "#1f77b4"),
    ("energy_import_cashflow_nzd", "Energy import cashflow", "#ff7f0e"),
    ("discharge_variable_cost_nzd", "Discharge variable cost", "#d62728"),
    ("frequency_keeping_cost_nzd", "Frequency keeping", "#9467bd"),
    ("trading_import_cost_nzd", "Trading import", "#7f7f7f"),
    ("trading_export_cost_nzd", "Trading export", "#bcbd22"),
    ("ir_allocation_cost_nzd", "IR allocation", "#2ca02c"),
    ("fixed_opex_cost_nzd", "Fixed O&M / transmission", "#8c564b"),
]

RESERVE_CASHFLOW_COMPONENTS = [
    ("energy_export_revenue_nzd", "Energy export revenue", "#1f77b4"),
    ("energy_import_cashflow_nzd", "Energy import cashflow", "#ff7f0e"),
    ("fir_reserve_revenue_nzd", "FIR availability revenue", "#17becf"),
    ("sir_reserve_revenue_nzd", "SIR availability revenue", "#2ca02c"),
    ("discharge_variable_cost_nzd", "Discharge variable cost", "#d62728"),
    ("frequency_keeping_cost_nzd", "Frequency keeping", "#9467bd"),
    ("trading_import_cost_nzd", "Trading import", "#7f7f7f"),
    ("trading_export_cost_nzd", "Trading export", "#bcbd22"),
    ("ir_allocation_cost_nzd", "IR allocation", "#e377c2"),
    ("fixed_opex_cost_nzd", "Fixed O&M / transmission", "#8c564b"),
]


def _build_pnl_by_period(intervals: pd.DataFrame, period_column: str) -> pd.DataFrame:
    """Aggregate operating and cashflow results by the supplied period column."""
    working = intervals.copy()
    working["fir_offered_mw_hours"] = working["fir_offer_mw"] * 0.5
    working["sir_offered_mw_hours"] = working["sir_offer_mw"] * 0.5
    value_columns = [
        "charge_mwh",
        "discharge_mwh",
        "fir_offered_mw_hours",
        "sir_offered_mw_hours",
        "energy_export_revenue_nzd",
        "energy_import_cashflow_nzd",
        "fir_reserve_revenue_nzd",
        "sir_reserve_revenue_nzd",
        *OPERATING_COST_COLUMNS,
        "fixed_opex_cost_nzd",
        "variable_margin_nzd",
        "net_cashflow_nzd",
    ]
    pnl = working.groupby(period_column, as_index=False)[value_columns].sum()
    average_offers = (
        working.groupby(period_column, as_index=False)[
            ["reserve_response_capacity_mw", "fir_offer_mw", "sir_offer_mw"]
        ]
        .mean()
        .rename(
            columns={
                "reserve_response_capacity_mw": "average_reserve_response_capacity_mw",
                "fir_offer_mw": "average_fir_offer_mw",
                "sir_offer_mw": "average_sir_offer_mw",
            }
        )
    )
    pnl = pnl.merge(average_offers, on=period_column, how="left", validate="one_to_one")
    pnl["gross_energy_cashflow_nzd"] = pnl["energy_export_revenue_nzd"] + pnl["energy_import_cashflow_nzd"]
    return pnl


def build_daily_pnl(intervals: pd.DataFrame) -> pd.DataFrame:
    """Aggregate operating and cashflow results by final-settlement trading date."""
    return _build_pnl_by_period(intervals, "TradingDate")


def build_monthly_pnl(intervals: pd.DataFrame) -> pd.DataFrame:
    """Aggregate operating and cashflow results by calendar month."""
    working = intervals.copy()
    working["Month"] = pd.to_datetime(working["TradingDate"]).dt.to_period("M").astype(str)
    return _build_pnl_by_period(working, "Month")


def build_scenario_comparison(
    energy_intervals: pd.DataFrame,
    reserve_intervals: pd.DataFrame,
    energy_finance_meta: dict[str, Any],
    reserve_finance_meta: dict[str, Any],
) -> pd.DataFrame:
    """Create a compact, machine-readable comparison of the two scenarios."""
    metrics: list[tuple[str, str, float, float]] = [
        ("energy_imported", "MWh", float(energy_intervals["charge_mwh"].sum()), float(reserve_intervals["charge_mwh"].sum())),
        ("energy_exported", "MWh", float(energy_intervals["discharge_mwh"].sum()), float(reserve_intervals["discharge_mwh"].sum())),
        (
            "fir_offered",
            "MW-h",
            float(energy_intervals["fir_offer_mw"].sum() * 0.5),
            float(reserve_intervals["fir_offer_mw"].sum() * 0.5),
        ),
        (
            "sir_offered",
            "MW-h",
            float(energy_intervals["sir_offer_mw"].sum() * 0.5),
            float(reserve_intervals["sir_offer_mw"].sum() * 0.5),
        ),
    ]
    cashflow_columns = [
        "energy_export_revenue_nzd",
        "energy_import_cashflow_nzd",
        "fir_reserve_revenue_nzd",
        "sir_reserve_revenue_nzd",
        *OPERATING_COST_COLUMNS,
        "fixed_opex_cost_nzd",
        "variable_margin_nzd",
        "net_cashflow_nzd",
    ]
    for column in cashflow_columns:
        metrics.append(
            (
                column.removesuffix("_nzd"),
                "NZD",
                float(energy_intervals[column].sum()),
                float(reserve_intervals[column].sum()),
            )
        )
    metrics.extend(
        [
            (
                "annualised_variable_margin",
                "NZD/year",
                float(energy_finance_meta["annualised_variable_margin_nzd"]),
                float(reserve_finance_meta["annualised_variable_margin_nzd"]),
            ),
            ("npv", "NZD", float(energy_finance_meta["npv_nzd"]), float(reserve_finance_meta["npv_nzd"])),
        ]
    )
    comparison = pd.DataFrame(
        metrics,
        columns=["metric", "unit", "energy_only", "fir_sir_price_taker"],
    )
    comparison["incremental_fir_sir_vs_energy_only"] = (
        comparison["fir_sir_price_taker"] - comparison["energy_only"]
    )
    return comparison


def _stack_signed_bars(
    ax: plt.Axes,
    daily: pd.DataFrame,
    columns: list[tuple[str, str, str]],
    width: float = 0.78,
) -> None:
    positive_bottom = pd.Series(0.0, index=daily.index)
    negative_bottom = pd.Series(0.0, index=daily.index)
    for column, label, colour in columns:
        values = daily[column]
        if values.abs().sum() < 1e-8:
            continue
        positives = values.clip(lower=0.0)
        negatives = values.clip(upper=0.0)
        ax.bar(daily.index, positives, bottom=positive_bottom, width=width, label=label, color=colour)
        ax.bar(daily.index, negatives, bottom=negative_bottom, width=width, color=colour)
        positive_bottom += positives
        negative_bottom += negatives


def _format_pnl_axis(ax: plt.Axes, pnl: pd.DataFrame, period_column: str) -> None:
    ax.axhline(0.0, color="black", linewidth=0.7)
    ax.grid(axis="y", alpha=0.25)
    ax.set_ylabel("NZD")
    ax.legend(ncol=3, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.19))
    dates = pd.to_datetime(pnl[period_column])
    if len(pnl) <= 16:
        tick_index = pnl.index
        labels = dates.dt.strftime("%b\n%Y")
    elif len(pnl) <= 62:
        tick_index = pnl.index[::2]
        labels = dates.dt.day.iloc[::2].astype(str)
    else:
        first_day_of_month = dates.dt.to_period("M").ne(dates.dt.to_period("M").shift())
        tick_index = pnl.index[first_day_of_month]
        labels = dates.loc[first_day_of_month].dt.strftime("%b\n%Y")
    ax.set_xticks(tick_index)
    ax.set_xticklabels(labels)


def _incremental_pnl(
    energy_pnl: pd.DataFrame, reserve_pnl: pd.DataFrame, period_column: str
) -> pd.DataFrame:
    """Re-express the reserve case in terms of the incremental revenue sources."""
    base = energy_pnl.set_index(period_column)
    reserve = reserve_pnl.set_index(period_column)
    delta = pd.DataFrame(index=reserve.index)
    delta["change_in_energy_cashflow_nzd"] = (
        reserve["energy_export_revenue_nzd"]
        + reserve["energy_import_cashflow_nzd"]
        - base["energy_export_revenue_nzd"]
        - base["energy_import_cashflow_nzd"]
    )
    delta["fir_reserve_revenue_nzd"] = reserve["fir_reserve_revenue_nzd"]
    delta["sir_reserve_revenue_nzd"] = reserve["sir_reserve_revenue_nzd"]
    delta["change_in_variable_costs_nzd"] = reserve[OPERATING_COST_COLUMNS].sum(axis=1) - base[
        OPERATING_COST_COLUMNS
    ].sum(axis=1)
    delta["change_in_fixed_cost_nzd"] = reserve["fixed_opex_cost_nzd"] - base["fixed_opex_cost_nzd"]
    delta["incremental_net_cashflow_nzd"] = reserve["net_cashflow_nzd"] - base["net_cashflow_nzd"]
    return delta.reset_index()


def _write_cashflow_comparison_chart(
    energy_pnl: pd.DataFrame,
    reserve_pnl: pd.DataFrame,
    period_column: str,
    period_label: str,
    output_path: Path,
) -> None:
    """Write the three-panel cashflow comparison at daily or monthly resolution."""
    fig, axes = plt.subplots(3, 1, figsize=(16, 15), sharex=True)

    _stack_signed_bars(axes[0], energy_pnl, BASE_CASHFLOW_COMPONENTS)
    axes[0].plot(
        energy_pnl.index,
        energy_pnl["net_cashflow_nzd"],
        color="black",
        marker="o",
        linewidth=1.25,
        label="Net cashflow",
    )
    axes[0].set_title(f"A. Energy-only dispatch - {period_label.lower()} cashflow")
    _format_pnl_axis(axes[0], energy_pnl, period_column)

    _stack_signed_bars(axes[1], reserve_pnl, RESERVE_CASHFLOW_COMPONENTS)
    axes[1].plot(
        reserve_pnl.index,
        reserve_pnl["net_cashflow_nzd"],
        color="black",
        marker="o",
        linewidth=1.25,
        label="Net cashflow",
    )
    axes[1].set_title(
        f"B. FIR/SIR price-taker case - {period_label.lower()} cashflow (optimistic shared-capacity stack)"
    )
    _format_pnl_axis(axes[1], reserve_pnl, period_column)

    incremental = _incremental_pnl(energy_pnl, reserve_pnl, period_column)
    _stack_signed_bars(
        axes[2],
        incremental,
        [
            ("change_in_energy_cashflow_nzd", "Change in energy cashflow", "#1f77b4"),
            ("fir_reserve_revenue_nzd", "FIR availability revenue", "#17becf"),
            ("sir_reserve_revenue_nzd", "SIR availability revenue", "#2ca02c"),
            ("change_in_variable_costs_nzd", "Change in variable costs", "#d62728"),
            ("change_in_fixed_cost_nzd", "Change in fixed cost", "#8c564b"),
        ],
    )
    axes[2].plot(
        incremental.index,
        incremental["incremental_net_cashflow_nzd"],
        color="black",
        marker="o",
        linewidth=1.25,
        label="Incremental net cashflow",
    )
    axes[2].set_title(f"C. FIR/SIR price-taker incremental {period_label.lower()} cashflow versus energy-only")
    _format_pnl_axis(axes[2], incremental, period_column)
    axes[2].set_xlabel(period_label)
    fig.subplots_adjust(hspace=0.62)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_charts(
    energy_intervals: pd.DataFrame,
    energy_daily: pd.DataFrame,
    energy_monthly: pd.DataFrame,
    reserve_intervals: pd.DataFrame,
    reserve_daily: pd.DataFrame,
    reserve_monthly: pd.DataFrame,
    output_dir: Path,
) -> None:
    """Write comparison charts with daily and monthly sources of reserve revenue exposed."""
    _write_cashflow_comparison_chart(
        energy_daily, reserve_daily, "TradingDate", "Trading date", output_dir / "daily_pnl.png"
    )
    _write_cashflow_comparison_chart(
        energy_monthly, reserve_monthly, "Month", "Month", output_dir / "monthly_pnl.png"
    )

    fig, axes = plt.subplots(4, 1, figsize=(16, 13), sharex=True, height_ratios=[1.25, 1, 1, 1])
    axes[0].plot(
        reserve_intervals["timestamp_nz"],
        reserve_intervals["sfd_price_nzd_per_mwh"],
        color="tab:gray",
        linewidth=0.8,
        label="SFD2201 final price",
    )
    axes[0].set_ylabel("NZD/MWh")
    power_axis = axes[0].twinx()
    power_axis.step(
        energy_intervals["timestamp_nz"],
        energy_intervals["net_grid_power_mw"],
        where="post",
        color="#1f77b4",
        linewidth=0.65,
        alpha=0.75,
        label="Energy-only net MW",
    )
    power_axis.step(
        reserve_intervals["timestamp_nz"],
        reserve_intervals["net_grid_power_mw"],
        where="post",
        color="#ff7f0e",
        linewidth=0.65,
        alpha=0.75,
        label="Reserve-case net MW",
    )
    power_axis.set_ylabel("MW (+ discharge)")
    price_handles, price_labels = axes[0].get_legend_handles_labels()
    power_handles, power_labels = power_axis.get_legend_handles_labels()
    axes[0].legend(price_handles + power_handles, price_labels + power_labels, loc="upper left", ncol=3, fontsize=8)
    axes[0].set_title("FIR/SIR price-taker operating case - energy dispatch, reserve offers and SoC")

    axes[1].step(
        reserve_intervals["timestamp_nz"],
        reserve_intervals["fir_offer_mw"],
        where="post",
        color="#17becf",
        linewidth=0.8,
        label="FIR offered MW",
    )
    axes[1].step(
        reserve_intervals["timestamp_nz"],
        reserve_intervals["sir_offer_mw"],
        where="post",
        color="#2ca02c",
        linewidth=0.8,
        label="SIR offered MW",
    )
    axes[1].step(
        reserve_intervals["timestamp_nz"],
        reserve_intervals["reserve_response_capacity_mw"],
        where="post",
        color="black",
        linestyle="--",
        linewidth=0.7,
        label="Shared response capacity",
    )
    axes[1].set_ylabel("MW")
    axes[1].set_ylim(bottom=0.0)
    axes[1].legend(loc="upper left", ncol=3, fontsize=8)
    axes[1].grid(axis="y", alpha=0.25)

    axes[2].step(
        reserve_intervals["timestamp_nz"],
        reserve_intervals["fir_price_nzd_per_mwh"],
        where="post",
        color="#17becf",
        linewidth=0.8,
        label="FIR final price",
    )
    axes[2].step(
        reserve_intervals["timestamp_nz"],
        reserve_intervals["sir_price_nzd_per_mwh"],
        where="post",
        color="#2ca02c",
        linewidth=0.8,
        label="SIR final price",
    )
    axes[2].set_ylabel("NZD/MW-h")
    axes[2].legend(loc="upper left", ncol=2, fontsize=8)
    axes[2].grid(axis="y", alpha=0.25)

    axes[3].plot(
        energy_intervals["timestamp_nz"],
        energy_intervals["soc_end_mwh"],
        color="#1f77b4",
        linewidth=0.8,
        label="Energy-only SoC",
    )
    axes[3].plot(
        reserve_intervals["timestamp_nz"],
        reserve_intervals["soc_end_mwh"],
        color="#ff7f0e",
        linewidth=0.8,
        label="Reserve-case SoC",
    )
    axes[3].set_ylabel("MWh")
    axes[3].set_xlabel("NZ time")
    axes[3].legend(loc="upper left", ncol=2, fontsize=8)
    axes[3].grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "dispatch_and_soc.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, float_format="%.6f")


def _write_single_case_charts(
    intervals: pd.DataFrame,
    daily: pd.DataFrame,
    monthly: pd.DataFrame,
    output_dir: Path,
) -> None:
    """Write transparent revenue/cost and operation charts for an energy-only system."""
    for pnl, period_column, period_label, filename in [
        (daily, "TradingDate", "Trading date", "daily_pnl.png"),
        (monthly, "Month", "Month", "monthly_pnl.png"),
    ]:
        fig, axis = plt.subplots(figsize=(16, 6))
        _stack_signed_bars(axis, pnl, BASE_CASHFLOW_COMPONENTS)
        axis.plot(pnl.index, pnl["net_cashflow_nzd"], color="black", marker="o", linewidth=1.25, label="Net cashflow")
        axis.set_title(f"Energy-only dispatch - {period_label.lower()} cashflow")
        _format_pnl_axis(axis, pnl, period_column)
        axis.set_xlabel(period_label)
        fig.tight_layout()
        fig.savefig(output_dir / filename, dpi=180, bbox_inches="tight")
        plt.close(fig)

    fig, axes = plt.subplots(3, 1, figsize=(16, 10), sharex=True)
    axes[0].plot(intervals["timestamp_nz"], intervals["sfd_price_nzd_per_mwh"], color="tab:gray", linewidth=0.8)
    axes[0].set_ylabel("NZD/MWh")
    axes[0].set_title("Energy-only operation")
    axes[1].step(intervals["timestamp_nz"], intervals["net_grid_power_mw"], where="post", color="#1f77b4", linewidth=0.7)
    axes[1].set_ylabel("MW (+ discharge)")
    axes[2].plot(intervals["timestamp_nz"], intervals["soc_end_mwh"], color="#ff7f0e", linewidth=0.8)
    axes[2].set_ylabel("MWh")
    axes[2].set_xlabel("NZ time")
    for axis in axes:
        axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "dispatch_and_soc.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_outputs(
    energy_intervals: pd.DataFrame,
    energy_daily: pd.DataFrame,
    energy_monthly: pd.DataFrame,
    energy_finance: pd.DataFrame,
    reserve_intervals: pd.DataFrame | None,
    reserve_daily: pd.DataFrame | None,
    reserve_monthly: pd.DataFrame | None,
    reserve_finance: pd.DataFrame | None,
    summary: dict[str, Any],
    scenario_comparison: pd.DataFrame | None,
    output_dir: Path,
) -> None:
    """Write legacy energy-only files plus named comparison-scenario outputs."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Keep the original filenames pointing to the energy-only case for compatibility.
    _write_csv(energy_intervals, output_dir / "interval_results.csv")
    _write_csv(energy_daily, output_dir / "daily_pnl.csv")
    _write_csv(energy_monthly, output_dir / "monthly_pnl.csv")
    _write_csv(energy_finance, output_dir / "project_cashflows.csv")

    _write_csv(energy_intervals, output_dir / "interval_results_energy_only.csv")
    _write_csv(energy_daily, output_dir / "daily_pnl_energy_only.csv")
    _write_csv(energy_monthly, output_dir / "monthly_pnl_energy_only.csv")
    _write_csv(energy_finance, output_dir / "project_cashflows_energy_only.csv")
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if reserve_intervals is None:
        _write_single_case_charts(energy_intervals, energy_daily, energy_monthly, output_dir)
        return
    if reserve_daily is None or reserve_monthly is None or reserve_finance is None or scenario_comparison is None:
        raise ValueError("Reserve output tables must be supplied together.")
    _write_csv(reserve_intervals, output_dir / "interval_results_fir_sir_price_taker.csv")
    _write_csv(reserve_daily, output_dir / "daily_pnl_fir_sir_price_taker.csv")
    _write_csv(reserve_monthly, output_dir / "monthly_pnl_fir_sir_price_taker.csv")
    _write_csv(reserve_finance, output_dir / "project_cashflows_fir_sir_price_taker.csv")
    _write_csv(scenario_comparison, output_dir / "scenario_comparison.csv")
    write_charts(energy_intervals, energy_daily, energy_monthly, reserve_intervals, reserve_daily, reserve_monthly, output_dir)
