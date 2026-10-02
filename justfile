# Content checks. Needs the code repo one level up (this repo lives at lynch/frameworks/).
check:
    #!/usr/bin/env bash
    set -euo pipefail
    cd ..
    python3 -c 'from eval.lib.frameworks import list_framework_paths, load_framework; ps = list_framework_paths(); [load_framework(p) for p in ps]; print(f"parsed {len(ps)} frameworks")'
    fail=0
    # AGENTS.md「现价 — 禁写契约」: no own current price outside §4 Changelog.
    python3 - <<'PY' || fail=1
    import sys
    from eval.lib.frameworks import list_framework_paths, price_free_violations
    bad = [f"FAIL {p.name} {e}" for p in list_framework_paths()
           for e in price_free_violations(p.read_text(encoding="utf-8"))]
    if bad:
        print(*bad, sep="\n")
    sys.exit(1 if bad else 0)
    PY
    # AGENTS.md「共享情景轴」共识行: tiers must parse; a mounted ticker's own line is shadowed by its axis.
    python3 - <<'PY' || fail=1
    import sys
    from eval.lib.axes import list_axis_paths, load_axis
    from eval.lib.frameworks import list_framework_paths, load_framework
    bad, mounted = [], {}
    for p in list_axis_paths():
        try:
            a = load_axis(p)
            # Rating and reference mounts alike: neither writes its own 共识 line (contracts.md「定档 / 参照挂载」).
            for t in a.mounts + a.refs:
                mounted.setdefault(t, []).append(p.stem)
        except ValueError as e:
            bad.append(f"FAIL axes/{p.name} {e}")
    for p in list_framework_paths():
        m = load_framework(p)
        if m.consensus is not None and m.ticker in mounted:
            print(f"WARN {p.name} 共识行 is shadowed by axis {', '.join(mounted[m.ticker])}")
    if bad:
        print(*bad, sep="\n")
    sys.exit(1 if bad else 0)
    PY
    for f in frameworks/eval/*.py; do
      python3 "$f" >/dev/null 2>&1 || { echo "FAIL $f"; fail=1; }
    done
    exit $fail
