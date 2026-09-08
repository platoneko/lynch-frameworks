#!/usr/bin/env python3
"""TSM.US valuation eval — recompute anchors from frameworks/TSM.US.md.

frameworks/TSM.US.md is the human-facing source of truth for inputs; this script
recomputes L/M/H / A/B / zone and exits 1 on mismatch.

formula_id (wafer): tsm_wafer_pe_v1
formula_id (non-wafer): tsm_cowos_capacity_uv_floor_v2
formula_id (combo): tsm_wafer_pe_plus_cowos_capacity_uv_v2

Run:  python3 eval/TSM.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import check_cowos_supply  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "TSM.US.md"
TOL = 0.15  # stated outputs rounded to 1 decimal


def parse_inputs(md: str) -> dict[str, float]:
    """Parse §3 Inputs table: | field | value | ... |"""
    out: dict[str, float] = {}
    in_inputs = False
    for line in md.splitlines():
        if line.startswith("### Inputs"):
            in_inputs = True
            continue
        if in_inputs and line.startswith("### "):
            break
        if not in_inputs or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        key, raw = cells[0], cells[1]
        if key in ("字段名", "--------", "---") or raw in ("取值",):
            continue
        if raw in ("待补", ""):
            continue
        try:
            out[key] = float(raw.replace(",", ""))
        except ValueError:
            continue
    return out


def zone_of(price: float, L: float, M: float, H: float) -> str:
    A = (L + M) / 2
    B = (M + H) / 2
    if price < L:
        return "deep_discount"
    if price < A:
        return "conservative"
    if price < B:
        return "neutral"
    if price <= H:
        return "optimistic"
    return "stretched"


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    inp = parse_inputs(md)
    required = [
        "price",
        "shares_adr",
        "eps_wafer_2027e",
        "eps_pkg_2027e",
        "pe_l",
        "pe_m",
        "pe_h",
        "cowos_wpm_l",
        "cowos_wpm_m",
        "cowos_wpm_h",
        "uv_per_10k_wpm",
        "npm_2027e_l",
        "npm_2027e_m",
    ]
    missing = [k for k in required if k not in inp]
    if missing:
        print("missing inputs:", ", ".join(missing), file=sys.stderr)
        return 1

    # A fast_grower's L must be a worse world, not the same world priced lower
    # (skill A2e-1): the L tier reverts 2027E net margin to the 2025 realised
    # 44.6% before the trough multiple is applied. M/H keep the 50% assumption.
    margin_l = inp["npm_2027e_l"] / inp["npm_2027e_m"]
    eps_wafer_l = inp["eps_wafer_2027e"] * margin_l
    eps_pkg_l = inp["eps_pkg_2027e"] * margin_l

    Pa_l = eps_wafer_l * inp["pe_l"]
    Pa_m = inp["eps_wafer_2027e"] * inp["pe_m"]
    Pa_h = inp["eps_wafer_2027e"] * inp["pe_h"]

    def pb(wpm: float, pe: float, eps_pkg: float) -> float:
        # v2: non-wafer earnings at same-tier PE floors the capacity leg
        capacity = (wpm / 10000.0) * inp["uv_per_10k_wpm"] / inp["shares_adr"]
        return max(capacity, eps_pkg * pe)

    Pb_l = pb(inp["cowos_wpm_l"], inp["pe_l"], eps_pkg_l)
    Pb_m = pb(inp["cowos_wpm_m"], inp["pe_m"], inp["eps_pkg_2027e"])
    Pb_h = pb(inp["cowos_wpm_h"], inp["pe_h"], inp["eps_pkg_2027e"])

    L = Pa_l + Pb_l
    M = Pa_m + Pb_m
    H = Pa_h + Pb_h
    if not (L < M < H):
        print(f"invariant L<M<H failed: {L=:.4f} {M=:.4f} {H=:.4f}", file=sys.stderr)
        return 1

    A = (L + M) / 2
    B = (M + H) / 2
    z = zone_of(inp["price"], L, M, H)

    # Stated outputs in §3
    stated = {}
    m = re.search(
        r"L\s*=\s*\*\*([0-9.]+)\*\*\s*·\s*M\s*=\s*\*\*([0-9.]+)\*\*\s*·\s*H\s*=\s*\*\*([0-9.]+)\*\*",
        md,
    )
    if m:
        stated["L"], stated["M"], stated["H"] = map(float, m.groups())
    m2 = re.search(
        r"A\s*=\s*\*\*([0-9.]+)\*\*\s*·\s*B\s*=\s*\*\*([0-9.]+)\*\*",
        md,
    )
    if m2:
        stated["A"], stated["Bcut"] = map(float, m2.groups())
    mz = re.search(r"zone\s*=\s*\*\*`([a-z_]+)`\*\*", md)
    stated_zone = mz.group(1) if mz else None

    print("recomputed:")
    print(f"  Pa L/M/H = {Pa_l:.1f}/{Pa_m:.1f}/{Pa_h:.1f}")
    print(f"  Pb L/M/H = {Pb_l:.1f}/{Pb_m:.1f}/{Pb_h:.1f}")
    print(f"  L/M/H    = {L:.1f}/{M:.1f}/{H:.1f}")
    print(f"  A/B      = {A:.1f}/{B:.1f}")
    print(f"  zone     = {z} (price={inp['price']})")
    print(
        f"  L 分子   = 净利率 {inp['npm_2027e_l']:.1%} (2025 实测) vs M/H "
        f"{inp['npm_2027e_m']:.1%} -> eps_wafer {eps_wafer_l:.2f} vs "
        f"{inp['eps_wafer_2027e']:.2f} ({margin_l - 1.0:+.1%})"
    )

    ok = True
    for err in check_cowos_supply(inp["cowos_wpm_m"]):
        print(f"MISMATCH axis: {err}", file=sys.stderr)
        ok = False
    for key, got in (("L", L), ("M", M), ("H", H), ("A", A), ("Bcut", B)):
        if key not in stated:
            continue
        if abs(stated[key] - got) > TOL:
            print(
                f"mismatch {key}: stated={stated[key]} recomputed={got:.4f}",
                file=sys.stderr,
            )
            ok = False
    if stated_zone and stated_zone != z:
        print(f"mismatch zone: stated={stated_zone} recomputed={z}", file=sys.stderr)
        ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
