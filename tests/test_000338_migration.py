"""Static contracts for the migrated model; never execute a real stock model."""

import ast
from pathlib import Path
import unittest

from eval.lib.gordon import check_g_cap, check_r
from eval.lib.inputs import check_missing, ladder, require_whole_years


SCRIPT = Path(__file__).resolve().parents[1] / 'eval' / '000338.SZ.py'


def function(tree, name):
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def literal_keys(node):
    return {key.value for key in node.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)}


class WeichaiMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(SCRIPT.read_text())
        cls.evaluate = function(cls.tree, 'evaluate')
        cls.calculate = function(cls.tree, 'calculate')

    def test_unified_entry_receives_declared_southbound_reference(self):
        assignment = next(node for node in self.tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'DEPENDENCIES' for t in node.targets))
        self.assertEqual(ast.literal_eval(assignment.value)['axes']['southbound'], 'southbound_repricing')
        calls = [node for node in ast.walk(self.calculate) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == 'evaluate']
        self.assertEqual(len(calls), 1)
        self.assertEqual(ast.unparse(calls[0].args[1]), "context['axes']['southbound']")
        self.assertIn('historical_southbound_reference_unavailable', ast.unparse(self.evaluate))

    def test_shared_guards_with_invented_inputs(self):
        self.assertTrue(check_missing({'earnings': 2}, ['earnings', 'shares']))
        self.assertEqual(check_missing({'earnings': 2, 'shares': 10}, ['earnings', 'shares']), [])
        self.assertEqual(check_r(.10, 'synthetic', 4), [])
        self.assertTrue(check_r(.13, 'synthetic', 4))
        self.assertEqual(check_g_cap(.02, .10, 'synthetic'), [])
        self.assertTrue(check_g_cap(.07, .10, 'synthetic'))
        self.assertEqual(ladder('synthetic', 1., 2., 3.), [])
        self.assertTrue(ladder('synthetic', 1., 3., 2.))
        for invalid in (2030.5, True, float('nan')):
            with self.subTest(year=invalid), self.assertRaises(ValueError):
                require_whole_years({'year': invalid}, ('year',))

    def test_required_data_and_denominators_fail_loudly(self):
        source = ast.unparse(self.evaluate)
        self.assertIn('check_missing(inp, REQUIRED)', source)
        self.assertIn('math.isfinite(inp[key])', source)
        self.assertIn('require_whole_years(', source)
        self.assertIn('invalid valuation discount or share denominator', source)
        self.assertIn('L<M<H violated', source)

    def test_rule_checks_and_historical_uncertainty_remain_visible(self):
        source = ast.unparse(self.evaluate)
        for check in ('check_r(', 'check_g_cap(', 'g2_power', 'pe_sinotruk_a', 'tau', 'p-class fields'):
            self.assertIn(check, source)
        self.assertIn('historical_input_guards_require_review', source)
        self.assertIn("warnings.append('historical_aftermarket_option_unavailable')", source)

    def test_three_legs_cash_window_option_and_h_share_are_distinct(self):
        returns = [node.value for node in ast.walk(self.evaluate) if isinstance(node, ast.Return)
                   and isinstance(node.value, ast.Dict) and 'ticker' in literal_keys(node.value)]
        self.assertEqual(len(returns), 1)
        fields = {key.value: value for key, value in zip(returns[0].keys, returns[0].values)
                  if isinstance(key, ast.Constant) and isinstance(key.value, str)}
        self.assertEqual(literal_keys(fields['segments']), {'core', 'kion', 'power', 'cash', 'window'})
        self.assertEqual(ast.unparse(fields['anchors']), 'tiers((L, M, H))')
        self.assertEqual(ast.unparse(fields['option']), 'option')
        self.assertEqual(ast.unparse(fields['h_share']), 'h_share')
        source = ast.unparse(self.evaluate)
        self.assertIn('L = sum(parts_l)', source)
        self.assertIn("x / inp['fx_hkdcny']", source)
        option = ast.unparse(function(self.tree, 'aftermarket_option'))
        self.assertIn("'status': 'unavailable'", option)
        self.assertIn("base[tier] + weight * value", option)

    def test_unconfirmed_dates_and_no_markdown_runtime_input(self):
        source = ast.unparse(self.evaluate)
        self.assertIn("'valuation_as_of': None", source)
        self.assertIn("'framework_as_of': None", source)
        for fn in (self.calculate, self.evaluate):
            calls = [ast.unparse(node.func) for node in ast.walk(fn) if isinstance(node, ast.Call)]
            self.assertFalse(any(name.endswith(('read_text', 'read_bytes', 'open')) for name in calls))


if __name__ == '__main__':
    unittest.main(verbosity=2)
