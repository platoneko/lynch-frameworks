"""Static contracts for the migrated model; no real stock execution."""

import ast
from pathlib import Path
import unittest

from eval.lib.gordon import check_basket_pair, check_k_declared, return_path_pe
from eval.lib.inputs import require_whole_years


SCRIPT = Path(__file__).resolve().parents[1] / 'eval' / 'AAOI.US.py'


def function(tree, name):
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def keys(node):
    return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


class AAOIPilotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(SCRIPT.read_text())
        cls.evaluate = function(cls.tree, '_evaluate')
        cls.calculate = function(cls.tree, 'calculate')

    def test_unified_entry_uses_declared_axis_references(self):
        declaration = next(node.value for node in self.tree.body if isinstance(node, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == 'DEPENDENCIES' for t in node.targets))
        axes = ast.literal_eval(declaration)['axes']
        self.assertEqual(axes['pluggable'], 'pluggable_module')
        self.assertEqual(axes['inp_laser'], 'inp_laser')
        source = ast.unparse(self.calculate)
        self.assertIn("context['axes']['pluggable']", source)
        self.assertIn("context['axes']['inp_laser']", source)
        self.assertIn("_evaluate(inp, references, context.get('rate_inputs'))", source)
        self.assertNotIn("inp['g2'] = plug['g2_pluggable']", source)

    def test_missing_nonfinite_and_fractional_inputs_are_guarded(self):
        source = ast.unparse(self.evaluate)
        self.assertIn('check_missing(inp, REQUIRED)', source)
        self.assertIn('inputs must be finite numbers', source)
        self.assertIn("('y1', 'y2', 'y1_opt', 'y2_opt', 't_opt')", source)
        self.assertIn('model years must be integers', source)
        self.assertIn('float(inp[key]).is_integer()', source)

    def test_shared_return_path_and_guards_with_invented_values(self):
        # Constant 20% return, 2% growth and 10% discount give (1-.02/.20)/(.10-.02).
        value = return_path_pe(2030, 2030, 2032, .20, .02, .20, .10)
        self.assertAlmostEqual(value, 11.25)
        with self.assertRaisesRegex(ValueError, 'years must be integers'):
            return_path_pe(2030, 2030.5, 2032, .20, .02, .20, .10)
        with self.assertRaises(ValueError):
            require_whole_years({'finish_year': 2032.5}, ('finish_year',))
        self.assertEqual(check_basket_pair(.15, .10, 'synthetic', 7, 4), [])
        self.assertTrue(check_k_declared(.15, .10, (0., None, 1.), 'synthetic'))
        self.assertEqual(check_k_declared(.15, .10, (0., .25, 1.), 'synthetic'), [])

    def test_option_credits_and_risk_discount_are_guarded(self):
        source = ast.unparse(self.evaluate)
        self.assertIn('len(P_TIERS) != 3', source)
        self.assertIn('0 <= p <= 1', source)
        self.assertIn('P_TIERS[0] <= P_TIERS[1] <= P_TIERS[2]', source)
        self.assertIn('采用新的增长或回报假设时须同步复核客户集中风险折扣', source)
        self.assertIn('期权价值及修正后的估值区间必须有效且按情景递增', source)

    def test_q3_cash_cases_are_separate_from_base(self):
        q3 = function(self.tree, 'q3_conditions')
        q3_source = ast.unparse(q3)
        for name in ('cash_fully_committed', 'cash_no_extra_gap', 'candidate_fully_committed',
                     'candidate_no_extra_gap', 'is_trial', 'payment_without_gap'):
            self.assertIn(name, q3_source)
        self.assertIn("'is_trial': True", q3_source)
        source = ast.unparse(self.evaluate)
        self.assertIn('q3_errors, conditional = q3_conditions(inp, references)', source)
        self.assertIn('base = dict(anchors)', source)
        returns = [node.value for node in ast.walk(self.evaluate) if isinstance(node, ast.Return)
                   and isinstance(node.value, ast.Dict) and 'ticker' in keys(node.value)]
        self.assertEqual(len(returns), 1)
        fields = {k.value: v for k, v in zip(returns[0].keys, returns[0].values) if isinstance(k, ast.Constant)}
        self.assertEqual(ast.unparse(fields['anchors']), 'base')
        self.assertEqual(ast.unparse(fields['conditional']), 'conditional')
        self.assertIn("'selected_value': rs", ast.unparse(fields['key_parameters']))
        self.assertIn("'reference_value': references['ss_return']", ast.unparse(fields['key_parameters']))
        self.assertIn("min(info['M'][1], rs)", ast.unparse(fields['key_parameters']))

    def test_unconfirmed_dates_and_output_shape(self):
        source = ast.unparse(self.calculate)
        self.assertIn('result[\'valuation_as_of\'] = result[\'framework_as_of\'] = None', source)
        self.assertIn("result['basis_changed'] = None", source)
        self.assertIn("result['partial_basis_changed'] = local_basis_changed(", source)
        self.assertIn('q3_funding_cases_not_adopted', source)
        returned = next(node.value for node in ast.walk(self.evaluate) if isinstance(node, ast.Return)
                        and isinstance(node.value, ast.Dict) and 'ticker' in keys(node.value))
        self.assertTrue({'anchors', 'candidate', 'option', 'segments', 'key_parameters', 'conditional',
                         'sensitivity', 'funding', 'payout', 'rate_sensitivity'} <= keys(returned))

    def test_no_markdown_runtime_read_or_old_json_cli(self):
        for fn in (self.calculate, self.evaluate, function(self.tree, 'q3_conditions')):
            calls = [ast.unparse(node.func) for node in ast.walk(fn) if isinstance(node, ast.Call)]
            self.assertFalse(any(name.endswith(('read_text', 'read_bytes', 'open')) for name in calls))
        self.assertFalse(any(isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'"
                             for node in self.tree.body))


if __name__ == '__main__':
    unittest.main(verbosity=2)
