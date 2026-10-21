"""Energy and FIR/SIR price-taker MILPs solved by SciPy's HiGHS backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix


HALF_HOUR = 0.5


@dataclass(frozen=True)
class Asset:
    charge_power_mw: float
    discharge_power_mw: float
    energy_mwh: float
    soc_min_mwh: float
    soc_max_mwh: float
    initial_soc_mwh: float
    eta_charge: float
    eta_discharge: float
    max_daily_efc: float | None

    @property
    def usable_energy_mwh(self) -> float:
        return self.soc_max_mwh - self.soc_min_mwh


@dataclass(frozen=True)
class ReservePriceTakerScenario:
    """Assumptions for the deliberately optimistic FIR/SIR availability case."""

    max_offer_mw: float
    product_stacking: str
    fir_sustain_hours: float
    sir_sustain_hours: float


@dataclass(frozen=True)
class DirectionalReserveProduct:
    """A single reserve product available from one physical operating direction."""

    enabled: bool
    max_offer_mw: float
    sustain_hours: float


@dataclass(frozen=True)
class DirectionalReservePriceTakerScenario:
    """Illustrative interruptible-load and generation-reserve capability envelope."""

    charging_product_stacking: str
    generation_product_stacking: str
    charging_fir: DirectionalReserveProduct
    charging_sir: DirectionalReserveProduct
    generation_fir: DirectionalReserveProduct
    generation_sir: DirectionalReserveProduct


def asset_from_config(config: dict[str, Any]) -> Asset:
    source = config["asset"]
    if "charge_efficiency" in source or "discharge_efficiency" in source:
        eta_charge = float(source["charge_efficiency"])
        eta_discharge = float(source["discharge_efficiency"])
        if not 0 < eta_charge <= 1 or not 0 < eta_discharge <= 1:
            raise ValueError("Charge and discharge efficiency must be in (0, 1].")
    else:
        rte = float(source["round_trip_efficiency"])
        if not 0 < rte <= 1:
            raise ValueError("round_trip_efficiency must be in (0, 1].")
        eta_charge = np.sqrt(rte)
        eta_discharge = np.sqrt(rte)

    energy = float(source["nominal_energy_mwh"])
    soc_min = energy * float(source["soc_min_fraction"])
    soc_max = energy * float(source["soc_max_fraction"])
    initial_soc = energy * float(source["initial_soc_fraction"])
    if not soc_min <= initial_soc <= soc_max:
        raise ValueError("Initial state of charge must sit within the usable SoC window.")

    max_daily_efc = source.get("max_equivalent_full_cycles_per_day")
    return Asset(
        charge_power_mw=float(source.get("charge_power_mw", source.get("power_mw"))),
        discharge_power_mw=float(source.get("discharge_power_mw", source.get("power_mw"))),
        energy_mwh=energy,
        soc_min_mwh=soc_min,
        soc_max_mwh=soc_max,
        initial_soc_mwh=initial_soc,
        eta_charge=eta_charge,
        eta_discharge=eta_discharge,
        max_daily_efc=None if max_daily_efc is None else float(max_daily_efc),
    )


def _variable_costs(config: dict[str, Any]) -> tuple[float, float]:
    costs = config["operating_costs"]
    import_cost = float(costs["frequency_keeping_charge_per_mwh_imported"]) + float(
        costs["trading_charge_per_mwh_imported"]
    )
    export_cost = (
        float(costs.get("discharge_variable_cost_per_mwh", costs.get("degradation_cost_per_mwh_discharged", 0.0)))
        + float(costs["trading_charge_per_mwh_exported"])
        + float(costs["instantaneous_reserve_cost_per_mwh_exported"])
    )
    return import_cost, export_cost


def reserve_scenario_from_config(config: dict[str, Any], asset: Asset) -> ReservePriceTakerScenario:
    """Read and validate the shared-response FIR/SIR price-taker assumptions."""
    source = config.get("reserve_price_taker", {})
    product_stacking = str(source.get("product_stacking", "common_response_capacity"))
    if product_stacking != "common_response_capacity":
        raise ValueError("Only product_stacking='common_response_capacity' is currently supported.")

    max_offer_mw = float(source.get("max_offer_mw", asset.discharge_power_mw))
    if not 0.0 <= max_offer_mw <= asset.discharge_power_mw:
        raise ValueError("reserve_price_taker.max_offer_mw must be between zero and battery power.")

    fir_sustain_hours = float(source.get("fir_sustain_minutes", 1.0)) / 60.0
    sir_sustain_hours = float(source.get("sir_sustain_minutes", 15.0)) / 60.0
    if fir_sustain_hours <= 0.0 or sir_sustain_hours <= 0.0:
        raise ValueError("FIR and SIR sustain durations must both be positive.")

    return ReservePriceTakerScenario(
        max_offer_mw=max_offer_mw,
        product_stacking=product_stacking,
        fir_sustain_hours=fir_sustain_hours,
        sir_sustain_hours=sir_sustain_hours,
    )


def _directional_product(
    source: dict[str, Any],
    name: str,
    default_max_mw: float,
    default_sustain_minutes: float,
) -> DirectionalReserveProduct:
    settings = source.get(name, {})
    if not isinstance(settings, dict):
        raise ValueError(f"Reserve product {name!r} must be a mapping.")
    enabled = bool(settings.get("enabled", False))
    max_offer_mw = float(settings.get("max_offer_mw", default_max_mw))
    sustain_hours = float(settings.get("sustain_minutes", default_sustain_minutes)) / 60.0
    if max_offer_mw < 0.0 or max_offer_mw > default_max_mw:
        raise ValueError(f"Reserve product {name!r} max_offer_mw must be between zero and asset power.")
    if sustain_hours <= 0.0:
        raise ValueError(f"Reserve product {name!r} sustain_minutes must be positive.")
    return DirectionalReserveProduct(enabled, max_offer_mw if enabled else 0.0, sustain_hours)


def directional_reserve_scenario_from_config(
    config: dict[str, Any], asset: Asset
) -> DirectionalReservePriceTakerScenario:
    """Read the explicit CAES-style reserve mechanisms from YAML."""
    source = config["reserve_price_taker"]
    charge = source.get("charging_interruptible_load", {})
    generation = source.get("discharging_generation", {})
    if not isinstance(charge, dict) or not isinstance(generation, dict):
        raise ValueError("Directional reserve settings must be mappings.")

    def stacking(block: dict[str, Any], label: str) -> str:
        value = str(block.get("product_stacking", "exclusive_capacity"))
        if value not in {"common_response_capacity", "exclusive_capacity"}:
            raise ValueError(
                f"{label}.product_stacking must be common_response_capacity or exclusive_capacity."
            )
        return value

    return DirectionalReservePriceTakerScenario(
        charging_product_stacking=stacking(charge, "charging_interruptible_load"),
        generation_product_stacking=stacking(generation, "discharging_generation"),
        charging_fir=_directional_product(charge, "fir", asset.charge_power_mw, 1.0),
        charging_sir=_directional_product(charge, "sir", asset.charge_power_mw, 15.0),
        generation_fir=_directional_product(generation, "fir", asset.discharge_power_mw, 1.0),
        generation_sir=_directional_product(generation, "sir", asset.discharge_power_mw, 15.0),
    )


def _solve_dispatch(
    market: pd.DataFrame,
    config: dict[str, Any],
    reserve_scenario: ReservePriceTakerScenario | None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Solve energy-only or integrated energy-and-reserve dispatch.

    In the reserve case, FIR and SIR are paid on a shared certified response capacity.
    This is deliberately optimistic: it is a historic-price, price-taker upper bound and
    must not be treated as a forecast of reserve clearing or an approved offer envelope.
    """
    asset = asset_from_config(config)
    costs = config["operating_costs"]
    solver_config = config["solver"]
    price = market["sfd_price_nzd_per_mwh"].to_numpy(dtype=float)
    intervals = len(market)
    import_variable_cost, export_variable_cost = _variable_costs(config)

    # Core variable blocks: charge[0:T], discharge[T:2T], soc[2T:3T+1],
    # charging_mode[3T+1:4T+1]. Reserve blocks are appended when enabled.
    charge_slice = slice(0, intervals)
    discharge_slice = slice(intervals, 2 * intervals)
    soc_slice = slice(2 * intervals, 3 * intervals + 1)
    mode_slice = slice(3 * intervals + 1, 4 * intervals + 1)
    core_variable_count = 4 * intervals + 1
    if reserve_scenario is None:
        response_capacity_slice = fir_offer_slice = sir_offer_slice = None
        variable_count = core_variable_count
    else:
        response_capacity_slice = slice(core_variable_count, core_variable_count + intervals)
        fir_offer_slice = slice(core_variable_count + intervals, core_variable_count + 2 * intervals)
        sir_offer_slice = slice(core_variable_count + 2 * intervals, core_variable_count + 3 * intervals)
        variable_count = core_variable_count + 3 * intervals

    objective = np.zeros(variable_count)
    objective[charge_slice] = (price + import_variable_cost) * HALF_HOUR
    objective[discharge_slice] = (-price + export_variable_cost) * HALF_HOUR
    if reserve_scenario is not None:
        objective[fir_offer_slice] = -market["fir_price_nzd_per_mwh"].to_numpy(dtype=float) * HALF_HOUR
        objective[sir_offer_slice] = -market["sir_price_nzd_per_mwh"].to_numpy(dtype=float) * HALF_HOUR

    lower_bounds = np.full(variable_count, -np.inf)
    upper_bounds = np.full(variable_count, np.inf)
    lower_bounds[charge_slice] = 0.0
    upper_bounds[charge_slice] = asset.charge_power_mw
    lower_bounds[discharge_slice] = 0.0
    upper_bounds[discharge_slice] = asset.discharge_power_mw
    lower_bounds[soc_slice] = asset.soc_min_mwh
    upper_bounds[soc_slice] = asset.soc_max_mwh
    lower_bounds[2 * intervals] = upper_bounds[2 * intervals] = asset.initial_soc_mwh
    lower_bounds[3 * intervals] = upper_bounds[3 * intervals] = asset.initial_soc_mwh
    lower_bounds[mode_slice] = 0.0
    upper_bounds[mode_slice] = 1.0
    if reserve_scenario is not None:
        lower_bounds[response_capacity_slice] = 0.0
        upper_bounds[response_capacity_slice] = reserve_scenario.max_offer_mw
        lower_bounds[fir_offer_slice] = 0.0
        upper_bounds[fir_offer_slice] = reserve_scenario.max_offer_mw
        lower_bounds[sir_offer_slice] = 0.0
        upper_bounds[sir_offer_slice] = reserve_scenario.max_offer_mw

    # SoC balance, no simultaneous charge/discharge, reserve deliverability and optional
    # throughput limit. FIR/SIR share one physical response capacity, but their different
    # sustain requirements each reserve energy at the end of the scheduled interval.
    reserve_rows = 5 * intervals if reserve_scenario is not None else 0
    rows = 3 * intervals + reserve_rows + (1 if asset.max_daily_efc is not None else 0)
    matrix = lil_matrix((rows, variable_count), dtype=float)
    constraint_lower = np.full(rows, -np.inf)
    constraint_upper = np.full(rows, np.inf)
    row = 0
    for t in range(intervals):
        # e[t+1] - e[t] - eta_c*c[t]*dt + d[t]*dt/eta_d = 0
        matrix[row, 2 * intervals + t + 1] = 1.0
        matrix[row, 2 * intervals + t] = -1.0
        matrix[row, t] = -asset.eta_charge * HALF_HOUR
        matrix[row, intervals + t] = HALF_HOUR / asset.eta_discharge
        constraint_lower[row] = constraint_upper[row] = 0.0
        row += 1

        # c[t] <= Pmax * mode[t]
        matrix[row, t] = 1.0
        matrix[row, 3 * intervals + 1 + t] = -asset.charge_power_mw
        constraint_upper[row] = 0.0
        row += 1

        # d[t] <= Pmax * (1 - mode[t])
        matrix[row, intervals + t] = 1.0
        matrix[row, 3 * intervals + 1 + t] = asset.discharge_power_mw
        constraint_upper[row] = asset.discharge_power_mw
        row += 1

        if reserve_scenario is not None:
            # A reserve response must fit within the inverter's generation headroom.
            matrix[row, intervals + t] = 1.0
            matrix[row, response_capacity_slice.start + t] = 1.0
            constraint_upper[row] = asset.discharge_power_mw
            row += 1

            # FIR and SIR can both be paid on this common response capacity. This is the
            # explicitly optimistic stacking assumption configured for this scenario.
            matrix[row, fir_offer_slice.start + t] = 1.0
            matrix[row, response_capacity_slice.start + t] = -1.0
            constraint_upper[row] = 0.0
            row += 1

            matrix[row, sir_offer_slice.start + t] = 1.0
            matrix[row, response_capacity_slice.start + t] = -1.0
            constraint_upper[row] = 0.0
            row += 1

            # Stored energy is held after scheduled dispatch so either reserve service
            # can be delivered for its configured sustain period.
            matrix[row, 2 * intervals + t + 1] = 1.0
            matrix[row, fir_offer_slice.start + t] = -reserve_scenario.fir_sustain_hours / asset.eta_discharge
            constraint_lower[row] = asset.soc_min_mwh
            row += 1

            matrix[row, 2 * intervals + t + 1] = 1.0
            matrix[row, sir_offer_slice.start + t] = -reserve_scenario.sir_sustain_hours / asset.eta_discharge
            constraint_lower[row] = asset.soc_min_mwh
            row += 1

    if asset.max_daily_efc is not None:
        matrix[row, discharge_slice] = HALF_HOUR
        days = market["TradingDate"].nunique()
        constraint_upper[row] = asset.max_daily_efc * asset.usable_energy_mwh * days

    integrality = np.zeros(variable_count, dtype=int)
    integrality[mode_slice] = 1
    result = milp(
        c=objective,
        integrality=integrality,
        bounds=Bounds(lower_bounds, upper_bounds),
        constraints=LinearConstraint(matrix.tocsr(), constraint_lower, constraint_upper),
        options={
            "time_limit": float(solver_config["time_limit_seconds"]),
            "mip_rel_gap": float(solver_config["mip_relative_gap"]),
            "disp": False,
        },
    )
    if not result.success or result.x is None:
        raise RuntimeError(f"HiGHS did not solve the MILP: {result.message}")

    charge = np.clip(result.x[charge_slice], 0.0, None)
    discharge = np.clip(result.x[discharge_slice], 0.0, None)
    soc = result.x[soc_slice]
    mode = np.rint(result.x[mode_slice]).astype(int)
    if reserve_scenario is None:
        response_capacity = np.zeros(intervals)
        fir_offer = np.zeros(intervals)
        sir_offer = np.zeros(intervals)
    else:
        fir_offer = np.clip(result.x[fir_offer_slice], 0.0, None)
        sir_offer = np.clip(result.x[sir_offer_slice], 0.0, None)
        # The capacity helper has no direct price, so HiGHS may leave it above the
        # cleared offers. Report the economically meaningful shared offered capacity.
        response_capacity = np.maximum(fir_offer, sir_offer)

    intervals_out = market.copy()
    intervals_out["charge_mw"] = charge
    intervals_out["discharge_mw"] = discharge
    intervals_out["net_grid_power_mw"] = discharge - charge
    intervals_out["soc_start_mwh"] = soc[:-1]
    intervals_out["soc_end_mwh"] = soc[1:]
    intervals_out["charging_mode"] = mode
    intervals_out["charge_mwh"] = charge * HALF_HOUR
    intervals_out["discharge_mwh"] = discharge * HALF_HOUR
    intervals_out["reserve_response_capacity_mw"] = response_capacity
    intervals_out["fir_offer_mw"] = fir_offer
    intervals_out["sir_offer_mw"] = sir_offer
    intervals_out["energy_export_revenue_nzd"] = intervals_out["discharge_mwh"] * price
    intervals_out["energy_import_cashflow_nzd"] = -intervals_out["charge_mwh"] * price
    intervals_out["fir_reserve_revenue_nzd"] = (
        intervals_out["fir_offer_mw"] * intervals_out["fir_price_nzd_per_mwh"] * HALF_HOUR
    )
    intervals_out["sir_reserve_revenue_nzd"] = (
        intervals_out["sir_offer_mw"] * intervals_out["sir_price_nzd_per_mwh"] * HALF_HOUR
    )
    # Direction-specific reserve fields are zero for the legacy BESS shared-response case.
    for column in [
        "fir_charge_interruptible_load_mw",
        "sir_charge_interruptible_load_mw",
        "fir_generation_reserve_mw",
        "sir_generation_reserve_mw",
        "fir_charge_interruptible_load_revenue_nzd",
        "sir_charge_interruptible_load_revenue_nzd",
        "fir_generation_reserve_revenue_nzd",
        "sir_generation_reserve_revenue_nzd",
    ]:
        intervals_out[column] = 0.0
    intervals_out["discharge_variable_cost_nzd"] = -intervals_out["discharge_mwh"] * float(
        costs.get("discharge_variable_cost_per_mwh", costs.get("degradation_cost_per_mwh_discharged", 0.0))
    )
    # Legacy alias retained in result tables produced by earlier BESS versions.
    intervals_out["degradation_cost_nzd"] = intervals_out["discharge_variable_cost_nzd"]
    intervals_out["frequency_keeping_cost_nzd"] = -intervals_out["charge_mwh"] * float(
        costs["frequency_keeping_charge_per_mwh_imported"]
    )
    intervals_out["trading_import_cost_nzd"] = -intervals_out["charge_mwh"] * float(
        costs["trading_charge_per_mwh_imported"]
    )
    intervals_out["trading_export_cost_nzd"] = -intervals_out["discharge_mwh"] * float(
        costs["trading_charge_per_mwh_exported"]
    )
    intervals_out["ir_allocation_cost_nzd"] = -intervals_out["discharge_mwh"] * float(
        costs["instantaneous_reserve_cost_per_mwh_exported"]
    )
    fixed_cost_per_interval = -(
        float(costs["fixed_opex_annual_nzd"]) + float(costs["transmission_and_connection_annual_nzd"])
    ) / 365.0 / 48.0
    intervals_out["fixed_opex_cost_nzd"] = fixed_cost_per_interval
    cashflow_columns = [
        "energy_export_revenue_nzd",
        "energy_import_cashflow_nzd",
        "fir_reserve_revenue_nzd",
        "sir_reserve_revenue_nzd",
        "discharge_variable_cost_nzd",
        "frequency_keeping_cost_nzd",
        "trading_import_cost_nzd",
        "trading_export_cost_nzd",
        "ir_allocation_cost_nzd",
        "fixed_opex_cost_nzd",
    ]
    intervals_out["variable_margin_nzd"] = intervals_out[cashflow_columns[:-1]].sum(axis=1)
    intervals_out["net_cashflow_nzd"] = intervals_out[cashflow_columns].sum(axis=1)

    calculated_objective_margin = float(intervals_out["variable_margin_nzd"].sum())
    if not np.isclose(calculated_objective_margin, -float(result.fun), atol=1e-3):
        raise RuntimeError("MILP objective does not reconcile to calculated variable margin.")
    if not np.all(charge * discharge < 1e-5):
        raise RuntimeError("Simultaneous charging and discharging detected.")
    if not np.isclose(soc[0], soc[-1], atol=1e-5):
        raise RuntimeError("Terminal state of charge does not reconcile to initial state of charge.")
    if reserve_scenario is not None:
        reserve_energy_fir = fir_offer * reserve_scenario.fir_sustain_hours / asset.eta_discharge
        reserve_energy_sir = sir_offer * reserve_scenario.sir_sustain_hours / asset.eta_discharge
        if not np.all(discharge + response_capacity <= asset.discharge_power_mw + 1e-5):
            raise RuntimeError("Reserve offer exceeds inverter generation headroom.")
        if not np.all(soc[1:] - reserve_energy_fir >= asset.soc_min_mwh - 1e-5):
            raise RuntimeError("FIR offer does not retain sufficient stored energy.")
        if not np.all(soc[1:] - reserve_energy_sir >= asset.soc_min_mwh - 1e-5):
            raise RuntimeError("SIR offer does not retain sufficient stored energy.")

    metadata = {
        "solver": "HiGHS via scipy.optimize.milp",
        "dispatch_case": "energy_only" if reserve_scenario is None else "fir_sir_price_taker",
        "solver_status": int(result.status),
        "solver_message": result.message,
        "objective_variable_margin_nzd": calculated_objective_margin,
        "mip_gap": None if getattr(result, "mip_gap", None) is None else float(result.mip_gap),
        "usable_energy_mwh": asset.usable_energy_mwh,
        "charge_power_mw": asset.charge_power_mw,
        "discharge_power_mw": asset.discharge_power_mw,
        "initial_soc_mwh": asset.initial_soc_mwh,
        "terminal_soc_mwh": float(soc[-1]),
    }
    if reserve_scenario is not None:
        metadata.update(
            {
                "reserve_case_status": "optimistic_price_taker_upper_bound",
                "reserve_product_stacking": reserve_scenario.product_stacking,
                "reserve_max_offer_mw": reserve_scenario.max_offer_mw,
                "fir_sustain_minutes": reserve_scenario.fir_sustain_hours * 60.0,
                "sir_sustain_minutes": reserve_scenario.sir_sustain_hours * 60.0,
            }
        )
    return intervals_out, metadata


def _solve_directional_reserve_dispatch(
    market: pd.DataFrame,
    config: dict[str, Any],
    reserve: DirectionalReservePriceTakerScenario,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Solve a storage model with distinct charge-side and generation-side reserve paths.

    Charging reserve is interruptible load: an offered MW must be scheduled as charging
    load, but does not consume stored energy when activated. Generation reserve must
    retain inverter headroom and enough stored energy for the configured sustain time.
    Activation itself is deliberately not simulated; this remains an availability-only,
    historic-price, price-taker illustration.
    """
    asset = asset_from_config(config)
    costs = config["operating_costs"]
    solver_config = config["solver"]
    price = market["sfd_price_nzd_per_mwh"].to_numpy(dtype=float)
    fir_price = market["fir_price_nzd_per_mwh"].to_numpy(dtype=float)
    sir_price = market["sir_price_nzd_per_mwh"].to_numpy(dtype=float)
    intervals = len(market)
    import_variable_cost, export_variable_cost = _variable_costs(config)

    # Core blocks followed by FIR/SIR interruptible-load offers and FIR/SIR
    # generation-reserve offers. Response capacity is derived from offers rather than
    # represented as an unpriced helper variable, avoiding unnecessary MILP degeneracy.
    charge_slice = slice(0, intervals)
    discharge_slice = slice(intervals, 2 * intervals)
    soc_slice = slice(2 * intervals, 3 * intervals + 1)
    mode_slice = slice(3 * intervals + 1, 4 * intervals + 1)
    core_count = 4 * intervals + 1
    charge_fir_slice = slice(core_count, core_count + intervals)
    charge_sir_slice = slice(core_count + intervals, core_count + 2 * intervals)
    generation_fir_slice = slice(core_count + 2 * intervals, core_count + 3 * intervals)
    generation_sir_slice = slice(core_count + 3 * intervals, core_count + 4 * intervals)
    variable_count = core_count + 4 * intervals

    objective = np.zeros(variable_count)
    objective[charge_slice] = (price + import_variable_cost) * HALF_HOUR
    objective[discharge_slice] = (-price + export_variable_cost) * HALF_HOUR
    objective[charge_fir_slice] = -fir_price * HALF_HOUR
    objective[generation_fir_slice] = -fir_price * HALF_HOUR
    objective[charge_sir_slice] = -sir_price * HALF_HOUR
    objective[generation_sir_slice] = -sir_price * HALF_HOUR

    lower_bounds = np.full(variable_count, -np.inf)
    upper_bounds = np.full(variable_count, np.inf)
    lower_bounds[charge_slice] = 0.0
    upper_bounds[charge_slice] = asset.charge_power_mw
    lower_bounds[discharge_slice] = 0.0
    upper_bounds[discharge_slice] = asset.discharge_power_mw
    lower_bounds[soc_slice] = asset.soc_min_mwh
    upper_bounds[soc_slice] = asset.soc_max_mwh
    lower_bounds[2 * intervals] = upper_bounds[2 * intervals] = asset.initial_soc_mwh
    lower_bounds[3 * intervals] = upper_bounds[3 * intervals] = asset.initial_soc_mwh
    lower_bounds[mode_slice] = 0.0
    upper_bounds[mode_slice] = 1.0
    for variable_slice, maximum in [
        (charge_fir_slice, reserve.charging_fir.max_offer_mw),
        (charge_sir_slice, reserve.charging_sir.max_offer_mw),
        (generation_fir_slice, reserve.generation_fir.max_offer_mw),
        (generation_sir_slice, reserve.generation_sir.max_offer_mw),
    ]:
        lower_bounds[variable_slice] = 0.0
        upper_bounds[variable_slice] = maximum

    # Three core constraints and eight directional-reserve constraints per interval.
    rows = 11 * intervals + (1 if asset.max_daily_efc is not None else 0)
    matrix = lil_matrix((rows, variable_count), dtype=float)
    constraint_lower = np.full(rows, -np.inf)
    constraint_upper = np.full(rows, np.inf)
    row = 0
    for t in range(intervals):
        # e[t+1] - e[t] - eta_c*c[t]*dt + d[t]*dt/eta_d = 0
        matrix[row, 2 * intervals + t + 1] = 1.0
        matrix[row, 2 * intervals + t] = -1.0
        matrix[row, t] = -asset.eta_charge * HALF_HOUR
        matrix[row, intervals + t] = HALF_HOUR / asset.eta_discharge
        constraint_lower[row] = constraint_upper[row] = 0.0
        row += 1

        matrix[row, t] = 1.0
        matrix[row, 3 * intervals + 1 + t] = -asset.charge_power_mw
        constraint_upper[row] = 0.0
        row += 1

        matrix[row, intervals + t] = 1.0
        matrix[row, 3 * intervals + 1 + t] = asset.discharge_power_mw
        constraint_upper[row] = asset.discharge_power_mw
        row += 1

        # Interruptible-load response can only be offered against scheduled charging load.
        if reserve.charging_product_stacking == "common_response_capacity":
            matrix[row, charge_fir_slice.start + t] = 1.0
            matrix[row, t] = -1.0
            constraint_upper[row] = 0.0
            row += 1
            matrix[row, charge_sir_slice.start + t] = 1.0
            matrix[row, t] = -1.0
            constraint_upper[row] = 0.0
            row += 1
        else:
            matrix[row, charge_fir_slice.start + t] = 1.0
            matrix[row, charge_sir_slice.start + t] = 1.0
            matrix[row, t] = -1.0
            constraint_upper[row] = 0.0
            row += 1
            matrix[row, charge_fir_slice.start + t] = 1.0
            matrix[row, t] = -1.0
            constraint_upper[row] = 0.0
            row += 1

        # Generation reserve must fit within discharge headroom and cannot coexist with charging.
        if reserve.generation_product_stacking == "common_response_capacity":
            matrix[row, intervals + t] = 1.0
            matrix[row, generation_fir_slice.start + t] = 1.0
            constraint_upper[row] = asset.discharge_power_mw
            row += 1
            matrix[row, generation_fir_slice.start + t] = 1.0
            matrix[row, 3 * intervals + 1 + t] = asset.discharge_power_mw
            constraint_upper[row] = asset.discharge_power_mw
            row += 1
            matrix[row, intervals + t] = 1.0
            matrix[row, generation_sir_slice.start + t] = 1.0
            constraint_upper[row] = asset.discharge_power_mw
            row += 1
            matrix[row, generation_sir_slice.start + t] = 1.0
            matrix[row, 3 * intervals + 1 + t] = asset.discharge_power_mw
            constraint_upper[row] = asset.discharge_power_mw
            row += 1
        else:
            matrix[row, intervals + t] = 1.0
            matrix[row, generation_fir_slice.start + t] = 1.0
            matrix[row, generation_sir_slice.start + t] = 1.0
            constraint_upper[row] = asset.discharge_power_mw
            row += 1
            matrix[row, generation_fir_slice.start + t] = 1.0
            matrix[row, generation_sir_slice.start + t] = 1.0
            matrix[row, 3 * intervals + 1 + t] = asset.discharge_power_mw
            constraint_upper[row] = asset.discharge_power_mw
            row += 1
            matrix[row, intervals + t] = 1.0
            matrix[row, generation_fir_slice.start + t] = 1.0
            constraint_upper[row] = asset.discharge_power_mw
            row += 1
            matrix[row, generation_sir_slice.start + t] = 1.0
            matrix[row, 3 * intervals + 1 + t] = asset.discharge_power_mw
            constraint_upper[row] = asset.discharge_power_mw
            row += 1

        # Only generation reserve has a stored-energy sustain requirement.
        matrix[row, 2 * intervals + t + 1] = 1.0
        matrix[row, generation_fir_slice.start + t] = -reserve.generation_fir.sustain_hours / asset.eta_discharge
        constraint_lower[row] = asset.soc_min_mwh
        row += 1
        matrix[row, 2 * intervals + t + 1] = 1.0
        matrix[row, generation_sir_slice.start + t] = -reserve.generation_sir.sustain_hours / asset.eta_discharge
        constraint_lower[row] = asset.soc_min_mwh
        row += 1

    if asset.max_daily_efc is not None:
        matrix[row, discharge_slice] = HALF_HOUR
        constraint_upper[row] = asset.max_daily_efc * asset.usable_energy_mwh * market["TradingDate"].nunique()

    integrality = np.zeros(variable_count, dtype=int)
    integrality[mode_slice] = 1
    result = milp(
        c=objective,
        integrality=integrality,
        bounds=Bounds(lower_bounds, upper_bounds),
        constraints=LinearConstraint(matrix.tocsr(), constraint_lower, constraint_upper),
        options={
            "time_limit": float(solver_config["time_limit_seconds"]),
            "mip_rel_gap": float(solver_config["mip_relative_gap"]),
            "disp": False,
        },
    )
    if not result.success or result.x is None:
        raise RuntimeError(f"HiGHS did not solve the directional reserve MILP: {result.message}")

    charge = np.clip(result.x[charge_slice], 0.0, None)
    discharge = np.clip(result.x[discharge_slice], 0.0, None)
    soc = result.x[soc_slice]
    mode = np.rint(result.x[mode_slice]).astype(int)
    charge_fir = np.clip(result.x[charge_fir_slice], 0.0, None)
    charge_sir = np.clip(result.x[charge_sir_slice], 0.0, None)
    generation_fir = np.clip(result.x[generation_fir_slice], 0.0, None)
    generation_sir = np.clip(result.x[generation_sir_slice], 0.0, None)
    charge_response = np.maximum(charge_fir, charge_sir) if reserve.charging_product_stacking == "common_response_capacity" else charge_fir + charge_sir
    generation_response = np.maximum(generation_fir, generation_sir) if reserve.generation_product_stacking == "common_response_capacity" else generation_fir + generation_sir

    intervals_out = market.copy()
    intervals_out["charge_mw"] = charge
    intervals_out["discharge_mw"] = discharge
    intervals_out["net_grid_power_mw"] = discharge - charge
    intervals_out["soc_start_mwh"] = soc[:-1]
    intervals_out["soc_end_mwh"] = soc[1:]
    intervals_out["charging_mode"] = mode
    intervals_out["charge_mwh"] = charge * HALF_HOUR
    intervals_out["discharge_mwh"] = discharge * HALF_HOUR
    intervals_out["charge_reserve_response_capacity_mw"] = charge_response
    intervals_out["generation_reserve_response_capacity_mw"] = generation_response
    intervals_out["reserve_response_capacity_mw"] = charge_response + generation_response
    intervals_out["fir_charge_interruptible_load_mw"] = charge_fir
    intervals_out["sir_charge_interruptible_load_mw"] = charge_sir
    intervals_out["fir_generation_reserve_mw"] = generation_fir
    intervals_out["sir_generation_reserve_mw"] = generation_sir
    intervals_out["fir_offer_mw"] = charge_fir + generation_fir
    intervals_out["sir_offer_mw"] = charge_sir + generation_sir
    intervals_out["energy_export_revenue_nzd"] = intervals_out["discharge_mwh"] * price
    intervals_out["energy_import_cashflow_nzd"] = -intervals_out["charge_mwh"] * price
    intervals_out["fir_charge_interruptible_load_revenue_nzd"] = charge_fir * fir_price * HALF_HOUR
    intervals_out["sir_charge_interruptible_load_revenue_nzd"] = charge_sir * sir_price * HALF_HOUR
    intervals_out["fir_generation_reserve_revenue_nzd"] = generation_fir * fir_price * HALF_HOUR
    intervals_out["sir_generation_reserve_revenue_nzd"] = generation_sir * sir_price * HALF_HOUR
    intervals_out["fir_reserve_revenue_nzd"] = (
        intervals_out["fir_charge_interruptible_load_revenue_nzd"] + intervals_out["fir_generation_reserve_revenue_nzd"]
    )
    intervals_out["sir_reserve_revenue_nzd"] = (
        intervals_out["sir_charge_interruptible_load_revenue_nzd"] + intervals_out["sir_generation_reserve_revenue_nzd"]
    )
    intervals_out["discharge_variable_cost_nzd"] = -intervals_out["discharge_mwh"] * float(
        costs.get("discharge_variable_cost_per_mwh", costs.get("degradation_cost_per_mwh_discharged", 0.0))
    )
    intervals_out["degradation_cost_nzd"] = intervals_out["discharge_variable_cost_nzd"]
    intervals_out["frequency_keeping_cost_nzd"] = -intervals_out["charge_mwh"] * float(
        costs.get("frequency_keeping_charge_per_mwh_imported", 0.0)
    )
    intervals_out["trading_import_cost_nzd"] = -intervals_out["charge_mwh"] * float(costs.get("trading_charge_per_mwh_imported", 0.0))
    intervals_out["trading_export_cost_nzd"] = -intervals_out["discharge_mwh"] * float(costs.get("trading_charge_per_mwh_exported", 0.0))
    intervals_out["ir_allocation_cost_nzd"] = -intervals_out["discharge_mwh"] * float(
        costs.get("instantaneous_reserve_cost_per_mwh_exported", 0.0)
    )
    intervals_out["fixed_opex_cost_nzd"] = -(
        float(costs["fixed_opex_annual_nzd"]) + float(costs["transmission_and_connection_annual_nzd"])
    ) / 365.0 / 48.0
    cashflow_columns = [
        "energy_export_revenue_nzd",
        "energy_import_cashflow_nzd",
        "fir_reserve_revenue_nzd",
        "sir_reserve_revenue_nzd",
        "discharge_variable_cost_nzd",
        "frequency_keeping_cost_nzd",
        "trading_import_cost_nzd",
        "trading_export_cost_nzd",
        "ir_allocation_cost_nzd",
        "fixed_opex_cost_nzd",
    ]
    intervals_out["variable_margin_nzd"] = intervals_out[cashflow_columns[:-1]].sum(axis=1)
    intervals_out["net_cashflow_nzd"] = intervals_out[cashflow_columns].sum(axis=1)

    calculated_margin = float(intervals_out["variable_margin_nzd"].sum())
    if not np.isclose(calculated_margin, -float(result.fun), atol=1e-3):
        raise RuntimeError("Directional reserve MILP objective does not reconcile to calculated variable margin.")
    if not np.all(charge * discharge < 1e-5):
        raise RuntimeError("Simultaneous charging and discharging detected.")
    if not np.isclose(soc[0], soc[-1], atol=1e-5):
        raise RuntimeError("Terminal state of charge does not reconcile to initial state of charge.")
    if not np.all(charge_response <= charge + 1e-5):
        raise RuntimeError("Interruptible-load reserve exceeds scheduled charging load.")
    if not np.all(discharge + generation_response <= asset.discharge_power_mw + 1e-5):
        raise RuntimeError("Generation reserve exceeds discharge headroom.")
    if not np.all(generation_response <= asset.discharge_power_mw * (1 - mode) + 1e-5):
        raise RuntimeError("Generation reserve was offered while charging.")
    if not np.all(soc[1:] - generation_fir * reserve.generation_fir.sustain_hours / asset.eta_discharge >= asset.soc_min_mwh - 1e-5):
        raise RuntimeError("Generation FIR offer does not retain sufficient stored energy.")
    if not np.all(soc[1:] - generation_sir * reserve.generation_sir.sustain_hours / asset.eta_discharge >= asset.soc_min_mwh - 1e-5):
        raise RuntimeError("Generation SIR offer does not retain sufficient stored energy.")

    return intervals_out, {
        "solver": "HiGHS via scipy.optimize.milp",
        "dispatch_case": "directional_fir_sir_price_taker",
        "solver_status": int(result.status),
        "solver_message": result.message,
        "objective_variable_margin_nzd": calculated_margin,
        "mip_gap": None if getattr(result, "mip_gap", None) is None else float(result.mip_gap),
        "usable_energy_mwh": asset.usable_energy_mwh,
        "charge_power_mw": asset.charge_power_mw,
        "discharge_power_mw": asset.discharge_power_mw,
        "initial_soc_mwh": asset.initial_soc_mwh,
        "terminal_soc_mwh": float(soc[-1]),
        "reserve_case_status": "illustrative_directional_price_taker_upper_bound",
        "charging_reserve_mechanism": "interruptible_load",
        "charging_product_stacking": reserve.charging_product_stacking,
        "generation_product_stacking": reserve.generation_product_stacking,
        "activation_energy_modelled": False,
    }


def solve_energy_dispatch(market: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Optimise energy arbitrage only with a binary operating-mode constraint."""
    return _solve_dispatch(market, config, reserve_scenario=None)


def solve_fir_sir_price_taker_dispatch(
    market: pd.DataFrame, config: dict[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Optimise energy plus configured FIR/SIR price-taker reserve capability."""
    asset = asset_from_config(config)
    reserve_config = config.get("reserve_price_taker", {})
    if "charging_interruptible_load" in reserve_config or "discharging_generation" in reserve_config:
        return _solve_directional_reserve_dispatch(
            market, config, directional_reserve_scenario_from_config(config, asset)
        )
    return _solve_dispatch(market, config, reserve_scenario_from_config(config, asset))


def revalue_dispatch(intervals: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """Apply a different cost case to an already optimised physical dispatch.

    This is intended for capital and operating-cost sensitivities. It does not claim
    that the dispatch would remain optimal after a changed variable operating cost.
    """
    costs = config["operating_costs"]
    result = intervals.copy()
    result["discharge_variable_cost_nzd"] = -result["discharge_mwh"] * float(
        costs.get("discharge_variable_cost_per_mwh", costs.get("degradation_cost_per_mwh_discharged", 0.0))
    )
    result["degradation_cost_nzd"] = result["discharge_variable_cost_nzd"]
    result["frequency_keeping_cost_nzd"] = -result["charge_mwh"] * float(
        costs.get("frequency_keeping_charge_per_mwh_imported", 0.0)
    )
    result["trading_import_cost_nzd"] = -result["charge_mwh"] * float(
        costs.get("trading_charge_per_mwh_imported", 0.0)
    )
    result["trading_export_cost_nzd"] = -result["discharge_mwh"] * float(
        costs.get("trading_charge_per_mwh_exported", 0.0)
    )
    result["ir_allocation_cost_nzd"] = -result["discharge_mwh"] * float(
        costs.get("instantaneous_reserve_cost_per_mwh_exported", 0.0)
    )
    result["fixed_opex_cost_nzd"] = -(
        float(costs["fixed_opex_annual_nzd"]) + float(costs["transmission_and_connection_annual_nzd"])
    ) / 365.0 / 48.0
    cashflow_columns = [
        "energy_export_revenue_nzd",
        "energy_import_cashflow_nzd",
        "fir_reserve_revenue_nzd",
        "sir_reserve_revenue_nzd",
        "discharge_variable_cost_nzd",
        "frequency_keeping_cost_nzd",
        "trading_import_cost_nzd",
        "trading_export_cost_nzd",
        "ir_allocation_cost_nzd",
        "fixed_opex_cost_nzd",
    ]
    result["variable_margin_nzd"] = result[cashflow_columns[:-1]].sum(axis=1)
    result["net_cashflow_nzd"] = result[cashflow_columns].sum(axis=1)
    return result
