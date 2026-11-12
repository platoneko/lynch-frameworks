"""Shared-axis boundaries without executing any stock or axis model."""

import ast
from pathlib import Path
import unittest

from eval.lib.metal_axis_checks import check_aluminium_price_upside


AXES = Path(__file__).resolve().parents[1] / 'axes'


def metadata_expression(axis):
    tree = ast.parse((AXES / f'{axis}.py').read_text())
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == 'inputs')
    candidates = [node for node in ast.walk(function) if isinstance(node, ast.Dict)
                  and any(isinstance(key, ast.Constant) and key.value == 'axis_metadata'
                          for key in node.keys)]
    if len(candidates) != 1:
        raise AssertionError(f'{axis}: expected exactly one axis metadata declaration')
    result = candidates[0]
    return next(value for key, value in zip(result.keys, result.values)
                if isinstance(key, ast.Constant) and key.value == 'axis_metadata')


def fields(node):
    return {key.value: value for key, value in zip(node.keys, node.values)
            if isinstance(key, ast.Constant) and isinstance(key.value, str)}


class SharedAxisContractTest(unittest.TestCase):
    def test_reference_only_axes_do_not_claim_priced_members(self):
        for axis in ('ai_capex', 'optical_comms', 'pluggable_module', 'inp_laser'):
            with self.subTest(axis=axis):
                meta = fields(metadata_expression(axis))
                self.assertEqual(ast.literal_eval(meta['role']), 'reference')
                self.assertEqual(ast.literal_eval(meta['priced_mounts']), [])
                self.assertIn('reference_mounts', meta)

    def test_crypto_reference_does_not_inherit_priced_consensus(self):
        meta = fields(metadata_expression('crypto_cycle'))
        role, consensus = meta['role'], meta['historical_consensus']
        self.assertIsInstance(role, ast.IfExp)
        self.assertEqual(ast.literal_eval(role.body), 'priced')
        self.assertEqual(ast.literal_eval(role.orelse), 'reference')
        self.assertIsInstance(consensus, ast.IfExp)
        self.assertEqual(ast.dump(role.test), ast.dump(consensus.test))
        self.assertIsNone(ast.literal_eval(consensus.orelse))

    def test_cross_commodity_guard_compares_prices_not_smelting_spreads(self):
        # Aluminium price rises 8.3%, while the smelting spread rises 50%;
        # copper rises 20%. Only the full price gives the correct comparison.
        aluminium = {'translated_price': {'M': 120, 'H': 130},
                     'spread_m': 20, 'spread_h': 30,
                     'units': {'translated_price': 'CNY_PER_METRIC_TONNE'}}
        copper = {'prices': {'copper': {'M': 100, 'H': 120}},
                  'units': {'copper': 'USD_PER_METRIC_TONNE'}}
        self.assertTrue(check_aluminium_price_upside(aluminium_axis=aluminium,
                                                      gold_copper_axis=copper))
        aluminium['translated_price']['H'] = 150
        self.assertFalse(check_aluminium_price_upside(aluminium_axis=aluminium,
                                                       gold_copper_axis=copper))


if __name__ == '__main__':
    unittest.main()
