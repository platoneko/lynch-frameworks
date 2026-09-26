#!/usr/bin/env python3
"""SOFI.US (SoFi Technologies) valuation eval — recompute anchors from frameworks/SOFI.US.md.

frameworks/SOFI.US.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: sofi_gordon_tbv_oe_v1

Main ruler: Gordon PB-ROE on tangible book, with *owner earnings* as the numerator.
  r comes from the leg's basket (A24: whole company → 篮 6 周期商品 / 小盘, 13%),
  read from the Inputs row and checked against gordon.BASKET_R via the 篮 N tag.
  SoFi expenses all customer acquisition, so GAAP NI is an investment-phase P&L.
  OE = NI + growth-acquisition-spend × (1 - t); the growth share of acquisition
  spend is derived from the fair-value model's runoff inputs (CPR + default +
  amortisation), and LPB origination marketing is treated as COGS.

  M/H (two-stage on, n = 1.5y — the excess-capital runway back to own-tested CET1 16%):
      E_term = OE_27 - GS_27 × (g / rev_g_27) × (1 - t)      # growth spend g needs
      b      = g × cet1_tgt × RWA_T / E_term                   # capital retention g needs
      P      = (1 - b) × E_term / (r - g) / shares / (1 + r)^n
  L (two-stage off, g = 0, undiscounted):
      OE_L = OE_26 - (ΔNII_{+100bp} + ΔCredit_{NCO→3.8%}) × (1 - t);  P_L = OE_L / r / shares

Run:  python3 eval/SOFI.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from math import ceil

from lib.gordon import check_g_cap, check_r, check_transition_years, g_cap  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "SOFI.US.md"
FORMULA_ID = "sofi_gordon_tbv_oe_v1"
LISTING_CCY = "USD"
MAINT_TOL = 0.005
# Own-tested P/TBV band (2022-12 trough 1.26×, 2026-07 cycle low 2.03×) — guardrail, not a generator.
PB_BAND = (1.26, 2.03)

REQUIRED = [
    "price", "shares", "tce", "cet1_cap", "cet1_ratio", "cet1_tgt",
    "ni_q1_26", "ni_q2_26", "ni_q3e_26", "ni_q4e_26",
    "eps_27_l", "eps_27_m", "eps_27_h", "rev_g_27",
    "lend_mkt_q", "fs_mkt_q", "pl_book", "pl_runoff", "sl_book", "sl_runoff",
    "orig_q", "lpb_q", "maint_fs", "tax", "r_op", "g2", "g2_l", "n",
    "nii_shock", "pl_loss_rate", "nco_peak", "mark_rate", "credit_sens_10",
    "rev_27", "piper_rev_g_28", "incr_ni_margin",
]
N_FY28 = 2.5  # coordinate band only: stage one stretched through FY28
# Stage one may only run as long as a consensus exists: FY26 and FY27 (A5/A6).
CONSENSUS_YEARS = 2


def maint_lend_of(inp: dict[str, float]) -> float:
    maint_orig_q = (inp["pl_book"] * inp["pl_runoff"] + inp["sl_book"] * inp["sl_runoff"]) / 4.0
    return (maint_orig_q + inp["lpb_q"]) / inp["orig_q"]


def growth_spend_26(inp: dict[str, float], maint_lend: float) -> float:
    return 4.0 * (inp["lend_mkt_q"] * (1.0 - maint_lend) + inp["fs_mkt_q"] * (1.0 - inp["maint_fs"]))


def tier_mh(inp: dict[str, float], eps27: float, gs27: float, g: float) -> dict[str, float]:
    """One M/H tier: returns price per share plus the disclosed intermediates."""
    ni_h2 = inp["ni_q3e_26"] + inp["ni_q4e_26"]
    ni27 = eps27 * inp["shares"]
    return _terminal(inp, ni_term=ni27, gs_term=gs27, rev_g_term=inp["rev_g_27"], g=g,
                     retained_before=ni_h2, n=inp["n"])


def _terminal(inp: dict[str, float], *, ni_term: float, gs_term: float, rev_g_term: float,
              g: float, retained_before: float, n: float) -> dict[str, float]:
    """Gordon terminal on owner earnings of the stage-end year, discounted n years.

    `retained_before` is the NI retained between today and the terminal year's
    opening balance; the terminal year's own NI is added on top for TCE_T / RWA_T.
    """
    t, r = inp["tax"], inp["r_op"]
    oe = ni_term + gs_term * (1.0 - t)
    e_term = oe - gs_term * (g / rev_g_term) * (1.0 - t)
    rwa_t = (inp["cet1_cap"] + retained_before + ni_term) / inp["cet1_tgt"]
    b = g * inp["cet1_tgt"] * rwa_t / e_term
    mult = (1.0 - b) / (r - g)
    tv = mult * e_term
    tce_open = inp["tce"] + retained_before
    tce_t = tce_open + ni_term
    return {
        "ni27": ni_term, "oe27": oe, "e_term": e_term, "rwa_t": rwa_t, "b": b,
        "mult": mult, "tv": tv, "tce_t": tce_t,
        "rotce_oe": oe / (0.5 * (tce_open + tce_t)),
        "pb_t": tv / tce_t,
        "price": tv / inp["shares"] / (1.0 + r) ** n,
    }


def fy28_coordinate(inp: dict[str, float], eps27: float, gs27: float, g: float) -> dict[str, float]:
    """A22 coordinate band (single-house Piper FY28 × own realized incremental NI margin).

    Reference only — never an anchor, never a zone input.  Same terminal mechanics
    as M/H with the stage stretched one year (N_FY28) so the two bands are comparable.
    """
    ni_h2 = inp["ni_q3e_26"] + inp["ni_q4e_26"]
    ni27 = eps27 * inp["shares"]
    d_rev_28 = inp["rev_27"] * inp["piper_rev_g_28"]
    ni28 = ni27 + inp["incr_ni_margin"] * d_rev_28
    gs28 = gs27 * (1.0 + inp["piper_rev_g_28"])
    out = _terminal(inp, ni_term=ni28, gs_term=gs28, rev_g_term=inp["piper_rev_g_28"], g=g,
                    retained_before=ni_h2 + ni27, n=N_FY28)
    out["rwa_g_28"] = out["rwa_t"] / ((inp["cet1_cap"] + ni_h2 + ni27) / inp["cet1_tgt"]) - 1.0
    return out


def tier_l(inp: dict[str, float], gs26: float) -> dict[str, float]:
    t, r = inp["tax"], inp["r_op"]
    ni_26 = inp["ni_q1_26"] + inp["ni_q2_26"] + inp["ni_q3e_26"] + inp["ni_q4e_26"]
    oe26 = ni_26 + gs26 * (1.0 - t)
    uplift = inp["nco_peak"] / inp["pl_loss_rate"] - 1.0
    d_credit = inp["pl_book"] * inp["pl_loss_rate"] * uplift
    oe_l = oe26 - (inp["nii_shock"] + d_credit) * (1.0 - t)
    mark_credit = inp["credit_sens_10"] * uplift / 0.10
    tce_l = inp["tce"] - inp["mark_rate"] - mark_credit
    price = oe_l / (r - inp["g2_l"]) / inp["shares"]  # g2_l = 0 → 1/r
    return {
        "ni_26": ni_26, "oe26": oe26, "d_credit": d_credit, "oe_l": oe_l,
        "mark_credit": mark_credit, "tce_l": tce_l,
        "rotce_l": oe_l / tce_l, "pb_l": price * inp["shares"] / tce_l, "price": price,
    }


def implied_g(inp: dict[str, float], gs27: float, lo: float = 0.0, hi: float | None = None) -> float:
    """Perpetual g at which the M numerator reproduces the market price (reference only).

    The search stops just short of the pole at g = r, so a price the multiple
    cannot reach reads as g* ≈ r (pathological), not as a clipped constant.
    """
    if hi is None:
        hi = inp["r_op"] - 0.0005
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if tier_mh(inp, inp["eps_27_m"], gs27, mid)["price"] < inp["price"]:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r, g, t = inp["r_op"], inp["g2"], inp["tax"]
    # valuation-rules.md「§r 篮子」: r is the named basket's value (A24), never a per-ticker dial.
    baskets = parse_baskets(md)
    if "r_op" not in baskets:
        errors.append("r_op: Inputs source cell names no 篮 N (A24 归篮)")
    errors += check_r(r, "r_op", baskets.get("r_op"))
    # valuation-rules.md「永续增长口径」: perpetual g capped by g_cap(r); stage one bounded by consensus years.
    errors += check_g_cap(g, r, "g2")
    errors += check_g_cap(inp["g2_l"], r, "g2_l")
    errors += check_transition_years(ceil(inp["n"]), CONSENSUS_YEARS, "n")
    if r - g <= 0:
        errors.append(f"g2={g} must be < r={r}")
    if inp["g2_l"] != 0.0:
        errors.append("g2_l must be 0 — L world is defined as growth stall (A7)")
    if not 0.0 < inp["maint_fs"] < 1.0:
        errors.append(f"maint_fs={inp['maint_fs']} must lie in (0,1)")
    if inp["nco_peak"] <= inp["pl_loss_rate"]:
        errors.append("nco_peak must exceed pl_loss_rate — L is a credit *deterioration*")

    # A18: maintenance share is recomputed from the fair-value model inputs, never typed in.
    maint_lend = maint_lend_of(inp)
    if not 0.0 < maint_lend < 1.0:
        errors.append(f"maint_lend={maint_lend:.3f} out of (0,1)")
    if abs(maint_lend - 0.464) > MAINT_TOL:
        errors.append(f"maint_lend recomputed {maint_lend:.4f} vs stated 0.464 (tol {MAINT_TOL})")

    gs26 = growth_spend_26(inp, maint_lend)
    gs27 = gs26 * (1.0 + inp["rev_g_27"])

    tl = tier_l(inp, gs26)
    tm = tier_mh(inp, inp["eps_27_m"], gs27, g)
    th = tier_mh(inp, inp["eps_27_h"], gs27, g)
    for lab, tier in (("M", tm), ("H", th)):
        if not 0.0 < tier["b"] < 1.0:
            errors.append(f"retention b_{lab}={tier['b']:.3f} out of (0,1)")
    if tl["oe_l"] <= 0:
        errors.append(f"OE_L={tl['oe_l']:.1f} must be positive")

    # A2e-2c: the ladder must already stand in the numerators.
    errors += ladder("numerator OE_L < E_term_M < E_term_H", tl["oe_l"], tm["e_term"], th["e_term"])
    errors += ladder("ROTCE", tl["rotce_l"], tm["rotce_oe"], th["rotce_oe"])
    if errors:
        return report(errors, "FAIL (inputs/guards)")

    L, M, H = tl["price"], tm["price"], th["price"]
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # flat-multiple check: every tier on mult_M; L also pays for g's growth spend and is discounted.
    disc = (1.0 + r) ** inp["n"]
    e_l_flat = tl["oe_l"] - gs26 * (g / inp["rev_g_27"]) * (1.0 - t)
    L_flat = e_l_flat * tm["mult"] / inp["shares"] / disc
    H_flat = th["e_term"] * tm["mult"] / inp["shares"] / disc
    if not (L_flat < M < H_flat):
        errors.append(f"flat-multiple ladder failed: {L_flat:.2f} / {M:.2f} / {H_flat:.2f}")

    g_star = implied_g(inp, gs27)
    e_needed = inp["price"] * inp["shares"] * disc / tm["mult"]
    x_excess = inp["cet1_cap"] - inp["cet1_tgt"] * inp["cet1_cap"] / inp["cet1_ratio"]

    print(f"formula_id={FORMULA_ID}")
    print(f"r_op={r:g} 篮 {baskets.get('r_op')}  g2={g:g} (cap {g_cap(r):.2f})")
    print(f"maint_lend={maint_lend:.3f}  GS26={gs26:.1f}  GS27={gs27:.1f}  X={x_excess:.0f}")
    print(f"{'档':<3}{'分子':>10}{'倍数':>8}{'ROTCE':>8}{'PB':>7}{'锚点':>8}")
    print(f"{'L':<3}{tl['oe_l']:10.1f}{1 / r:8.2f}{tl['rotce_l']:8.1%}{tl['pb_l']:7.2f}{L:8.2f}   (OE26 {tl['oe26']:.1f} − 冲击, g=0, 不折现)")
    print(f"{'M':<3}{tm['e_term']:10.1f}{tm['mult']:8.2f}{tm['rotce_oe']:8.1%}{tm['pb_t']:7.2f}{M:8.2f}   (OE27 {tm['oe27']:.1f}, b={tm['b']:.3f}, 折 {inp['n']:.1f}y)")
    print(f"{'H':<3}{th['e_term']:10.1f}{th['mult']:8.2f}{th['rotce_oe']:8.1%}{th['pb_t']:7.2f}{H:8.2f}   (OE27 {th['oe27']:.1f}, b={th['b']:.3f})")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.0%}  V_opt/M=0")
    print(
        f"分解 L/M = 分子比 {tl['oe_l'] / tm['e_term']:.3f} × 倍数比 {(1 / r) / tm['mult']:.3f} × 折现差 {disc:.3f}; "
        f"H/M = 分子比 {th['e_term'] / tm['e_term']:.3f} × 倍数比 {th['mult'] / tm['mult']:.3f}"
    )
    print(f"flat(mult_M 全档): L={L_flat:.2f} M={M:.2f} H={H_flat:.2f}")
    print(f"price={inp['price']} zone={zone}  P/H={inp['price'] / H:.3f}  P/TBV={inp['price'] * inp['shares'] / inp['tce']:.2f}")
    print(f"市价隐含 g*={g_star:.2%} (M 分子)；g={g:.0%} 下需 E_term {e_needed:.0f} = M 的 {e_needed / tm['e_term']:.2f}×")
    # Disclosure only (A24 / Outputs): implied r(P) is the single-stage Gordon r = g + E/P on the
    # M-tier consensus EPS; the band-low check is ③ 护栏 read on M/H only (L is *built* to sit at
    # the tested trough).  The 2022-12 band low printed in a loss year (1b 失真), so a reading
    # below it is disclosed, not a downgrade trigger and not an error.
    implied_r = g + inp["eps_27_m"] / inp["price"]
    print(f"隐含 r(P)={implied_r:.1%} (g2 + eps_27_m / price) vs 篮 {baskets.get('r_op')} r {r:.0%}：δ {implied_r - r:+.1%}（只披露）")
    mh_ok = all(PB_BAND[0] <= pb for pb in (tm["pb_t"], th["pb_t"]))
    print(
        f"③ 护栏 P/TBV 带 {PB_BAND}: PB_M {tm['pb_t']:.2f} / PB_H {th['pb_t']:.2f} → "
        f"{'within' if mh_ok else '形式出带（带下沿 2022-12 亏损年印出，1b 判失真 → ③ 不可判定，只披露）'}；"
        f"PB_L {tl['pb_l']:.2f} vs 实测底 {PB_BAND[0]}（贴底属构造）"
    )
    print(f"地板（只披露）: 无独立清算地板；L 世界一次性标记 −{inp['mark_rate'] + tl['mark_credit']:.0f} → TBV_L {tl['tce_l']:.0f}，TBVPS_L {tl['tce_l'] / inp['shares']:.2f}（不进 g=0 的价格）")
    for lab, key in (("均值", "seller_tp_mean"), ("下沿", "seller_tp_lo"), ("上沿", "seller_tp_hi")):
        if key in inp:
            print(f"卖方 TP {lab} {inp[key]:.2f} → zone={zone_of(inp[key], L, M, H)}（映射，不进公式）")
    # sensitivities (reference)
    for fsm in (0.0, 1.0):
        gs = 4.0 * (inp["lend_mkt_q"] * (1 - maint_lend) + inp["fs_mkt_q"] * (1 - fsm)) * (1 + inp["rev_g_27"])
        print(f"敏感性 maint_fs={fsm:.0%}: M={tier_mh(inp, inp['eps_27_m'], gs, g)['price']:.2f}")
    for gg in (0.03, 0.05):
        print(f"敏感性 g={gg:.0%}: M={tier_mh(inp, inp['eps_27_m'], gs27, gg)['price']:.2f} H={tier_mh(inp, inp['eps_27_h'], gs27, gg)['price']:.2f}")
    print(f"敏感性 g_H=5%: H={tier_mh(inp, inp['eps_27_h'], gs27, 0.05)['price']:.2f}")
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves r_op
    # 1:1 — the L 1/r multiple, the M/H Gordon multiple and their n-year discount —
    # while numerators, g and the CET1 retention stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        inp_dr = {**inp, "r_op": r + dr}
        return (
            tier_l(inp_dr, gs26)["price"],
            tier_mh(inp_dr, inp["eps_27_m"], gs27, g)["price"],
            tier_mh(inp_dr, inp["eps_27_h"], gs27, g)["price"],
        )

    rf = rf_block(LISTING_CCY, {"r_op": r}, band_rf, inp["price"])
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    # A22 candidate band (AGENTS.md「共识升级候选带」): recomputed and compared with the
    # Outputs 候选带 line the digest reads; never a zone input here.
    cm = fy28_coordinate(inp, inp["eps_27_m"], gs27, g)
    ch = fy28_coordinate(inp, inp["eps_27_h"], gs27, g)
    cand = (L, cm["price"], ch["price"])  # L′ = L: the L world carries no transition
    stated = load_framework(FRAMEWORK).candidate
    if stated is None:
        errors.append("候选带 line missing from Outputs (A22)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), stated, cand):
            if abs(said - got) > 0.05:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")
    print(
        f"候选带（Piper 营收 +{inp['piper_rev_g_28']:.0%} × 增量净利率 {inp['incr_ni_margin']:.0%}，n={N_FY28}；不进底牌/zone 判定）: "
        f"NI28 {cm['ni27']:.0f}/{ch['ni27']:.0f}  E_term {cm['e_term']:.0f}/{ch['e_term']:.0f}  "
        f"b {cm['b']:.3f}/{ch['b']:.3f}  L′/M′/H′={cand[0]:.2f}/{cand[1]:.2f}/{cand[2]:.2f}  "
        f"候选 zone={zone_of(inp['price'], *cand)}  P/H′={inp['price'] / ch['price']:.3f}  "
        f"CET1 钉 16% 时 FY28 RWA 增速 {cm['rwa_g_28']:.0%}"
    )

    # Only a clean run feeds the daily digest (output/rates/).
    if not errors:
        write_rf_readings("SOFI.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
