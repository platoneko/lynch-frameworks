#!/usr/bin/env python3
"""601975.SH (China Merchants Nanjing Tanker / 招商南油) valuation eval.

frameworks/601975.SH.md is the source of truth; this script re-derives
L/M/H / A/B and the candidate band from its §3 Inputs table and exits 1 on
mismatch.  The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so
nothing here computes a zone or a market-implied reading.

formula_id: cmsn_roic_center_point_gordon_v1

Main ruler: one company-wide leg, operating basis with excess cash split out
(valuation-rules「经营价值与超额现金」).

    IC    = parent equity + NCI + net debt + operating-cash anchor (0)
    E_M   = ROIC_center x IC x 归母转化                cycle-center operating profit
    PE    = (1 - g2/RONIC) / (r - g2),  RONIC = max(ronic_hist, r) = r  -> 1/r
    M     = (E_M x PE + C_ex) / shares
    L     = ((E_L + E_M x PE)/(1+r) + C_ex) / shares    worst measured 12 months,
                                                        then back to the center
    H     = (sum_t E_t/(1+r)^t + E_M x PE/(1+r)^2.5 + C_ex) / shares
            t = 0.5 / 1.5 / 2.5: consensus 2026H2 / 2027 / 2028, then the center

Point semantics at both ends (valuation-rules「周期票 regime / point 双口径」):
the measured troughs (2018, 2021) each lasted one year; H is the consensus
path because the consensus mean sits above the measured best year (②-b).
r is the basket-6 start stepped down to 11% by a clean equal-earnings band
(③, A4 / A5).

Run:  python3 frameworks/eval/601975.SH.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import basket_r, check_g_cap, check_r  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, outputs_section, parse_baskets,
    parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval.lib.frameworks import load_framework  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "601975.SH.md"
FORMULA_ID = "cmsn_roic_center_point_gordon_v1"
YI = 1e8
TOL = 0.05

# Measured trough length (2018, 2021: one year each, A2) and the consensus path
# timing from the 2026-06-30 valuation date (A3).  Changing them is a framework
# correction, so they live here rather than in Inputs.
N_RECOVERY_L = 1
T_PATH = (0.5, 1.5, 2.5)
FROM_BASKET = 6  # initial basket before the ③ step-down (A4)
TO_BASKET = 5

REQUIRED = [
    "shares_total", "equity_parent", "nci", "cash", "debt_cur", "debt_lt", "op_cash_anchor",
    "np_parent_fy25", "np_total_fy25", "tax_rate", "cash_yield",
    "roic_center", "roic_center_soft", "roic_center_tight",
    "kf_l_4q", "intexp_l_4q", "ic_l_avg",
    "ronic_hist", "r_perp", "g2",
    "np_cons_2026", "np_cons_2027", "np_cons_2028", "np_h1_2026",
    "np_gh_2026", "np_gh_2027", "np_gh_2028",
    "roic_best_fy", "pe_band_min", "pe_band_max", "pe_band_median", "pb_low_5y",
    "newbuild_remaining", "gp_dom_fy25", "gp_for_fy25",
]


def stated_triple(md: str, label: str) -> tuple[float, float, float] | None:
    """`<label> x / y / z` on one Outputs line (contrast and sensitivity rows)."""
    num = r"(-?[0-9]+(?:\.[0-9]+)?)"
    m = re.search(re.escape(label) + r"[^\n0-9]*?" + num + r"\s*/\s*" + num + r"\s*/\s*" + num,
                  outputs_section(md))
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def check_triple(md: str, label: str, computed: tuple[float, float, float]) -> list[str]:
    said = stated_triple(md, label)
    if said is None:
        return [f"stated triple '{label}' not found in Outputs"]
    bad = [f"{s} vs {c:.4f}" for s, c in zip(said, computed) if abs(s - c) > TOL]
    return [f"'{label}': {', '.join(bad)}"] if bad else []


def stated_value(md: str, label: str) -> float | None:
    m = re.search(re.escape(label) + r"[^\n0-9]*?(-?[0-9]+(?:\.[0-9]+)?)", outputs_section(md))
    return float(m.group(1)) if m else None


def check_value(md: str, label: str, computed: float) -> list[str]:
    said = stated_value(md, label)
    if said is None:
        return [f"stated value '{label}' not found in Outputs"]
    return [f"'{label}': {said} vs {computed:.4f}"] if abs(said - computed) > TOL else []


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # --- basket, g guards -----------------------------------------------------------------
    baskets = parse_baskets(md)
    r = inp["r_perp"]
    if baskets.get("r_perp") != TO_BASKET:
        errors.append(f"r_perp: Inputs source cell must name 篮 {TO_BASKET} first, got {baskets.get('r_perp')} (A4)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    extra = sorted(k for k in baskets if k != "r_perp")
    if extra:
        errors.append(f"only r_perp may carry a 篮 N tag; also found {extra} (AGENTS.md 篮子声明)")
    g2 = inp["g2"]
    errors += check_g_cap(g2, r, "g2")

    # --- operating capital and excess cash (A6) ----------------------------------------------
    shares = inp["shares_total"] / YI
    t = inp["tax_rate"]
    nc = inp["cash"] - inp["debt_cur"] - inp["debt_lt"]
    par = inp["equity_parent"] / (inp["equity_parent"] + inp["nci"])
    cex = max(nc - inp["op_cash_anchor"], 0.0) * par
    ic = inp["equity_parent"] + inp["nci"] - nc + inp["op_cash_anchor"]
    conv = inp["np_parent_fy25"] / inp["np_total_fy25"]
    cinc = cex * inp["cash_yield"] * (1 - t)  # after-tax income on C_ex, stripped from consensus

    # --- numerators ----------------------------------------------------------------------------
    roic_l = (inp["kf_l_4q"] + inp["intexp_l_4q"] * (1 - t)) / inp["ic_l_avg"]
    e_l = roic_l * ic * conv
    e_m = inp["roic_center"] * ic * conv

    def path(c26: float, c27: float, c28: float) -> list[tuple[float, float]]:
        return list(zip(T_PATH, (c26 - inp["np_h1_2026"] - cinc / 2, c27 - cinc, c28 - cinc)))

    cons = path(inp["np_cons_2026"], inp["np_cons_2027"], inp["np_cons_2028"])
    gh = path(inp["np_gh_2026"], inp["np_gh_2027"], inp["np_gh_2028"])

    def band(r_: float, em: float = e_m, p: list[tuple[float, float]] = cons,
             g: float = g2) -> tuple[float, float, float, float]:
        """(L, M, H, PE) — the one formula every band here uses."""
        ronic = max(inp["ronic_hist"], r_)
        pe = (1 - g / ronic) / (r_ - g)
        vm = em * pe
        m = (vm + cex) / shares
        ell = ((e_l + vm) / (1 + r_) ** N_RECOVERY_L + cex) / shares
        h = (sum(e / (1 + r_) ** tt for tt, e in p) + vm / (1 + r_) ** T_PATH[-1] + cex) / shares
        return ell, m, h, pe

    L, M, H, pe = band(r)
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}"])
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # RONIC = r puts the domain on the pathological edge: PE = 1/r for any g (A7).
    if abs(pe - 1 / r) > 1e-9:
        errors.append(f"PE {pe:.4f} != 1/r {1 / r:.4f} — RONIC no longer equals r; rewrite A7")

    # 2c flat-multiple ladder: operating EPS L < M < H (H = consensus 2028).
    eps_flat = (e_l / shares, e_m / shares, cons[-1][1] / shares)
    errors += ladder("operating EPS", *eps_flat)

    # ②-b: the consensus world sits above the measured best year -> H is the consensus path.
    roic_cons28 = cons[-1][1] / conv / ic
    if roic_cons28 <= inp["roic_best_fy"]:
        errors.append(f"②-b: consensus 2028 ROIC {roic_cons28:.1%} no longer above measured best "
                      f"{inp['roic_best_fy']:.1%} — H must be rebuilt (A3)")

    # --- ③: clean equal-earnings band (A5) -----------------------------------------------------
    if not (inp["pe_band_min"] <= pe <= inp["pe_band_max"]):
        errors.append(f"PE {pe:.2f} outside the clean band [{inp['pe_band_min']}, {inp['pe_band_max']}] — "
                      "re-run ③ (A5)")
    pe_from = 1 / basket_r(FROM_BASKET)
    if pe_from >= inp["pe_band_min"]:
        errors.append(f"basket {FROM_BASKET} PE {pe_from:.2f} back inside the band — step-down stale (A4)")
    b6 = band(basket_r(FROM_BASKET))[:3]
    b4 = band(basket_r(4))[:3]
    errors += check_triple(md, f"初分篮 {FROM_BASKET}（13%）→", b6)

    # --- candidate band (A16): the 2022-25 tight-market center, same formula -------------------
    cand = band(r, em=inp["roic_center_tight"] * ic * conv)[:3]
    stated_cand = load_framework(FRAMEWORK).candidate
    if stated_cand is None:
        errors.append("候选带 line missing from Outputs (A16)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), stated_cand, cand):
            if abs(said - got) > TOL:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")

    # --- disclosure coordinates -----------------------------------------------------------------
    g_up = band(r, g=g2 + 0.01)[:3]
    g_dn = band(r, g=g2 - 0.01)[:3]
    errors += check_triple(md, "g2 +1pp →", g_up)
    errors += check_triple(md, "g2 −1pp →", g_dn)
    gh_h = band(r, p=gh)[2]
    errors += check_value(md, "国海单家路径 H =", gh_h)
    soft_m = band(r, em=inp["roic_center_soft"] * ic * conv)[1]
    errors += check_value(md, "多年低谷压力坐标 M =", soft_m)
    regime_l = (e_l / r + cex) / shares
    regime_h = (cons[-1][1] / r + cex) / shares
    errors += check_value(md, "regime L =", regime_l)
    errors += check_value(md, "regime H =", regime_h)
    w_dom = inp["gp_dom_fy25"] / (inp["gp_dom_fy25"] + inp["gp_for_fy25"])
    split_m = (e_m * w_dom / basket_r(4) + e_m * (1 - w_dom) / r + cex) / shares
    errors += check_value(md, "内外贸分腿 M =", split_m)
    nb_pen = inp["newbuild_remaining"] * (1 - inp["ronic_hist"] / r) * par / shares
    coord_min = inp["pe_band_min"] * e_m / shares + cex / shares
    coord_med = inp["pe_band_median"] * e_m / shares + cex / shares
    coord_pb = inp["pb_low_5y"] * inp["equity_parent"] / shares

    # --- report ----------------------------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"shares {shares:.4f}亿; net cash {nc:.2f}; parent share {par:.4f}; C_ex {cex:.2f} "
          f"({cex / shares:.4f}/sh); IC {ic:.2f}; 归母转化 {conv:.4f}; C_ex income {cinc:.3f}/yr")
    print(f"basket: r_perp 篮 {baskets.get('r_perp')} r={r:g} (from 篮 {FROM_BASKET}); g2={g2:g}; "
          f"RONIC max({inp['ronic_hist']:g}, r) -> PE {pe:.3f}x (= 1/r)")
    print(f"ROIC L {roic_l:.2%} / M {inp['roic_center']:.1%}; E_L {e_l:.3f} E_M {e_m:.3f}; "
          f"consensus path " + " / ".join(f"t{tt}:{e:.2f}" for tt, e in cons))
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"ratios: L/M={L / M:.4f} H/M={H / M:.4f} (H-L)/2M={(H - L) / (2 * M):.4f} V_opt/M 0 | "
          f"C_ex share of M {cex / shares / M:.1%}")
    print("operating EPS ladder: " + " / ".join(f"{v:.4f}" for v in eps_flat) + " (2c OK)")
    print(f"②-b: consensus 2028 ROIC {roic_cons28:.1%} > measured best {inp['roic_best_fy']:.1%}")
    print(f"③: band [{inp['pe_band_min']}, {inp['pe_band_max']}] clean; 篮 6 {pe_from:.2f}x out, "
          f"篮 5 {pe:.2f}x in; contrast 13%: " + " / ".join(f"{v:.2f}" for v in b6)
          + " | 10%: " + " / ".join(f"{v:.2f}" for v in b4))
    print("候选带 出清·紧平衡: " + " / ".join(f"{v:.2f}" for v in cand)
          + "  A′={:.2f} B′={:.2f}".format(*cut_points(*cand)))
    print("g2 +1pp: " + " / ".join(f"{v:.2f}" for v in g_up) + " | g2 -1pp: " + " / ".join(f"{v:.2f}" for v in g_dn))
    print(f"国海 path H {gh_h:.2f}; multi-year trough M {soft_m:.2f}; regime L {regime_l:.2f} / H {regime_h:.2f}")
    print(f"domestic/foreign split M {split_m:.2f} (domestic GP weight {w_dom:.3f}); newbuild penalty at "
          f"RONIC {inp['ronic_hist']:g}: -{nb_pen:.3f}/sh")
    print(f"coordinates: equal-earnings min {coord_min:.2f} / median {coord_med:.2f}; "
          f"5y PB low x BPS {coord_pb:.2f}")
    print("rf block: CNY segment of _AXIS.rates is [待建] — no rates readings")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
