from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bess_model.data import configured_months, configured_period_label


class DataConfigTests(unittest.TestCase):
    def test_single_month_is_retained(self) -> None:
        config = {"month": "2026-06"}
        self.assertEqual(configured_months(config), ["2026-06"])
        self.assertEqual(configured_period_label(config), "2026-06")

    def test_inclusive_historic_range_is_expanded(self) -> None:
        config = {"start_month": "2025-07", "end_month": "2026-06"}
        months = configured_months(config)
        self.assertEqual(len(months), 12)
        self.assertEqual(months[0], "2025-07")
        self.assertEqual(months[-1], "2026-06")
        self.assertEqual(configured_period_label(config), "2025-07_to_2026-06")

    def test_reversed_range_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            configured_months({"start_month": "2026-06", "end_month": "2025-07"})


if __name__ == "__main__":
    unittest.main()
