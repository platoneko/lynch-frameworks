#!/usr/bin/env python3
"""QCOM.US valuation eval — recompute anchors from frameworks/QCOM.US.md.

frameworks/QCOM.US.md is the source of truth for inputs; this script recomputes
the base L/M/H, A/B, zone and V_opt, and exits 1 on mismatch with stated Outputs.

formula_id: qcom_sotp_base4_rtier_vopt_residual_fy27_v2

Three things here are specific to this ticker:

- The multiple is flat across tiers. `cyclical` policy asks for it (A2e-5), and
  for this ticker it is also the honest reading: neither a perpetual growth rate
  nor a discount rate should move with the cycle. The cycle lives in the numerator.
- `r` is per leg, not per ticker (AGENTS.md「永续增长口径」). QTL sits in the
  contracted tier at 7% because payer, rate and term are fixed in signed licences
  (A14); the other three are ordinary operating cash flow at 10%. Picking the
  tier from the leg's contracts rather than from the answer is the whole point --
  this single choice moves the market-implied p from 1.27 to 0.99.
- Probabilities never touch the base. `P_K` is deliberately absent from the
  Inputs table and enters only 表3; `check_no_p_leak` proves it by rebuilding
  the p=0 row and requiring it to equal the base L exactly.

Run:  python3 eval/QCOM.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import R_CONTRACTED, R_OPERATING, check_r, perpetual_pe  # noqa: E402
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_inputs,
    report,
)
from eval.lib.tiers import report as tier_report  # noqa: E402
from eval.lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "QCOM.US.md"
MM = 1e6  # revenue inputs are $M; shares and equity are absolute

LEGS = ("qtl", "hs", "auto", "iot")
TIERS = ("l", "m", "h")

# Which discount tier each leg's cash flow belongs to (A14). Only QTL is
# contracted -- payer, rate and term are in the signed licences, and the royalty
# is charged per handset, so it does not ride utilisation or commodity prices.
R_INPUT = {"qtl": "r_qtl", "hs": "r_op", "auto": "r_op", "iot": "r_op"}
R_EXPECTED = {"r_qtl": R_CONTRACTED, "r_op": R_OPERATING}

# 表3 only. Not an Input by design (A2e-7a). p_H defaults to 1.0 (A2e-7d);
# p_M is anchored on the vested warrant fraction and the named-customer coverage
# of FY27 guidance -- see A11.
P_K = (0.00, 0.35, 1.00)

REQUIRED = (
    ["price", "shares", "tax_rate", "equity", "v_opt", "r_qtl", "r_op"]
    + [f"rev_{leg}_{t}" for leg in LEGS for t in TIERS]
    + [f"om_{leg}_{t}" for leg in LEGS for t in TIERS]
    + [f"unalloc_{t}" for t in TIERS]
    + [f"g_{leg}" for leg in LEGS]
)


def tier_legs(inp: dict[str, float], t: str) -> tuple[dict[str, float], float]:
    """Per-leg after-tax EPS for one tier, with the closing item pro-rated.

    The closing item carries the Data Center loss (A8). Its upside sits in
    V_opt, but the money it is losing today is real and belongs to the base --
    dropping it here would hand the base an improvement that has not happened,
    and the consensus reconciliation in §3 would stop tying out.

    The AWS deal (2026-09-09) made DC revenue computable without making its
    earnings positive, so this split survives the event: pulling the loss out
    here and giving DC a positive leg drifts consensus from -1.5% to +5.7%.
    """
    net = 1.0 - inp["tax_rate"]
    gross = {
        leg: inp[f"rev_{leg}_{t}"] * MM * inp[f"om_{leg}_{t}"] * net / inp["shares"]
        for leg in LEGS
    }
    drag = inp[f"unalloc_{t}"] * MM * net / inp["shares"]
    total = sum(gross.values())
    scale = (total - drag) / total
    return {leg: eps * scale for leg, eps in gross.items()}, total - drag


def check_no_p_leak(base_l: float, row_l: float) -> list[str]:
    """A2e-7a: p must not reach the base. The p=0 row has to reproduce base L."""
    if abs(row_l - base_l) > 1e-9:
        return [f"p leaked into the base: 表3 L row {row_l:.4f} != base L {base_l:.4f}"]
    return []


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    legs_by_tier, eps_by_tier = [], []
    for t in TIERS:
        legs, eps = tier_legs(inp, t)
        legs_by_tier.append(legs)
        eps_by_tier.append(eps)
    roe_m = eps_by_tier[1] * inp["shares"] / inp["equity"]

    # One multiple per leg, shared by all three tiers (flat policy, A2e-5).
    # r comes from the leg's cash-flow tier, not from the ticker (A14).
    r_leg = {leg: inp[R_INPUT[leg]] for leg in LEGS}
    pe = {leg: perpetual_pe(inp[f"g_{leg}"], roe_m, r_leg[leg]) for leg in LEGS}
    base = [sum(legs_by_tier[i][leg] * pe[leg] for leg in LEGS) for i in range(3)]
    L, M, H = base
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    # A10: an external residual (HSBC's DC sensitivity x the FY29 target), not a
    # leg of this model -- so it is an Input, not something recomputed from one.
    v_opt = inp["v_opt"]
    adj = [base[i] + P_K[i] * v_opt for i in range(3)]
    weighted_r = sum(legs_by_tier[1][leg] * r_leg[leg] for leg in LEGS) / eps_by_tier[1]

    print(f"formula_id: qcom_sotp_base4_rtier_vopt_residual_fy27_v2")
    print(f"表1  {'leg':6} {'L / M / H ($/sh)':30} {'g':>7} {'r':>6} {'pe':>7}")
    for leg in LEGS:
        cells = " / ".join(f"{legs_by_tier[i][leg] * pe[leg]:6.2f}" for i in range(3))
        print(f"     {leg:6} {cells:30} {inp[f'g_{leg}']:+7.1%}"
              f" {r_leg[leg]:6.0%} {pe[leg]:7.2f}")
    print(f"     {'TOTAL':6} " + " / ".join(f"{v:6.2f}" for v in base))
    print(f"     {'eps':6} " + " / ".join(f"{e:6.3f}" for e in eps_by_tier)
          + f"   ROE_M {roe_m:.1%}")
    print(f"base L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}"
          f" V_opt/M={v_opt / M:.1%}  加权r={weighted_r:.2%}")
    for line in tier_report(
        tuple(base), tuple(base[i] / eps_by_tier[i] for i in range(3)), tuple(eps_by_tier)
    ):
        print(line)
    print(f"表2  price {inp['price']} -> zone = {zone}")
    print(f"表3  V_opt={v_opt:.2f}  " + "  ".join(
        f"{n}:{base[i]:.2f}+{P_K[i]:.2f}xV={adj[i]:.2f}" for i, n in enumerate("LMH")))
    if inp["price"] > H:
        print(f"     市价隐含 p = {(inp['price'] - H) / v_opt:.2f}")

    errors += check_against_stated(
        md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, tol=0.05
    )
    errors += ladder("base", L, M, H)
    # A2e-2c: the tiers must already separate in the numerator, before multiples.
    errors += ladder("eps", *eps_by_tier)
    errors += check_no_p_leak(L, adj[0])
    # r is a tier picked from the leg's contracts, so a stray value here means
    # someone dialled the answer rather than re-reading the disclosure (A14).
    for field, expected in R_EXPECTED.items():
        errors += check_r(inp[field], field)
        if abs(inp[field] - expected) > 1e-9:
            errors += [f"{field}={inp[field]} != {expected} — 换档属仓库级框架纠正，见 A14"]
    if not P_K[0] <= P_K[1] <= P_K[2]:
        errors += [f"p_k must be non-decreasing, got {P_K}"]
    if v_opt < 0:
        errors += [f"V_opt must be >= 0, got {v_opt:.2f}"]
    # A2e-7a also bars p from the Inputs table itself.
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors += [f"p-class fields must not appear in Inputs (A2e-7a): {leaked}"]
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
