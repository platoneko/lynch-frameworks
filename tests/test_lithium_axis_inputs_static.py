"""Check the lithium model inputs without importing or executing stock scripts."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {'li2co3_l', 'li2co3_m', 'li2co3_h', 'axis_g2_li'}


class LithiumAxisInputBoundary(unittest.TestCase):
    def test_each_model_selects_numeric_axis_fields_before_evaluation(self):
        for ticker in ('000792.SZ', '9696.HK'):
            with self.subTest(ticker=ticker):
                module = ast.parse((ROOT / 'eval' / f'{ticker}.py').read_text())
                declarations = [node.value for node in module.body if isinstance(node, ast.Assign)
                                and any(isinstance(t, ast.Name) and t.id == 'LITHIUM_INPUTS'
                                        for t in node.targets)]
                self.assertEqual(len(declarations), 1, 'numeric axis field declaration missing')
                self.assertEqual(set(ast.literal_eval(declarations[0])), EXPECTED)
                calculate = next(node for node in module.body
                                 if isinstance(node, ast.FunctionDef) and node.name == 'calculate')
                axis_assignment = next(node for node in calculate.body
                                       if isinstance(node, ast.Assign)
                                       and any(isinstance(t, ast.Name) and t.id == 'axis'
                                               for t in node.targets))
                self.assertIsInstance(axis_assignment.value, ast.DictComp)
                source = ast.unparse(axis_assignment.value)
                self.assertIn('LITHIUM_INPUTS', source)
                self.assertIn("context['axes']['lithium']", source)

    def test_shared_axis_retains_metadata_and_other_consumers(self):
        module = ast.parse((ROOT / 'axes/lithium_carbonate.py').read_text())
        declarations = {t.id: node.value for node in module.body if isinstance(node, ast.Assign)
                        for t in node.targets if isinstance(t, ast.Name)}
        mounts = set(ast.literal_eval(declarations['MOUNTS']))
        self.assertTrue({'000792.SZ', '9696.HK', '1772.HK', '600499.SH'} <= mounts)
        inputs = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'inputs')
        self.assertTrue(any(isinstance(node, ast.Constant) and node.value == 'axis_metadata'
                            for node in ast.walk(inputs)))


if __name__ == '__main__':
    unittest.main()
