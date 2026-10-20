"""Load composable storage-system, cost-case and market-simulation configurations."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Configuration file {path} must contain a mapping.")
    return data


def _resolved_reference(config_path: Path, reference: str) -> Path:
    path = Path(reference)
    return path if path.is_absolute() else (config_path.parent / path).resolve()


def _currency_multiplier(cost_case: dict[str, Any]) -> float:
    currency = cost_case.get("currency", {})
    code = str(currency.get("code", "NZD")).upper()
    if code == "NZD":
        return 1.0
    if code == "USD":
        try:
            return float(currency["nzd_per_unit"])
        except KeyError as error:
            raise ValueError("USD cost cases require currency.nzd_per_unit.") from error
    raise ValueError(f"Unsupported cost-case currency: {code}")


def _normalise_cost_case(cost_case: dict[str, Any], asset: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    """Convert an investment cost case to the model's existing NZD cost fields."""
    multiplier = _currency_multiplier(cost_case)
    capital = cost_case["capital"]
    model = str(capital.get("model", "direct"))
    discharge_power_mw = float(asset.get("discharge_power_mw", asset.get("power_mw")))
    energy_mwh = float(asset["nominal_energy_mwh"])

    if model == "direct":
        capex = float(capital["project_capex"]) * multiplier
        capital_breakdown = {"direct_project_capex_nzd": capex}
    elif model == "power_and_energy":
        power_island = discharge_power_mw * 1000.0 * float(capital["power_island_cost_per_kw"]) * multiplier
        storage = energy_mwh * 1000.0 * float(capital["storage_cost_per_kwh"]) * multiplier
        interconnection = (
            discharge_power_mw * 1000.0 * float(capital.get("interconnection_cost_per_kw", 0.0)) * multiplier
        )
        capex = power_island + storage + interconnection
        capital_breakdown = {
            "power_island_capex_nzd": power_island,
            "storage_capex_nzd": storage,
            "interconnection_capex_nzd": interconnection,
        }
    else:
        raise ValueError(f"Unsupported capital.model: {model}")

    operating = cost_case.get("operating_costs", {})
    if "fixed_opex_annual" in operating:
        fixed_opex = float(operating["fixed_opex_annual"]) * multiplier
    else:
        fixed_opex = (
            discharge_power_mw * 1000.0 * float(operating.get("fixed_om_per_kw_year", 0.0)) * multiplier
        )
    operating_costs = {
        "discharge_variable_cost_per_mwh": float(
            operating.get("discharge_variable_cost_per_mwh", operating.get("degradation_cost_per_mwh_discharged", 0.0))
        )
        * multiplier,
        "frequency_keeping_charge_per_mwh_imported": float(
            operating.get("frequency_keeping_charge_per_mwh_imported", 0.0)
        )
        * multiplier,
        "trading_charge_per_mwh_imported": float(operating.get("trading_charge_per_mwh_imported", 0.0)) * multiplier,
        "trading_charge_per_mwh_exported": float(operating.get("trading_charge_per_mwh_exported", 0.0)) * multiplier,
        "instantaneous_reserve_cost_per_mwh_exported": float(
            operating.get("instantaneous_reserve_cost_per_mwh_exported", 0.0)
        )
        * multiplier,
        "fixed_opex_annual_nzd": fixed_opex,
        "transmission_and_connection_annual_nzd": float(
            operating.get("transmission_and_connection_annual", 0.0)
        )
        * multiplier,
    }
    metadata = {
        "cost_case_id": cost_case.get("id", "unnamed_cost_case"),
        "cost_case_description": cost_case.get("description"),
        "source_currency": cost_case.get("currency", {"code": "NZD"}),
        "currency_to_nzd_multiplier": multiplier,
        "capital_model": model,
        "capital_breakdown_nzd": capital_breakdown,
        "discharge_variable_cost_label": operating.get("discharge_variable_cost_label", "Discharge variable cost"),
    }
    return {"operating_costs": operating_costs, "project_capex_nzd": capex}, metadata


def load_study_config(
    config_path: Path,
    cost_case_override: Path | None = None,
    asset_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load either a composable study config or a legacy all-in-one config.

    The returned mapping deliberately retains the original ``asset``, ``operating_costs``
    and ``finance`` interface so that optimisation code remains independent of YAML layout.
    """
    config_path = config_path.resolve()
    simulation = _read_yaml(config_path)
    simulation_info = simulation.get("simulation", {})
    system_reference = simulation_info.get("system_file")
    cost_reference = simulation_info.get("cost_case_file")
    if not system_reference or not cost_reference:
        return simulation

    system_path = _resolved_reference(config_path, str(system_reference))
    cost_path = cost_case_override.resolve() if cost_case_override else _resolved_reference(config_path, str(cost_reference))
    system = _read_yaml(system_path)
    cost_case = _read_yaml(cost_path)
    asset = deepcopy(system["asset"])
    if asset_overrides:
        asset.update(asset_overrides)
    normalised, cost_metadata = _normalise_cost_case(cost_case, asset)

    result = deepcopy(simulation)
    result["asset"] = asset
    result["operating_costs"] = normalised["operating_costs"]
    result["reserve_price_taker"] = deepcopy(system.get("reserve_price_taker", {"enabled": False}))
    result.setdefault("finance", {})["project_capex_nzd"] = normalised["project_capex_nzd"]
    result["system"] = {
        "id": system.get("id", "unnamed_system"),
        "technology": system.get("technology", "storage"),
        "description": system.get("description"),
        "source_file": str(system_path),
    }
    result["cost_case"] = {**cost_metadata, "source_file": str(cost_path)}
    return result
