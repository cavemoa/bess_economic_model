from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bess_model.configuration import load_study_config


class ComposableConfigurationTests(unittest.TestCase):
    def test_bess_simulation_resolves_to_existing_economic_inputs(self) -> None:
        config = load_study_config(PROJECT_ROOT / "config" / "base_case.yaml")
        self.assertEqual(config["system"]["id"], "bess_huntly_like_100mw_200mwh")
        self.assertEqual(config["asset"]["charge_power_mw"], 100.0)
        self.assertEqual(config["asset"]["discharge_power_mw"], 100.0)
        self.assertEqual(config["finance"]["project_capex_nzd"], 150_000_000.0)
        self.assertEqual(config["operating_costs"]["discharge_variable_cost_per_mwh"], 62.5)
        self.assertTrue(config["reserve_price_taker"]["enabled"])

    def test_acaes_central_case_composes_power_and_energy_capex(self) -> None:
        config = load_study_config(PROJECT_ROOT / "config" / "acaes_sfd2201_annual_sensitivity.yaml")
        self.assertEqual(config["system"]["technology"], "adiabatic_compressed_air_energy_storage")
        self.assertTrue(config["reserve_price_taker"]["enabled"])
        self.assertTrue(config["reserve_price_taker"]["charging_interruptible_load"]["fir"]["enabled"])
        self.assertFalse(config["reserve_price_taker"]["discharging_generation"]["fir"]["enabled"])
        self.assertTrue(config["reserve_price_taker"]["discharging_generation"]["sir"]["enabled"])
        self.assertAlmostEqual(config["finance"]["project_capex_nzd"], 265_650_000.0, places=6)
        self.assertAlmostEqual(config["operating_costs"]["fixed_opex_annual_nzd"], 3_300_000.0, places=6)
        self.assertAlmostEqual(config["operating_costs"]["discharge_variable_cost_per_mwh"], 4.5375, places=6)


if __name__ == "__main__":
    unittest.main()
