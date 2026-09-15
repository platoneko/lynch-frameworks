#!/usr/bin/env python3
"""QCOM.US valuation eval — recompute anchors from frameworks/QCOM.US.md.

frameworks/QCOM.US.md is the source of truth for inputs; this script recomputes
the base L/M/H, A/B, zone and V_opt, and exits 1 on mismatch with stated Outputs.

formula_id: qcom_sotp_base4_qtl_evebit_vopt_fy27_v1

Three things here are specific to this ticker:

- QTL exits Gordon. Same ruler AND the same ladder as NOK.US's Technology
  Standards leg: scaled pre-tax EBT/share × EV/EBIT 10 / 12.4 / 18.9 (L/M/H),
  current-year, undiscounted.  The three rungs are prints for the
  licensing-annuity class (BofA "other businesses" 10x / sell-side QTL SOTP
  cluster midpoint / IDCC realised 18.9x) and are checked rung by rung against
  frameworks/NOK.US.md -- a rung moved on one side only is a drift.  Debt-like
  cash-flow quality is carried by the multiple band, not by r=7%.
- The other three legs stay Gordon flat at r_op=10%. `cyclical` policy asks
  for flat multiples on those legs (A2e-5); the cycle lives in the numerator.
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

from eval.lib.gordon import R_OPERATING, check_g_cap, check_r, implied_g, perpetual_pe  # noqa: E402
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
# One annuity ladder for the asset class (A2e-5b): NOK's Technology Standards
# leg prices on the same three rungs.  Pattern: eval/603799.SH.py SHARED_LADDER.
PEER = REPO_ROOT / "frameworks" / "NOK.US.md"
FORMULA_ID = "qcom_sotp_base4_qtl_evebit_vopt_fy27_v1"
MM = 1e6  # revenue inputs are $M; shares and equity are absolute

LEGS = ("qtl", "hs", "auto", "iot")
OP_LEGS = ("hs", "auto", "iot")
TIERS = ("l", "m", "h")
SHARED_LADDER = {f"ev_ebit_ts_{t}": f"ev_ebit_ts_{t}" for t in TIERS}

# 表3 only. Not an Input by design (A2e-7a). p_H defaults to 1.0 (A2e-7d);
# p_M is anchored on the vested warrant fraction and the named-customer coverage
# of FY27 guidance -- see A11.
P_K = (0.00, 0.35, 1.00)

REQUIRED = (
    ["price", "shares", "tax_rate", "equity", "v_opt", "r_op", "pe_own_min", "pe_own_max"]
    + [f"ev_ebit_ts_{t}" for t in TIERS]
    + [f"rev_{leg}_{t}" for leg in LEGS for t in TIERS]
    + [f"om_{leg}_{t}" for leg in LEGS for t in TIERS]
    + [f"unalloc_{t}" for t in TIERS]
    + [f"g2_{leg}" for leg in OP_LEGS]
)


def tier_legs(
    inp: dict[str, float], t: str
) -> tuple[dict[str, float], dict[str, float], float]:
    """Per-leg scaled EBT/share and after-tax EPS, with the closing item pro-rated.

    The closing item carries the Data Center loss (A8). Its upside sits in
    V_opt, but the money it is losing today is real and belongs to the base --
    dropping it here would hand the base an improvement that has not happened,
    and the consensus reconciliation in §3 would stop tying out.

    The AWS deal (2026-09-09) made DC revenue computable without making its
    earnings positive, so this split survives the event: pulling the loss out
    here and giving DC a positive leg drifts consensus from -1.5% to +5.7%.

    QTL is valued on scaled EBT × EV/EBIT (pre-tax, same as NOK TS); the other
    three legs take after-tax EPS × Gordon PE. Scale is identical for both.
    """
    net = 1.0 - inp["tax_rate"]
    gross_ebt = {
        leg: inp[f"rev_{leg}_{t}"] * MM * inp[f"om_{leg}_{t}"] / inp["shares"]
        for leg in LEGS
    }
    drag_ebt = inp[f"unalloc_{t}"] * MM / inp["shares"]
    total_ebt = sum(gross_ebt.values())
    scale = (total_ebt - drag_ebt) / total_ebt
    ebt = {leg: v * scale for leg, v in gross_ebt.items()}
    eps = {leg: ebt[leg] * net for leg in LEGS}
    return ebt, eps, sum(eps.values())


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

    ebt_by_tier, eps_by_tier_map, eps_by_tier = [], [], []
    for t in TIERS:
        ebt, eps, total_eps = tier_legs(inp, t)
        ebt_by_tier.append(ebt)
        eps_by_tier_map.append(eps)
        eps_by_tier.append(total_eps)
    roe_m = eps_by_tier[1] * inp["shares"] / inp["equity"]

    # Operating legs: one Gordon PE each, shared by all three tiers (flat, A2e-5).
    pe_op = {leg: perpetual_pe(inp[f"g2_{leg}"], roe_m, inp["r_op"]) for leg in OP_LEGS}
    ev_ebit = [inp[f"ev_ebit_ts_{t}"] for t in TIERS]

    leg_vals: list[dict[str, float]] = []
    base: list[float] = []
    for i, t in enumerate(TIERS):
        vals = {leg: eps_by_tier_map[i][leg] * pe_op[leg] for leg in OP_LEGS}
        vals["qtl"] = ebt_by_tier[i]["qtl"] * ev_ebit[i]
        leg_vals.append(vals)
        base.append(sum(vals.values()))
    L, M, H = base
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    # A10: an external residual (HSBC's DC sensitivity x the FY29 target), not a
    # leg of this model -- so it is an Input, not something recomputed from one.
    v_opt = inp["v_opt"]
    adj = [base[i] + P_K[i] * v_opt for i in range(3)]

    print(f"formula_id: {FORMULA_ID}")
    print(f"表1  {'leg':6} {'L / M / H ($/sh)':30} {'mult':>18}")
    for leg in LEGS:
        cells = " / ".join(f"{leg_vals[i][leg]:6.2f}" for i in range(3))
        if leg == "qtl":
            mult = " / ".join(f"{ev_ebit[i]:g}×" for i in range(3))
        else:
            mult = f"{pe_op[leg]:.2f}× flat"
        print(f"     {leg:6} {cells:30} {mult:>18}")
    print(f"     {'TOTAL':6} " + " / ".join(f"{v:6.2f}" for v in base))
    print(f"     {'eps':6} " + " / ".join(f"{e:6.3f}" for e in eps_by_tier)
          + f"   ROE_M {roe_m:.1%}")
    print(f"base L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}"
          f" V_opt/M={v_opt / M:.1%}")
    for line in tier_report(
        tuple(base), tuple(base[i] / eps_by_tier[i] for i in range(3)), tuple(eps_by_tier)
    ):
        print(line)
    print(f"表2  price {inp['price']} -> zone = {zone}")
    print(f"表3  V_opt={v_opt:.2f}  " + "  ".join(
        f"{n}:{base[i]:.2f}+{P_K[i]:.2f}xV={adj[i]:.2f}" for i, n in enumerate("LMH")))
    if inp["price"] > H:
        print(f"     市价隐含 p = {(inp['price'] - H) / v_opt:.2f}")

    # Flat@M control: QTL multiples pinned to the M rung; numerator ladder still holds.
    flat_m = [
        ebt_by_tier[i]["qtl"] * ev_ebit[1]
        + sum(eps_by_tier_map[i][leg] * pe_op[leg] for leg in OP_LEGS)
        for i in range(3)
    ]
    print(f"Flat@{ev_ebit[1]:g}×  L={flat_m[0]:.2f} M={flat_m[1]:.2f} H={flat_m[2]:.2f}")

    # Shared annuity ladder (A14): every rung must equal NOK's TS rung.
    peer = parse_inputs(PEER.read_text(encoding="utf-8"))
    for ours, theirs in SHARED_LADDER.items():
        if theirs not in peer:
            errors += [f"peer NOK.US missing {theirs}"]
        elif abs(inp[ours] - peer[theirs]) > 1e-9:
            errors += [f"shared annuity ladder drift: {ours}={inp[ours]:g} vs NOK.{theirs}={peer[theirs]:g}"]
    print("shared ladder vs NOK.US TS: " + ("drift" if any("shared annuity ladder" in e for e in errors)
                                             else f"OK ({' / '.join(f'{x:g}' for x in ev_ebit)})"))

    # Guardrail (valuation-rules 裁决顺序 ③): the per-leg Gordon multiples have no
    # per-leg realised band to sit in, so the test is run on the whole-company
    # multiple each tier implies (base / tier EPS) against the ticker's own
    # 5-year trailing PE band.  Outside the band would call for a band-edge g,
    # not a wider band.
    own_lo, own_hi = inp["pe_own_min"], inp["pe_own_max"]
    blended = [base[i] / eps_by_tier[i] for i in range(3)]
    g_lo, _ = implied_g(own_lo, roe_m, inp["r_op"])
    g_hi, _ = implied_g(own_hi, roe_m, inp["r_op"])
    print(f"guardrail (③): blended L/M/H = {blended[0]:.2f}/{blended[1]:.2f}/{blended[2]:.2f}x"
          f" vs own 5y band [{own_lo:.2f}, {own_hi:.2f}] | band-edge g at ROE_M: {g_lo:+.2%} .. {g_hi:+.2%}")
    for name, pe in zip("LMH", blended):
        if not (own_lo - 1e-9 <= pe <= own_hi + 1e-9):
            errors += [f"guardrail: {name} blended multiple {pe:.2f}x outside own band [{own_lo}, {own_hi}] — reverse-solve g to the band edge, do not widen the band"]

    errors += check_against_stated(
        md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, tol=0.05
    )
    errors += ladder("base", L, M, H)
    # A2e-2c: the tiers must already separate in the numerator, before multiples.
    errors += ladder("eps", *eps_by_tier)
    errors += ladder("ev_ebit_ts", *ev_ebit)
    errors += check_no_p_leak(L, adj[0])
    errors += check_r(inp["r_op"], "r_op")
    # AGENTS.md「永续增长口径」: every Gordon leg's perpetual g stays at or below the cap.
    for leg in OP_LEGS:
        errors += check_g_cap(inp[f"g2_{leg}"], f"g2_{leg}")
    if abs(inp["r_op"] - R_OPERATING) > 1e-9:
        errors += [f"r_op={inp['r_op']} != {R_OPERATING} — 换档属仓库级框架纠正"]
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
