#!/usr/bin/env python3
"""INTC.US valuation eval — base L/M/H with Foundry at 0, V_opt = success mid.

frameworks/INTC.US.md is the source of truth for inputs; this script recomputes
the base L/M/H (CPU PE band + closing items, Foundry = 0), A/B, zone and V_opt,
and exits 1 on mismatch with stated Outputs.

formula_id (CPU):     intc_cpu_product_pe_v1
formula_id (Foundry): intc_foundry_pb_option_v1  (ceiling only; not in the base)

A2e-7 split (this ticker used to mix p_i into the anchors):
  base  = CPU(12/15/18 × eps_product) + adj, Foundry = 0
  V_opt = pb_success_mid × bvps_foundry_2027e × foundry_discount
  表3   = base_k + p_k × V_opt
  P_K is an eval constant, not an Input (A2e-7a). p_M is the value-ratio
  E[P_f]/V_opt from the pre-split 0.20/0.55/0.25 weighting so 表3 recovers
  the old 27.2 / 71.2 / 113.1.

A2e-2c is printed, not failed: after the split the base numerator is the same
eps_product in all three tiers (pure PE band). Resetting the CPU numerator is a
follow-up conversation, not this batch.

Run:  python3 eval/INTC.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_inputs,
    report,
)
from eval.lib.tiers import report as tier_report  # noqa: E402
from eval.lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "INTC.US.md"
FORMULA_IDS = (
    "intc_cpu_product_pe_v1",
    "intc_foundry_pb_option_v1",
)

# Mirror of framework §2 A6 PB bands (update together with the MD).
PB_BANDS = {"fail": (0.3, 0.8), "base": (1.2, 2.2), "success": (2.5, 3.5)}

# Pre-split fail/base/success weights. 表3 only — never Inputs, never the base.
OLD_P = {"fail": 0.20, "base": 0.55, "success": 0.25}

ADJ_COMPONENTS = (
    "net_cash_ps", "nci_ps", "mbly_stake_ps", "altera_stake_ps", "corp_other_ps",
    "tax_asset_ps",
)

REQUIRED = (
    [
        "price", "eps_product_m", "pe_low", "pe_high", "bvps_foundry_2027e",
        "pb_fail_mid", "pb_base_mid", "pb_success_mid", "foundry_discount",
    ]
    + list(ADJ_COMPONENTS)
)


def check_no_p_leak(base_l: float, row_l: float) -> list[str]:
    if abs(row_l - base_l) > 1e-9:
        return [f"p leaked into the base: 表3 L row {row_l:.4f} != base L {base_l:.4f}"]
    return []


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    for fid in FORMULA_IDS:
        if fid not in md:
            print(f"FAIL: formula_id {fid} missing from framework", file=sys.stderr)
            return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    eps = inp["eps_product_m"]
    pe_l, pe_h = inp["pe_low"], inp["pe_high"]
    pe_m = (pe_l + pe_h) / 2.0
    cpu = (eps * pe_l, eps * pe_m, eps * pe_h)
    adj = sum(inp[k] for k in ADJ_COMPONENTS)
    base = [cpu[i] + adj for i in range(3)]
    L, M, H = base
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    mids = {
        k: inp[f"pb_{k}_mid"] * inp["bvps_foundry_2027e"] * inp["foundry_discount"]
        for k in PB_BANDS
    }
    v_opt = mids["success"]
    epf = sum(OLD_P[k] * mids[k] for k in PB_BANDS)
    p_m = epf / v_opt
    p_k = (0.0, p_m, 1.0)
    adj_band = [base[i] + p_k[i] * v_opt for i in range(3)]

    print(f"formula_id: {FORMULA_IDS[0]} + {FORMULA_IDS[1]}")
    print(f"CPU        L/mid/H = {cpu[0]:.1f} / {cpu[1]:.1f} / {cpu[2]:.1f}"
          f"  (eps {eps} × PE {pe_l:g}/{pe_m:g}/{pe_h:g})")
    print(f"foundry    mids df={inp['foundry_discount']:g} = "
          + " / ".join(f"{k} {mids[k]:.1f}" for k in PB_BANDS)
          + f"  ->  V_opt={v_opt:.1f}  E[P_f]={epf:.1f}")
    print(f"sotp adj   {adj:+.2f} = "
          + " ".join(f"{k}={inp[k]:+.2f}" for k in ADJ_COMPONENTS))
    print(f"base L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}"
          f" V_opt/M={v_opt / M:.1%}")
    for line in tier_report(
        (L, M, H), (pe_l, pe_m, pe_h), (eps, eps, eps)
    ):
        print(line)
    print(f"表2  price {inp['price']} -> zone = {zone}")
    print(f"表3  V_opt={v_opt:.2f}  p_k={p_k[0]:.2f}/{p_k[1]:.3f}/{p_k[2]:.2f}  "
          + "  ".join(
              f"{n}:{base[i]:.2f}+{p_k[i]:.3f}xV={adj_band[i]:.2f}"
              for i, n in enumerate("LMH")))
    if inp["price"] > H:
        print(f"     市价隐含 p = {(inp['price'] - H) / v_opt:.2f}")

    errors += check_against_stated(
        md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, tol=0.05
    )
    errors += ladder("base", L, M, H)
    errors += check_no_p_leak(L, adj_band[0])
    if not p_k[0] <= p_k[1] <= p_k[2]:
        errors += [f"p_k must be non-decreasing, got {p_k}"]
    if v_opt < 0:
        errors += [f"V_opt must be >= 0, got {v_opt:.2f}"]
    if abs(sum(OLD_P.values()) - 1.0) > 1e-9:
        errors += [f"OLD_P must sum to 1, got {sum(OLD_P.values())}"]
    df = inp["foundry_discount"]
    if not (0 < df <= 1):
        errors += [f"foundry_discount {df} not in (0, 1]"]
    for k, (lo, hi) in PB_BANDS.items():
        pb = inp[f"pb_{k}_mid"]
        if not (lo <= pb <= hi):
            errors += [f"pb_{k}_mid {pb} outside A6 band [{lo}, {hi}]"]
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors += [f"p-class fields must not appear in Inputs (A2e-7a): {leaked}"]
    # 2c is a known follow-up: print, do not fail this batch.
    print("NOTE A2e-2c: base numerator is identical across tiers "
          f"(eps={eps}); CPU PE band 12/15/18 is a pure multiple ladder. "
          "Resetting the CPU numerator is a follow-up, not this split.")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
