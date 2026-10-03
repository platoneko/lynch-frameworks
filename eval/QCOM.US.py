#!/usr/bin/env python3
"""QCOM.US valuation eval — recompute anchors from frameworks/QCOM.US.md.

frameworks/QCOM.US.md is the source of truth for inputs; this script recomputes
the base L/M/H, A/B and V_opt, and exits 1 on mismatch with stated Outputs.  The
doc carries no current price (AGENTS.md「现价 — 禁写契约」): which zone a quote
falls in is derived live by the daily digest and the app, so nothing here reads
a price.

formula_id: qcom_sotp_base4_qtl_evebit_vopt_fy27_v2

v2 (2026-10-03 migration, valuation-rules「未建模期权」/「增长的表达顺序」):
- V_opt is recomputed here, no longer an external constant.  Units = the
  company's named FY29 Data Center target less what consensus already holds
  (the FY27 guidance); unit economics = the only leg-level sell-side number
  (HSBC's FY27 incremental DC margin); valued on this ticker's ruler (basket r,
  ROE_M, the DC leg's g2 from the semis cross-section, capped) in FY29 and
  discounted to the FY27 numerator year.  HSBC's 17x target multiple is gone
  (borrow quantity, not price).
- g2_auto comes from the auto/analog cross-section (NXPI / TXN, AVGO A18),
  not a self-set 6% at the cap carrying the near-term growth.

Three things here are specific to this ticker:

- QTL exits Gordon. Same ruler AND the same ladder as NOK.US's Technology
  Standards leg: scaled pre-tax EBT/share × EV/EBIT 10 / 12.4 / 18.9 (L/M/H),
  current-year, undiscounted.  The three rungs are prints for the
  licensing-annuity class (BofA "other businesses" 10x / sell-side QTL SOTP
  cluster midpoint / IDCC realised 18.9x) and are checked rung by rung against
  frameworks/NOK.US.md -- a rung moved on one side only is a drift.  Debt-like
  cash-flow quality is carried by the multiple band, not by r=7%.
- The other three legs stay Gordon flat at r_op = the basket r named in the
  Inputs source cell (篮 4 龙头制造 10%, A15; enforced by `check_r`), on ROE_M =
  FY27 M-tier EPS / the FY27 opening book per share (FY26Q3 equity rolled over
  the Q4 FY26 unbooked earnings at b1 = g/ROE, E_{n+1}/B_n, A16).  QTL sits
  in 篮 3 按量专利许可 but its 8.5% never enters a formula -- the ladder carries
  the annuity quality, so there is no r_qtl row.  `cyclical` policy asks for
  flat multiples on the operating legs (A2e-5); the cycle lives in the numerator.
- The g2 +/-1pp lever is printed as disclosure only (A15); it never touches
  the base.
- Probabilities never touch the base. `P_K` is deliberately absent from the
  Inputs table and enters only 表3; `check_no_p_leak` proves it by rebuilding
  the p=0 row and requiring it to equal the base L exactly.

Run:  python3 frameworks/eval/QCOM.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import BASKET_R, check_g_cap, check_r, g_cap, implied_g, perpetual_pe  # noqa: E402
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_baskets,
    parse_inputs,
    report,
)
from eval.lib.tiers import report as tier_report  # noqa: E402
from eval.lib.zones import cut_points  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "QCOM.US.md"
# One annuity ladder for the asset class (A2e-5b): NOK's Technology Standards
# leg prices on the same three rungs.  Pattern: eval/603799.SH.py SHARED_LADDER.
PEER = REPO_ROOT / "frameworks" / "NOK.US.md"
FORMULA_ID = "qcom_sotp_base4_qtl_evebit_vopt_fy27_v2"
NUM_YEAR = 2027  # FY27 = t=1, the numerator year (A12)
MIN_R_MINUS_G = 0.02
MM = 1e6  # revenue inputs are $M; shares and equity are absolute
LISTING_CCY = "USD"

LEGS = ("qtl", "hs", "auto", "iot")
OP_LEGS = ("hs", "auto", "iot")
TIERS = ("l", "m", "h")
SHARED_LADDER = {f"ev_ebit_ts_{t}": f"ev_ebit_ts_{t}" for t in TIERS}

# 表3 only. Not an Input by design (A2e-7a). p_H defaults to 1.0 (A2e-7d);
# p_M is anchored on the vested warrant fraction and the named-customer coverage
# of FY27 guidance -- see A11.
P_K = (0.00, 0.35, 1.00)

REQUIRED = (
    ["shares", "tax_rate", "equity", "r_op", "pe_own_min", "pe_own_max"]
    + ["dc_target_rev", "dc_cons_rev", "hsbc_eps_fy27", "hsbc_dc_uplift", "hsbc_dc_drev", "g2_dc_src", "t_opt"]
    + ["eps_fy26_cons", "eps_9m_fy26", "payout_3y"]
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


def stated_v_opt(md: str) -> float | None:
    m = re.search(r"V_\{opt\}\\\)\s*=\s*\*\*([0-9.]+)\*\*", md)
    return float(m.group(1)) if m else None


def option_value(inp: dict[str, float], roe_m: float, g2_dc: float, r: float) -> tuple[float, float, float, float]:
    """A10: Data Center option, closed by public data (valuation-rules 2026-10-03).

    Units: company FY29 DC target minus the FY27 guidance consensus already
    carries.  Unit economics: HSBC's FY27 DC sensitivity, read as after-tax EPS
    per dollar of DC revenue (no multiple taken from it).  Ruler: this ticker's
    Gordon PE at r_op, ROE_M and the DC leg's g2, struck in the target year and
    discounted to FY27.  Returns (V_opt, income/share, pre-tax margin, PE).
    """
    opt_rev = (inp["dc_target_rev"] - inp["dc_cons_rev"]) * MM
    eps_per_rev = inp["hsbc_eps_fy27"] * inp["hsbc_dc_uplift"] / (inp["hsbc_dc_drev"] * MM)
    inc = opt_rev * eps_per_rev
    margin = eps_per_rev * inp["shares"] / (1.0 - inp["tax_rate"])
    pe = perpetual_pe(g2_dc, roe_m, r)
    return inc * pe / (1.0 + r) ** (inp["t_opt"] - NUM_YEAR), inc, margin, pe


def check_no_p_leak(base_l: float, row_l: float) -> list[str]:
    """A2e-7a: p must not reach the base. The p=0 row has to reproduce base L."""
    if abs(row_l - base_l) > 1e-9:
        return [f"p leaked into the base: 表3 L row {row_l:.4f} != base L {base_l:.4f}"]
    return []


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    inp = parse_inputs(md)
    baskets = parse_baskets(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    ebt_by_tier, eps_by_tier_map, eps_by_tier = [], [], []
    for t in TIERS:
        ebt, eps, total_eps = tier_legs(inp, t)
        ebt_by_tier.append(ebt)
        eps_by_tier_map.append(eps)
        eps_by_tier.append(total_eps)
    # ROE_M = E_{n+1} / B_n: the FY27 M-tier EPS over the FY27 OPENING book (= end
    # FY26), not today's FY26Q3 book (valuation-rules 裁决表 ② as of
    # 2026-09-21; A16).  The FY26Q3 book is rolled over the Q4 FY26 earnings not
    # yet booked (FY26 consensus minus 9M actual, non-GAAP) at the GROWTH-REQUIRED
    # retention b1 = g/ROE, not the actual payout complement.  No g1 window, so
    # the roll g is the company g the multiples actually charge: the M-tier
    # EPS-weighted g2 of the three Gordon legs, the QTL leg at 0 (its EV/EBIT
    # ladder charges no retention).  Closed form: BPS = BPS0 / (1 - g·N/eps).
    # Actual retention beyond b1 is the B bucket, printed as a disclosure only.
    unbooked = inp["eps_fy26_cons"] - inp["eps_9m_fy26"]  # per share, Q4 FY26 only
    bps_q3 = inp["equity"] / inp["shares"]
    eps_m_legs = eps_by_tier_map[1]
    g_roll = sum(eps_m_legs[leg] * inp[f"g2_{leg}"] for leg in OP_LEGS) / eps_by_tier[1]
    bps_open = bps_q3 / (1.0 - g_roll * unbooked / eps_by_tier[1])
    roe_m = eps_by_tier[1] / bps_open
    b1 = g_roll / roe_m
    if not (0.0 < b1 < 1.0):
        errors += [f"growth-required retention b1 = {b1:.3f} outside (0,1)"]
    excess_cash = (1.0 - inp["payout_3y"] - b1) * unbooked  # disclosure only

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
    # A10: recomputed on this ticker's ruler (v2); see option_value.
    g2_dc = min(inp["g2_dc_src"], g_cap(inp["r_op"]))
    v_opt, opt_inc, dc_margin, pe_dc = option_value(inp, roe_m, g2_dc, inp["r_op"])
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
    print(f"ROE basis: BPS_open_FY27 = {bps_open:.2f} USD/sh (FY26Q3 book {bps_q3:.2f} rolled over Q4 FY26 unbooked "
          f"{unbooked:.2f}/sh at b1 = g/ROE = {b1:.4f}, g_roll {g_roll:.2%} = M-tier EPS-weighted g2, QTL at 0); "
          f"FY26Q3-book basis would read ROE_M {eps_by_tier[1] * inp['shares'] / inp['equity']:.1%}")
    print(f"B bucket (modelled-as-distributed, actually retained): actual retention {1 - inp['payout_3y']:.1%} − b1 → "
          f"{excess_cash:.2f} USD/sh over Q4 FY26 (disclosure only; not a leg, not in BPS)")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}"
          f" V_opt/M={v_opt / M:.1%}")
    for line in tier_report(
        tuple(base), tuple(base[i] / eps_by_tier[i] for i in range(3)), tuple(eps_by_tier)
    ):
        print(line)
    print(f"V_opt chain: ({inp['dc_target_rev']:g} - {inp['dc_cons_rev']:g}) $M DC rev x HSBC FY27 incremental "
          f"pre-tax margin {dc_margin:.2%} x (1-t) -> {opt_inc:.4f}/sh x PE {pe_dc:.2f}x (r {inp['r_op']:.0%}, "
          f"g2_dc {g2_dc:.2%} from src {inp['g2_dc_src']:.2%}, ROE_M {roe_m:.1%}) / 1.1^{int(inp['t_opt']) - NUM_YEAR} = {v_opt:.2f}")
    v_alt = option_value(inp, roe_m, 0.04, inp["r_op"])[0]
    print(f"V_opt sensitivity: g2_dc 4% (AVGO XPU mega-hardware cap) -> {v_alt:.2f}; undiscounted {v_opt * (1 + inp['r_op']) ** (inp['t_opt'] - NUM_YEAR):.2f}")
    print(f"表3  V_opt={v_opt:.2f}  " + "  ".join(
        f"{n}:{base[i]:.2f}+{P_K[i]:.2f}xV={adj[i]:.2f}" for i, n in enumerate("LMH")))

    # Flat@M control: QTL multiples pinned to the M rung; numerator ladder still holds.
    flat_m = [
        ebt_by_tier[i]["qtl"] * ev_ebit[1]
        + sum(eps_by_tier_map[i][leg] * pe_op[leg] for leg in OP_LEGS)
        for i in range(3)
    ]
    print(f"Flat@{ev_ebit[1]:g}×  L={flat_m[0]:.2f} M={flat_m[1]:.2f} H={flat_m[2]:.2f}")

    # Disclosure only (A15): the g2 lever.  It never reaches the base.
    def anchors_at(r: float, g2_shift: dict[str, float]) -> list[float]:
        pe = {leg: perpetual_pe(inp[f"g2_{leg}"] + g2_shift.get(leg, 0.0), roe_m, r) for leg in OP_LEGS}
        return [
            ebt_by_tier[i]["qtl"] * ev_ebit[i]
            + sum(eps_by_tier_map[i][leg] * pe[leg] for leg in OP_LEGS)
            for i in range(3)
        ]

    cap = g_cap(inp["r_op"])
    basket = baskets.get("r_op")
    basket_name = BASKET_R[basket][0] if basket in BASKET_R else "unnamed"  # missing tag is reported below
    print(f"r_op {inp['r_op']:.1%} = 篮 {basket} {basket_name} | g_cap(r) {cap:.1%}")
    for label, shift in (
        ("all -1pp", {leg: -0.01 for leg in OP_LEGS}),
        ("hs/iot +1pp", {leg: +0.01 for leg in OP_LEGS if inp[f"g2_{leg}"] + 0.01 <= cap + 1e-9}),
        ("auto -1pp", {"auto": -0.01}),
        ("auto @cap 6%", {"auto": cap - inp["g2_auto"]}),  # v1 value / broad-semis cluster capped
    ):
        lmh = anchors_at(inp["r_op"], shift)
        print(f"g2 lever {label:12} L={lmh[0]:.2f} M={lmh[1]:.2f} H={lmh[2]:.2f}")
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_op 1:1 on the three Gordon legs; the QTL leg prices on EV/EBIT (no r), and
    # ROE_M / numerators stay put.  Disclosure only: base L/M/H are the 中枢 column.
    def band_rf(dr: float) -> tuple[float, float, float]:
        lmh = anchors_at(inp["r_op"] + dr, {})
        return lmh[0], lmh[1], lmh[2]

    rf = rf_block(LISTING_CCY, {"r_op": inp["r_op"]}, band_rf)
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors += ["r_f readings: the dr = 0 column does not reproduce L/M/H"]

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
        md, {"L": L, "M": M, "H": H, "A": A, "B": B}, tol=0.05
    )
    errors += ladder("base", L, M, H)
    # A2e-2c: the tiers must already separate in the numerator, before multiples.
    errors += ladder("eps", *eps_by_tier)
    errors += ladder("ev_ebit_ts", *ev_ebit)
    errors += check_no_p_leak(L, adj[0])
    # valuation-rules「§r 篮子」: r_op must be the basket the Inputs source cell names (A15).
    if "r_op" not in baskets:
        errors += ["r_op: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)"]
    errors += check_r(inp["r_op"], "r_op", baskets.get("r_op"))
    # valuation-rules「永续增长口径」: every Gordon leg's perpetual g stays at or below g_cap(r).
    for leg in OP_LEGS:
        errors += check_g_cap(inp[f"g2_{leg}"], inp["r_op"], f"g2_{leg}")
    if not P_K[0] <= P_K[1] <= P_K[2]:
        errors += [f"p_k must be non-decreasing, got {P_K}"]
    errors += check_g_cap(g2_dc, inp["r_op"], "g2_dc")
    if inp["r_op"] - g2_dc < MIN_R_MINUS_G:
        errors += [f"r - g2_dc = {inp['r_op'] - g2_dc:.2%} < 2% — at the pole"]
    if inp["t_opt"] <= NUM_YEAR:
        errors += ["option year must lie after the numerator year (A10)"]
    if inp["dc_target_rev"] <= inp["dc_cons_rev"]:
        errors += ["DC target does not exceed what consensus already holds — no option units (A10)"]
    said_v = stated_v_opt(md)
    if said_v is None or abs(said_v - v_opt) > 0.05:
        errors += [f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}"]
    if FORMULA_ID not in md:
        errors += [f"formula_id {FORMULA_ID} missing from framework"]
    if v_opt < 0:
        errors += [f"V_opt must be >= 0, got {v_opt:.2f}"]
    # A2e-7a also bars p from the Inputs table itself.
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors += [f"p-class fields must not appear in Inputs (A2e-7a): {leaked}"]
    # Only a clean run feeds the daily digest (output/rates/).
    if not errors:
        write_rf_readings("QCOM.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
