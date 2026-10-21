"""Fast capital-cost frontier calculations for a fixed storage dispatch case."""

from __future__ import annotations

import numpy as np
import pandas as pd


def build_npv_cost_surface(
    operating_present_value_nzd: float,
    power_mw: float,
    energy_mwh: float,
    currency_to_nzd: float,
    interconnection_cost_per_kw: float,
    power_island_costs_per_kw: np.ndarray,
    storage_costs_per_kwh: np.ndarray,
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Return the NPV grid and its zero-NPV power-cost frontier.

    The dispatch and all annual operating cashflows are held fixed. Therefore, only
    initial CAPEX changes across the grid and no additional MILP solves are needed.
    Cost axes are in the cost-case source currency; NPV and CAPEX are NZD.
    """
    power_costs = np.asarray(power_island_costs_per_kw, dtype=float)
    storage_costs = np.asarray(storage_costs_per_kwh, dtype=float)
    if power_costs.ndim != 1 or storage_costs.ndim != 1:
        raise ValueError("Cost axes must be one-dimensional arrays.")
    if power_mw <= 0.0 or energy_mwh <= 0.0 or currency_to_nzd <= 0.0:
        raise ValueError("Power, energy and currency conversion must be positive.")
    if np.any(power_costs < 0.0) or np.any(storage_costs < 0.0) or interconnection_cost_per_kw < 0.0:
        raise ValueError("Capital cost inputs must be non-negative.")

    power_kw = power_mw * 1000.0
    energy_kwh = energy_mwh * 1000.0
    power_grid, storage_grid = np.meshgrid(power_costs, storage_costs)
    capex_nzd = currency_to_nzd * (
        power_kw * (power_grid + interconnection_cost_per_kw) + energy_kwh * storage_grid
    )
    npv_nzd = operating_present_value_nzd - capex_nzd
    grid = pd.DataFrame(
        {
            "power_island_cost_per_kw": power_grid.ravel(),
            "storage_cost_per_kwh": storage_grid.ravel(),
            "project_capex_nzd": capex_nzd.ravel(),
            "npv_nzd": npv_nzd.ravel(),
        }
    )
    break_even_power_cost = (
        operating_present_value_nzd / currency_to_nzd
        - power_kw * interconnection_cost_per_kw
        - energy_kwh * storage_costs
    ) / power_kw
    break_even = pd.DataFrame(
        {
            "storage_cost_per_kwh": storage_costs,
            "break_even_power_island_cost_per_kw": break_even_power_cost,
        }
    )
    return grid, break_even, npv_nzd
