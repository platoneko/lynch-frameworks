from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import patch


def updater():
    path = Path(__file__).resolve().parents[1] / 'scripts/update_finance_skills.py'
    spec = importlib.util.spec_from_file_location('framework_finance_skills', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def hashes(directory):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob('*') if p.is_file()}


def project(root):
    skills = root / '.claude/skills'
    for name in ('sediment-framework', 'old-finance'):
        (skills / name).mkdir(parents=True)
        (skills / name / 'SKILL.md').write_text(name)
    (skills / '.finance-skills.json').write_text(json.dumps({
        'source': 'himself65/finance-skills', 'skills': {'old-finance': hashes(skills / 'old-finance')}}))
    return skills


def installer(names=('earnings-recap', 'new-finance'), *, fail=False):
    def run(argv, *, cwd, env, check, stdout, text):
        assert 'skills@1.7.6' in argv and 'himself65/finance-skills' in argv
        assert all(n in argv for n in ('claude-code', 'codex', 'grok', 'opencode'))
        assert 'PROVIDER_PRIVATE_TOKEN' not in env
        if fail:
            return SimpleNamespace(returncode=1, stdout='[]')
        for name in names:
            skill = Path(cwd) / '.agents/skills' / name
            (skill / 'references').mkdir(parents=True)
            (skill / 'SKILL.md').write_text(name)
            (skill / 'references/data.md').write_text('reference')
        (Path(cwd) / 'skills-lock.json').write_text(json.dumps({'skills': {
            n: {'source': 'himself65/finance-skills', 'computedHash': 'upstream-hash'} for n in names}}))
        return SimpleNamespace(returncode=0, stdout=json.dumps([
            {'name': n, 'status': 'installed', 'source': 'himself65/finance-skills',
             'agents': ['Claude Code', 'Codex', 'Grok Build', 'OpenCode']} for n in names]))
    return run


class FinanceSkillsTests(unittest.TestCase):
    def setUp(self):
        temporary = Path(__file__).resolve().parents[1] / '_local/tmp'
        temporary.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=temporary)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.skills = project(self.root)
        self.module = updater()

    def install(self, **kwargs):
        with patch.object(self.module.subprocess, 'run', installer(**kwargs)):
            return self.module.update_finance_skills(self.root)

    def test_first_update_of_clean_upstream_checkout(self):
        source = Path(__file__).resolve().parents[1] / '.claude/skills'
        checkout = self.root / 'fresh'
        shutil.copytree(source, checkout / '.claude/skills')
        self.assertFalse((checkout / '.claude/skills/.finance-skills.json').exists())
        with patch.object(self.module.subprocess, 'run', installer(('yfinance-data',))):
            names = self.module.update_finance_skills(checkout)
        self.assertEqual(names, ['yfinance-data'])
        self.assertEqual((checkout / '.claude/skills/sediment-framework/SKILL.md').read_bytes(),
                         (source / 'sediment-framework/SKILL.md').read_bytes())

    def test_concurrent_protected_skill_edit_before_switch_is_preserved(self):
        protected = self.skills / 'sediment-framework/SKILL.md'
        replace = self.module.os.replace

        def edit_before_switch(source, target):
            if Path(source) == self.skills and Path(target).name == 'previous':
                protected.write_text('concurrent user edit')
            return replace(source, target)

        try:
            with patch.object(self.module.os, 'replace', edit_before_switch):
                self.install()
        except self.module.SkillsUpdateError:
            pass
        self.assertEqual(protected.read_text(), 'concurrent user edit')

    def test_edit_through_open_protected_file_during_publish_is_preserved(self):
        protected = self.skills / 'sediment-framework/SKILL.md'
        with protected.open('r+') as stream:
            def edit_after_switch(names):
                stream.seek(0)
                stream.write('late user edit')
                stream.truncate()
                stream.flush()

            with patch.object(self.module.subprocess, 'run', installer()):
                self.module.update_finance_skills(self.root, on_updated=edit_after_switch)
        self.assertEqual(protected.read_text(), 'late user edit')

    def test_unknown_recovery_directory_is_preserved_in_place(self):
        transaction = self.root / '_local/tmp/finance-skills-publication'
        transaction.mkdir(parents=True)
        note = transaction / 'personal.txt'
        note.write_text('personal content')
        with self.assertRaisesRegex(self.module.SkillsUpdateError, '冲突'):
            self.install()
        self.assertEqual(note.read_text(), 'personal content')

    def test_open_managed_file_saved_after_update_remains_active(self):
        managed = self.skills / 'old-finance/SKILL.md'
        with managed.open('r+') as stream:
            self.install(names=('old-finance',))
            stream.seek(0)
            stream.write('edit after update')
            stream.truncate()
            stream.flush()
        backups = list((self.root / '_local/tmp').glob('finance-skills-backup-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'previous/old-finance/SKILL.md').read_text(), 'edit after update')
        self.assertEqual(managed.read_text(), 'edit after update')

    def test_standalone_repository_owns_complete_files_and_internal_agent_entries(self):
        self.assertEqual(self.install(), ['earnings-recap', 'new-finance'])
        for prefix in ('.agents', '.claude', '.grok'):
            for name in ('earnings-recap', 'new-finance', 'sediment-framework'):
                entry = self.root / prefix / 'skills' / name
                self.assertTrue((entry / 'SKILL.md').is_file())
                self.assertTrue(entry.resolve().is_relative_to(self.root))
        self.assertFalse((self.skills / 'earnings-recap').is_symlink())
        self.assertEqual((self.skills / 'earnings-recap/references/data.md').read_text(), 'reference')
        self.assertEqual((self.skills / 'sediment-framework/SKILL.md').read_text(), 'sediment-framework')
        self.assertFalse((self.skills / 'old-finance').exists())
        manifest = json.loads((self.skills / '.finance-skills.json').read_text())
        self.assertEqual(set(manifest['skills']), {'earnings-recap', 'new-finance'})

    def test_failed_install_preserves_files(self):
        before = hashes(self.skills)
        with self.assertRaises(self.module.SkillsUpdateError):
            self.install(fail=True)
        self.assertEqual(hashes(self.skills), before)

    def test_local_edits_and_unmanaged_name_collisions_are_preserved(self):
        for kind in ('edit', 'collision'):
            with self.subTest(kind=kind):
                target = self.skills / ('old-finance/SKILL.md' if kind == 'edit' else 'earnings-recap/SKILL.md')
                target.parent.mkdir(exist_ok=True)
                target.write_text('private change')
                with self.assertRaisesRegex(self.module.SkillsUpdateError, '修改|冲突|覆盖'):
                    self.install()
                self.assertEqual(target.read_text(), 'private change')
                target.unlink()
                if kind == 'edit':
                    target.write_text('old-finance')

    def test_foreign_agent_directory_is_not_overwritten(self):
        entry = self.root / '.agents/skills'
        entry.mkdir(parents=True)
        (entry / 'private').write_text('keep')
        with self.assertRaisesRegex(self.module.SkillsUpdateError, '冲突|覆盖'):
            self.install()
        self.assertEqual((entry / 'private').read_text(), 'keep')
        self.assertEqual((self.skills / 'old-finance/SKILL.md').read_text(), 'old-finance')

    def test_interrupted_directory_publication_restores_old_files_and_can_retry(self):
        before = hashes(self.skills)
        original = self.module.os.replace

        def interrupt(source, target):
            if Path(source).name == 'new-skills' and Path(target) == self.skills:
                raise OSError('publication interrupted')
            return original(source, target)

        with patch.object(self.module.os, 'replace', interrupt):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual(hashes(self.skills), before)
        self.assertEqual(self.install(), ['earnings-recap', 'new-finance'])

    def test_hard_interruption_recovers_on_next_update(self):
        before = hashes(self.skills)
        original = self.module.os.replace

        def interrupt(source, target):
            if Path(source).name == 'new-skills' and Path(target) == self.skills:
                raise KeyboardInterrupt()
            return original(source, target)

        with patch.object(self.module.os, 'replace', interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.install()
        self.assertFalse(self.skills.exists())
        with self.assertRaises(self.module.SkillsUpdateError):
            self.install(fail=True)
        self.assertEqual(hashes(self.skills), before)

    def test_unchanged_update_preserves_file_inodes(self):
        self.install()
        before = (self.skills / 'earnings-recap/SKILL.md').stat().st_ino
        self.install()
        self.assertEqual((self.skills / 'earnings-recap/SKILL.md').stat().st_ino, before)

    def test_concurrent_updates_serialize_installer_publication_and_consumer(self):
        events = []
        install = installer()

        def run(*args, **kwargs):
            events.append('start')
            time.sleep(0.03)
            result = install(*args, **kwargs)
            events.append('installed')
            return result

        def consume(names):
            self.assertEqual(names, sorted(json.loads((self.skills / '.finance-skills.json').read_text())['skills']))
            events.append('consumer')

        with patch.object(self.module.subprocess, 'run', run), ThreadPoolExecutor(max_workers=2) as pool:
            tasks = [pool.submit(self.module.update_finance_skills, self.root, on_updated=consume) for _ in range(2)]
            for task in tasks:
                task.result()
        self.assertEqual(events, ['start', 'installed', 'consumer'] * 2)

    def test_pending_publication_file_and_external_temp_directory_are_preserved(self):
        transaction = self.root / '_local/tmp/finance-skills-publication'
        transaction.parent.mkdir(parents=True, exist_ok=True)
        transaction.write_text('private')
        with self.assertRaisesRegex(self.module.SkillsUpdateError, '冲突'):
            self.install()
        self.assertEqual(transaction.read_text(), 'private')

    def test_upstream_symlinks_are_rejected(self):
        install = installer()

        def run(*args, **kwargs):
            result = install(*args, **kwargs)
            directory = Path(kwargs['cwd']) / '.agents/skills/earnings-recap'
            (directory / 'linked').symlink_to(directory / 'SKILL.md')
            return result

        before = hashes(self.skills)
        with patch.object(self.module.subprocess, 'run', run):
            with self.assertRaisesRegex(self.module.SkillsUpdateError, '软链接'):
                self.module.update_finance_skills(self.root)
        self.assertEqual(hashes(self.skills), before)

    def test_consumer_failure_rolls_back_published_content(self):
        before = hashes(self.skills)

        def fail(names):
            self.assertTrue((self.skills / names[0] / 'SKILL.md').is_file())
            raise OSError('consumer failed')

        with patch.object(self.module.subprocess, 'run', installer()):
            with self.assertRaises(OSError):
                self.module.update_finance_skills(self.root, on_updated=fail)
        self.assertEqual(hashes(self.skills), before)

    def test_consumer_repaired_after_hard_interruption_before_offline_retry(self):
        before = hashes(self.skills)

        def interrupt(names):
            raise KeyboardInterrupt()

        with patch.object(self.module.subprocess, 'run', installer()):
            with self.assertRaises(KeyboardInterrupt):
                self.module.update_finance_skills(self.root, on_updated=interrupt)
        events = []

        def repair(names):
            self.assertEqual(hashes(self.skills), before)
            events.append(names)

        with patch.object(self.module.subprocess, 'run', installer(fail=True)):
            with self.assertRaises(self.module.SkillsUpdateError):
                self.module.update_finance_skills(self.root, on_updated=repair)
        self.assertEqual(events, [['old-finance']])

    def test_commit_failure_restores_consumer_after_content_rollback(self):
        events = []
        rename = Path.rename

        def fail_commit(path, target):
            if Path(target).name.startswith('finance-skills-backup-'):
                raise OSError('commit failed')
            return rename(path, target)

        with patch.object(self.module.subprocess, 'run', installer()), patch.object(Path, 'rename', fail_commit):
            with self.assertRaisesRegex(OSError, 'commit failed'):
                self.module.update_finance_skills(self.root, on_updated=events.append)
        self.assertEqual(events, [['earnings-recap', 'new-finance'], ['old-finance']])

    def test_failed_consumer_repair_is_retried_even_if_installer_will_fail(self):
        def interrupt(names):
            raise KeyboardInterrupt()

        with patch.object(self.module.subprocess, 'run', installer()):
            with self.assertRaises(KeyboardInterrupt):
                self.module.update_finance_skills(self.root, on_updated=interrupt)

        def fail_repair(names):
            raise OSError('repair failed')

        with patch.object(self.module.subprocess, 'run', installer(fail=True)):
            with self.assertRaisesRegex(OSError, 'repair failed'):
                self.module.update_finance_skills(self.root, on_updated=fail_repair)
            events = []
            with self.assertRaises(self.module.SkillsUpdateError):
                self.module.update_finance_skills(self.root, on_updated=events.append)
        self.assertEqual(events, [['old-finance']])

    def test_consumer_marker_is_published_complete_before_callback(self):
        replace = self.module.os.replace
        marker = self.root / '_local/tmp/finance-skills-consumer-recovery'

        def interrupt(source, target):
            if Path(target) == marker:
                self.assertEqual(Path(source).read_text(), 'pending\n')
                raise KeyboardInterrupt()
            return replace(source, target)

        with patch.object(self.module.subprocess, 'run', installer()), patch.object(self.module.os, 'replace', interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.module.update_finance_skills(self.root, on_updated=lambda names: None)
        self.assertFalse(marker.exists())
        with patch.object(self.module.subprocess, 'run', installer(fail=True)):
            with self.assertRaisesRegex(self.module.SkillsUpdateError, '安装失败'):
                self.module.update_finance_skills(self.root, on_updated=lambda names: None)

    def test_invalid_success_and_reserved_names_do_not_change_existing_files(self):
        for names in ((), ('sediment-framework',), ('../escape',)):
            with self.subTest(names=names):
                before = hashes(self.skills)
                with self.assertRaises(self.module.SkillsUpdateError):
                    self.install(names=names)
                self.assertEqual(hashes(self.skills), before)


if __name__ == '__main__':
    unittest.main()
