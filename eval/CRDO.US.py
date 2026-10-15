#!/usr/bin/env python3
"""CRDO.US (Credo Technology) valuation eval — recompute anchors from
frameworks/CRDO.US.md.

frameworks/CRDO.US.md is the source of truth; this script re-derives L/M/H /
A/B and the candidate band from the §3 Inputs table and exits 1 on mismatch.
The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so nothing
here reads a quote.

formula_id: crdo_fy28_econ_eps_gordon_macro_g2_k_v2

Operating value plus excess cash (valuation-rules「经营价值与超额现金」,
2026-10-15 framework correction, A22): excess cash C_ex = extended net cash
- operating cash anchor (min(lowest net cash / revenue, 2 months of revenue) x
FY26 revenue) is split out and added back per share at lambda 1; its after-tax
income leaves every numerator, and C_ex leaves the FY28 opening book, so the
per-tier ROE becomes an operating RONIC.  The retention haircut k applies to
the operating value only.  Historical-price readings (③ band low, 对账门
coordinates) are restated on operating multiples.

Main ruler: whole company, one leg (basket 4).  Numerator year FY2028 (fiscal
year ending ~2028-04) — the furthest year with a >=2-house consensus range.
Numerator = consensus non-GAAP EPS minus after-tax SBC per non-GAAP diluted
share ("economic EPS"), because the street's non-GAAP adds back an SBC bill
of roughly 40% of non-GAAP operating income (A1).  SBC for the year =
max(Q2 FY27 guided quarterly SBC x 4, FY26 realised SBC/revenue x the tier's
FY28 revenue).  L = FY28 digestion year: revenue and non-GAAP EPS stay at the
FY27 consensus (A3).  M / H = FY28 consensus mean / high.

Multiple: perpetual Gordon at r 10% (basket 4) and g2 4% (named macro; the
peer cluster is filtered to n = 0, A7), each tier at its own ROE = FY28 EPS /
FY28 opening book (Q1 FY27 equity + the unbooked FY27 economic profit retained
at b = g/ROE, fixed point, A8).  No transition year: no FY29 consensus.
Anchors = operating value x (1 - k) (A10) + C_ex per share (lambda 1, A22).

Candidate band (A21): the single-house FY29 input (Jefferies CY28 bull EPS)
as a one-year transition on M / H; L' = L.

Run:  python3 frameworks/eval/CRDO.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import check_capex_mount  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    check_branch,
    check_g_cap,
    check_r,
    g_cap,
    implied_g,
    payout,
    perpetual_pe,
    two_stage_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    outputs_section,
    parse_baskets,
    parse_inputs,
    report,
)
from eval.lib.rf_report import rf_block  # noqa: E402
from eval.lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from eval.lib.zones import cut_points  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "CRDO.US.md"
FORMULA_ID = "crdo_fy28_econ_eps_gordon_macro_g2_k_v2"
TICKER = "CRDO.US"
LISTING_CCY = "USD"
TOL = 0.05
MIN_R_MINUS_G = 0.02
TIERS = ("L", "M", "H")

REQUIRED = [
    "eps_fy27_m", "eps_fy27_q1", "eps_fy28_l", "eps_fy28_m", "eps_fy28_h",
    "rev_fy27_cons", "rev_fy28_m", "rev_fy28_h",
    "sbc_q1_fy27", "sbc_q2_guide", "sbc_fy26", "rev_fy26", "tax_sbc",
    "shares_ng", "equity_q1", "r_perp", "g2", "k_l", "k_m", "k_h", "payout_obs",
    "pe_own_min", "pe_own_max", "lb_fwd_eps", "pb_own_min",
    "jef_eps_cy28", "capex_l", "capex_m", "capex_h",
    "net_cash_ext_q1", "ncash_rev_min", "c_ex", "cash_yield", "tax_eff", "payout_op",
    "px_pe_lo", "net_cash_ext_pe_lo", "shares_pe_lo", "bps_pe_lo",
]
ANCHOR_CAP = 2 / 12  # 2 months of revenue (valuation-rules ①「经营所需现金锚」)
UNBOOKED_FY27 = 0.75  # Q2-Q4 FY27: share of FY27 cash income not yet in Q1 equity

_CANDIDATE = re.compile(
    r"候选带（[^）]+）[^\n]*?L′ = \*\*([0-9.]+)\*\*[^\n]*?M′ = \*\*([0-9.]+)\*\*[^\n]*?H′ = \*\*([0-9.]+)\*\*"
)


def check_inputs(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    e: list[str] = []
    if "r_perp" not in baskets:
        e.append("r_perp: Inputs source cell names no 篮 N (A6)")
    e += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    e += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    if inp["r_perp"] - inp["g2"] < MIN_R_MINUS_G:
        e.append(f"r - g2 < {MIN_R_MINUS_G:.0%}: at the pole")
    if inp["g2"] <= 0:
        e.append("g2 <= 0 barred: FY27 -> FY28 consensus rises (同世界门, A7)")
    e += ladder("FY28 consensus range", inp["eps_fy28_l"], inp["eps_fy28_m"], inp["eps_fy28_h"])
    e += ladder("FY28 revenue", inp["rev_fy27_cons"], inp["rev_fy28_m"], inp["rev_fy28_h"])
    if not (0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] < 1):
        e.append("k must satisfy 0 <= k_L <= k_M <= k_H < 1 (留存去向审计, A10)")
    if not (0 <= inp["tax_sbc"] < 0.25):
        e.append("tax_sbc out of range")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        e.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")
    return e


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    baskets = parse_baskets(md)
    errors = check_inputs(inp, baskets)
    errors += check_capex_mount((inp["capex_l"], inp["capex_m"], inp["capex_h"]))
    if errors:
        return report(errors)

    r, g2 = inp["r_perp"], inp["g2"]
    sh = inp["shares_ng"]  # 百万股; money inputs are 百万 USD
    after_tax = 1 - inp["tax_sbc"]

    # ---- Step 1: FY28 economic EPS (A1 / A3 / A4) ----
    sbc_floor = inp["sbc_q2_guide"] * 4
    sbc_ratio = inp["sbc_fy26"] / inp["rev_fy26"]
    rev = {"L": inp["rev_fy27_cons"], "M": inp["rev_fy28_m"], "H": inp["rev_fy28_h"]}
    eps_ng = {"L": inp["eps_fy27_m"], "M": inp["eps_fy28_m"], "H": inp["eps_fy28_h"]}
    sbc = {t: max(sbc_floor, sbc_ratio * rev[t]) for t in TIERS}
    # ---- Step 0: excess cash (A22) ----
    anchor_ratio = min(inp["ncash_rev_min"], ANCHOR_CAP)
    anchor = max(anchor_ratio * inp["rev_fy26"], 0.0)
    c_ex = inp["net_cash_ext_q1"] - anchor
    if abs(c_ex - inp["c_ex"]) > 0.05:
        errors.append(f"c_ex {inp['c_ex']} != net_cash_ext_q1 − anchor {c_ex:.3f}")
    if c_ex < 0.15 * inp["equity_q1"]:
        errors.append("c_ex below 15% of equity: the excess-cash line should not exist (A22)")
    cps = c_ex / sh
    inc = c_ex * inp["cash_yield"] * (1 - inp["tax_eff"]) / sh  # after-tax cash income per share

    eps_econ = {t: eps_ng[t] - sbc[t] * after_tax / sh for t in TIERS}
    eps = {t: eps_econ[t] - inc for t in TIERS}  # operating economic EPS

    # ---- Step 2: FY28 opening operating book, fixed point on b = g/RONIC (A8 / A22) ----
    bps0 = inp["equity_q1"] / sh - cps
    rem_econ = (inp["eps_fy27_m"] - inp["eps_fy27_q1"]) - inp["sbc_q2_guide"] * 3 * after_tax / sh
    rem = rem_econ - UNBOOKED_FY27 * inc

    def book(e: float, g: float, b0: float = bps0, n: float = rem) -> tuple[float, float]:
        bps = b0 + n
        for _ in range(200):
            nxt = b0 + n * min(1.0, g / (e / bps))
            if abs(nxt - bps) < 1e-12:
                break
            bps = nxt
        return bps, e / bps

    def anchors_at(rr: float, g: float = g2) -> tuple[float, float, float]:
        out = []
        for t in TIERS:
            _, roe_ = book(eps[t], g)
            out.append(eps[t] * perpetual_pe(g, roe_, rr) * (1 - k[t]) + cps)
        return tuple(out)

    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}
    bps, roe, pe = {}, {}, {}
    for t in TIERS:
        bps[t], roe[t] = book(eps[t], g2)
        pe[t] = perpetual_pe(g2, roe[t], r)
    pre = {t: eps[t] * pe[t] for t in TIERS}  # operating value before k
    L, M, H = (pre[t] * (1 - k[t]) + cps for t in TIERS)
    A, B = cut_points(L, M, H)
    errors += ladder("anchors", L, M, H)
    for t in TIERS:
        if roe[t] - r < 0.03:
            errors.append(f"{t}: ROE {roe[t]:.3f} not in the monotone domain at r {r:g}")
        errors += check_branch(g2, roe[t], r, inp["payout_op"], f"g2@{t}")
        # ③ constraint 2: g <= (1 - d) x RONIC (d = paid-out share, here none).
        if g2 > (1 - inp["payout_obs"]) * roe[t]:
            errors.append(f"{t}: g2 {g2:.2%} above (1 − d) × RONIC {(1 - inp['payout_obs']) * roe[t]:.2%}")

    # ---- A2e-2c flat ladder + decomposition (operating value; cash is the same add-on) ----
    flat_errs, flat = flat_multiple_ladder((eps["L"], eps["M"], eps["H"]), pe["M"])
    errors += flat_errs
    flat = tuple(f + cps for f in flat)
    op = {t: pre[t] * (1 - k[t]) for t in TIERS}
    dec = decompose((op["L"], op["M"], op["H"]), tuple(pe[t] * (1 - k[t]) for t in TIERS))

    # ---- Candidate band (A21): Jefferies' bull-case EPS is a level (construction §7h) ----
    # A single-point upside case caps H′ at the source (FY29 non-GAAP = 18, SBC share held at the
    # tier ratio); M′ copies base M — the single point is both midpoint and top.
    g1 = max(0.0, inp["jef_eps_cy28"] / inp["eps_fy28_h"] - 1)
    cand = {"L": L, "M": M}
    cand_roe, cand_b1 = {}, {}
    for t in ("H",):
        _, cand_roe[t] = book(eps[t], g1)
        cand_b1[t] = g1 / cand_roe[t]
        cand[t] = eps[t] * two_stage_pe(g1, 1, g2, cand_roe[t], r) * (1 - k[t]) + cps
    errors += ladder("candidate band", cand["L"], cand["M"], cand["H"])

    # ---- Reconcile stated Outputs ----
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    cm = _CANDIDATE.search(outputs_section(md))
    if cm is None:
        errors.append("candidate band line not found in Outputs")
    else:
        for t, said in zip(TIERS, (float(x) for x in cm.groups())):
            if abs(said - cand[t]) > TOL:
                errors.append(f"candidate {t}′: stated {said} vs recomputed {cand[t]:.4f}")

    # ---- Report ----
    print(f"formula_id={FORMULA_ID}")
    print(f"r {r:g} (篮 {baskets['r_perp']}) g2 {g2:.2%} (named macro; cap {g_cap(r):.0%})")
    print(f"SBC FY28 = max(Q2 guide x4 {sbc_floor:.1f}, FY26 ratio {sbc_ratio:.2%} x revenue) "
          + " ".join(f"{t} {sbc[t]:.1f}" for t in TIERS) + f" ($M); after-tax x{after_tax:.3f} / {sh:.3f}M sh")
    print(f"超额现金: 扩展口径净现金 {inp['net_cash_ext_q1']:.1f} − 锚 {anchor:.1f}"
          f"（min(最低比例 {inp['ncash_rev_min']:.1%}, 2 个月 {ANCHOR_CAP:.1%}) × FY26 收入 {inp['rev_fy26']:.1f}）"
          f" = C_ex {c_ex:.1f}（每股 {cps:.3f}，占权益 {c_ex / inp['equity_q1']:.1%}，λ 1）;"
          f" 税后收益/股 {inc:.4f}（收益率 {inp['cash_yield']:.2%} × (1 − 税率 {inp['tax_eff']:.2%})）")
    print(f"FY28 opening operating book: BPS0 {bps0:.3f} (= {inp['equity_q1'] / sh:.3f} − {cps:.3f})"
          f" + unbooked FY27 operating EPS {rem:.3f} x b")
    for t in TIERS:
        print(f"{t}: nonGAAP {eps_ng[t]:.4f} - SBC/sh {sbc[t] * after_tax / sh:.4f} - cash inc {inc:.4f} = EPS_op {eps[t]:.4f}"
              f" | BPS_open {bps[t]:.3f} RONIC {roe[t]:.3f} PE {pe[t]:.3f} (payout {payout(g2, roe[t]):.3f})"
              f" -> {pre[t]:.2f} x (1-k {k[t]:.2f}) = {op[t]:.2f} + cash {cps:.2f} = {op[t] + cps:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat ladder @ M {pe['M']:.2f}x (pre-k, + cash): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"L/M {L / M:.3f} · H/M {H / M:.3f} · width {(H - L) / (2 * M):.3f} | operating value:"
          f" L/M {dec['lm']:.3f} = num {dec['num_lm']:.3f} x pe {dec['pe_lm']:.3f}, H/M {dec['hm']:.3f}"
          f" = num {dec['num_hm']:.3f} x pe {dec['pe_hm']:.3f} | V_opt/M 0")
    print(f"candidate (level: H capped at single-house bull CY28 {inp['jef_eps_cy28']:g}, FY29 g1_H {g1:+.2%};"
          f" M′ = M): L′ {cand['L']:.2f} M′ {cand['M']:.2f} H′ {cand['H']:.2f}"
          f"  A′ {(cand['L'] + cand['M']) / 2:.2f} B′ {(cand['M'] + cand['H']) / 2:.2f}; "
          + " ".join(f"{t} ROE {cand_roe[t]:.3f} b1 {cand_b1[t]:.2f}" for t in ("H",))
          + ("  [b1 > 1: stage-1 payout negative = growth funded by share issuance]"
             if max(cand_b1.values()) > 1 else ""))

    # ③ guardrail — band on non-GAAP forward EPS, restated on operating multiples at the band-low
    # day (price − that day's C_ex per share) ÷ (forward EPS − that day's cash income) (A17 / A22).
    if abs(inp["px_pe_lo"] / inp["bps_pe_lo"] - inp["pb_own_min"]) > 0.01:
        errors.append("px_pe_lo / bps_pe_lo do not reproduce pb_own_min (A18)")
    c_lo = (inp["net_cash_ext_pe_lo"] - anchor) / inp["shares_pe_lo"]  # same anchor: FY26 revenue (当年)
    inc_lo = c_lo * inp["cash_yield"] * (1 - inp["tax_eff"])
    eps_lo = inp["px_pe_lo"] / inp["pe_own_min"]
    pe_op_lo = (inp["px_pe_lo"] - c_lo) / (eps_lo - inc_lo)
    pb_op_lo = (inp["px_pe_lo"] - c_lo) / (inp["bps_pe_lo"] - c_lo)
    m_on_band = (M - cps) / (inp["lb_fwd_eps"] - inc)
    print(f"③ band low on operating multiple: ({inp['px_pe_lo']:g} − C_ex/sh {c_lo:.3f}) ÷ ({eps_lo:.3f} − {inc_lo:.4f})"
          f" = {pe_op_lo:.2f}x (whole-equity {inp['pe_own_min']:g}x; high {inp['pe_own_max']:g}x not restated)")
    print(f"  M operating same-basis: ({M:.2f} − {cps:.2f}) ÷ ({inp['lb_fwd_eps']:g} − {inc:.4f}) = {m_on_band:.2f}x -> "
          f"{'inside' if pe_op_lo <= m_on_band else 'below band low (distorted band: 不可判定, A17)'}")
    for t in TIERS:
        edge = pe_op_lo * (inp["lb_fwd_eps"] - inc)
        g_lo, ok = implied_g(edge / eps[t] / (1 - k[t]), roe[t], r)
        print(f"  band-low edge implied g @ {t} (operating): {g_lo:+.2%}{'' if ok else ' (ill-conditioned)'}")
    print(f"  C_ex/sh then {c_lo:.2f} vs now {cps:.2f} (x{c_lo / cps:.2f}"
          + ("; > 1x apart — if the market discounts cash, the historical operating multiple reads high)"
             if c_lo > 2 * cps or cps > 2 * c_lo else ")"))
    # 对账门 coordinates (A18) — disclosure, user-approved; operating basis + cash.
    e_over_r = eps["M"] / r + cps
    pb_floor = pb_op_lo * bps["M"] + cps
    print(f"对账门: E_op,M/r + cash {e_over_r:.2f} ({M / e_over_r - 1:+.1%}) | op-PB-floor {pb_op_lo:.2f} x op BPS {bps['M']:.2f}"
          f" + cash = {pb_floor:.2f} ({M / pb_floor - 1:+.1%}) | pre-k M {pre['M'] + cps:.2f}")
    # 多留部分 (④): modelled 1 − b − d left in the company; lambda 1 → PV stays out of the anchors.
    keep = {t: 1 - g2 / roe[t] - inp["payout_obs"] for t in TIERS}
    print("多留部分 (1 − b − d, $/股/年 @FY28): "
          + " ".join(f"{t} {keep[t]:.1%} {keep[t] * eps[t]:.2f}" for t in TIERS)
          + f" | PV(M, ÷(r−g2)) {keep['M'] * eps['M'] / (r - g2):.2f}; λ 1 → not in anchors"
          + f" | 经营口径派息 {inp['payout_op']:.1%} vs model {payout(g2, roe['M']):.1%}")
    for g in (g2 - 0.01, g2 + 0.01, g_cap(r)):
        v = anchors_at(r, g)
        print(f"  sens g2={g:.2%}: {v[0]:.2f}/{v[1]:.2f}/{v[2]:.2f}")
    print(f"  k = 0 reference: {pre['L'] + cps:.2f}/{pre['M'] + cps:.2f}/{pre['H'] + cps:.2f}")
    no_sbc = []
    rem_ns = (inp["eps_fy27_m"] - inp["eps_fy27_q1"]) - UNBOOKED_FY27 * inc
    for t in TIERS:
        e_ns = eps_ng[t] - inc
        _, roe_ns = book(e_ns, g2, bps0, rem_ns)
        no_sbc.append(e_ns * perpetual_pe(g2, roe_ns, r) * (1 - k[t]) + cps)
    print(f"  SBC not deducted (street basis): {no_sbc[0]:.2f}/{no_sbc[1]:.2f}/{no_sbc[2]:.2f}")
    print(f"capex axis implied share (wide, FY28 revenue): "
          + " ".join(f"{t} {rev[t] * 1e6 / inp[f'capex_{t.lower()}']:.2%}" for t in TIERS))

    # r_f readings (_AXIS.rates USD): Δr_f moves r_perp 1:1; numerators, g2, ROE stay put.
    rf = rf_block(LISTING_CCY, {"r_perp": r}, lambda dr: anchors_at(r + dr))
    if any(abs(x - y) > TOL for x, y in zip(anchors_at(r), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    if not errors:
        write_rf_readings(TICKER, rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
