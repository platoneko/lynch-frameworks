"""Optional-value status with fictional inputs and no stock execution."""

import unittest

from eval.lib.valuation_guards import nonnegative_option_value
from eval.lib.licensing import bind_ladder


class OptionalValueTests(unittest.TestCase):
    def test_negative_value_is_unavailable_not_a_negative_credit(self):
        self.assertIsNone(nonnegative_option_value(-0.01))
        self.assertEqual(nonnegative_option_value(0), 0)
        self.assertEqual(nonnegative_option_value(5.2), 5.2)

    def test_invalid_value_is_not_treated_as_zero(self):
        for value in (float('nan'), float('inf'), True, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                nonnegative_option_value(value)


class LicensingLadderTests(unittest.TestCase):
    def test_shared_ladder_is_bound_and_conflicting_local_copy_is_rejected(self):
        ladder = {'id': 'patent_licensing_annuity_evebit', 'version': '2000-01-01',
                  'measure': 'pre_tax_ev_ebit',
                  'businesses': {'QCOM.US': 'qtl', 'NOK.US': 'technology_standards'},
                  'tiers': {'l': 5., 'm': 8., 'h': 12.}}
        for ticker in ('QCOM.US', 'NOK.US'):
            with self.subTest(ticker=ticker):
                bound = bind_ladder({'independent': 1}, ladder, ticker)
                self.assertEqual(bound['ev_ebit_ts_m'], 8.)
                with self.assertRaises(ValueError):
                    bind_ladder({'ev_ebit_ts_m': 9.}, ladder, ticker)


if __name__ == '__main__':
    unittest.main()
