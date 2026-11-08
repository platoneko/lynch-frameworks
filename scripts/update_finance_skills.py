#!/usr/bin/env python3
"""Update the content repository's vendored finance skills without a lynch checkout."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Callable
import uuid

SOURCE = 'himself65/finance-skills'
AGENTS = {'claude-code': 'Claude Code', 'codex': 'Codex', 'grok': 'Grok Build', 'opencode': 'OpenCode'}
INSTALLER = ('npx', '--yes', '--package', 'node@22.20.0', '--package', 'skills@1.7.6', 'skills')
MANIFEST = '.finance-skills.json'
RESERVED = {'sediment-framework', 'discover-kol'}
CONSUMER_PENDING = 'finance-skills-consumer-recovery'


class SkillsUpdateError(Exception):
    pass


def installer_env(root: Path) -> dict[str, str]:
    keys = {'PATH', 'HOME', 'LANG', 'LC_ALL', 'SSL_CERT_FILE', 'SSL_CERT_DIR', 'NODE_EXTRA_CA_CERTS',
            'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY'}
    temporary = root / '_local/tmp'
    return {**{k: v for k, v in os.environ.items() if k in keys}, 'TMPDIR': str(temporary),
            'npm_config_cache': str(temporary / 'npm-cache'), 'GIT_TERMINAL_PROMPT': '0', 'DISABLE_TELEMETRY': '1'}


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(value, dict):
            return value
    except (OSError, ValueError):
        pass
    raise SkillsUpdateError(f'技能元数据无效：{path.name}')


def _name(name) -> bool:
    return isinstance(name, str) and bool(name) and Path(name).name == name and not name.startswith('.')


def _files(directory: Path, *, inside: Path | None = None) -> dict[str, str]:
    files = {}
    for path in sorted(directory.rglob('*')):
        relative = path.relative_to(directory).as_posix()
        if path.is_symlink():
            if inside is None or not path.exists() or not path.resolve().is_relative_to(inside):
                raise SkillsUpdateError(f'技能包含不安全的软链接：{relative}')
            files[relative] = 'link:' + str(path.readlink())
        elif path.is_file():
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def _installation(stage: Path, output: str) -> dict:
    try:
        rows = json.loads(output)
        names = [row['name'] for row in rows]
        if (not names or len(set(names)) != len(names)
                or any(not _name(n) or n in RESERVED for n in names)
                or any(row.get('status') != 'installed' or row.get('source') != SOURCE
                       or set(row.get('agents', [])) != set(AGENTS.values()) for row in rows)):
            raise ValueError
        lock = _read_json(stage / 'skills-lock.json')['skills']
        if set(lock) != set(names) or any(lock[n].get('source') != SOURCE or not lock[n].get('computedHash')
                                        for n in names):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise SkillsUpdateError('安装器未完整安装四种 agent 的全部技能') from None
    skills = {}
    for name in sorted(names):
        directory = stage / '.agents/skills' / name
        if directory.is_symlink() or not (directory / 'SKILL.md').is_file():
            raise SkillsUpdateError(f'技能缺少完整源码：{name}')
        skills[name] = _files(directory)
    return {'source': SOURCE, 'installer': 'skills@1.7.6', 'skills': skills,
            'upstreamHashes': {n: lock[n]['computedHash'] for n in sorted(names)}}


def _link(path: Path, target: Path) -> None:
    if path.is_symlink() and path.resolve() == target.resolve():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{uuid.uuid4().hex}')
    temporary.symlink_to(os.path.relpath(target, path.parent), target_is_directory=True)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _aliases(root: Path, skills: Path) -> list[Path]:
    aliases = [root / '.agents/skills', root / '.grok/skills']
    for path in aliases:
        if not path.parent.resolve().is_relative_to(root):
            raise SkillsUpdateError('agent 技能目录存在外部路径冲突')
        if ((path.exists() or path.is_symlink()) and
                (not path.is_symlink() or path.resolve() != skills.resolve())):
            raise SkillsUpdateError(f'agent 技能目录冲突，拒绝覆盖：{path.parent.name}')
    return aliases


def _recover(root: Path) -> bool:
    transaction = root / '_local/tmp/finance-skills-publication'
    if not transaction.exists():
        if transaction.is_symlink():
            raise SkillsUpdateError('技能发布目录冲突')
        return False
    if transaction.is_symlink() or not transaction.is_dir():
        raise SkillsUpdateError('技能发布目录冲突')
    previous = transaction / 'previous'
    skills = root / '.claude/skills'
    restored = previous.exists()
    if restored:
        if previous.is_symlink() or skills.is_symlink():
            raise SkillsUpdateError('技能恢复目录冲突')
        if skills.exists():
            os.replace(skills, transaction / 'interrupted-skills')
        os.replace(previous, skills)
    transaction.rename(transaction.with_name(f'finance-skills-recovered-{uuid.uuid4().hex}'))
    return restored


def _consumer_marker(root: Path) -> Path:
    path = root / '_local/tmp' / CONSUMER_PENDING
    if path.is_symlink() or (path.exists() and (not path.is_file() or path.read_text() != 'pending\n')):
        raise SkillsUpdateError('技能入口恢复标记冲突')
    return path


def _repair_consumer(root: Path, on_updated: Callable[[list[str]], None] | None) -> None:
    marker = _consumer_marker(root)
    if not marker.exists() or on_updated is None:
        return
    path = root / '.claude/skills' / MANIFEST
    old = _read_json(path) if path.exists() else {'source': SOURCE, 'skills': {}}
    if old.get('source') != SOURCE or not isinstance(old.get('skills'), dict):
        raise SkillsUpdateError('恢复的技能清单无效')
    names = sorted(old['skills'])
    if any(not _name(n) or n in RESERVED for n in names):
        raise SkillsUpdateError('恢复的技能清单无效')
    on_updated(names)
    marker.unlink()  # A failed or interrupted repair leaves the marker for the next invocation.


def _mark_consumer(root: Path) -> None:
    marker = _consumer_marker(root)
    with tempfile.NamedTemporaryFile(mode='w', prefix='finance-skills-consumer-', dir=marker.parent,
                                     delete=False) as output:
        temporary = Path(output.name)
        output.write('pending\n')
    try:
        os.replace(temporary, marker)
    finally:
        temporary.unlink(missing_ok=True)


def _publish(root: Path, stage: Path, manifest: dict, on_updated: Callable[[list[str]], None] | None) -> None:
    skills = root / '.claude/skills'
    aliases = _aliases(root, skills)
    before = _files(skills, inside=root)
    old = _read_json(skills / MANIFEST) if (skills / MANIFEST).exists() else {'source': SOURCE, 'skills': {}}
    if old.get('source') != SOURCE or not isinstance(old.get('skills'), dict):
        raise SkillsUpdateError('技能来源清单无效')
    for name, expected in old['skills'].items():
        directory = skills / name
        if not _name(name) or name in RESERVED:
            raise SkillsUpdateError('技能来源清单含有保留名称')
        if directory.is_symlink() or not directory.is_dir() or _files(directory) != expected:
            raise SkillsUpdateError(f'技能有本地修改，拒绝覆盖：{name}')
    for name in manifest['skills']:
        if name not in old['skills'] and (skills / name).exists():
            raise SkillsUpdateError(f'技能入口冲突，拒绝覆盖：{name}')
    if manifest != old:
        transaction = root / '_local/tmp/finance-skills-publication'
        transaction.mkdir()
        replacement = transaction / 'new-skills'
        try:
            shutil.copytree(skills, replacement, symlinks=True)
            for name in old['skills']:
                shutil.rmtree(replacement / name)
            for name in manifest['skills']:
                shutil.copytree(stage / '.agents/skills' / name, replacement / name)
            (replacement / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
            if _files(skills, inside=root) != before:
                raise SkillsUpdateError('更新期间技能发生本地修改，拒绝覆盖')
            os.replace(skills, transaction / 'previous')
            os.replace(replacement, skills)
            for path in aliases:
                _link(path, skills)
            if on_updated is not None:
                _mark_consumer(root)
                on_updated(sorted(manifest['skills']))
            # Rename commits publication; an interrupted transaction is rolled back on the next run.
            transaction.rename(transaction.with_name(f'finance-skills-backup-{uuid.uuid4().hex}'))
        except Exception:
            _recover(root)
            _repair_consumer(root, on_updated)
            raise
        if on_updated is not None:
            _consumer_marker(root).unlink()
    else:
        for path in aliases:
            _link(path, skills)
        if on_updated is not None:
            marker = _consumer_marker(root)
            _mark_consumer(root)
            on_updated(sorted(manifest['skills']))
            marker.unlink()


def update_finance_skills(repo_root: Path, *, on_updated: Callable[[list[str]], None] | None = None) -> list[str]:
    root = repo_root.resolve()
    temporary = root / '_local/tmp'
    if not temporary.resolve().is_relative_to(root):
        raise SkillsUpdateError('临时技能目录存在外部路径冲突')
    temporary.mkdir(parents=True, exist_ok=True)
    with (temporary / 'finance-skills.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (root / '.claude').is_symlink() or (root / '.claude/skills').is_symlink():
            raise SkillsUpdateError('内容仓库技能目录冲突，拒绝覆盖')
        _recover(root)
        if not (root / '.claude/skills/sediment-framework/SKILL.md').is_file():
            raise SkillsUpdateError('内容仓库缺少 sediment-framework')
        _repair_consumer(root, on_updated)  # Recover entries before a network failure can block the retry.
        with tempfile.TemporaryDirectory(prefix='finance-skills-stage-', dir=temporary) as work:
            stage = Path(work)
            argv = [*INSTALLER, 'add', SOURCE, '--skill', '*', '--yes', '--json',
                    *[arg for agent in AGENTS for arg in ('--agent', agent)]]
            result = subprocess.run(argv, cwd=stage, env=installer_env(root), check=False,
                                    stdout=subprocess.PIPE, text=True)
            with tempfile.NamedTemporaryFile(mode='w', prefix='finance-skills-installer-', suffix='.json',
                                             dir=temporary, delete=False) as evidence:
                evidence.write(result.stdout)
            if result.returncode:
                raise SkillsUpdateError('finance-skills 安装失败，现有技能保持不变')
            manifest = _installation(stage, result.stdout)
            _publish(root, stage, manifest, on_updated)
            names = sorted(manifest['skills'])
            return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    args = parser.parse_args()
    try:
        names = update_finance_skills(args.repo_root)
    except (SkillsUpdateError, OSError) as error:
        print(f'finance-skills 更新失败：{error}')
        return 1
    print(f'finance-skills 已更新：{len(names)} 个技能，由 lynch-frameworks 保存，四种 agent 共用')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
