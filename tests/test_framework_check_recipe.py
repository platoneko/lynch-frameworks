"""Exercise just check solely against a fake repository and fake model runner."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
JUSTFILE = Path(os.environ.get('LYNCH_TEST_JUSTFILE', HERE.parent / 'justfile'))
TMP = Path(os.environ.get('LYNCH_TEST_TMPDIR', HERE.parent.parent / '_local/tmp'))
CODE_ROOT = Path(os.environ.get('LYNCH_TEST_CODE_ROOT', HERE.parent.parent))


class CheckRecipe(unittest.TestCase):
    def setUp(self):
        TMP.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='framework-check-fixture-', dir=TMP)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        content = self.root / 'frameworks'
        (content / 'eval').mkdir(parents=True)
        (content / '.claude/skills/sediment-framework').mkdir(parents=True)
        (self.root / 'eval/lib').mkdir(parents=True)
        (self.root / 'eval/__init__.py').touch()
        (self.root / 'eval/lib/__init__.py').touch()
        for filename in ('result_service.py', 'valuation_drafts.py', 'external_history.py'):
            shutil.copyfile(CODE_ROOT / 'eval/lib' / filename, self.root / 'eval/lib' / filename)
        shutil.copyfile(JUSTFILE, content / 'justfile')
        (self.root / 'eval/lib/frameworks.py').write_text('''\
from pathlib import Path
from types import SimpleNamespace
def list_framework_paths(): return sorted(Path("frameworks").glob("*.md"))
def parse_framework_identity(text, stem):
    if not text.startswith("# " + stem + " — "): raise ValueError("wrong identity")
    return SimpleNamespace(ticker=stem)
def price_free_violations(text): return ["current price"] if "BAD_PRICE" in text else []
def load_framework(path):
    if "L=" not in path.read_text(): raise ValueError("missing prose valuation band")
    return SimpleNamespace(ticker=path.stem, consensus=None)
''')
        (self.root / 'eval/lib/valuation_runner.py').write_text('''\
import json, os
from pathlib import Path
def run(code_root, content_root, ticker, *, rate_inputs=None, external_inputs=None, peer_results=None):
    with open(os.environ['FAKE_LOG'], 'a') as file:
        file.write(json.dumps([ticker, str(code_root), str(content_root), rate_inputs, external_inputs, peer_results]) + "\\n")
    if ticker == 'FAIL.US': raise ValueError('fake rule failed')
    if ticker == 'NO_RATE.US' and rate_inputs is not None: raise ValueError('rate inputs not accepted')
    return {'anchors': {'L': 1, 'M': 2, 'H': 3},
            'peer_missing': ['comparison'] if ticker == 'OPTION.US' else []}
''')
        self.log = self.root / 'calls.jsonl'
        self.archive = self.root / 'archived.json'
        self.archive.write_text('["ARCH.US"]')
        self.write_stock('FAKE.US', 'ordinary prose without a machine valuation band')
        self.write_stock('ARCH.US', 'archived unconverted material')
        self.env = {**os.environ, 'LYNCH_FRAMEWORK_ARCHIVE': str(self.archive),
                    'FAKE_LOG': str(self.log), 'PYTHONDONTWRITEBYTECODE': '1'}
        self.env.pop('LYNCH_FRAMEWORK_CHECK_INPUTS', None)
        self.env.pop('LYNCH_VALUATION_SOURCES', None)

    def write_stock(self, ticker, body):
        (self.root / 'frameworks' / (ticker + '.md')).write_text(
            '# ' + ticker + ' — Fake\n> 林奇：`stalwart`\n\n' + body + '\n')
        (self.root / 'frameworks/eval' / (ticker + '.py')).write_text(
            "raise AssertionError('direct stock execution forbidden in this test')\n")

    def run_check(self):
        return subprocess.run(['just', 'check'], cwd=self.root / 'frameworks',
                              env=self.env, text=True, capture_output=True)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def sources(self, external_sources, **additional):
        config = self.root / 'sources.json'
        config.write_text(json.dumps({'code_root': str(self.root), 'content_root': str(self.root / 'frameworks'),
            'tickers': {'FAKE.US': 'USD', 'NEXT.US': 'USD', 'NO_RATE.US': 'USD'},
            'external_sources': external_sources, **additional}))
        self.env['LYNCH_VALUATION_SOURCES'] = str(config)

    def test_runs_unified_interface_and_skips_archived_without_markdown_anchors(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.calls()
        self.assertEqual([call[0] for call in calls], ['FAKE.US'])
        self.assertEqual(calls[0][1:3], [str(self.root), str(self.root / 'frameworks')])

    def test_data_is_explicitly_passed_to_runner(self):
        inputs = self.root / 'inputs.json'
        inputs.write_text(json.dumps({'FAKE.US': {'external_inputs': {'series': [1, 2]},
                                                   'peer_results': {'peer': {'ticker': 'OTHER.US'}},
                                                   'rate_inputs': {'fake_rate': 0.1}}}))
        self.env['LYNCH_FRAMEWORK_CHECK_INPUTS'] = str(inputs)
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls()[0][3:], [{'fake_rate': .1}, {'series': [1, 2]},
                                               {'peer': {'ticker': 'OTHER.US'}}])

    def test_configured_history_reaches_actual_check_without_server_import(self):
        history = self.root / 'history.json'
        history.write_text(json.dumps({'index_history': {'source_ref': 'fake'}}))
        self.sources({'FAKE.US': str(history)}, rate_inputs={'fixture': .03})
        self.write_stock('NO_RATE.US', 'plain text')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = {row[0]: row for row in self.calls()}
        self.assertEqual(calls['FAKE.US'][3:], [None, {'index_history': {'source_ref': 'fake'}}, None])
        self.assertEqual(calls['NO_RATE.US'][3:], [None, None, None])

    def test_missing_one_history_does_not_stop_other_stocks(self):
        self.write_stock('NEXT.US', 'plain text')
        self.sources({'FAKE.US': str(self.root / 'not-found.json')})
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('FAKE.US', result.stderr)
        self.assertEqual([call[0] for call in self.calls()], ['NEXT.US'])

    def test_explicit_override_skips_missing_configured_history(self):
        self.sources({'FAKE.US': str(self.root / 'not-found.json')})
        inputs = self.root / 'inputs.json'
        inputs.write_text(json.dumps({'FAKE.US': {'external_inputs': {'override': True}}}))
        self.env['LYNCH_FRAMEWORK_CHECK_INPUTS'] = str(inputs)
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls()[0][4], {'override': True})

    def test_bad_shared_configuration_is_reported_before_any_stock_runs(self):
        config = self.root / 'sources.json'
        config.write_text('{malformed')
        self.env['LYNCH_VALUATION_SOURCES'] = str(config)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('valuation source configuration unavailable', result.stderr)
        self.assertEqual(self.calls(), [])

    def test_real_failures_are_reported_but_other_tickers_still_checked(self):
        self.write_stock('FAIL.US', 'valid prose')
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('fake rule failed', result.stdout + result.stderr)
        self.assertEqual({row[0] for row in self.calls()}, {'FAIL.US', 'FAKE.US'})

    def test_current_price_rule_remains_enforced(self):
        self.write_stock('FAKE.US', 'BAD_PRICE')
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('current price', result.stdout + result.stderr)

    def test_missing_archive_does_not_silently_include_archived(self):
        self.env.pop('LYNCH_FRAMEWORK_ARCHIVE')
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertIn('LYNCH_FRAMEWORK_ARCHIVE', result.stdout + result.stderr)

    def test_invalid_data_file_fails_before_model_runs(self):
        inputs = self.root / 'inputs.json'
        inputs.write_text(json.dumps({'FAKE.US': {'external_inputs': {}, 'oops': 1}}))
        self.env['LYNCH_FRAMEWORK_CHECK_INPUTS'] = str(inputs)
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_invalid_archive_fails_before_any_model_runs(self):
        self.archive.write_text('{"ARCH.US": true}')
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('archive must contain a list', result.stdout + result.stderr)
        self.assertEqual(self.calls(), [])

    def test_document_identity_is_checked_without_prose_valuation_rows(self):
        (self.root / 'frameworks/FAKE.US.md').write_text('# WRONG.US — Fake\n')
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('wrong identity', result.stdout + result.stderr)
        self.assertEqual(self.calls(), [])

    def test_missing_optional_peer_is_visible_without_erasing_base_result(self):
        self.write_stock('OPTION.US', 'valid prose')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('OPTION.US', result.stdout + result.stderr)
        self.assertIn('comparison', result.stdout + result.stderr)
        self.assertIn('WARN', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
