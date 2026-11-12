# Check unarchived frameworks using their calculation scripts as the source of
# valuation and rules. Set LYNCH_FRAMEWORK_ARCHIVE to the app's archive list.
# LYNCH_VALUATION_SOURCES supplies the same historical sources as the app.
# LYNCH_FRAMEWORK_CHECK_INPUTS optionally overrides inputs for specific tickers.
check:
    #!/usr/bin/env bash
    set -euo pipefail
    # Skills must remain usable when this content repo is cloned elsewhere.
    python3 - <<'PY'
    from pathlib import Path
    root = Path.cwd().resolve()
    skills = root / ".claude/skills"
    for path in [skills, *skills.rglob("*")]:
        if path.is_symlink() and (path.readlink().is_absolute() or not path.exists() or not path.resolve().is_relative_to(root)):
            raise SystemExit(f"FAIL {path.relative_to(root)}: skill symlink must be relative and stay inside the content repo")
    PY
    cd ..
    python3 - <<'PY'
    import json
    import os
    import re
    import sys
    from pathlib import Path
    from eval.lib.frameworks import list_framework_paths, parse_framework_identity, price_free_violations
    from eval.lib.result_service import check_input_sources
    from eval.lib.valuation_runner import run

    def required_file(variable):
        value = os.environ.get(variable)
        if not value:
            raise ValueError(f'{variable} must name an existing file')
        path = Path(value)
        if not path.is_absolute() or not path.is_file():
            raise ValueError(f'{variable} must name an existing absolute file path')
        return path

    try:
        archive = json.loads(required_file('LYNCH_FRAMEWORK_ARCHIVE').read_text(encoding='utf-8'))
        if not isinstance(archive, list) or any(not isinstance(t, str) for t in archive):
            raise ValueError('archive must contain a list of ticker strings')
        optional_inputs = {}
        if os.environ.get('LYNCH_FRAMEWORK_CHECK_INPUTS'):
            path = required_file('LYNCH_FRAMEWORK_CHECK_INPUTS')
            optional_inputs = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(optional_inputs, dict):
                raise ValueError('check inputs must map tickers to input objects')
            for ticker, values in optional_inputs.items():
                if (not isinstance(ticker, str) or not isinstance(values, dict)
                        or set(values) - {'external_inputs', 'peer_results', 'rate_inputs'}
                        or any(value is not None and not isinstance(value, dict) for value in values.values())):
                    raise ValueError(f'invalid check inputs for {ticker}')
        root = Path.cwd().resolve()
        content = root / 'frameworks'
        sources = check_input_sources(os.environ.get('LYNCH_VALUATION_SOURCES'),
                                      code_root=root, content_root=content)
        paths = list_framework_paths()
    except (OSError, ValueError, TypeError) as exc:
        print(f'FAIL check setup: {exc}', file=sys.stderr)
        sys.exit(1)

    failures = []
    archived = set(archive)
    active = [p for p in paths if p.stem not in archived]
    for path in active:
        try:
            text = path.read_text(encoding='utf-8')
            identity = parse_framework_identity(text, path.stem)
            failures.extend(f'FAIL {path.name}: {error}' for error in price_free_violations(text))
            if not (content / 'eval' / f'{identity.ticker}.py').is_file():
                raise ValueError('valuation script missing')
            inputs = sources.for_ticker(identity.ticker, optional_inputs.get(identity.ticker, {}))
            result = run(root, content, identity.ticker, **inputs)
            if result.get('peer_missing'):
                print(f"WARN {path.name}: missing optional peer results: {', '.join(result['peer_missing'])}", file=sys.stderr)
        except Exception as exc:
            failures.append(f'FAIL {path.name}: {type(exc).__name__}: {exc}')

    # This is a skill-authoring rule, not a document valuation format check.
    ticker = re.compile(r'\b[0-9A-Z]{1,6}\.(US|HK|SH|SZ)\b')
    scratch = re.compile(r'_local/tmp/[A-Za-z0-9]')
    format_row = re.compile(r'^\| (美股|港股|A 股) \|')
    for path in sorted((content / '.claude/skills/sediment-framework').rglob('*.md')):
        for line_number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if not format_row.match(line) and (ticker.search(line) or scratch.search(line)):
                failures.append(f'FAIL {path.relative_to(content)}:{line_number} names a sample ticker or scratch path')
    if failures:
        print(*failures, sep='\n', file=sys.stderr)
    print(f'checked {len(active)} active frameworks; skipped {len(paths) - len(active)} archived')
    sys.exit(1 if failures else 0)
    PY
