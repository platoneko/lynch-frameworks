# Content checks. Needs the code repo one level up (this repo lives at lynch/frameworks/).
check:
    #!/usr/bin/env bash
    set -euo pipefail
    cd ..
    python3 -c 'from eval.lib.frameworks import list_framework_paths, load_framework; ps = list_framework_paths(); [load_framework(p) for p in ps]; print(f"parsed {len(ps)} frameworks")'
    fail=0
    for f in frameworks/eval/*.py; do
      python3 "$f" >/dev/null 2>&1 || { echo "FAIL $f"; fail=1; }
    done
    exit $fail
