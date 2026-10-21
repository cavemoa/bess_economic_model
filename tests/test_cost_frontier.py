from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bess_model.cost_frontier import build_npv_cost_surface


class CostFrontierTests(unittest.TestCase):
    def test_capex_surface_and_break_even_line_are_calculated_without_dispatch_re_solves(self) -> None:
        grid, break_even, surface = build_npv_cost_surface(
            operating_present_value_nzd=1_000_000.0,
            power_mw=1.0,
            energy_mwh=2.0,
            currency_to_nzd=1.0,
            interconnection_cost_per_kw=100.0,
            power_island_costs_per_kw=np.array([0.0, 100.0]),
            storage_costs_per_kwh=np.array([0.0, 100.0]),
        )

        self.assertEqual(len(grid), 4)
        self.assertEqual(surface.shape, (2, 2))
        # At zero variable capital cost, only 1 MW x $100/kW connection CAPEX remains.
        self.assertAlmostEqual(float(surface[0, 0]), 900_000.0, places=6)
        # $100/kW power plus $100/kWh storage adds $100k + $200k to connection CAPEX.
        self.assertAlmostEqual(float(surface[1, 1]), 600_000.0, places=6)
        self.assertAlmostEqual(float(break_even.iloc[0]["break_even_power_island_cost_per_kw"]), 900.0, places=6)
        # Two MWh per MW means each $/kWh reduces break-even $/kW by two.
        self.assertAlmostEqual(float(break_even.iloc[1]["break_even_power_island_cost_per_kw"]), 700.0, places=6)


if __name__ == "__main__":
    unittest.main()
