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

v4 (中枢分子, valuation-rules「周期票的中枢分子与 PE < 1/r 的读法」): a cyclical's
M numerator must be mid-cycle earnings, and a sub-10x market multiple is read
FIRST as "the current print sits above mid-cycle".  The test is 当期 ÷ 中枢:
2026H1 run-rate 163.84 / bridged mid-cycle 167.89 = 0.976, TTM 0.915, FY26E
consensus 0.987, FY27E 1.013 -- all <= 1.15, so the current print is NOT an
upper-side coordinate and the reading falls through to branch / r (as in v3).
The framework's second mid-cycle reading (seven-year IFRS 归母 mean 141.83亿,
EPS 1.2481 HKD) is 18.4% below the bridged one -- inside the 20% tolerance;
the bridge is used because it holds volume, cost and the non-coal legs at
2026H1 and moves only price.  Guard 3a checks px_m against the filed series,
the two readings against each other, and prints the four ratios.

gordon_v3/v4: the flat multiple is generated, not read off a percentile, and it
sits on the RETENTION branch.  Tier ROE = tier net profit / equity (1,643.8亿
CNY) = 7.11 / 10.21 / 10.69%, so ROE_M is within 0.21pp of r: the 病态区 of
valuation-rules「反解分支」.  There PE_M(g) = (1 - g/ROE_M)/(r - g) is
10.00 / 10.05 / 10.14 / 10.31x at g = 0 / 2 / 4 / 6% -- the g a multiple inverts
to is not a reading, and the conclusion is "M ~ 10x mid-cycle EPS" whatever g2
is.  What still carries information is the BRANCH: China Coal pays out 34.9%
(FY2025 DPS 0.382 CNY / IFRS EPS 1.093) and retains 65%, and consensus FY26E ->
FY27E is up (+2.6%, n=3), so it sits on the retention branch and g2 comes
from its own payout policy: (1 - 0.349) x ROE_M = 6.65%, above the cap,
clipped to 6.00%.  `check_branch` guards the branch mechanically (sign + 20pp
payout gap), and the zone must hold across the evidence interval [4.61%, 6%].

gordon_v2 took the coal peer cluster's 100%-payout reading (兖矿 -2.26% /
兖煤澳 -1.48% -> -1.87%, flat 8.42x).  That world needs China Coal to pay out
100% (1.44 HKD/share at M, an 11.87% yield) against 0.43 actually paid -- a
65pp `check_branch` gap -- and g2 <= 0 fails the same-world gate.  Per peer:
兖矿's full-payout reading is legitimately ITS world (62% payout, NI -37%/yr,
consensus down) but a different one from China Coal's -> cross only; 兖煤澳's
12.62x on ROE 3.3% is unreachable (the hump tops at 10x), so its -1.48% was a
145%-payout artefact -> BLOCKED.  Usable cluster n = 0.  Both the v2 band and
the v3 band (current-print numerator 494 x 9.95) are printed as 对照带.

`cyclical` flat: all three tiers take PE_M.  Tier-ROE payouts are NOT used --
at ROE_L 7.11% the retention term would push the L payout to 16% and the
multiple to 3.91x, pricing the trough twice (the ASP ladder already carries
the cycle).  The L tier is a price-ladder RUNG (2025H1 ASP on 2026H1 volume
and cost), not the ticker's own realised trough year, so the 谷底档 recovery
stage does not apply.  Two pressure coordinates are printed only: the own
trough half-year (`np_h1_prev` x2) x 1/r, and the pre-2022-regime trough price
(FY2020 402) on today's cost x the flat PE.  The realised 5-year PE band is a
guardrail.  ②-b is checked on the mid-cycle M: the furthest >=2-house consensus
range (FY2027E, 3 houses) must have its mean inside [EPS_M, EPS_H] and within
20% of EPS_M, and EPS_H may not exceed that year's consensus high.

The asset floor (PB = 1.0 = 14.4661 HKD) is deliberately NOT used to backstop
L: L must be a scenario.  It now sits below M (ROE_M ~ r makes M ~ 1.05x book
by construction) and above L, in `neutral`; guard 5 asserts L < floor < H so a
revision that pushes the whole earnings band under book goes back to the
conversation.

Run:  python3 eval/1898.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.gordon import (  # noqa: E402
    G_CAP, check_branch, check_g_cap, check_r, implied_g, implied_g_retaining, payout, payout_gap, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, outputs_section, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

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
G2_TOL = 0.0005
TOL = 0.05
V2_G2 = -0.0187  # the retired peer full-payout reading, printed as the wrong-branch coordinate
TIERS = ("l", "m", "h")
ASP_YEARS = ("asp_fy19", "asp_fy20", "asp_fy21", "asp_fy22", "asp_fy23", "asp_fy24", "asp_fy25")
NI_IFRS_YEARS = ("ni_ifrs_fy19", "ni_ifrs_fy20", "ni_ifrs_fy21", "ni_ifrs_fy22", "ni_ifrs_fy23", "ni_ifrs_fy24")

REQUIRED = [
    "price", "shares", "fx_cny_hkd", "np_h1", "op_h1", "vol_yr",
    "px_base", "px_l", "px_m", "px_h", *ASP_YEARS, *NI_IFRS_YEARS,
    "conv", "r_perp", "g2", "equity",
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
    def px_from_port(qhd: float) -> float:
        return inp["px_base"] * (1.0 + (qhd - inp["qhd_m"]) / inp["qhd_m"] * inp["pass_through"])

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
    def net_profit_yi(px: float) -> float:
        dgp = (px - inp["px_base"]) * inp["vol_yr"]  # 元/吨 x 亿吨 = 亿 CNY
        return 2.0 * inp["np_h1"] + dgp * inp["conv"]

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

    # --- Step 4: tier ROE, then g2 on the retention branch (A9) ----------------
    equity_derived = inp["bps"] / fx * inp["shares"] / YI
    if abs(inp["equity"] - equity_derived) > EQUITY_TOL_YI:
        errors.append(f"equity {inp['equity']} vs bps ÷ fx × shares = {equity_derived:.1f} 亿CNY")
    roe = {t: npp[t] / inp["equity"] for t in npp}
    payout_fy25 = inp["dps_fy25"] * inp["shares"] / (inp["ni_fy25"] * YI)
    g2_raw = (1.0 - payout_fy25) * roe["m"]
    g2 = inp["g2"]
    errors += check_r(r, "r_perp")
    errors += check_g_cap(g2, "g2")
    # g2 <= 0 is the 100%-payout branch; on a company retaining 65% it describes
    # a different company (A9 / valuation-rules「反解分支」).
    if g2 <= 0:
        errors.append(f"g2={g2:+.4f} <= 0 is the full-payout branch — China Coal pays out {payout_fy25:.0%} (A9)")
    if abs(g2 - min(g2_raw, G_CAP)) > G2_TOL:
        errors.append(f"g2 {g2} vs min((1 - payout {payout_fy25:.4f}) x ROE_M {roe['m']:.4f} = {g2_raw:.4f}, cap {G_CAP}) (A9)")
    errors += check_branch(g2, roe["m"], r, payout_fy25, "g2")
    if not (inp["g_evid_min"] - 1e-9 <= g2 <= inp["g_evid_max"] + 1e-9):
        errors.append(f"g2 {g2} outside the evidence interval [{inp['g_evid_min']}, {inp['g_evid_max']}] (A9)")
    # The interval's floor is defined as the branch guard's threshold, so the
    # floor itself has to pass; the ceiling is the perpetual cap.
    errors += check_branch(inp["g_evid_min"], roe["m"], r, payout_fy25, "g_evid_min")
    if abs(inp["g_evid_max"] - G_CAP) > 1e-9:
        errors.append(f"g_evid_max {inp['g_evid_max']} must be the perpetual cap {G_CAP} (A9)")
    if abs(inp["g_peer_yankuang"] - g2) < 1e-9:
        errors.append("g_peer_yankuang leaked into g2 — it is a different-world cross, not the source (A9)")
    if errors:
        return report(errors, "FAIL (growth 口径)")

    # --- Step 5: the flat multiple (cyclical: every tier at PE_M) --------------
    pe = {t: perpetual_pe(g2, roe["m"], r) for t in TIERS}
    if not (pe["l"] == pe["m"] == pe["h"]):
        errors.append(f"multiple not flat: {pe} — cyclical policy (A9)")
    if not (inp["pe_own_min"] - 1e-9 <= pe["m"] <= inp["pe_own_max"] + 1e-9):
        errors.append(
            f"guardrail: generated PE {pe['m']:.2f} outside own band "
            f"[{inp['pe_own_min']}, {inp['pe_own_max']}] — stop, back to the conversation"
        )
    if errors:
        return report(errors, "FAIL (guardrail)")

    # --- Step 6: anchors, floor, zone, candidate band --------------------------
    def band_at(g: float) -> tuple[float, float, float]:
        pe_g = perpetual_pe(g, roe["m"], r)
        return tuple(eps[t] * pe_g for t in TIERS)  # type: ignore[return-value]

    L, M, H = band_at(g2)
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}"])
    A, B = cut_points(L, M, H)
    if not (L < inp["bps"] < H):
        errors.append(
            f"asset floor PB=1.0 ({inp['bps']:g} HKD) no longer sits inside [L {L:.2f}, H {H:.2f}] — "
            "A10's 'floor is a reference, not a backstop' premise needs re-deciding"
        )
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # 校验步骤 4a: the zone must hold across the g2 evidence interval, else the
    # framework is picking a g inside the interval to make the zone look right.
    evid = {g: band_at(g) for g in (inp["g_evid_min"], inp["g_evid_max"])}
    for g, b in evid.items():
        if zone_of(inp["price"], *b) != zone:
            errors.append(f"zone flips to {zone_of(inp['price'], *b)} at g2={g:+.2%} inside the evidence interval — BLOCKED (A9)")

    # candidate band: exactly one line, L' = L, M' = M, H' recomputed
    cand_h = eps["c"] * pe["m"]
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
    for tag, t in (("L", "l"), ("M", "m"), ("H", "h"), ("H′", "c"), ("基线", "base")):
        anchor = eps[t] * pe["m"]
        print(
            f"{tag:2}: asp={px[t]:>6.1f}元/吨  Δgp={(px[t] - inp['px_base']) * inp['vol_yr']:+7.2f}亿CNY  np={npp[t]:7.2f}亿CNY  "
            f"ROE={roe[t]:6.2%}  eps={eps_cny[t]:.4f}CNY={eps[t]:.4f}HKD  anchor={anchor:.4f}HKD  PB={anchor / inp['bps']:.3f}"
            + ("  (2026H1 print, coordinate only)" if t == "base" else "")
        )
    print(f"中枢 (A3‴): px_m {inp['px_m']:g} = FY2019-25 filed ASP mean {px_mid:.1f} ({'/'.join(f'{inp[k]:g}' for k in ASP_YEARS)}); "
          f"2026H1 {inp['px_base']:g} = {inp['px_base'] / px_mid:.3f}x 中枢, FY2022 peak {inp['asp_fy22']:g} = {inp['asp_fy22'] / px_mid:.2f}x, "
          f"FY2020 trough {inp['asp_fy20']:g} = {inp['asp_fy20'] / px_mid:.2f}x")
    print(f"  bridged mid-cycle NI {npp['m']:.2f}亿 vs realised seven-year IFRS mean {ni_mid_realised:.2f}亿 "
          f"({'/'.join(f'{v:g}' for v in ni_hist)}): {mid_gap:+.1%} (≤ {MID_CROSS_TOL:.0%} ✓); "
          f"realised-mean coordinate EPS {ni_mid_realised * YI / inp['shares'] * fx:.4f} HKD × PE = "
          f"{ni_mid_realised * YI / inp['shares'] * fx * pe['m']:.2f} (zone {zone_of(ni_mid_realised * YI / inp['shares'] * fx * pe['m'], L, M, H)})")
    print("  当期 ÷ 中枢: " + "; ".join(f"{k} {v:.2f}亿 → {ratios[k]:.3f}" for k, v in current.items())
          + f" → {'> ' + str(PEAK_RATIO) + ': current print is an UPPER-side coordinate, M = 中枢' if peak_numerator else f'all ≤ {PEAK_RATIO}: not a peak numerator; PE < 1/r reads via branch / r (A9)'}")
    peak_eps = inp["ni_ifrs_fy23"] * YI / inp["shares"] * fx
    trough_fy_eps = inp["ni_fy25"] * YI / inp["shares"] * fx
    print(f"  coordinates × flat PE: FY2023 IFRS peak EPS {peak_eps:.4f} ({inp['ni_ifrs_fy23'] / npp['m']:.2f}x 中枢) → {peak_eps * pe['m']:.2f} "
          f"(zone {zone_of(peak_eps * pe['m'], L, M, H)}); FY2025 trough EPS {trough_fy_eps:.4f} ({inp['ni_fy25'] / npp['m']:.2f}x) → {trough_fy_eps * pe['m']:.2f} "
          f"(zone {zone_of(trough_fy_eps * pe['m'], L, M, H)}); TTM → {ttm * YI / inp['shares'] * fx * pe['m']:.2f}; 2026H1 基线 → {eps['base'] * pe['m']:.2f}")
    print(f"  ②-b on 中枢 M: FY27E consensus {c_low:.4f}/{c_mean:.4f}/{c_high:.4f} HKD; mean in [EPS_M {eps['m']:.4f}, EPS_H {eps['h']:.4f}] ✓, "
          f"M dev {c_mean / eps['m'] - 1:+.1%} ✓; EPS_H ≤ high ✓; ② 直读 × PE = {c_low * pe['m']:.2f}/{c_mean * pe['m']:.2f}/{c_high * pe['m']:.2f}")
    print(f"分支: 留存 (FY2025 派息率 {payout_fy25:.1%} = DPS {inp['dps_fy25']} CNY × shares ÷ IFRS 归母 {inp['ni_fy25']:.2f}亿, "
          f"EPS {inp['ni_fy25'] * YI / inp['shares']:.3f}); g2_raw = (1-{payout_fy25:.3f}) × ROE_M {roe['m']:.2%} = {g2_raw:+.2%} "
          f"→ {'截顶 cap' if g2_raw > G_CAP else '未越 cap'} → g2 {g2:+.2%}; 证据区间 [{inp['g_evid_min']:+.2%}, {inp['g_evid_max']:+.2%}]; "
          f"兖矿全派息分支 {inp['g_peer_yankuang']:+.2%} 只作交叉 (不同世界)")
    modelled, gap = payout_gap(g2, roe["m"], payout_fy25)
    modelled_lo, gap_lo = payout_gap(inp["g_evid_min"], roe["m"], payout_fy25)
    print(f"check_branch ✓ (病态区 |ROE_M−r| = {abs(roe['m'] - r):.2%} < 3pp, 幅度测试生效): 模型派息率 {modelled:.1%} vs 实付 {payout_fy25:.1%}, "
          f"差 {gap:+.1%}; 下沿 {inp['g_evid_min']:+.2%} 模型 {modelled_lo:.1%}, 差 {gap_lo:+.1%} (≤ 20pp)")
    print(f"ROE ≈ r 显式陈述 (A13 式): ROE_x − r = {roe['l'] - r:+.2%}/{roe['m'] - r:+.2%}/{roe['h'] - r:+.2%}; "
          f"PE_M(g) @ g=0/2/4/6% = {'/'.join(f'{perpetual_pe(g, roe['m'], r):.3f}' for g in (0.0, 0.02, 0.04, 0.06))} "
          f"→ 结论 M ≈ 10× × 中枢 EPS, 对 g2 不敏感 (净现金公司留存资本未必按账面 ROE 再投: g 无信息, 只有分支有信息)")
    tiered = [perpetual_pe(g2, roe[t], r) for t in TIERS]
    print(f"倍数生成: r={r:.0%}, cyclical flat PE_L=PE_M=PE_H = {pe['m']:.4f} (分档 ROE 不进倍数: 若分档 → "
          f"{'/'.join(f'{v:.2f}' for v in tiered)}, L 档派息率 {payout(g2, roe['l']):.0%} — 周期算两遍); "
          f"护栏 [{inp['pe_own_min']}, {inp['pe_own_max']}] ✓; Gordon PB (ROE_M−g2)/(r−g2) = {(roe['m'] - g2) / (r - g2):.3f}")
    pe_min_pos = min(perpetual_pe(i / 1000, roe["m"], r) for i in range(int(G_CAP * 1000) + 1))
    for label, p in (("现价", inp["price"]), ("LB 一致 TP 15.49", 15.49), ("高盛 TP 17.5", 17.5)):
        pe_px = p / eps["m"]
        if pe_px > pe["m"]:
            print(f"  {label:<14} {pe_px:6.2f}× 中枢 EPS → 高于 {pe['m']:.2f}× 顶, 留存分支任何 g≤6% 不可达 (r≈{1 / pe_px:.1%})")
            continue
        g_ret, ok = implied_g_retaining(pe_px, roe["m"], r)
        g_full, _ = implied_g(pe_px, roe["m"], r)
        reach = "可达" if pe_px >= pe_min_pos else f"不可达 (g∈[0,6%] 最低 {pe_min_pos:.2f}×, 说的是 r≈{1 / pe_px:.1%})"
        print(f"  {label:<14} {pe_px:6.2f}× 中枢 EPS → 留存分支 {reach}; 反解 {g_ret:+.2%} (well_conditioned={ok}); "
              f"全派息读数 {g_full:+.2%} (派息率 {payout_fy25:.0%} 否决)")
    d0 = inp["dps_fy25_hkd"]
    g_div_px = (inp["price"] * r - d0) / (inp["price"] + d0)
    print(f"DDM 对照: D0 {d0} HKD × (1+g2) ÷ (r−g2) = {d0 * (1 + g2) / (r - g2):.2f}; g=0 → {d0 / r:.2f}; "
          f"现价 {inp['price']} 隐含股息增长 {g_div_px:+.2%}; M 上 FY26E 模型股息 {eps['m'] * modelled:.4f} HKD → 股息率 "
          f"{eps['m'] * modelled / M:.1%} (= r − g2); FY25 实付对三档股息率 {d0 / L:.2%}/{d0 / M:.2%}/{d0 / H:.2%}")
    trough_eps = 2.0 * inp["np_h1_prev"] * YI / inp["shares"] * fx
    trough = trough_eps / r
    old_regime = net_profit_yi(inp["asp_fy20"])
    old_regime_px = old_regime * YI / inp["shares"] * fx * pe["m"]
    print(f"L tier: price-ladder rung (not the own trough year) -> same flat PE; own trough half-year 2025H1 x2 = "
          f"{2 * inp['np_h1_prev']:.2f} 亿CNY -> EPS {trough_eps:.4f} HKD x 1/r = {trough:.2f} HKD (zone {zone_of(trough, L, M, H)}; "
          f"above L because L stacks the trough ASP on today's cost); pre-2022-regime trough price {inp['asp_fy20']:g} on today's cost -> "
          f"NI {old_regime:.2f} 亿 -> {old_regime_px:.2f} HKD (deep_discount pressure coordinate, zone {zone_of(old_regime_px, L, M, H)})")
    print(f"port ladder QHD5500 {inp['qhd_m']:g} -> {inp['qhd_h']:g} 元/吨 x pass_through {inp['pass_through']:g}"
          f" => px_h {inp['px_h']:g} (derived {px_h_expected:.1f}); candidate {inp['qhd_h_cand']:g} => px_h′ {px['c']:.1f}")
    per_10 = 10.0 * inp["vol_yr"] * inp["conv"] * YI / inp["shares"] * fx * pe["m"]
    print(f"sensitivity: +10元/吨 ASP -> anchor {per_10:+.2f} HKD; floor PB=1.0 = {inp['bps']:g} HKD "
          f"(zone {zone_of(inp['bps'], L, M, H)}, {inp['bps'] - M:+.2f} vs M; L < floor < H ✓, floor does not backstop L)")
    for pt in (0.3, 0.7):
        ph = px_from_port_at(inp, inp["qhd_h"], pt)
        pc = px_from_port_at(inp, inp["qhd_h_cand"], pt)
        print(f"  pass_through={pt}: px_h {ph:.1f} -> H {net_profit_yi(ph) * YI / inp['shares'] * fx * pe['m']:.2f}; "
              f"px_h′ {pc:.1f} -> H′ {net_profit_yi(pc) * YI / inp['shares'] * fx * pe['m']:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  candidate H′={cand_h:.2f}")
    print(f"ratios: L/M={L / M:.4f} H/M={H / M:.4f} (H-L)/2M={(H - L) / (2 * M):.4f} "
          f"| 分子比 L={eps['l'] / eps['m']:.4f} H={eps['h'] / eps['m']:.4f} | 倍数比 {pe['l'] / pe['m']:.4f}/{pe['h'] / pe['m']:.4f} flat")
    for g, b in evid.items():
        print(f"证据区间 g2={g:+.2%} (PE {perpetual_pe(g, roe['m'], r):.4f}): {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    for dg in (-0.01, 0.01):
        g = g2 + dg
        note = " (> cap, 参考)" if g > G_CAP + 1e-9 else ""
        b = band_at(g)
        print(f"敏感性 g2 {dg:+.0%} ({g:+.2%}{note}): PE {perpetual_pe(g, roe['m'], r):.2f} -> {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    zero = band_at(0.0)
    print(f"零增长参照 g2=0 (10× flat): {'/'.join(f'{x:.2f}' for x in zero)} zone={zone_of(inp['price'], *zero)} — 与 g2 6% 差 {M - zero[1]:+.2f}/股 "
          f"(病态区: ROE_M 略高于 r 时封顶的 g 抬高派息项, 不是增长 credit)")
    pe_v3 = perpetual_pe(G_CAP, roe["base"], r)
    v3 = tuple(eps[t] * pe_v3 for t in ("l", "base", "h"))
    print(f"对照 v3 当期分子 {inp['px_base']:g} × ROE {roe['base']:.2%} → flat {pe_v3:.2f}×: {'/'.join(f'{x:.2f}' for x in v3)} "
          f"zone={zone_of(inp['price'], *v3)} (当期分子的坐标: 当期 ÷ 中枢 {ratios['run-rate 2026H1x2']:.3f}, 非峰值)")
    pe_v2 = perpetual_pe(V2_G2, roe["base"], r)
    old = tuple(eps[t] * pe_v2 for t in ("l", "base", "h"))
    print(f"对照 v2 全派息分支 g2 {V2_G2:+.2%} flat {pe_v2:.2f}×: {'/'.join(f'{x:.2f}' for x in old)} "
          f"zone={zone_of(inp['price'], *old)} (分支错误的坐标: 隐含股息率 {r - V2_G2:.2%}, M 档每股派 {eps['base']:.2f} HKD vs 实付 {d0})")
    implied_ni = inp["price"] / pe["m"] / fx * inp["shares"] / YI
    implied_asp = inp["px_base"] + (implied_ni - 2 * inp["np_h1"]) / inp["conv"] / inp["vol_yr"]
    print(f"price={inp['price']} zone={zone}  implied self-mined ASP at price: {implied_asp:.1f} 元/吨 ({implied_asp / px_mid:.3f}x 中枢; "
          f"implied NI {implied_ni:.2f} 亿 vs FY2025 IFRS {inp['ni_fy25']}); zone-boundary ASP: "
          + ", ".join(f"{n} {inp['px_m'] + (v - M) / per_10 * 10:.0f}" for n, v in (("L", L), ("A", A), ("M", M), ("B", B), ("H", H))))
    return report(errors)


def px_from_port_at(inp: dict[str, float], qhd: float, pass_through: float) -> float:
    """Self-mined ASP implied by a port price at a given pass-through (sensitivity only)."""
    return inp["px_base"] * (1.0 + (qhd - inp["qhd_m"]) / inp["qhd_m"] * pass_through)


if __name__ == "__main__":
    sys.exit(main())
