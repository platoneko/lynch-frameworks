#!/usr/bin/env python3
"""INTC.US valuation eval — recompute anchors from frameworks/INTC.US.md and enforce consistency.

frameworks/INTC.US.md stays the human-facing source of truth for inputs; this
script is the enforcement layer that keeps its number chain honest:

    parse §3 Inputs table -> recompute E[P_f], L/M/H, A/B, zone
                          -> diff against the numbers printed in §3 Outputs
                          -> exit 1 on any mismatch or invariant violation

Checks (mirror of framework §3 校验步骤):
  1. p_fail + p_base + p_success == 1
  2. each pb_*_mid lies inside its A6 band
  3. L < M < H, and stated anchors/cut-points/zone-table boundaries match
     recomputation within ±0.05 (stated numbers are rounded to 1 decimal)
  4. zone implied by price matches the zone printed in Outputs
  5. TODO: same-year product-vs-consolidated EPS reconciliation (needs segment data)

formula_id (CPU):     intc_cpu_product_pe_v1
formula_id (Foundry): intc_foundry_pb_option_v1

Run after every edit of frameworks/INTC.US.md:  python3 eval/INTC.US.py

TODO: emit output/bands/INTC.US.json; move zone slicing into eval/lib/ once a
second ticker lands.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "INTC.US.md"

FORMULA_IDS = (
    "intc_cpu_product_pe_v1",
    "intc_foundry_pb_option_v1",
)

# Mirror of framework §2 A6 PB bands (update together with the MD).
PB_BANDS = {"fail": (0.3, 0.8), "base": (1.2, 2.2), "success": (2.5, 3.5)}

TOL = 0.055  # stated numbers are rounded to 1 decimal

# SOTP closing items (A10): adj is always recomputed as their sum — the MD
# carries no hand-written total that could drift.
ADJ_COMPONENTS = (
    "net_cash_ps", "nci_ps", "mbly_stake_ps", "altera_stake_ps", "corp_other_ps",
    "tax_asset_ps",
)

REQUIRED = (
    "price", "eps_product_m", "pe_low", "pe_high", "bvps_foundry_2027e",
    "pb_fail_mid", "pb_base_mid", "pb_success_mid",
    "p_fail", "p_base", "p_success", "foundry_discount",
) + ADJ_COMPONENTS


# ---------------------------------------------------------------- parsing

def parse_inputs(text: str) -> tuple[dict, list[str]]:
    """Parse the §3 Inputs markdown table. 待补 -> None (reported as gap)."""
    section = text.split("### Inputs", 1)[1].split("### Formula", 1)[0]
    inputs: dict[str, float | None] = {}
    gaps: list[str] = []
    for line in section.splitlines():
        m = re.match(r"\|\s*([a-z][a-z0-9_]*)\s*\|\s*([^|]+)\|", line)
        if not m:
            continue
        field, raw = m.group(1), m.group(2).strip()
        if raw.startswith("待补"):
            inputs[field] = None
            gaps.append(field)
            continue
        num = re.match(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?", raw)
        if num:
            inputs[field] = float(num.group(0))
    missing = [f for f in REQUIRED if inputs.get(f) is None]
    if missing:
        sys.exit(f"FATAL: required inputs missing/待补 in {FRAMEWORK}: {missing}")
    return inputs, gaps


def parse_stated(text: str) -> dict:
    """Parse anchors, cut-points, zone-table boundaries and zone id from §3 Outputs."""
    out = text.split("### Outputs", 1)[1].split("## 4.", 1)[0]
    anchors = re.search(
        r"L ≈ \*\*([\d.]+)\*\* · M ≈ \*\*([\d.]+)\*\* · H ≈ \*\*([\d.]+)\*\*", out)
    cuts = re.search(
        r"A=\(L\+M\)/2 ≈ \*\*([\d.]+)\*\* · B=\(M\+H\)/2 ≈ \*\*([\d.]+)\*\*", out)
    zone = re.search(r"zone = \*\*`(\w+)`\*\*", out)
    if not (anchors and cuts and zone):
        sys.exit("FATAL: cannot parse Outputs section (anchors/cuts/zone line)")
    # Only the price-interval column (index 2) carries boundary numbers; the
    # scenario column holds narrative figures that must not enter table_nums.
    table = "\n".join(
        l.strip().strip("|").split("|")[2]
        for l in out.splitlines() if l.lstrip().startswith("|") and "`" in l)
    return {
        "L": float(anchors.group(1)), "M": float(anchors.group(2)),
        "H": float(anchors.group(3)),
        "A": float(cuts.group(1)), "B": float(cuts.group(2)),
        "zone": zone.group(1),
        "table_nums": {float(x) for x in re.findall(r"\d+(?:\.\d+)?", table)},
    }


# ---------------------------------------------------------------- computation

def compute(v: dict) -> dict:
    """Recompute the full chain per framework §3 Formula (source of truth: MD)."""
    cpu_l = v["eps_product_m"] * v["pe_low"]
    cpu_h = v["eps_product_m"] * v["pe_high"]
    cpu_mid = (cpu_l + cpu_h) / 2
    # A11: foundry leg is discounted (true forward BVPS); CPU leg is not
    # (normalized earnings power, today-multiple).
    mids = {k: v[f"pb_{k}_mid"] * v["bvps_foundry_2027e"] * v["foundry_discount"]
            for k in PB_BANDS}
    epf = sum(v[f"p_{k}"] * mids[k] for k in PB_BANDS)
    adj = sum(v[k] for k in ADJ_COMPONENTS)
    L = cpu_l + adj
    M = cpu_mid + epf + adj
    H = cpu_h + mids["success"] + adj
    return {
        "cpu_l": cpu_l, "cpu_mid": cpu_mid, "cpu_h": cpu_h,
        "mids": mids, "epf": epf, "adj": adj,
        "L": L, "M": M, "H": H, "A": (L + M) / 2, "B": (M + H) / 2,
    }


def zone_of(price: float, c: dict) -> str:
    # AGENTS.md five-tier rule: midpoints of L/M/H slice the band.
    if price < c["L"]:
        return "deep_discount"
    if price < c["A"]:
        return "conservative"
    if price < c["B"]:
        return "neutral"
    if price <= c["H"]:
        return "optimistic"
    return "stretched"


def implied_p_success(target: float, v: dict, c: dict) -> float:
    """Solve p_success from target price, holding p_fail fixed (p_base absorbs)."""
    e_target = target - c["cpu_mid"] - c["adj"]
    f, b, s = (c["mids"][k] for k in ("fail", "base", "success"))
    return (e_target - v["p_fail"] * f - (1 - v["p_fail"]) * b) / (s - b)


# ---------------------------------------------------------------- main

def main() -> None:
    text = FRAMEWORK.read_text(encoding="utf-8")
    v, gaps = parse_inputs(text)
    stated = parse_stated(text)
    c = compute(v)

    checks: list[tuple[bool, str]] = []
    psum = v["p_fail"] + v["p_base"] + v["p_success"]
    checks.append((abs(psum - 1) < 1e-9, f"probabilities sum to 1 (got {psum})"))
    df = v["foundry_discount"]
    checks.append((0 < df <= 1, f"foundry_discount {df} in (0, 1]"))
    for k, (lo, hi) in PB_BANDS.items():
        pb = v[f"pb_{k}_mid"]
        checks.append((lo <= pb <= hi, f"pb_{k}_mid {pb} in A6 band [{lo}, {hi}]"))
    checks.append((c["L"] < c["M"] < c["H"],
                   f"L < M < H ({c['L']:.1f} < {c['M']:.1f} < {c['H']:.1f})"))
    for key in ("L", "M", "H", "A", "B"):
        checks.append((abs(stated[key] - c[key]) <= TOL,
                       f"stated {key}={stated[key]} matches computed {c[key]:.3f}"))
    expected_bounds = {round(c[k], 1) for k in ("L", "A", "B", "H")}
    checks.append((stated["table_nums"] == expected_bounds,
                   f"zone table boundaries {sorted(stated['table_nums'])} "
                   f"== {sorted(expected_bounds)}"))
    z = zone_of(v["price"], c)
    checks.append((z == stated["zone"],
                   f"zone at price {v['price']}: computed `{z}` == stated `{stated['zone']}`"))

    print(f"framework : {FRAMEWORK.name}")
    print(f"CPU leg   : L/mid/H = {c['cpu_l']:.1f} / {c['cpu_mid']:.1f} / {c['cpu_h']:.1f}")
    print(f"foundry   : mids $/sh (df={v['foundry_discount']}) = "
          + " / ".join(f"{k} {c['mids'][k]:.1f}" for k in PB_BANDS)
          + f"  ->  E[P_f] = {c['epf']:.1f}")
    print(f"sotp adj  : {c['adj']:+.2f} = "
          + " ".join(f"{k}={v[k]:+.2f}" for k in ADJ_COMPONENTS))
    print(f"anchors   : L {c['L']:.1f} · M {c['M']:.1f} · H {c['H']:.1f}"
          f"  (A {c['A']:.1f} · B {c['B']:.1f})")

    print("\nsensitivity (p_success, p_fail fixed):")
    for ps in (0.15, 0.25, 0.35):
        pb_ = 1 - v["p_fail"] - ps
        epf_ = (v["p_fail"] * c["mids"]["fail"] + pb_ * c["mids"]["base"]
                + ps * c["mids"]["success"])
        m_ = c["cpu_mid"] + epf_ + c["adj"]
        c_ = dict(c, M=m_, A=(c["L"] + m_) / 2, B=(m_ + c["H"]) / 2)
        print(f"  p_s={ps:.2f}: M={m_:.1f}, zone@{v['price']}={zone_of(v['price'], c_)}")

    print("implied p_success: "
          f"@price {v['price']} -> {implied_p_success(v['price'], v, c):.1%}; "
          f"@raise 95 -> {implied_p_success(95, v, c):.1%}")

    if gaps:
        print(f"\ngaps (待补, not consumed yet): {', '.join(gaps)}")

    print("\nchecks:")
    failed = False
    for ok, label in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        failed |= not ok
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
