"""Migrated adapters declare the code and axes they actually depend on."""

import ast
from pathlib import Path
import unittest


CONTENT = Path(__file__).resolve().parents[1]
TICKERS = ('AAOI.US', '1810.HK', '600900.SH', '601975.SH', '600309.SH', '000338.SZ')


class StockDependencyTests(unittest.TestCase):
    def test_selected_stocks_declare_imported_libraries_and_existing_axes(self):
        for ticker in TICKERS:
            with self.subTest(ticker=ticker):
                tree = ast.parse((CONTENT / 'eval' / f'{ticker}.py').read_text())
                declaration = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                                   and any(isinstance(target, ast.Name) and target.id == 'DEPENDENCIES'
                                           for target in node.targets))
                dependencies = ast.literal_eval(declaration)
                imports = {node.module.split('.', 1)[1] for node in ast.walk(tree)
                           if isinstance(node, ast.ImportFrom) and node.module
                           and node.module.startswith('lib.')}
                self.assertEqual(imports, set(dependencies['libraries']))
                self.assertFalse(any(isinstance(node, ast.ImportFrom) and node.module
                                     and node.module.startswith('eval.lib') for node in ast.walk(tree)))
                for axis in dependencies['axes'].values():
                    self.assertTrue((CONTENT / 'axes' / f'{axis}.py').is_file(), axis)


if __name__ == '__main__':
    unittest.main()
