"""Scenario NPV calculation built from a historic model-period operating result."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def calculate_project_npv(intervals: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, float]]:
    """Calculate a transparent pre-tax, unlevered NPV using the configured annualisation."""
    finance = config["finance"]
    costs = config["operating_costs"]
    years = int(finance["project_life_years"])
    discount_rate = float(finance["real_discount_rate"])
    annualisation_factor = float(finance["annualisation_factor"])
    fade = float(finance["annual_variable_margin_fade"])
    capex = float(finance["project_capex_nzd"])
    annual_variable_margin = float(intervals["variable_margin_nzd"].sum()) * annualisation_factor
    annual_fixed_opex = float(costs["fixed_opex_annual_nzd"]) + float(costs["transmission_and_connection_annual_nzd"])
    augmentation_by_year = {
        int(item["year"]): float(item["cost_nzd"])
        for item in finance.get("augmentation", [])
    }

    records = [
        {
            "year": 0,
            "variable_margin_nzd": 0.0,
            "fixed_opex_nzd": 0.0,
            "augmentation_nzd": 0.0,
            "net_cashflow_nzd": -capex,
            "discount_factor": 1.0,
            "present_value_nzd": -capex,
        }
    ]
    for year in range(1, years + 1):
        variable_margin = annual_variable_margin * (1.0 - fade) ** (year - 1)
        augmentation = augmentation_by_year.get(year, 0.0)
        net_cashflow = variable_margin - annual_fixed_opex - augmentation
        discount_factor = 1.0 / (1.0 + discount_rate) ** year
        records.append(
            {
                "year": year,
                "variable_margin_nzd": variable_margin,
                "fixed_opex_nzd": -annual_fixed_opex,
                "augmentation_nzd": -augmentation,
                "net_cashflow_nzd": net_cashflow,
                "discount_factor": discount_factor,
                "present_value_nzd": net_cashflow * discount_factor,
            }
        )

    cashflows = pd.DataFrame(records)
    return cashflows, {
        "npv_nzd": float(cashflows["present_value_nzd"].sum()),
        "annualised_variable_margin_nzd": annual_variable_margin,
        "annual_fixed_opex_nzd": annual_fixed_opex,
        "project_capex_nzd": capex,
        "real_discount_rate": discount_rate,
    }
