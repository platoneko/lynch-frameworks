#!/usr/bin/env python3
"""1766.HK (CRRC Corporation) valuation eval.

frameworks/1766.HK.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: crrc_hk_anchored_consensus_pe_gordon_v3

Main ruler: whole-company PE on the H share.  EPS tiers rescale one consensus
range (2026-04-20: low .514 / mean .554 / high .594) onto the latest mean
(.538), so both ends stay same-source even though the newest print has
degenerated to a point estimate.  FY2026 is the furthest year with >= 2
houses AND a range (裁决顺序 ②); FY2027 exists only as single points (UBS
0.55, one yfinance house per line), so the UBS point rides the candidate band
(A9) and never the base deck.

The multiple is GENERATED (valuation-rules「永续增长口径」), with r set by the
leg's basket (篮 4 龙头制造, HKD segment) and the southbound dividend tax taken
as a numerator discount k on the paid-out part (A14):

    PE_x = k (1 - g2/ROE_x) / (r - g2),   k = 1 - hk_div_tax x payout_FY25

With ROE 8-9% < r the Gordon multiple is a hump peaking at k/r, so every
multiple below it has TWO readings: a business paying out 100% and shrinking
(what `implied_g` returns for PE < 1/r) or one retaining g2/ROE and growing.
The formula cannot tell them apart; the payout ratio can.  CRRC pays out 50%
(FY2025 DPS 0.23 / EPS 0.459) and has grown DPS at +6% for seven years, so it
sits on the RETENTION branch: g2 = (1 - payout) x ROE_M = +4.37%, shared by
all tiers, and each tier's own ROE sets the payout it needs (46/50/53%) and
hence its multiple (7.38/8.00/8.54 after tax).  `check_branch` guards this
mechanically.  The peer cluster's 100%-payout reading (-3.67%, flat 7.32x)
describes a different company and also fails the same-world gate (裁决顺序 ④):
CRRC's consensus and realised growth both point up.

The A-share companion band reprices the same CNY earnings at the same basket
r (方案 A: basket r fixed across currencies, `r_perp_a` = 篮 4, k = 1).  The
CNY r_f segment reading (r - `cny_rf_gap`) is a disclosure line only, pending
`_AXIS.rates`.  The 1/(r - g) shortcut (b_g ~ 0) was rejected on the PP&E
series (A16), so the retention-branch honest form stays the ruler.

The own-year quantile band (5.49 / 9.20 / 13.19) stays a cross-ruler; the
realised 5y monthly TTM band [6.08, 10.90] is the guardrail.

Two things this script deliberately does NOT do, both recorded as `待补`:

  * It does not split the two legs into the numerator.  CRRC's segment table
    sums to 778.6亿 against 1,316.8亿 of revenue — a 41% gap.  The guard
    prints the gap.
  * It does not give 新产业 a growth multiple.  Times Electric (3898.HK), the
    listed crown jewel of that segment, trades at PE 8.48 — below CRRC's own
    9.28.  There is no market evidence for a segment premium.

Run:  python3 eval/1766.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import AXIS_SOUTHBOUND  # noqa: E402
from lib.frameworks import load_framework  # noqa: E402
from lib.gordon import (  # noqa: E402
    check_branch, check_g_cap, check_r, g_cap, implied_g_retaining, payout, payout_gap, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "1766.HK.md"
FORMULA_ID = "crrc_hk_anchored_consensus_pe_gordon_v3"

TIERS = ("l", "m", "h")
# The 2026-04-20 consensus range the tiers are rescaled from (A1).
CONSENSUS_LOW, CONSENSUS_MEAN, CONSENSUS_HIGH = 0.514, 0.554, 0.594
EPS_TOL = 0.001
G2_TOL = 0.0005
SEGMENT_GAP_WARN = 0.20
CANDIDATE_TOL = 0.05
YI = 1e8

REQUIRED = [
    "price", "price_a", "shares", "bps", "equity", "fx_hkdcny",
    "eps_l", "eps_m", "eps_h",
    "r_perp", "r_perp_a", "cny_rf_gap", "hk_div_tax", "net_cash", "nppe_fy25",
    "dps_fy25", "ni_fy25", "g2_l", "g2_m", "g2_h",
    "g_evid_min", "g_evid_max", "g_peer_crsc",
    "pe_own_min", "pe_own_max",
    "pe_hk_ownyear_l", "pe_hk_ownyear_m", "pe_hk_ownyear_h", "eps_fy27_ubs",
    "w_rail", "w_new", "emu_2026", "emu_2025",
    "pe_a_mid", "seg_total_h1", "rev_h1",
]
# Reference rows: present in Inputs, never in an anchor path (校验步骤 4d / 7).
NOT_FORMULA = ("pe_hk_ownyear_l", "pe_hk_ownyear_m", "pe_hk_ownyear_h", "pe_a_mid", "eps_fy27_ubs", "g_peer_crsc")


def check_southbound_mount(md: str) -> list[str]:
    """Axis §3 rule 3: a mounted ticker reports the A-share companion band and live H/A.

    The southbound axis locks no numerator and, now that the multiple is
    Gordon-generated (A8/A11), no multiple either; what it still locks is the
    reporting contract its own §4 direction check depends on.
    """
    if not AXIS_SOUTHBOUND.exists():
        return [f"axis file missing: {AXIS_SOUTHBOUND.name}"]
    errors: list[str] = []
    if "1766.HK" not in AXIS_SOUTHBOUND.read_text(encoding="utf-8"):
        errors.append("1766.HK is not declared on _AXIS.southbound-repricing.md — "
                      "a mount has to exist on both sides")
    if "A 股对照带" not in md:
        errors.append("framework lacks the A-share companion band (axis §3 rule 3)")
    if not re.search(r"H/A\s*=\s*\*{0,2}[01]\.\d+", md):
        errors.append("framework does not state the current H/A reading (axis §3 rule 3)")
    return errors


def check_r_rows(r: float, r_a: float, baskets: dict[str, int]) -> list[str]:
    """Both r rows are the same basket: basket r is fixed across currencies
    (方案 A, A14), so the A-share companion band carries 篮 4 too."""
    errors: list[str] = []
    for where, value in (("r_perp", r), ("r_perp_a", r_a)):
        if where not in baskets:
            errors.append(f"{where}: no 篮 N in the Inputs source cell (valuation-rules.md「§r 篮子」)")
        errors += check_r(value, where, baskets.get(where))
    if baskets.get("r_perp_a") != baskets.get("r_perp"):
        errors.append(f"r_perp_a 篮 {baskets.get('r_perp_a')} != r_perp 篮 {baskets.get('r_perp')} — one company, one basket (A14)")
    return errors


def band_at(g2: float, eps: dict[str, float], roe: dict[str, float], r: float, k: float, fx: float) -> tuple[float, float, float]:
    """L/M/H in HKD for one shared g2 -- each tier's own ROE sets its payout and multiple; k is the dividend-tax discount."""
    return tuple(eps[t] * k * perpetual_pe(g2, roe[t], r) / fx for t in TIERS)  # type: ignore[return-value]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    errors += check_southbound_mount(md)
    baskets = parse_baskets(md)
    r = inp["r_perp"]
    r_a = inp["r_perp_a"]
    fx = inp["fx_hkdcny"]
    eps = {t: inp[f"eps_{t}"] for t in TIERS}

    # --- Step 1: numerator ladder and provenance -----------------------------
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    # Both EPS ends must come from the same consensus range (A1).
    for tag, ref in (("l", CONSENSUS_LOW), ("h", CONSENSUS_HIGH)):
        derived = eps["m"] * ref / CONSENSUS_MEAN
        if abs(derived - eps[tag]) > EPS_TOL:
            errors.append(
                f"eps_{tag} {eps[tag]} vs rescaled {derived:.4f} "
                f"(mean {eps['m']} x {ref}/{CONSENSUS_MEAN}) — ends not same-source"
            )
    if errors:
        return report(errors, "FAIL (numerators)")

    # --- Step 2: tier ROE, then g2 on the retention branch (A11) --------------
    roe = {t: eps[t] * inp["shares"] / (inp["equity"] * YI) for t in TIERS}
    payout_fy25 = inp["dps_fy25"] * inp["shares"] / (inp["ni_fy25"] * YI)
    g2_derived = (1.0 - payout_fy25) * roe["m"]
    # Southbound dividend tax as a numerator discount on the paid-out part (A14).
    k = 1.0 - inp["hk_div_tax"] * payout_fy25
    errors += check_r_rows(r, r_a, baskets)
    for t in TIERS:
        errors += check_g_cap(inp[f"g2_{t}"], r, f"g2_{t}")
    errors += check_g_cap(inp["g2_m"], r_a, "g2_m@r_perp_a")
    # Disclosure-only CNY r_f segment (A14): g2 must also clear its tighter cap.
    r_ccy = r_a - inp["cny_rf_gap"]
    errors += check_g_cap(inp["g2_m"], r_ccy, "g2_m@CNY 段 (披露)")
    if not (inp["g2_l"] == inp["g2_m"] == inp["g2_h"]):
        errors.append(f"g2 tiers {inp['g2_l']}/{inp['g2_m']}/{inp['g2_h']} must be one shared value (A11)")
    # A negative g2 is the 100%-payout branch; on a company paying out half it
    # describes a different company (A11 / valuation-rules「反解分支」).
    if inp["g2_m"] <= 0:
        errors.append(f"g2={inp['g2_m']:+.4f} <= 0 is the full-payout branch — CRRC pays out {payout_fy25:.0%} (A11)")
    if abs(inp["g2_m"] - g2_derived) > G2_TOL:
        errors.append(f"g2_m {inp['g2_m']} vs (1 - payout {payout_fy25:.4f}) x ROE_M {roe['m']:.4f} = {g2_derived:.4f} (A11)")
    errors += check_branch(inp["g2_m"], roe["m"], r, payout_fy25, "g2_m")
    if not (inp["g_evid_min"] - 1e-9 <= inp["g2_m"] <= inp["g_evid_max"] + 1e-9):
        errors.append(f"g2_m {inp['g2_m']} outside the evidence interval [{inp['g_evid_min']}, {inp['g_evid_max']}] (A11)")
    if errors:
        return report(errors, "FAIL (growth 口径)")
    pe = {t: k * perpetual_pe(inp[f"g2_{t}"], roe[t], r) for t in TIERS}
    # 校验步骤 4: guardrail — generated (after-tax) multiples inside the realised band.
    for t in TIERS:
        if not (inp["pe_own_min"] <= pe[t] <= inp["pe_own_max"]):
            errors.append(
                f"guardrail: generated PE_{t} {pe[t]:.2f} outside realised band "
                f"[{inp['pe_own_min']}, {inp['pe_own_max']}] (A2) — STOP, do not force g"
            )
    if errors:
        return report(errors, "FAIL (guardrail)")

    # --- Step 3: check-layer only (legs never enter the anchor path) --------
    if abs(inp["w_rail"] + inp["w_new"] - 1.0) > 1e-6:
        errors.append(f"leg weights must sum to 1: {inp['w_rail']} + {inp['w_new']}")
    gap = 1.0 - inp["seg_total_h1"] / inp["rev_h1"]
    if inp["emu_2026"] >= inp["emu_2025"]:
        errors.append(
            f"EMU tender {inp['emu_2026']:.0f} >= prior {inp['emu_2025']:.0f} — "
            "§1 属性 C assumes a declining-but-better-than-feared tender; rerun the narrative"
        )
    # Comparison-only fields must not have leaked into the multiple path.
    for key in ("pe_a_mid", "pe_hk_ownyear_m"):
        if abs(inp[key] - pe["m"]) < 1e-9:
            errors.append(f"{key} leaked into the multiple path — it is a comparison field")
    if abs(inp["g_peer_crsc"] - inp["g2_m"]) < 1e-9:
        errors.append("g_peer_crsc leaked into g2 — it is an n=1 cross-check, not the source (A11)")
    leaked = [k_ for k_ in NOT_FORMULA if k_ not in inp]
    if leaked:
        errors.append(f"reference rows missing from Inputs: {leaked}")

    # --- Step 4: anchors -----------------------------------------------------
    L, M, H = band_at(inp["g2_m"], eps, roe, r, k, fx)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    # 校验步骤 4a: the zone must hold across the g2 evidence interval, else the
    # framework is picking a g inside the interval to make the zone look right.
    evid = {g: band_at(g, eps, roe, r, k, fx) for g in (inp["g_evid_min"], inp["g_evid_max"])}
    for g, b in evid.items():
        if zone_of(inp["price"], *b) != zone:
            errors.append(f"zone flips to {zone_of(inp['price'], *b)} at g2={g:+.2%} inside the evidence interval — BLOCKED (A11)")

    flat_errs, flat_cny = flat_multiple_ladder((eps["l"], eps["m"], eps["h"]), pe["m"])
    errors += flat_errs
    flat = tuple(v / fx for v in flat_cny)
    flat_width = (flat[2] - flat[0]) / (2 * flat[1])

    # 校验步骤 4c (A9): candidate band swaps only the M-tier EPS for the UBS
    # FY2027 single point; L'/H' copy the base.  Compared to the Outputs line
    # the digest reads; never a zone input.
    cand = (L, inp["eps_fy27_ubs"] * pe["m"] / fx, H)
    errors += ladder("候选带", *cand)
    stated_cand = load_framework(FRAMEWORK).candidate
    if stated_cand is None:
        errors.append("候选带 line missing from Outputs (A9)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), stated_cand, cand):
            if abs(said - got) > CANDIDATE_TOL:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # A-share companion band: same CNY earnings, same basket r, no dividend
    # tax (A14).  The CNY r_f segment band is a disclosure line only.
    pe_a = {t: perpetual_pe(inp[f"g2_{t}"], roe[t], r_a) for t in TIERS}
    la, ma, ha = (eps[t] * pe_a[t] for t in TIERS)
    pe_ccy = {t: perpetual_pe(inp[f"g2_{t}"], roe[t], r_ccy) for t in TIERS}
    lc, mc, hc = (eps[t] * pe_ccy[t] for t in TIERS)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"r_perp = 篮 {baskets['r_perp']} {r:.1%} (r_f 4.0 + 篮子溢价 6.0); r_perp_a = 篮 {baskets['r_perp_a']} {r_a:.1%} 跨市场固定 (对照带); "
          f"CNY 段披露 r = r_perp_a − cny_rf_gap = {r_ccy:.1%}; cap g2 ≤ {g_cap(r):.1%} / {g_cap(r_ccy):.1%} (段)")
    print(f"{'档':<3}{'EPS(CNY)':>10}{'ROE':>8}{'g2':>8}{'派息率':>7}{'PE(税后)':>9}{'CNY价值':>10}{'锚点HKD':>10}")
    for t, a in zip(TIERS, (L, M, H)):
        print(f"{t.upper():<3}{eps[t]:10.4f}{roe[t]:8.1%}{inp[f'g2_{t}']:+8.2%}{payout(inp[f'g2_{t}'], roe[t]):7.0%}"
              f"{pe[t]:9.2f}{eps[t] * pe[t]:10.3f}{a:10.2f}")
    print(f"共识区间同源 ✓ ({CONSENSUS_LOW}/{CONSENSUS_MEAN}/{CONSENSUS_HIGH} "
          f"缩放至最新 mean {eps['m']}); 裁决顺序 ②: FY2026 = 最远带区间共识年, FY2027 仅单点 → 候选带")
    print(f"分支: 留存 (FY2025 派息率 {payout_fy25:.1%} = DPS {inp['dps_fy25']} × shares ÷ 归母 {inp['ni_fy25']:.0f}亿); "
          f"g2 = (1-{payout_fy25:.3f}) × ROE_M {roe['m']:.2%} = {g2_derived:+.2%} ✓ (cap {g_cap(r):.0%}; CNY 段披露 {g_cap(r_ccy):.1%}); "
          f"证据区间 [{inp['g_evid_min']:+.2%}, {inp['g_evid_max']:+.2%}], 通号留存分支 {inp['g_peer_crsc']:+.2%} (n=1 互证)")
    modelled, pgap = payout_gap(inp["g2_m"], roe["m"], payout_fy25)
    print(f"check_branch ✓ (峰形区 ROE_M {roe['m']:.2%} < r): 模型派息率 {modelled:.1%} vs 实付 {payout_fy25:.1%}, 差 {pgap:+.1%}")
    print(f"红利税分子折扣 k = 1 − {inp['hk_div_tax']:.0%} × {payout_fy25:.3f} = {k:.4f} (A14)")
    print(f"倍数生成: r={r:.0%}, PE_x = k(1-g2/ROE_x)/(r-g2) = {pe['l']:.2f}/{pe['m']:.2f}/{pe['h']:.2f} 同向 "
          f"(税前 {pe['l'] / k:.2f}/{pe['m'] / k:.2f}/{pe['h'] / k:.2f}); "
          f"护栏 [{inp['pe_own_min']}, {inp['pe_own_max']}] ✓; M 档 Gordon PB {(roe['m'] - inp['g2_m']) / (r - inp['g2_m']):.2f}")
    g_mid, ok_mid = implied_g_retaining(inp["pe_hk_ownyear_m"], roe["m"], r)
    print(f"带边反解 (裁决顺序 ③, 留存分支税前, M 档 ROE {roe['m']:.1%} < r): 月频中位 9.21x ↔ g {implied_g_retaining(9.21, roe['m'], r)[0]:+.2%}; "
          f"own-year 中位 {inp['pe_hk_ownyear_m']}x ↔ {g_mid:+.2%}; 10x 顶 ↔ 0%; 下沿 {inp['pe_own_min']}x ↔ "
          f"{implied_g_retaining(inp['pe_own_min'], roe['m'], r)[0]:+.2%} (> cap, 不可达)")
    top = k / r
    print(f"ROE < r 显式歧义 (A13): ROE−r = {roe['l'] - r:+.2%}/{roe['m'] - r:+.2%}/{roe['h'] - r:+.2%}; "
          f"零增长全派息税后 k/r {top:.2f}x 对照带 {eps['l'] * top / fx:.2f}/{eps['m'] * top / fx:.2f}/{eps['h'] * top / fx:.2f}; "
          f"M 档 {pe['m']:.2f}x 亦可读作 g=0、全派息、r≈{k / pe['m']:.1%}")
    for label, px in (("H 股现价", inp["price"] * fx), ("A 股现价", inp["price_a"]), ("H 股 TP 6.47", 6.47 * fx)):
        pe_px = px / eps["m"]
        if pe_px > top:
            print(f"  {label:<10} 隐含 PE={pe_px:6.2f}x → 高于税后顶 {top:.2f}x, 任何分支无解 (HKD 段)")
            continue
        g_px, ok = implied_g_retaining(pe_px / k, roe["m"], r)
        print(f"  {label:<10} 隐含 PE={pe_px:6.2f}x → 留存分支 g={g_px:+.2%} (well_conditioned={ok})")
    # Implied r at the market price, honest form, M tier (A14 / Outputs 披露行).
    pe_h_mkt = inp["price"] * fx / eps["m"]
    pe_a_mkt = inp["price_a"] / eps["m"]
    r_h = inp["g2_m"] + k * (1 - inp["g2_m"] / roe["m"]) / pe_h_mkt
    r_h_pre = inp["g2_m"] + (1 - inp["g2_m"] / roe["m"]) / pe_h_mkt
    r_a_mkt = inp["g2_m"] + (1 - inp["g2_m"] / roe["m"]) / pe_a_mkt
    print(f"隐含 r(P) 诚实式 M 档: H {inp['price']} = {pe_h_mkt:.2f}x → 税后 {r_h:.2%} (篮 4 {r_h - r:+.2%}; 税前 {r_h_pre:.2%}); "
          f"A {inp['price_a']} = {pe_a_mkt:.2f}x → {r_a_mkt:.2%} (篮 4 {r_a_mkt - r_a:+.2%}; CNY 段披露 {r_a_mkt - r_ccy:+.2%}); "
          f"A/H 税后差 {r_h - r_a_mkt:+.2%} vs r_f 段差 {inp['cny_rf_gap']:+.2%}")
    # DDM cross on the FY2025 dividend actually paid (D0), same r / g2, pre-tax.
    d0_hkd = inp["dps_fy25"] / fx
    ddm = d0_hkd * (1 + inp["g2_m"]) / (r - inp["g2_m"])
    g_div_px = (inp["price"] * r - d0_hkd) / (inp["price"] + d0_hkd)
    print(f"DDM 对照 (税前): D0 {d0_hkd:.4f} HKD × (1+g2) ÷ (r−g2) = {ddm:.2f}; 现价 {inp['price']} 隐含股息增长 {g_div_px:+.2%}; "
          f"M 上 FY26E 股息率 {eps['m'] * payout(inp['g2_m'], roe['m']) / fx / M:.1%}")
    net_cash_ps = inp["net_cash"] * YI / inp["shares"] / fx
    print(f"地板 (只披露): BPS {inp['bps']} CNY = {inp['bps'] / fx:.2f} HKD (> H); 锚点隐含 PB "
          f"{L * fx / inp['bps']:.2f}/{M * fx / inp['bps']:.2f}/{H * fx / inp['bps']:.2f}, 现价 PB {inp['price'] * fx / inp['bps']:.2f}; "
          f"净现金 {inp['net_cash']:.0f}亿 CNY = {net_cash_ps:.2f} HKD/股 ({net_cash_ps / inp['price']:.0%} 市值) 不加 "
          f"(加回 → {L + net_cash_ps:.2f}/{M + net_cash_ps:.2f}/{H + net_cash_ps:.2f}); 净 PP&E FY25 {inp['nppe_fy25']:.0f}亿 (A16)")
    marker = "⚠" if gap > SEGMENT_GAP_WARN else " "
    print(f"{marker} 分部缺口 {gap:.0%} (分部合计 {inp['seg_total_h1'] / 1e8:.0f}亿 vs "
          f"营收 {inp['rev_h1'] / 1e8:.0f}亿) — 两腿仅在校验层, 未入分子路径 (A5)")
    print(f"  两腿权重(仅校验): 铁路系 {inp['w_rail']:.4f} / 新产业 {inp['w_new']:.4f}; "
          f"M 档 EPS 分解 {eps['m'] * inp['w_rail']:.3f} / {eps['m'] * inp['w_new']:.3f}")
    print(f"  动车组招标 {inp['emu_2026']:.0f} 列 vs 上年 {inp['emu_2025']:.0f} 列 "
          f"({inp['emu_2026'] / inp['emu_2025'] - 1:+.1%})")
    d = decompose((L, M, H), (pe["l"], pe["m"], pe["h"]))
    print(f"分子比 L/M={d['num_lm']:.3f} H/M={d['num_hm']:.3f} | 倍数比 L/M={d['pe_lm']:.3f} H/M={d['pe_hm']:.3f}")
    print(f"flat-multiple @PE_M={pe['m']:.2f}: L={flat[0]:.2f} M={flat[1]:.2f} H={flat[2]:.2f} — 带宽 {flat_width:.1%}")
    own = tuple(eps[t] * inp[f"pe_hk_ownyear_{t}"] / fx for t in TIERS)
    print(f"交叉尺 own-year 分位 {inp['pe_hk_ownyear_l']}/{inp['pe_hk_ownyear_m']}/{inp['pe_hk_ownyear_h']} (A2): "
          f"{own[0]:.2f}/{own[1]:.2f}/{own[2]:.2f}, 现价 zone={zone_of(inp['price'], *own)}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.1%}")
    print(f"price(H)={inp['price']} zone={zone} P/M={inp['price'] / M:.2f}"
          + (f" | 溢价 (P-H)/H = {(inp['price'] - H) / H:+.1%}" if inp["price"] > H else ""))
    print(f"候选带 (A9, UBS FY2027 单家 {inp['eps_fy27_ubs']} 换入 M′): L′/M′/H′={cand[0]:.2f}/{cand[1]:.2f}/{cand[2]:.2f}  "
          f"候选 zone={zone_of(inp['price'], *cand)}")
    for g, b in evid.items():
        print(f"证据区间 g2={g:+.2%}: {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    for dg in (-0.01, 0.01):
        b = band_at(inp["g2_m"] + dg, eps, roe, r, k, fx)
        print(f"敏感性 g2 {dg:+.0%} ({inp['g2_m'] + dg:+.2%}): {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    for kk in (0.93, 1.07):
        eps_k = {t: eps[t] * kk for t in TIERS}
        roe_k = {t: eps_k[t] * inp["shares"] / (inp["equity"] * YI) for t in TIERS}
        b = band_at(inp["g2_m"], eps_k, roe_k, r, k, fx)
        print(f"敏感性 eps ×{kk}: {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    notax = band_at(inp["g2_m"], eps, roe, r, 1.0, fx)
    print(f"敏感性 红利税折扣撤销 (k=1): {'/'.join(f'{x:.2f}' for x in notax)} zone={zone_of(inp['price'], *notax)}")
    old = tuple(eps[t] / (r + 0.0367) / fx for t in TIERS)
    print(f"对照 同业负分支 g2 −3.67% flat 7.32x (税前): {'/'.join(f'{x:.2f}' for x in old)} zone={zone_of(inp['price'], *old)} (分支错误的坐标)")
    print(f"A股对照(CNY, 篮 {baskets['r_perp_a']} r={r_a:.1%} 跨市场固定, k=1): PE {pe_a['l']:.2f}/{pe_a['m']:.2f}/{pe_a['h']:.2f} → "
          f"L={la:.2f} M={ma:.2f} H={ha:.2f} A={(la + ma) / 2:.2f} B={(ma + ha) / 2:.2f} "
          f"| price_a={inp['price_a']} zone_a={zone_of(inp['price_a'], la, ma, ha)} P/M={inp['price_a'] / ma:.2f}")
    print(f"  CNY 段披露 (r {r_ccy:.1%} = r_perp_a − cny_rf_gap, 待 _AXIS.rates 建成后复核): PE {pe_ccy['l']:.2f}/{pe_ccy['m']:.2f}/{pe_ccy['h']:.2f} → "
          f"{lc:.2f}/{mc:.2f}/{hc:.2f} A={(lc + mc) / 2:.2f} B={(mc + hc) / 2:.2f} zone={zone_of(inp['price_a'], lc, mc, hc)} P/M={inp['price_a'] / mc:.2f}")
    print(f"H/A = {inp['price'] * fx / inp['price_a']:.3f}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
