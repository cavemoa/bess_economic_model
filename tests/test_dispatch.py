from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bess_model.dispatch import solve_energy_dispatch, solve_fir_sir_price_taker_dispatch
from bess_model.finance import calculate_project_npv


def tiny_config() -> dict:
    return {
        "asset": {
            "power_mw": 10.0,
            "nominal_energy_mwh": 10.0,
            "soc_min_fraction": 0.0,
            "soc_max_fraction": 1.0,
            "initial_soc_fraction": 0.0,
            "round_trip_efficiency": 1.0,
            "max_equivalent_full_cycles_per_day": None,
        },
        "operating_costs": {
            "degradation_cost_per_mwh_discharged": 0.0,
            "frequency_keeping_charge_per_mwh_imported": 0.0,
            "trading_charge_per_mwh_imported": 0.0,
            "trading_charge_per_mwh_exported": 0.0,
            "instantaneous_reserve_cost_per_mwh_exported": 0.0,
            "fixed_opex_annual_nzd": 0.0,
            "transmission_and_connection_annual_nzd": 0.0,
        },
        "solver": {"time_limit_seconds": 30, "mip_relative_gap": 0.0},
        "finance": {
            "project_life_years": 2,
            "real_discount_rate": 0.1,
            "annualisation_factor": 12,
            "annual_variable_margin_fade": 0.0,
            "project_capex_nzd": 100.0,
            "augmentation": [],
        },
    }


class DispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.market = pd.DataFrame(
            {
                "timestamp_nz": pd.date_range("2026-06-01", periods=4, freq="30min"),
                "TradingDate": ["2026-06-01"] * 4,
                "TradingPeriod": [1, 2, 3, 4],
                "sfd_price_nzd_per_mwh": [10.0, 20.0, 100.0, 30.0],
                "fir_price_nzd_per_mwh": [0.0] * 4,
                "sir_price_nzd_per_mwh": [0.0] * 4,
            }
        )

    def test_milp_respects_operating_constraints_and_selects_spread(self) -> None:
        intervals, meta = solve_energy_dispatch(self.market, tiny_config())
        self.assertAlmostEqual(float(intervals["soc_start_mwh"].iloc[0]), 0.0, places=6)
        self.assertAlmostEqual(float(intervals["soc_end_mwh"].iloc[-1]), 0.0, places=6)
        self.assertTrue(((intervals["charge_mw"] * intervals["discharge_mw"]) < 1e-6).all())
        self.assertLessEqual(float(intervals["charge_mw"].max()), 10.0 + 1e-6)
        self.assertLessEqual(float(intervals["discharge_mw"].max()), 10.0 + 1e-6)
        self.assertAlmostEqual(float(intervals["charge_mw"].iloc[0]), 10.0, places=6)
        self.assertAlmostEqual(float(intervals["discharge_mw"].iloc[2]), 10.0, places=6)
        # The 10 MWh battery charges in both lower-priced intervals and empties
        # across both higher-priced intervals: 5*(100 + 30 - 10 - 20) = $500.
        self.assertAlmostEqual(meta["objective_variable_margin_nzd"], 500.0, places=6)

    def test_finance_includes_initial_capex(self) -> None:
        intervals, _ = solve_energy_dispatch(self.market, tiny_config())
        cashflows, meta = calculate_project_npv(intervals, tiny_config())
        self.assertEqual(len(cashflows), 3)
        self.assertAlmostEqual(float(cashflows.loc[0, "net_cashflow_nzd"]), -100.0, places=6)
        self.assertGreater(meta["npv_nzd"], -100.0)

    def test_shared_fir_sir_response_capacity_earns_both_products(self) -> None:
        market = pd.DataFrame(
            {
                "timestamp_nz": pd.date_range("2026-06-01", periods=1, freq="30min"),
                "TradingDate": ["2026-06-01"],
                "TradingPeriod": [1],
                "sfd_price_nzd_per_mwh": [0.0],
                "fir_price_nzd_per_mwh": [2.0],
                "sir_price_nzd_per_mwh": [3.0],
            }
        )
        config = tiny_config()
        config["asset"]["initial_soc_fraction"] = 0.1
        config["reserve_price_taker"] = {
            "max_offer_mw": 10.0,
            "product_stacking": "common_response_capacity",
            "fir_sustain_minutes": 1.0,
            "sir_sustain_minutes": 15.0,
        }

        intervals, meta = solve_fir_sir_price_taker_dispatch(market, config)

        # The 1 MWh stored above minimum supports 4 MW for a 15-minute SIR response,
        # while the one-minute FIR response can use the full 10 MW inverter capacity.
        self.assertAlmostEqual(float(intervals["reserve_response_capacity_mw"].iloc[0]), 10.0, places=6)
        self.assertAlmostEqual(float(intervals["fir_offer_mw"].iloc[0]), 10.0, places=6)
        self.assertAlmostEqual(float(intervals["sir_offer_mw"].iloc[0]), 4.0, places=6)
        self.assertAlmostEqual(float(intervals["fir_reserve_revenue_nzd"].sum()), 10.0, places=6)
        self.assertAlmostEqual(float(intervals["sir_reserve_revenue_nzd"].sum()), 6.0, places=6)
        self.assertAlmostEqual(meta["objective_variable_margin_nzd"], 16.0, places=6)

    def test_directional_charge_stack_earns_fir_and_sir_against_scheduled_load(self) -> None:
        market = pd.DataFrame(
            {
                "timestamp_nz": pd.date_range("2026-06-01", periods=2, freq="30min"),
                "TradingDate": ["2026-06-01"] * 2,
                "TradingPeriod": [1, 2],
                "sfd_price_nzd_per_mwh": [0.0, 0.0],
                "fir_price_nzd_per_mwh": [2.0, 0.0],
                "sir_price_nzd_per_mwh": [3.0, 0.0],
            }
        )
        config = tiny_config()
        config["reserve_price_taker"] = {
            "charging_interruptible_load": {
                "product_stacking": "common_response_capacity",
                "fir": {"enabled": True, "max_offer_mw": 10.0, "sustain_minutes": 1.0},
                "sir": {"enabled": True, "max_offer_mw": 10.0, "sustain_minutes": 15.0},
            },
            "discharging_generation": {
                "product_stacking": "exclusive_capacity",
                "fir": {"enabled": False, "max_offer_mw": 0.0, "sustain_minutes": 1.0},
                "sir": {"enabled": False, "max_offer_mw": 0.0, "sustain_minutes": 15.0},
            },
        }

        intervals, meta = solve_fir_sir_price_taker_dispatch(market, config)

        self.assertEqual(meta["dispatch_case"], "directional_fir_sir_price_taker")
        self.assertAlmostEqual(float(intervals["fir_charge_interruptible_load_mw"].iloc[0]), 10.0, places=6)
        self.assertAlmostEqual(float(intervals["sir_charge_interruptible_load_mw"].iloc[0]), 10.0, places=6)
        self.assertLessEqual(
            float((intervals["charge_reserve_response_capacity_mw"] - intervals["charge_mw"]).max()), 1e-6
        )
        self.assertAlmostEqual(float(intervals["fir_reserve_revenue_nzd"].sum()), 10.0, places=6)
        self.assertAlmostEqual(float(intervals["sir_reserve_revenue_nzd"].sum()), 15.0, places=6)

    def test_directional_generation_sir_holds_15_minute_energy_cover(self) -> None:
        market = pd.DataFrame(
            {
                "timestamp_nz": pd.date_range("2026-06-01", periods=1, freq="30min"),
                "TradingDate": ["2026-06-01"],
                "TradingPeriod": [1],
                "sfd_price_nzd_per_mwh": [0.0],
                "fir_price_nzd_per_mwh": [0.0],
                "sir_price_nzd_per_mwh": [3.0],
            }
        )
        config = tiny_config()
        config["asset"]["initial_soc_fraction"] = 0.1
        config["reserve_price_taker"] = {
            "charging_interruptible_load": {
                "fir": {"enabled": False},
                "sir": {"enabled": False},
            },
            "discharging_generation": {
                "product_stacking": "exclusive_capacity",
                "fir": {"enabled": False},
                "sir": {"enabled": True, "max_offer_mw": 10.0, "sustain_minutes": 15.0},
            },
        }

        intervals, _ = solve_fir_sir_price_taker_dispatch(market, config)

        # 1 MWh above minimum sustains exactly 4 MW for 15 minutes at unit efficiency.
        self.assertAlmostEqual(float(intervals["sir_generation_reserve_mw"].iloc[0]), 4.0, places=6)
        self.assertAlmostEqual(float(intervals["fir_generation_reserve_mw"].sum()), 0.0, places=6)
        self.assertAlmostEqual(float(intervals["sir_reserve_revenue_nzd"].sum()), 6.0, places=6)


if __name__ == "__main__":
    unittest.main()
