#!/usr/bin/env python3
"""1898.HK (China Coal Energy) valuation eval.

frameworks/1898.HK.md is the source of truth; this script re-derives
L/M/H / A/B / zone / the candidate band from its §3 Inputs table and exits 1
on mismatch.

formula_id: chinacoal_selfmined_asp_ladder_flat_pe_hkd_v2_gordon_v4

Main ruler: the company's own self-mined thermal coal ASP, not the port price.

    L = 436   元/吨  — 2025H1, reconstructed from the filed +13.3% YoY (low-regime rung)
    M = 499   元/吨  — MID-CYCLE: the FY2019-25 seven-year mean of the filed ASP
                       (432 / 402 / 570 / 622 / 532 / 499 / 436)
    H = 508.7 元/吨  — QHD 5,500 rising from 755 to the >=2-house 2026 full-year
                       cluster median 800, passed through at 0.5
    base = 494 元/吨 — 2026H1 filed; the bridge's baseline (NP(base) = 2 x H1), a
                       coordinate inside the band, NOT the M numerator
    H' (candidate) — the single-house Goldman 2026H2 950, same pass-through

中枢分子 (valuation-rules「周期票的中枢分子与 PE < 1/r 的读法」): a cyclical's
M numerator must be mid-cycle earnings, and a sub-1/r market multiple is read
FIRST as "the current print sits above mid-cycle".  The test is 当期 ÷ 中枢:
2026H1 run-rate 163.84 / bridged mid-cycle 167.89 = 0.976, TTM 0.915, FY26E
consensus 0.987, FY27E 1.013 -- all <= 1.15, so the current print is NOT an
upper-side coordinate and the reading falls through to r.  The framework's
second mid-cycle reading (seven-year IFRS 归母 mean 141.83亿, EPS 1.2481 HKD)
is 18.4% below the bridged one -- inside the 20% tolerance; the bridge is used
because it holds volume, cost and the non-coal legs at 2026H1 and moves only
price.  Guard 3a checks px_m against the filed series, the two readings
against each other, and prints the four ratios.

Multiple: r is the BASKET value (valuation-rules「r 篮子」) -- the whole company
sits in basket 6 (周期商品, A16) at 13%: earnings are a function of the coal
price, and 13% is the H-share China Coal's r (A 12.1x <-> ~10%, H 7.8x <-> 13%,
the 35% A/H discount ~ 3pp).  The retention audit (valuation-rules「留存去向
审计」, A9) puts 2023-27 retention in bucket D -- a NAMED build window (coal
chemicals 2026-12, 苇子沟 2026, 里必 2027), not steady-state compounding -- so
g2 = 0, the flat multiple is 1/r = 7.69x, and the projects are priced as a
separate finite NPV:

    V_proj = (K_spent + K_remain x n) x ROE_proj / r / (1+r)^T
             - sum_k K_remain / (1+r)^(0.3+k)          (亿 CNY -> HKD/share)

with T = 0.3 + (n-1) (full production at end-2027).  Spent capex (275亿) is
sunk and its post-2027 profit is not in the mid-cycle numerator, so it is
ADDED as a profit PV; only the remaining 2026-27 capex is penalised at
(ROE_proj/r - 1).  ROE_proj is 待补; the deck takes the 10% middle case and
the 8 / 10 / 13% coordinates are printed side by side.  The retired perpetual
retention branch (b x ROE_M = 6.65% -> 6% cap -> 5.89x at 13%) and the old
r = 10% + g 6% reading are printed as 对照带 only.

Anchor_x = EPS_x x (1/r) + V_proj.  `cyclical` flat: all three tiers take the
same multiple; tier ROE never enters it.  The L tier is a price-ladder RUNG
(2025H1 ASP on 2026H1 volume and cost), not the ticker's own realised trough
year, so the 谷底档 recovery stage does not apply.  Two pressure coordinates
are printed only.  The realised 5-year PE band is a guardrail (③ 出带).  ②-b
is checked on the mid-cycle M against the FY2027E consensus range.

The asset floor (PB = 1.0 = 14.4661 HKD) sits ABOVE H: with r 13% > ROE_M
10.2% the justified PB is ROE/r = 0.79 and the whole earnings band sits under
book by construction.  The floor is printed, never max()'d (A10).

Run:  python3 eval/1898.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.gordon import (  # noqa: E402
    check_g_cap, check_r, g_cap, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, outputs_section, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

# rf_report / bands_io import through the `eval.lib` package, so the repo root
# must be importable too; appended so `lib.*` above still resolves first.
sys.path.append(str(Path(__file__).resolve().parents[1]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "1898.HK.md"
FORMULA_ID = "chinacoal_selfmined_asp_ladder_flat_pe_hkd_v2_gordon_v4"
YI = 1e8

BASE_NP_PARENT_YI = 163.84  # 2026H1 归母 81.92亿 CNY x 2
BASE_NP_TOL_YI = 0.5
EQUITY_TOL_YI = 1.0
PX_H_TOL = 1.0  # 元/吨
PX_MID_TOL = 0.5  # 元/吨: px_m must be the filed-series mean
MID_CROSS_TOL = 0.20  # the two mid-cycle readings must agree within this (valuation-rules「周期票的中枢分子」)
PEAK_RATIO = 1.15  # 当期 ÷ 中枢 above this makes the current print an upper-side coordinate
CONSENSUS_DEV_TOL = 0.20  # ②-b: M within this of the furthest-year consensus mean
TOL = 0.05
YEAR_END_OFFSET = 0.3  # years from the 2026-09 as-of to end-2026: capex and full-production PV points sit on year ends
ROE_PROJ_COORDS = (0.08, 0.10, 0.13)  # A9: ROE_proj is 待补; the deck takes the middle case
V1_R, V1_G2 = 0.10, 0.06  # the pre-basket reading, printed as 对照带
# _AXIS.rates segment: HKD rides the USD r_f via the peg (valuation-rules「按上市货币取段」).
LISTING_CCY = "HKD"
TIERS = ("l", "m", "h")
ASP_YEARS = ("asp_fy19", "asp_fy20", "asp_fy21", "asp_fy22", "asp_fy23", "asp_fy24", "asp_fy25")
NI_IFRS_YEARS = ("ni_ifrs_fy19", "ni_ifrs_fy20", "ni_ifrs_fy21", "ni_ifrs_fy22", "ni_ifrs_fy23", "ni_ifrs_fy24")

REQUIRED = [
    "price", "shares", "fx_cny_hkd", "np_h1", "op_h1", "vol_yr",
    "px_base", "px_l", "px_m", "px_h", *ASP_YEARS, *NI_IFRS_YEARS,
    "conv", "r_perp", "g2", "equity",
    "capex_spent", "capex_remain_yr", "capex_remain_n", "roe_proj", "net_cash",
    "dps_fy25", "dps_fy25_hkd", "ni_fy25", "eps_fy26e", "eps_fy27e_low", "eps_fy27e_mean", "eps_fy27e_high",
    "g_evid_min", "g_evid_max", "g_peer_yankuang",
    "np_h1_prev", "pe_own_min", "pe_own_max",
    "pass_through", "qhd_m", "qhd_h", "qhd_h_cand", "bps",
]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    r, fx = inp["r_perp"], inp["fx_cny_hkd"]

    # --- Step 1: the ASP ladder and its provenance -----------------------------
    errors += ladder("self-mined ASP", inp["px_l"], inp["px_m"], inp["px_h"])
    if not (0.0 < inp["conv"] < 1.0):
        errors.append(f"conv={inp['conv']} outside (0,1)")
    if not (1.05 < fx < 1.25):
        errors.append(f"fx_cny_hkd={fx} outside plausible band")
    if inp["np_h1_prev"] <= 0:
        errors.append("np_h1_prev must be positive (own trough year for the pressure coordinate)")
    bad = [k for k in (*ASP_YEARS, *NI_IFRS_YEARS) if inp[k] <= 0]
    if bad:
        errors.append(f"non-positive history inputs {bad}")

    # H is derived, not chosen: weld it to the port cluster and the pass-through.
    def px_from_port(qhd: float, pass_through: float = inp["pass_through"]) -> float:
        return inp["px_base"] * (1.0 + (qhd - inp["qhd_m"]) / inp["qhd_m"] * pass_through)

    px_h_expected = px_from_port(inp["qhd_h"])
    if abs(inp["px_h"] - px_h_expected) > PX_H_TOL:
        errors.append(f"px_h={inp['px_h']:g} vs derived {px_h_expected:.1f} — H must follow the port ladder")
    # M is derived too: the seven-year mean of the filed ASP series (A3‴).
    px_mid = sum(inp[k] for k in ASP_YEARS) / len(ASP_YEARS)
    if abs(inp["px_m"] - px_mid) > PX_MID_TOL:
        errors.append(f"px_m={inp['px_m']:g} vs FY2019-25 filed mean {px_mid:.1f} — M must be the mid-cycle price (A3‴)")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields in Inputs (A2e-7a): {leaked}")
    if errors:
        return report(errors, "FAIL (numerators)")

    # --- Step 2: numerator per tier (CNY net profit -> HKD EPS) ----------------
    def net_profit_yi(px: float, vol: float = inp["vol_yr"]) -> float:
        dgp = (px - inp["px_base"]) * vol  # 元/吨 x 亿吨 = 亿 CNY
        return 2.0 * inp["np_h1"] + dgp * inp["conv"]

    def per_share_hkd(yi_cny: float) -> float:
        return yi_cny * YI / inp["shares"] * fx

    px = {"l": inp["px_l"], "m": inp["px_m"], "h": inp["px_h"], "c": px_from_port(inp["qhd_h_cand"]), "base": inp["px_base"]}
    npp = {t: net_profit_yi(v) for t, v in px.items()}
    eps_cny = {t: v * YI / inp["shares"] for t, v in npp.items()}
    eps = {t: v * fx for t, v in eps_cny.items()}
    if abs(npp["base"] - BASE_NP_PARENT_YI) > BASE_NP_TOL_YI:
        errors.append(f"baseline closure broken: NP at px_base {npp['base']:.4f}亿CNY vs filed {BASE_NP_PARENT_YI}亿")

    # --- Step 3: mid-cycle check (校验 3a) --------------------------------------
    # Two mid-cycle readings must agree; the current print, TTM and consensus are
    # then placed against the mid-cycle numerator (valuation-rules「周期票的中枢分子」).
    ni_hist = [inp[k] for k in NI_IFRS_YEARS] + [inp["ni_fy25"]]
    ni_mid_realised = sum(ni_hist) / len(ni_hist)
    mid_gap = npp["m"] / ni_mid_realised - 1.0
    if abs(mid_gap) > MID_CROSS_TOL:
        errors.append(f"bridged mid-cycle NI {npp['m']:.2f}亿 vs realised seven-year IFRS mean {ni_mid_realised:.2f}亿: "
                      f"{mid_gap:+.1%} beyond {MID_CROSS_TOL:.0%} — BLOCKED, back to the conversation (A3‴)")
    ttm = inp["ni_fy25"] - inp["np_h1_prev"] + inp["np_h1"]
    current = {
        "run-rate 2026H1x2": 2.0 * inp["np_h1"],
        "TTM": ttm,
        "FY26E consensus": inp["eps_fy26e"] * inp["shares"] / YI,
        "FY27E consensus": inp["eps_fy27e_mean"] * inp["shares"] / YI,
    }
    ratios = {k: v / npp["m"] for k, v in current.items()}
    peak_numerator = max(ratios["run-rate 2026H1x2"], ratios["TTM"], ratios["FY26E consensus"]) > PEAK_RATIO
    # Whatever the case, M must be the mid-cycle numerator, never the current print.
    if abs(eps["m"] - eps["base"]) < 1e-9 and abs(inp["px_m"] - px_mid) > PX_MID_TOL:
        errors.append("EPS_M equals the 2026H1 print — the M numerator must be the mid-cycle EPS (A3‴)")
    # ②-b on the mid-cycle M: furthest >=2-house range year's mean inside [M, H], M within 20% of it.
    c_low, c_mean, c_high = (inp[k] * fx for k in ("eps_fy27e_low", "eps_fy27e_mean", "eps_fy27e_high"))
    if not (eps["m"] - 1e-9 <= c_mean <= eps["h"] + 1e-9):
        errors.append(f"②-b: FY27E consensus mean {c_mean:.4f} HKD outside [EPS_M {eps['m']:.4f}, EPS_H {eps['h']:.4f}] (A1)")
    if abs(c_mean / eps["m"] - 1.0) > CONSENSUS_DEV_TOL:
        errors.append(f"②-b: EPS_M {eps['m']:.4f} deviates {c_mean / eps['m'] - 1:+.1%} from FY27E consensus mean {c_mean:.4f} (A1)")
    if eps["h"] > c_high + 1e-9:
        errors.append(f"EPS_H {eps['h']:.4f} exceeds FY27E consensus high {c_high:.4f} HKD — H must stay a modelled upper edge (A3)")

    # --- Step 4: basket r, g2 = 0, project value (A9 / A16) --------------------
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules「r 篮子」, A16)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    equity_derived = inp["bps"] / fx * inp["shares"] / YI
    if abs(inp["equity"] - equity_derived) > EQUITY_TOL_YI:
        errors.append(f"equity {inp['equity']} vs bps ÷ fx × shares = {equity_derived:.1f} 亿CNY")
    roe = {t: npp[t] / inp["equity"] for t in npp}
    g2 = inp["g2"]
    errors += check_g_cap(g2, r, "g2")
    # Retention goes into a named build window (bucket D), priced as V_proj below;
    # a perpetual g here would count the same capex twice (A9).
    if abs(g2) > 1e-9:
        errors.append(f"g2={g2:+.4f} must be 0 — retention is a finite build window priced as V_proj, not a perpetual g (A9)")
    if abs(inp["g_evid_min"]) > 1e-9 or abs(inp["g_evid_max"]) > 1e-9:
        errors.append(f"g_evid interval [{inp['g_evid_min']}, {inp['g_evid_max']}] must collapse to 0 — g is not a reading here (A9)")
    if abs(inp["g_peer_yankuang"] - g2) < 1e-9:
        errors.append("g_peer_yankuang leaked into g2 — it is a different-world cross, not the source (A9)")
    n_remain = inp["capex_remain_n"]
    if n_remain <= 0 or abs(n_remain - round(n_remain)) > 1e-9:
        errors.append(f"capex_remain_n={n_remain} must be a positive integer number of build years (A9)")
    if not (0.0 < inp["roe_proj"] < 1.0):
        errors.append(f"roe_proj={inp['roe_proj']} outside (0,1) (A9)")
    if inp["capex_spent"] < 0 or inp["capex_remain_yr"] < 0:
        errors.append("capex_spent / capex_remain_yr must be non-negative (A9)")
    if errors:
        return report(errors, "FAIL (growth 口径)")
    n_remain = int(round(n_remain))

    def project_value_yi(roe_proj: float, r_: float = r, remain_yr: float = inp["capex_remain_yr"]) -> tuple[float, float, float]:
        """(total, built, unbuilt) project value in 亿 CNY at the sunk-cost reading (A9).

        Built capex is sunk and its post-window profit is outside the mid-cycle
        numerator, so it is added as a profit PV; only the remaining build-years'
        capex is penalised against its own profit PV.
        """
        t_full = YEAR_END_OFFSET + (n_remain - 1)
        pv_profit = lambda k: k * roe_proj / r_ / (1.0 + r_) ** t_full  # noqa: E731
        pv_capex = sum(remain_yr / (1.0 + r_) ** (YEAR_END_OFFSET + k) for k in range(n_remain))
        built = pv_profit(inp["capex_spent"])
        unbuilt = pv_profit(remain_yr * n_remain) - pv_capex
        return built + unbuilt, built, unbuilt

    v_proj_yi, v_built_yi, v_unbuilt_yi = project_value_yi(inp["roe_proj"])
    v_proj = per_share_hkd(v_proj_yi)

    # --- Step 5: the flat multiple (cyclical: every tier at 1/r) ---------------
    pe = {t: perpetual_pe(g2, roe["m"], r) for t in TIERS}
    if not (pe["l"] == pe["m"] == pe["h"]):
        errors.append(f"multiple not flat: {pe} — cyclical policy (A9)")
    if abs(pe["m"] - 1.0 / r) > 1e-9:
        errors.append(f"PE {pe['m']:.4f} != 1/r {1 / r:.4f} — g2 = 0 must give exactly 1/r")
    if not (inp["pe_own_min"] - 1e-9 <= pe["m"] <= inp["pe_own_max"] + 1e-9):
        errors.append(
            f"guardrail (③ 出带): generated PE {pe['m']:.2f} outside own band "
            f"[{inp['pe_own_min']}, {inp['pe_own_max']}] — stop, back to the conversation"
        )
    if errors:
        return report(errors, "FAIL (guardrail)")

    # --- Step 6: anchors, floor (disclosure), zone, candidate band -------------
    def band(pe_: float, v: float, vol: float = inp["vol_yr"]) -> tuple[float, float, float]:
        return tuple(per_share_hkd(net_profit_yi(px[t], vol)) * pe_ + v for t in TIERS)  # type: ignore[return-value]

    L, M, H = band(pe["m"], v_proj)
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}"])
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # candidate band: exactly one line, L' = L, M' = M, H' recomputed (with V_proj)
    cand_h = eps["c"] * pe["m"] + v_proj
    cand = re.findall(
        r"候选带（[^）]+）[^\n]*?L′ = \*\*([\d.]+)\*\*[^\n]*?M′ = \*\*([\d.]+)\*\*[^\n]*?H′ = \*\*([\d.]+)\*\*",
        outputs_section(md))
    if len(cand) != 1:
        errors.append(f"expected exactly one 候选带 line in Outputs, found {len(cand)}")
    else:
        for name, said, want in zip(("L′", "M′", "H′"), cand[0], (L, M, cand_h)):
            if abs(float(said) - want) > TOL:
                errors.append(f"候选带 {name}: stated {said} vs recomputed {want:.4f}")
        if not (L < M < cand_h):
            errors.append("candidate band L′<M′<H′ violated")

    # --- report ----------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"baskets={baskets} r_perp={r:.3f} (篮 {baskets['r_perp']}) g2={g2:+.2%} cap={g_cap(r):.3f} PE=1/r={pe['m']:.4f} flat")
    for tag, t in (("L", "l"), ("M", "m"), ("H", "h"), ("H′", "c"), ("基线", "base")):
        anchor = eps[t] * pe["m"] + v_proj
        print(
            f"{tag:2}: asp={px[t]:>6.1f}元/吨  Δgp={(px[t] - inp['px_base']) * inp['vol_yr']:+7.2f}亿CNY  np={npp[t]:7.2f}亿CNY  "
            f"ROE={roe[t]:6.2%}  eps={eps_cny[t]:.4f}CNY={eps[t]:.4f}HKD  eps×PE={eps[t] * pe['m']:.4f}  +V_proj={v_proj:.4f}  "
            f"anchor={anchor:.4f}HKD  PB={anchor / inp['bps']:.3f}"
            + ("  (2026H1 print, coordinate only)" if t == "base" else "")
        )
    print(f"中枢 (A3‴): px_m {inp['px_m']:g} = FY2019-25 filed ASP mean {px_mid:.1f} ({'/'.join(f'{inp[k]:g}' for k in ASP_YEARS)}); "
          f"2026H1 {inp['px_base']:g} = {inp['px_base'] / px_mid:.3f}x 中枢, FY2022 peak {inp['asp_fy22']:g} = {inp['asp_fy22'] / px_mid:.2f}x, "
          f"FY2020 trough {inp['asp_fy20']:g} = {inp['asp_fy20'] / px_mid:.2f}x")
    realised_coord = per_share_hkd(ni_mid_realised) * pe["m"] + v_proj
    print(f"  bridged mid-cycle NI {npp['m']:.2f}亿 vs realised seven-year IFRS mean {ni_mid_realised:.2f}亿 "
          f"({'/'.join(f'{v:g}' for v in ni_hist)}): {mid_gap:+.1%} (≤ {MID_CROSS_TOL:.0%} ✓); "
          f"realised-mean coordinate EPS {per_share_hkd(ni_mid_realised):.4f} HKD × PE + V_proj = {realised_coord:.2f} (zone {zone_of(realised_coord, L, M, H)})")
    print("  当期 ÷ 中枢: " + "; ".join(f"{k} {v:.2f}亿 → {ratios[k]:.3f}" for k, v in current.items())
          + f" → {'> ' + str(PEAK_RATIO) + ': current print is an UPPER-side coordinate, M = 中枢' if peak_numerator else f'all ≤ {PEAK_RATIO}: not a peak numerator; PE < 1/r reads via r (A16)'}")
    coords = {
        "FY2023 IFRS peak": inp["ni_ifrs_fy23"], "FY2025 trough": inp["ni_fy25"], "TTM": ttm, "2026H1 基线": npp["base"],
        "FY26E consensus": current["FY26E consensus"], "FY27E consensus": current["FY27E consensus"],
    }
    print("  coordinates × 1/r + V_proj: " + "; ".join(
        f"{k} {v / npp['m']:.2f}x 中枢 → {per_share_hkd(v) * pe['m'] + v_proj:.2f} ({zone_of(per_share_hkd(v) * pe['m'] + v_proj, L, M, H)})"
        for k, v in coords.items()))
    print(f"  ②-b on 中枢 M: FY27E consensus {c_low:.4f}/{c_mean:.4f}/{c_high:.4f} HKD; mean in [EPS_M {eps['m']:.4f}, EPS_H {eps['h']:.4f}] ✓, "
          f"M dev {c_mean / eps['m'] - 1:+.1%} ✓; EPS_H ≤ high ✓; ② 直读 × PE + V_proj = "
          f"{'/'.join(f'{c * pe['m'] + v_proj:.2f}' for c in (c_low, c_mean, c_high))}")

    # Project value (A9): the retention audit's bucket D, priced as a finite NPV.
    payout_fy25 = inp["dps_fy25"] * inp["shares"] / (inp["ni_fy25"] * YI)
    t_full = YEAR_END_OFFSET + (n_remain - 1)
    print(f"项目价值 (A9, 沉没成本口径): K_spent {inp['capex_spent']:g} + K_remain {inp['capex_remain_yr']:g} × {n_remain} yr, "
          f"ROE_proj {inp['roe_proj']:.0%}, full production at t={t_full:.1f} → built +{v_built_yi:.1f}亿 ({per_share_hkd(v_built_yi):+.2f} HKD/股), "
          f"unbuilt {v_unbuilt_yi:+.1f}亿 ({per_share_hkd(v_unbuilt_yi):+.2f}) → V_proj {v_proj_yi:+.1f}亿 CNY = {v_proj:+.4f} HKD/股; "
          f"net cash {inp['net_cash']:g}亿 = {per_share_hkd(inp['net_cash']):.2f} HKD/股 disclosed, not added")
    print(f"  留存去向: FY2025 派息率 {payout_fy25:.1%} (DPS {inp['dps_fy25']} CNY × shares ÷ IFRS 归母 {inp['ni_fy25']:.2f}亿), 留存 {1 - payout_fy25:.0%} "
          f"→ named build window (bucket D) → g2 = 0, V_proj separate; 兖矿全派息分支 {inp['g_peer_yankuang']:+.2%} 只作交叉 (不同世界)")
    for roe_proj in ROE_PROJ_COORDS:
        v_yi, b_yi, u_yi = project_value_yi(roe_proj)
        b3 = band(pe["m"], per_share_hkd(v_yi))
        mark = " ← 底牌" if abs(roe_proj - inp["roe_proj"]) < 1e-9 else ""
        print(f"  三坐标 ROE_proj {roe_proj:.0%}: V_proj {per_share_hkd(v_yi):+.2f} (built {per_share_hkd(b_yi):+.2f} / unbuilt {per_share_hkd(u_yi):+.2f}) → "
              f"{'/'.join(f'{x:.2f}' for x in b3)} zone={zone_of(inp['price'], *b3)} P/M={inp['price'] / b3[1]:.2f}{mark}")
    for remain in (0.0, 150.0):
        print(f"  capex_remain_yr {remain:g}: V_proj {per_share_hkd(project_value_yi(inp['roe_proj'], remain_yr=remain)[0]):+.2f} HKD/股")
    print(f"ROE_M < r 显式陈述: ROE_x − r = {roe['l'] - r:+.2%}/{roe['m'] - r:+.2%}/{roe['h'] - r:+.2%} (病态区 |ROE_M−r| = {abs(roe['m'] - r):.2%}); "
          f"PE_M(g) @ g=0/2/4/6% = {'/'.join(f'{perpetual_pe(g, roe['m'], r):.3f}' for g in (0.0, 0.02, 0.04, 0.06))} "
          f"→ 留存分支上每一元留存毁值, g 不是读数; 结论 M ≈ 1/r × 中枢 EPS + V_proj")
    print(f"倍数生成: r={r:.0%} 篮 {baskets['r_perp']}, cyclical flat PE_L=PE_M=PE_H = 1/r = {pe['m']:.4f} (分档 ROE 不进倍数); "
          f"护栏 [{inp['pe_own_min']}, {inp['pe_own_max']}] ✓ (③ 出带不触发); Gordon PB ROE_M/r = {roe['m'] / r:.3f}")
    for label, p in (("现价", inp["price"]), ("LB 一致 TP 15.49", 15.49), ("高盛 TP 17.5", 17.5)):
        pe_px = p / eps["m"]
        rel = "≈" if abs(pe_px - pe["m"]) < 0.5 else ("高于" if pe_px > pe["m"] else "低于")
        print(f"  {label:<14} {pe_px:6.2f}× 中枢 EPS {rel} 1/r {pe['m']:.2f}× → 隐含 r (g=0) {eps['m'] / p:.1%} (篮 {baskets['r_perp']} {eps['m'] / p - r:+.1%}); "
              f"扣 V_proj 后 {eps['m'] / (p - v_proj):.1%}")
    d0 = inp["dps_fy25_hkd"]
    print(f"DDM 对照 (g=0): D0 {d0} HKD ÷ r = {d0 / r:.2f}; FY25 实付对三档股息率 {d0 / L:.2%}/{d0 / M:.2%}/{d0 / H:.2%}")
    trough = per_share_hkd(2.0 * inp["np_h1_prev"]) * pe["m"] + v_proj
    old_regime = net_profit_yi(inp["asp_fy20"])
    old_regime_px = per_share_hkd(old_regime) * pe["m"] + v_proj
    print(f"L tier: price-ladder rung (not the own trough year) -> same flat PE; own trough half-year 2025H1 x2 = "
          f"{2 * inp['np_h1_prev']:.2f} 亿CNY -> EPS {per_share_hkd(2 * inp['np_h1_prev']):.4f} HKD x 1/r + V_proj = {trough:.2f} HKD (zone {zone_of(trough, L, M, H)}; "
          f"above L because L stacks the trough ASP on today's cost); pre-2022-regime trough price {inp['asp_fy20']:g} on today's cost -> "
          f"NI {old_regime:.2f} 亿 -> {old_regime_px:.2f} HKD (deep_discount pressure coordinate, zone {zone_of(old_regime_px, L, M, H)})")
    print(f"port ladder QHD5500 {inp['qhd_m']:g} -> {inp['qhd_h']:g} 元/吨 x pass_through {inp['pass_through']:g}"
          f" => px_h {inp['px_h']:g} (derived {px_h_expected:.1f}); candidate {inp['qhd_h_cand']:g} => px_h′ {px['c']:.1f}")
    per_10 = per_share_hkd(10.0 * inp["vol_yr"] * inp["conv"]) * pe["m"]
    print(f"sensitivity: +10元/吨 ASP -> anchor {per_10:+.2f} HKD; fx ±1% -> M {M * 0.01:+.2f}")
    # 校验 5: the floor is a disclosure, never a backstop (A10).
    print(f"地板 (只披露, A10): PB=1.0 = {inp['bps']:g} HKD → zone {zone_of(inp['bps'], L, M, H)}, {inp['bps'] - H:+.2f} vs H; "
          f"anchors at PB {L / inp['bps']:.2f}/{M / inp['bps']:.2f}/{H / inp['bps']:.2f}; scenario_L {L:.2f} wins, no max()")
    for pt in (0.3, 0.7):
        ph, pc = px_from_port(inp["qhd_h"], pt), px_from_port(inp["qhd_h_cand"], pt)
        print(f"  pass_through={pt}: px_h {ph:.1f} -> H {per_share_hkd(net_profit_yi(ph)) * pe['m'] + v_proj:.2f}; "
              f"px_h′ {pc:.1f} -> H′ {per_share_hkd(net_profit_yi(pc)) * pe['m'] + v_proj:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  candidate H′={cand_h:.2f}")
    print(f"ratios: L/M={L / M:.4f} H/M={H / M:.4f} (H-L)/2M={(H - L) / (2 * M):.4f} "
          f"| 分子比 L={eps['l'] / eps['m']:.4f} H={eps['h'] / eps['m']:.4f} | 倍数比 {pe['l'] / pe['m']:.4f}/{pe['h'] / pe['m']:.4f} flat")
    for dr in (-0.005, 0.005):
        r_s = r + dr
        v_s = per_share_hkd(project_value_yi(inp["roe_proj"], r_=r_s)[0])
        b = band(1.0 / r_s, v_s)
        print(f"敏感区 r_perp {dr:+.1%} ({r_s:.1%}, 篮外只作敏感区): PE {1 / r_s:.2f}, V_proj {v_s:+.2f} -> {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    for dg in (0.01, -0.01):
        g = g2 + dg
        b = band(perpetual_pe(g, roe["m"], r), v_proj)
        print(f"敏感区 g2 {dg:+.0%} ({g:+.2%}): PE {perpetual_pe(g, roe['m'], r):.2f} -> {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    bare = band(pe["m"], 0.0)
    print(f"对照 项目按 0 (纯 1/r): {'/'.join(f'{x:.2f}' for x in bare)} zone={zone_of(inp['price'], *bare)}")
    g_ret = min((1.0 - payout_fy25) * roe["m"], g_cap(r))
    pe_ret = perpetual_pe(g_ret, roe["m"], r)
    ret = band(pe_ret, 0.0)
    print(f"对照 撤回的永续留存分支 g2 {g_ret:+.2%} @ r {r:.0%} → {pe_ret:.2f}×: {'/'.join(f'{x:.2f}' for x in ret)} zone={zone_of(inp['price'], *ret)} "
          f"(假设 {1 - payout_fy25:.0%} 留存永远按 ROE_M {roe['m']:.1%} 复投, 与命名建设窗口矛盾)")
    pe_v1 = perpetual_pe(V1_G2, roe["m"], V1_R)
    v1 = band(pe_v1, 0.0)
    print(f"对照 旧口径 r {V1_R:.0%} + g {V1_G2:.0%} → {pe_v1:.2f}×: {'/'.join(f'{x:.2f}' for x in v1)} zone={zone_of(inp['price'], *v1)}")
    guide = band(pe["m"], v_proj, vol=1.31)
    print(f"对照 vol_yr 1.31 (公司指引): {'/'.join(f'{x:.2f}' for x in guide)} zone={zone_of(inp['price'], *guide)}")
    for label, years in (("六年 FY2020-25", ASP_YEARS[1:]), ("五年 FY2021-25", ASP_YEARS[2:])):
        px_w = sum(inp[k] for k in years) / len(years)
        m_w = per_share_hkd(net_profit_yi(px_w)) * pe["m"] + v_proj
        print(f"对照 中枢窗口 {label} {px_w:.0f} 元/吨 → M {m_w:.2f}{' (> H, 须同步改 H 轴)' if m_w > H else ''}")
    implied_ni = (inp["price"] - v_proj) / pe["m"] / fx * inp["shares"] / YI
    implied_asp = inp["px_base"] + (implied_ni - 2 * inp["np_h1"]) / inp["conv"] / inp["vol_yr"]
    print(f"price={inp['price']} zone={zone}  implied self-mined ASP at price (net of V_proj): {implied_asp:.1f} 元/吨 ({implied_asp / px_mid:.3f}x 中枢; "
          f"implied NI {implied_ni:.2f} 亿 vs FY2025 IFRS {inp['ni_fy25']}); zone-boundary ASP: "
          + ", ".join(f"{n} {inp['px_m'] + (v - M) / per_10 * 10:.0f}" for n, v in (("L", L), ("A", A), ("M", M), ("B", B), ("H", H))))
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): r_perp is
    # the one r in the anchors — it sets the flat multiple AND discounts V_proj,
    # so both move.  The ASP ladder, g2, ROE_proj and capex stay put.
    # Disclosure only — the anchors above are the 中枢 column.
    def band_rf(dr: float) -> tuple[float, float, float]:
        r_s = r + dr
        return band(perpetual_pe(g2, roe["m"], r_s), per_share_hkd(project_value_yi(inp["roe_proj"], r_=r_s)[0]))

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf, inp["price"])
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    # Only a clean run writes, so a FAIL never feeds the daily digest.
    if not errors:
        write_rf_readings("1898.HK", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
