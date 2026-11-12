"""Static wiring guards: these tests never import either stock model."""
import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def top_assignment(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not declared")


class StockWiringStatic(unittest.TestCase):
    def test_both_stocks_declare_shared_axes_and_do_not_store_their_values(self):
        specifications = {
            '000100.SZ': ({'panel': 'lcd_tv_panel'}, {'r_display', 'r_display_ref', 'life_l', 'life_m', 'life_h'}),
            '000725.SZ': ({'panel': 'lcd_tv_panel', 'glass': 'glass_core_substrate'},
                          {'r_perp', 'r_perp_ref', 'life_l', 'life_m', 'life_h',
                           'gcs_abs_rev_usd', 'gcs_abs_cap_m2', 'gcs_panel_m2', 'gcs_price_h_usd',
                           'gcs_opm_weak', 'gcs_opm_strong', 'gcs_yield_disc', 'g2_gcs_src'}),
        }
        for ticker, (axes, shared_fields) in specifications.items():
            with self.subTest(ticker=ticker):
                text = (ROOT / 'eval' / f'{ticker}.py').read_text()
                tree = ast.parse(text)
                self.assertEqual(top_assignment(tree, 'DEPENDENCIES')['axes'], axes)
                self.assertTrue(shared_fields.isdisjoint(top_assignment(tree, 'INPUTS')))
                self.assertIn('calculate', {node.name for node in tree.body if isinstance(node, ast.FunctionDef)})
                self.assertNotIn('PANEL_AXIS', text)
                self.assertNotIn('GCS_AXIS', text)
                self.assertNotIn('parse_inputs', text)
                self.assertIn("context['axes']", text)
                self.assertNotIn('from eval.lib', text)

    def test_tcl_checks_whole_years_but_keeps_fractional_discount_durations(self):
        tree = ast.parse((ROOT / 'eval' / '000100.SZ.py').read_text())
        call_sources = [ast.unparse(node) for node in ast.walk(tree)
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == 'require_whole_years']
        self.assertTrue(call_sources)
        self.assertTrue(any('release_years' in call for call in call_sources))
        self.assertFalse(any('tau' in call or 'unspent_years' in call for call in call_sources))

    def test_boe_uses_shared_glass_rule_before_publishing(self):
        tree = ast.parse((ROOT / 'eval' / '000725.SZ.py').read_text())
        self.assertIn('glass_ruler_rules', top_assignment(tree, 'DEPENDENCIES')['libraries'])
        calls = [ast.unparse(node) for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == 'check_glass_ruler']
        self.assertEqual(len(calls), 1)
        self.assertIn('gcs', calls[0])


if __name__ == '__main__':
    unittest.main()
