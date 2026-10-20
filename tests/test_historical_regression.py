"""Slow historical regression tests, enabled explicitly before release runs."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bess_model.configuration import load_study_config
from bess_model.data import load_market_data
from bess_model.dispatch import solve_energy_dispatch, solve_fir_sir_price_taker_dispatch
from bess_model.finance import calculate_project_npv


@unittest.skipUnless(
    os.getenv("RUN_HISTORICAL_REGRESSION") == "1",
    "Set RUN_HISTORICAL_REGRESSION=1 to run cached June and annual HiGHS regressions.",
)
class HistoricalBessRegressionTests(unittest.TestCase):
    def _assert_case(self, filename: str, energy_margin: float, energy_npv: float, reserve_margin: float, reserve_npv: float) -> None:
        config = load_study_config(PROJECT_ROOT / "config" / filename)
        market, _ = load_market_data(config, PROJECT_ROOT)
        energy, _ = solve_energy_dispatch(market, config)
        _, energy_finance = calculate_project_npv(energy, config)
        reserve, _ = solve_fir_sir_price_taker_dispatch(market, config)
        _, reserve_finance = calculate_project_npv(reserve, config)
        self.assertAlmostEqual(float(energy["variable_margin_nzd"].sum()), energy_margin, places=3)
        self.assertAlmostEqual(float(energy_finance["npv_nzd"]), energy_npv, places=3)
        self.assertAlmostEqual(float(reserve["variable_margin_nzd"].sum()), reserve_margin, places=3)
        self.assertAlmostEqual(float(reserve_finance["npv_nzd"]), reserve_npv, places=3)

    def test_june_2026_result_is_preserved(self) -> None:
        self._assert_case(
            "base_case.yaml",
            105_802.22475542716,
            -160_845_686.49144962,
            221_921.45892479375,
            -148_504_002.28869367,
        )

    def test_annual_2024_12_to_2025_11_result_is_preserved(self) -> None:
        self._assert_case(
            "annual_complete_2024-12_to_2025-11.yaml",
            5_518_892.082749823,
            -123_209_737.07347804,
            8_524_954.796359744,
            -96_584_893.96110941,
        )


if __name__ == "__main__":
    unittest.main()
