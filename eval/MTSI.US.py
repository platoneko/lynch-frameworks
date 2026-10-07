#!/usr/bin/env python3
"""MTSI.US (MACOM Technology Solutions) valuation eval — recompute anchors from
frameworks/MTSI.US.md.

frameworks/MTSI.US.md is the source of truth; this script re-derives L/M/H /
A/B, the band-edge-r parallel table and the borrowed-year candidate band from
the §3 Inputs table and exits 1 on mismatch.  The doc carries no current price
(AGENTS.md「现价 — 禁写契约」), so nothing here reads a quote.

formula_id: mtsi_fy27_econ_eps_gordon_axis_g2_conv_v1

Main ruler: whole company, one leg (basket 4).  Numerator year FY2027 (fiscal
year ending ~2027-10-01) — the furthest year with a >=2-house consensus range.
Numerator = "economic EPS": consensus non-GAAP EPS is grossed up from the
company's 3% non-GAAP tax rate to pre-tax, SBC is deducted, and the result is
taxed at the company's own estimated annual effective rate (18.5%), because
the federal NOLs that carry the 3% run out within about a year (A1 / A2).
L = FY27 digestion year at the FY26 consensus; M / H = FY27 consensus mean /
high.

Multiple: perpetual Gordon at r 10% (basket 4) and g2 6% from the peer-ruler
axis `_AXIS.optical-electrical-chip` (named macro cap; one-name peer read
corroborates), each tier at its own ROE = FY27 economic NI / FY27 opening
equity (2026-07-03 equity + unbooked Q4 FY26 economic NI retained at
b = g/ROE, fixed point).  No transition: no FY28 consensus.  k = 0 (A11).

Per share: the 2029 convertible (principal in cash, excess in shares) is
priced the way the holder would choose — the lower of "deduct principal over
ex-convert shares" and "no deduction over fully converted shares".

Candidate band (A20): one borrowed transition year — the data-center leg
grows at the lender's (MRVL Connectivity, via the axis) FY29 rate, the rest
of the company at g2 — two_stage_pe(n=1).  L' = L.

Run:  python3 frameworks/eval/MTSI.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    check_branch,
    check_g_cap,
    check_r,
    g_cap,
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

FRAMEWORK = REPO_ROOT / "frameworks" / "MTSI.US.md"
AXIS = REPO_ROOT / "frameworks" / "axes" / "optical-electrical-chip.md"
LENDER = REPO_ROOT / "frameworks" / "MRVL.US.md"
FORMULA_ID = "mtsi_fy27_econ_eps_gordon_axis_g2_conv_v1"
TICKER = "MTSI.US"
LISTING_CCY = "USD"
TOL = 0.05
MIN_R_MINUS_G = 0.02
TIERS = ("L", "M", "H")

# (this ticker's Inputs key, axis Inputs key): rows taken from the peer-ruler axis.
AXIS_ROWS = (("g2", "g2_oe_chip"), ("g_borrow", "g1_borrow_mrvl_conn"))

REQUIRED = [
    "eps_fy26_cons", "eps_fy27_l", "eps_fy27_m", "eps_fy27_h",
    "rev_fy26_cons", "rev_fy27_m", "rev_fy27_h",
    "eps_q4_guide", "rev_q4_guide", "sbc_q3", "sbc_9m", "rev_9m",
    "tax_ng", "tax_norm", "shares_ng", "conv_dil_q3", "conv_principal", "conv_shares",
    "equity_q3", "r_perp", "g2", "k_l", "k_m", "k_h", "payout_obs",
    "pe_own_min", "pe_own_max", "lb_fwd_eps",
    "w_dc", "w_dc_hi", "w_dc_eq", "g_borrow",
]

_CANDIDATE = re.compile(
    r"候选带（[^）]+）[^\n]*?L′ = \*\*([0-9.]+)\*\*[^\n]*?M′ = \*\*([0-9.]+)\*\*[^\n]*?H′ = \*\*([0-9.]+)\*\*"
)
_EDGE = re.compile(r"带边 r ([0-9.]+)%")
_EDGE_BAND = re.compile(r"带边 r 价带：L″ = \*\*([0-9.]+)\*\* · M″ = \*\*([0-9.]+)\*\* · H″ = \*\*([0-9.]+)\*\*")


def check_inputs(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    e: list[str] = []
    if "r_perp" not in baskets:
        e.append("r_perp: Inputs source cell names no 篮 N (A4)")
    e += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    e += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    if inp["r_perp"] - inp["g2"] < MIN_R_MINUS_G:
        e.append(f"r - g2 < {MIN_R_MINUS_G:.0%}: at the pole")
    if inp["g2"] <= 0:
        e.append("g2 <= 0 barred: FY26 -> FY27 consensus rises (同世界门, A5)")
    e += ladder("FY27 consensus range", inp["eps_fy27_l"], inp["eps_fy27_m"], inp["eps_fy27_h"])
    e += ladder("numerator EPS", inp["eps_fy26_cons"], inp["eps_fy27_m"], inp["eps_fy27_h"])
    e += ladder("numerator revenue", inp["rev_fy26_cons"], inp["rev_fy27_m"], inp["rev_fy27_h"])
    if not (0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] < 1):
        e.append("k must satisfy 0 <= k_L <= k_M <= k_H < 1 (留存去向审计, A11)")
    if not (0 <= inp["tax_ng"] < inp["tax_norm"] < 0.35):
        e.append("tax rates out of range (A2)")
    if not (inp["w_dc_eq"] <= inp["w_dc"] <= inp["w_dc_hi"] <= 1):
        e.append("data-center profit weight interval out of order (A19)")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        e.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")
    return e


def check_axis(inp: dict[str, float]) -> list[str]:
    """Peer-ruler axis rows must match the axis file; the axis's borrowed
    growth must match the lender framework's own Inputs."""
    e: list[str] = []
    ax = parse_inputs(AXIS.read_text(encoding="utf-8"))
    for mine, theirs in AXIS_ROWS:
        if theirs not in ax:
            e.append(f"axis {AXIS.name}: missing {theirs}")
        elif abs(inp[mine] - ax[theirs]) > 1e-9:
            e.append(f"{mine} {inp[mine]:g} != axis {theirs} {ax[theirs]:g}")
    lend = parse_inputs(LENDER.read_text(encoding="utf-8"))
    want = lend["eps_fy29_cons"] / lend["eps_fy28_m"] - 1
    if "g1_borrow_mrvl_conn" in ax and abs(ax["g1_borrow_mrvl_conn"] - round(want, 4)) > 1e-9:
        e.append(f"axis g1_borrow_mrvl_conn {ax['g1_borrow_mrvl_conn']:g} != MRVL eps_fy29_cons/eps_fy28_m - 1 = {want:.4f}")
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
    errors = check_inputs(inp, baskets) + check_axis(inp)
    if errors:
        return report(errors)

    r, g2 = inp["r_perp"], inp["g2"]
    sh = inp["shares_ng"]                      # 百万股; money in 百万 USD
    sh_ex = sh - inp["conv_dil_q3"]            # ex-convert diluted shares
    sh_full = sh_ex + inp["conv_shares"]       # fully converted
    t_ng, t_n = inp["tax_ng"], inp["tax_norm"]
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}

    # ---- Step 1: economic NI (A1 / A2) ----
    sbc_ratio = inp["sbc_9m"] / inp["rev_9m"]
    sbc_floor = inp["sbc_q3"] * 4
    eps_ng = {"L": inp["eps_fy26_cons"], "M": inp["eps_fy27_m"], "H": inp["eps_fy27_h"]}
    rev = {"L": inp["rev_fy26_cons"], "M": inp["rev_fy27_m"], "H": inp["rev_fy27_h"]}
    sbc = {t: max(sbc_floor, sbc_ratio * rev[t]) for t in TIERS}

    def econ_ni(eps: float, s: float, tax: float = t_n, deduct: bool = True) -> float:
        return (eps * sh / (1 - t_ng) - (s if deduct else 0.0)) * (1 - tax)

    ni = {t: econ_ni(eps_ng[t], sbc[t]) for t in TIERS}
    q4_sbc = max(inp["sbc_q3"], sbc_ratio * inp["rev_q4_guide"])

    # ---- Step 2: FY27 opening equity, fixed point on b = g/ROE (A6) ----
    def book(n: float, g: float, tax: float = t_n, deduct: bool = True) -> tuple[float, float]:
        q4 = (inp["eps_q4_guide"] * sh / (1 - t_ng) - (q4_sbc if deduct else 0.0)) * (1 - tax)
        eq = inp["equity_q3"] + q4
        for _ in range(200):
            nxt = inp["equity_q3"] + q4 * min(1.0, g / (n / eq))
            if abs(nxt - eq) < 1e-9:
                break
            eq = nxt
        return eq, n / eq

    def per_share(v: float) -> float:
        return min((v - inp["conv_principal"]) / sh_ex, v / sh_full)

    def anchors_at(rr: float, g: float = g2, tax: float = t_n, deduct: bool = True) -> tuple[float, ...]:
        out = []
        for t in TIERS:
            n = econ_ni(eps_ng[t], sbc[t], tax, deduct)
            _, roe_ = book(n, g, tax, deduct)
            out.append(per_share(n * perpetual_pe(g, roe_, rr) * (1 - k[t])))
        return tuple(out)

    eq, roe, pe, val = {}, {}, {}, {}
    for t in TIERS:
        eq[t], roe[t] = book(ni[t], g2)
        pe[t] = perpetual_pe(g2, roe[t], r)
        val[t] = ni[t] * pe[t] * (1 - k[t])
    L, M, H = (per_share(val[t]) for t in TIERS)
    A, B = cut_points(L, M, H)
    errors += ladder("anchors", L, M, H)
    for t in TIERS:
        if roe[t] - r < 0.03:
            errors.append(f"{t}: ROE {roe[t]:.3f} not in the monotone domain at r {r:g}")
        errors += check_branch(g2, roe[t], r, inp["payout_obs"], f"g2@{t}")

    # ---- A2e-2c flat ladder + decomposition (multiples in per-share terms) ----
    eps_e = {t: ni[t] / sh for t in TIERS}
    mult = {t: per_share(val[t]) / eps_e[t] for t in TIERS}
    flat_errs, flat = flat_multiple_ladder((eps_e["L"], eps_e["M"], eps_e["H"]), mult["M"])
    errors += flat_errs
    dec = decompose((L, M, H), tuple(mult[t] for t in TIERS))

    # ---- ③ guardrail: band on LB non-GAAP forward EPS (A16); band-edge r (表2′) ----
    m_on_band = M / inp["lb_fwd_eps"]
    target = inp["pe_own_min"] * inp["lb_fwd_eps"]
    lo, hi = g2 + MIN_R_MINUS_G, r
    for _ in range(100):
        mid = (lo + hi) / 2
        if anchors_at(mid)[1] > target:
            lo = mid
        else:
            hi = mid
    r_edge = (lo + hi) / 2
    edge = anchors_at(r_edge)

    # ---- Candidate band (A20): one borrowed year on the data-center leg ----
    def cand_at(w: float) -> dict[str, float]:
        g1 = w * inp["g_borrow"] + (1 - w) * g2
        out = {"L": L}
        for t in ("M", "H"):
            _, roe1 = book(ni[t], g1)
            out[t] = per_share(ni[t] * two_stage_pe(g1, 1, g2, roe1, r) * (1 - k[t]))
        return out | {"g1": g1}

    cand = cand_at(inp["w_dc"])
    errors += ladder("candidate band", cand["L"], cand["M"], cand["H"])

    # ---- Reconcile stated Outputs ----
    out_md = outputs_section(md)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    cm = _CANDIDATE.search(out_md)
    if cm is None:
        errors.append("candidate band line not found in Outputs")
    else:
        for t, said in zip(TIERS, (float(x) for x in cm.groups())):
            if abs(said - cand[t]) > TOL:
                errors.append(f"candidate {t}′: stated {said} vs recomputed {cand[t]:.4f}")
    em, eb = _EDGE.search(out_md), _EDGE_BAND.search(out_md)
    if em is None or eb is None:
        errors.append("band-edge r line / table 2′ anchors not found in Outputs")
    else:
        if abs(float(em.group(1)) / 100 - r_edge) > 0.0005:
            errors.append(f"band-edge r: stated {em.group(1)}% vs recomputed {r_edge:.4%}")
        for t, said, got in zip(TIERS, (float(x) for x in eb.groups()), edge):
            if abs(said - got) > TOL:
                errors.append(f"band-edge {t}″: stated {said} vs recomputed {got:.4f}")

    # ---- Report ----
    print(f"formula_id={FORMULA_ID}")
    print(f"r {r:g} (篮 {baskets['r_perp']}) g2 {g2:.2%} (axis {AXIS.stem}; cap {g_cap(r):.0%})")
    print(f"SBC = max(Q3 x4 {sbc_floor:.1f}, 9M ratio {sbc_ratio:.2%} x revenue) "
          + " ".join(f"{t} {sbc[t]:.1f}" for t in TIERS)
          + f" ($M); tax {t_ng:.0%} -> {t_n:.1%}; shares ng {sh:g} / ex-conv {sh_ex:.3f} / full {sh_full:.3f}")
    for t in TIERS:
        print(f"{t}: nonGAAP {eps_ng[t]:.4f} -> econ NI {ni[t]:.1f} (EPS {eps_e[t]:.4f}) | equity_open {eq[t]:.1f}"
              f" ROE {roe[t]:.3f} PE {pe[t]:.3f} (payout {payout(g2, roe[t]):.3f}) -> V {val[t]:.0f}"
              f" | debt basis {(val[t] - inp['conv_principal']) / sh_ex:.2f} vs conv basis {val[t] / sh_full:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat ladder @ M {mult['M']:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"L/M {dec['lm']:.3f} = num {dec['num_lm']:.3f} x pe {dec['pe_lm']:.3f} | H/M {dec['hm']:.3f}"
          f" = num {dec['num_hm']:.3f} x pe {dec['pe_hm']:.3f} | width {(H - L) / (2 * M):.3f} | V_opt/M 0")
    print(f"③ band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] on LB forward EPS; M / {inp['lb_fwd_eps']:g}"
          f" = {m_on_band:.2f}x -> {'inside' if m_on_band >= inp['pe_own_min'] else 'BELOW band low (③ 出带, A16)'}")
    print(f"band-edge r {r_edge:.2%}: {edge[0]:.2f}/{edge[1]:.2f}/{edge[2]:.2f}")
    print(f"candidate (w_dc {inp['w_dc']:g}, g_borrow {inp['g_borrow']:+.2%} -> g1 {cand['g1']:+.2%}): "
          f"L′ {cand['L']:.2f} M′ {cand['M']:.2f} H′ {cand['H']:.2f}")
    for lab, w in (("w_dc_hi", inp["w_dc_hi"]), ("w_dc_eq", inp["w_dc_eq"])):
        c = cand_at(w)
        print(f"  candidate @ {lab} {w:g} (g1 {c['g1']:+.2%}): {c['L']:.2f}/{c['M']:.2f}/{c['H']:.2f}")
    print("视同派出、实际留存 ($/股/年, k=0): "
          + " ".join(f"{t} {(1 - inp['payout_obs'] - g2 / roe[t]) * eps_e[t]:.2f}" for t in TIERS))
    for g in (g2 - 0.01,):
        v = anchors_at(r, g)
        print(f"  sens g2={g:.2%}: {v[0]:.2f}/{v[1]:.2f}/{v[2]:.2f}")
    v = anchors_at(r, tax=t_ng)
    print(f"  tax kept at {t_ng:.0%} (no normalisation): {v[0]:.2f}/{v[1]:.2f}/{v[2]:.2f}")
    v = anchors_at(r, tax=t_ng, deduct=False)
    print(f"  street basis (3% tax, SBC not deducted): {v[0]:.2f}/{v[1]:.2f}/{v[2]:.2f}")

    # r_f readings (_AXIS.rates USD): Δr_f moves r_perp 1:1.
    rf = rf_block(LISTING_CCY, {"r_perp": r}, lambda dr: anchors_at(r + dr))
    if any(abs(x - y) > TOL for x, y in zip(anchors_at(r), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    if not errors:
        write_rf_readings(TICKER, rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
