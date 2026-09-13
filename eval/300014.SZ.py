#!/usr/bin/env python3
"""300014.SZ (EVE Energy) valuation eval.

frameworks/300014.SZ.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: eve_core_excl_smoore_perpetual_g_plus_listed_stake_v1

Main ruler: an asymmetric SOTP.

  A leg   core net profit (扣非 minus Smoore equity income, so the stake is not
          counted twice) x Gordon:  PE = min(1, 1 - g/ROE) / (r - g),  r = 10%
  B leg   30.25% of Smoore International (6969.HK) at market, discounted:
          L = EVE's own carrying value, M = 70% of market, H = 90%
  anchor  (V_A + V_B) * 1e8 / shares          <- the base band; zone reads this
  V_opt   power-cell unit gross margin converging on CATL's — NOT in the base

The other half of the turnaround does not fit in H.  H's ROE of 13.52% buys
"FY2025's seasonality repeats in 2026 plus volume" — the unit economics do not
improve by a single fen.  Whether EVE's power cells ever earn what CATL's earn
is not computable today (B6: the gap is pricing power and cost structure, and
no second-tier cell maker has closed it), but its CEILING is measured and
sitting right there: CATL booked 139.5 CNY/kWh of gross profit per power cell
in FY2025 against EVE's 80.0, on products one comparison table away from
identical (ASP differs by 12%).  So it goes to V_opt per A2e-7b, priced tier by
tier in 表3, and never touches a zone boundary.

  V_opt = anchor(nic_h + after-tax convergence delta) - H   (same Gordon ruler,
          so it carries the multiple re-rating that the higher ROE earns)

p_M = 0.10 is anchored, and the anchor points the wrong way: 2026H1 power unit
gross margin came in at 78.24 CNY/kWh, BELOW FY2025's 80.0.  Storage is left
out entirely — CATL sells cabinets and system integration there, EVE sells
cells, and B6 never split that gap into 口径 vs pricing power.  Folding it in
anyway would take V_opt to 58.82 (204% of M); see the sensitivity block.

Why the B leg gets a price and not a growth rate: Smoore is listed, so its value
is quoted every day.  Keda's Lanke Lithium (600499.SH) had to be folded into a
leg's g because it publishes no standalone accounts and its value could only be
reverse-engineered from Keda's own investment income — the same data twice.
Smoore has no such problem, and its driver (vaping / HNB regulation) has nothing
to do with batteries, so blending it into a composite g would be wrong.

Why ROE carries this framework: EVE's group net income sat at 40.50 / 40.76 /
41.34亿 for three straight years while revenue grew 26%, and ROE slid 14.52% ->
10.35% — landing on the repo's r.  At ROE = r the Gordon multiple is 1/r for
ANY g, which is the whole explanation for those three years of flat valuation.
So `turnaround` here is computable and does not mean "returning from a loss"
(EVE never lost money); it means ROE climbing back above r.  The three tiers'
core ROE — 6.43% / 11.57% / 13.52% — straddle r deliberately.

The consequence, stated rather than smoothed: the generated multiples
(10.00 / 10.34 / 11.40) all sit BELOW this stock's own-year measured low of
15.0x.  That is not a fence breach — the fence guards the top — it is a real
disagreement with the market, and it comes entirely from applying a repo-wide
r = 10% to a business earning 11-14% on equity.  r MUST NOT be tuned per
ticker (AGENTS.md); changing it is a repo-level correction.

Run:  python3 eval/300014.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.gordon import implied_g, payout, perpetual_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.tiers import flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "300014.SZ.md"
FORMULA_ID = "eve_core_excl_smoore_perpetual_g_plus_listed_stake_v1"

TIERS = ("l", "m", "h")

FORMULA_FIELDS = frozenset({
    "shares", "equity_core", "r_perp",
    "nic_l", "nic_m", "nic_h",
    "g_l", "g_m", "g_h",
    "smoore_book", "smoore_mv", "disc_m", "disc_h",
})

# V_opt's own inputs (B15).  Disjoint from FORMULA_FIELDS on purpose: the
# convergence option MUST NOT reach the base band or any zone boundary.
VOPT_FIELDS = frozenset({
    "vol_power_fy2025", "ugm_catl_power", "ugm_eve_power", "tax_conv",
})

# 表3 only — never Inputs, never the base band (A2e-7a).
P_K = (0.0, 0.10, 1.0)

REQUIRED = sorted(FORMULA_FIELDS | VOPT_FIELDS | {
    "price", "bps",
    "pe_own_hi", "pe_own_lo",
    "ni_group_fy2025", "ni_excl_fy2025",
    "smoore_equity_fy2025", "smoore_equity_h1", "eps_fy2026e",
    "tp_street", "net_debt", "ocf_h1",
    "opt_outstanding", "opt_strike", "sbc_h1",
    "px_low_2025", "px_low_2024",
    "ugm_eve_power_h1",
})


def core_roe(inp: dict[str, float], tag: str) -> float:
    return inp[f"nic_{tag}"] / inp["equity_core"]


def multiple(inp: dict[str, float], tag: str) -> float:
    return perpetual_pe(inp[f"g_{tag}"], core_roe(inp, tag), inp["r_perp"])


def leg_a(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    pe = flat_pe if flat_pe is not None else multiple(inp, tag)
    return inp[f"nic_{tag}"] * pe


def leg_b(inp: dict[str, float], tag: str) -> float:
    """L reads EVE's own carrying value; M/H read 6969.HK at a discount."""
    if tag == "l":
        return inp["smoore_book"]
    return inp["smoore_mv"] * inp[f"disc_{tag}"]


def anchor(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    return (leg_a(inp, tag, flat_pe) + leg_b(inp, tag)) * 1e8 / inp["shares"]


def convergence_option(inp: dict[str, float], base_h: float) -> dict[str, float]:
    """V_opt — EVE's power cells earning what CATL's already earn (B15).

    Runs the converged numerator back through the SAME Gordon ruler rather than
    multiplying the delta by PE_H: the extra profit lifts core ROE from 13.52%
    to 19.36%, and at r = 10% that lifts the multiple too.  Pricing the delta at
    the old multiple would understate the option by about a quarter.
    """
    gap = inp["ugm_catl_power"] - inp["ugm_eve_power"]      # CNY/kWh
    delta_gp = inp["vol_power_fy2025"] * gap / 100.0        # GWh x CNY/kWh -> 亿
    delta_ni = delta_gp * (1.0 - inp["tax_conv"])
    nic_conv = inp["nic_h"] + delta_ni
    roe_conv = nic_conv / inp["equity_core"]
    pe_conv = perpetual_pe(inp["g_h"], roe_conv, inp["r_perp"])
    anchor_conv = (nic_conv * pe_conv + leg_b(inp, "h")) * 1e8 / inp["shares"]
    return {
        "gap": gap, "delta_gp": delta_gp, "delta_ni": delta_ni,
        "nic_conv": nic_conv, "roe_conv": roe_conv, "pe_conv": pe_conv,
        "anchor_conv": anchor_conv, "v_opt": anchor_conv - base_h,
    }


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r = inp["r_perp"]

    # --- Step 1: ladders ----------------------------------------------------
    errors += ladder("nic", inp["nic_l"], inp["nic_m"], inp["nic_h"])
    errors += ladder("g", inp["g_l"], inp["g_m"], inp["g_h"])
    if inp["equity_core"] <= 0:
        errors.append(f"equity_core={inp['equity_core']} must be positive")
    if errors:
        return report(errors, "FAIL (inputs/ladders)")

    roe = {t: core_roe(inp, t) for t in TIERS}

    # --- Step 2: convergence and retention (B5) -----------------------------
    for t in TIERS:
        if roe[t] <= 0:
            errors.append(f"ROE_core_{t}={roe[t]:.4f} must be positive")
        g = inp[f"g_{t}"]
        if r - g <= 0:
            errors.append(f"g_{t}={g:.4f} >= r={r} — perpetuity diverges")
        pay = payout(g, roe[t])
        if not 0.0 < pay <= 1.0 + 1e-12:
            errors.append(f"payout_{t}={pay:.3f} outside (0, 1]")
        if g <= 0 and abs(pay - 1.0) > 1e-12:
            errors.append(f"payout_{t}={pay:.3f} but g={g:.2%} <= 0 — cap not binding")
    if errors:
        return report(errors, "FAIL (convergence/payout)")

    # --- Step 3: the Smoore leg (B4) ---------------------------------------
    vb = {t: leg_b(inp, t) for t in TIERS}
    errors += ladder("V_B", vb["l"], vb["m"], vb["h"])
    if not 0.0 < inp["disc_m"] < inp["disc_h"] <= 1.0:
        errors.append(
            f"discounts must satisfy 0 < disc_m={inp['disc_m']} < "
            f"disc_h={inp['disc_h']} <= 1"
        )
    if inp["smoore_book"] >= inp["smoore_mv"]:
        errors.append(
            f"smoore_book={inp['smoore_book']} >= smoore_mv={inp['smoore_mv']} — "
            f"the stake trades at or below EVE's carrying value; the B leg's "
            f"tier construction (book as the floor) no longer holds"
        )

    pe = {t: multiple(inp, t) for t in TIERS}
    if pe["h"] > inp["pe_own_hi"] + 1e-9:
        errors.append(
            f"PE_H={pe['h']:.2f} above own-year measured high {inp['pe_own_hi']}"
        )

    # --- Step 4: the non-formula fields really are non-formula -------------
    lean = {k: v for k, v in inp.items() if k in FORMULA_FIELDS}
    if any(abs(anchor(lean, t) - anchor(inp, t)) > 1e-9 for t in TIERS):
        errors.append("anchor path touches a non-formula field")
    if errors:
        return report(errors, "FAIL (guards)")

    # --- Step 5: anchors ----------------------------------------------------
    L, M, H = (anchor(inp, t) for t in TIERS)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    nic3 = (inp["nic_l"], inp["nic_m"], inp["nic_h"])
    flat_errs, flat_va = flat_multiple_ladder(nic3, pe["m"])
    errors += flat_errs
    errors += ladder("flat V_A", *flat_va)
    flat_anchor = tuple(anchor(inp, t, flat_pe=pe["m"]) for t in TIERS)
    errors += ladder("flat anchor", *flat_anchor)

    # B13: the incentive grant is out of the money across all three tiers.
    if inp["opt_strike"] <= H:
        errors.append(
            f"opt_strike={inp['opt_strike']} <= H={H:.2f} — the 6.902% dilution "
            f"switch is inside the band; `shares` MUST be reset (B13)"
        )

    # --- Step 6: V_opt, held outside the base band (A2e-7a) -----------------
    if FORMULA_FIELDS & VOPT_FIELDS:
        errors.append("V_opt inputs leaked into the base formula field set")
    leaked_p = sorted(k for k in inp if k.startswith("p_"))
    if leaked_p:
        errors.append(f"probability fields present in §3 Inputs: {leaked_p} (A2e-7a)")

    opt = convergence_option(inp, H)
    if opt["v_opt"] < 0:
        errors.append(f"V_opt={opt['v_opt']:.2f} must be >= 0")
    band3 = tuple(base + P_K[i] * opt["v_opt"] for i, base in enumerate((L, M, H)))
    if abs(band3[0] - L) > 1e-9:
        errors.append(
            f"p leaked into the base: 表3 L row {band3[0]:.4f} != base L {L:.4f}"
        )

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report -------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}  (r={r:.0%}, 零增长={1 / r:.1f}x)")
    print(f"思摩尔 30.25%：账面 {inp['smoore_book']:.2f} 亿 / 市值口径 "
          f"{inp['smoore_mv']:.2f} 亿（{inp['smoore_mv'] * 1e8 / inp['shares']:.2f} 元/股，"
          f"占现价 {inp['smoore_mv'] * 1e8 / inp['shares'] / inp['price']:.1%}）")
    print(f"{'档':<3}{'核心扣非':>10}{'ROEcore':>10}{'g':>7}{'派息':>8}{'PE':>8}"
          f"{'V_A':>9}{'V_B':>9}{'合计':>10}{'锚点CNY':>10}")
    for t in TIERS:
        g = inp[f"g_{t}"]
        print(f"{t.upper():<3}{inp[f'nic_{t}']:10.2f}{roe[t]:10.2%}{g:7.1%}"
              f"{payout(g, roe[t]):8.3f}{pe[t]:8.2f}{leg_a(inp, t):9.2f}"
              f"{vb[t]:9.2f}{leg_a(inp, t) + vb[t]:10.2f}{anchor(inp, t):10.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.1%}")
    print(f"分子比 L/M={inp['nic_l'] / inp['nic_m']:.3f} "
          f"H/M={inp['nic_h'] / inp['nic_m']:.3f} | "
          f"倍数比 L/M={pe['l'] / pe['m']:.3f} H/M={pe['h'] / pe['m']:.3f}"
          f"  — 两端同质（都由分子主导）")
    print(f"flat-multiple @PE_M={pe['m']:.2f}: V_A {flat_va[0]:.2f}/{flat_va[1]:.2f}/"
          f"{flat_va[2]:.2f} → 锚点 {flat_anchor[0]:.2f}/{flat_anchor[1]:.2f}/"
          f"{flat_anchor[2]:.2f} — 阶梯成立（A2e-2c）")
    print(f"ROE 横跨 r：{roe['l']:.2%} / {roe['m']:.2%} / {roe['h']:.2%}，r={r:.0%}"
          f" —— L 档 ROE 低于 r，增长毁灭价值，倍数就是 {1 / r:.0f}×")
    print(f"倍数从 L 到 H 只走 {pe['h'] / pe['l'] - 1:+.1%}，分子走 "
          f"{inp['nic_h'] / inp['nic_l'] - 1:+.1%} —— 价带几乎全由分子决定")

    print(f"price={inp['price']} zone={zone}（底牌）")

    # 表3 · zone+V（B15 / A2e-7d）——不参与任何判定
    a3, b3 = cut_points(*band3)
    print(f"表3 V_opt={opt['v_opt']:.2f}（V_opt/M={opt['v_opt'] / M:.1%}）"
          f"  p_k={P_K[0]:.2f}/{P_K[1]:.2f}/{P_K[2]:.2f}"
          f"  → {band3[0]:.2f} / {band3[1]:.2f} / {band3[2]:.2f}"
          f"  A'={a3:.2f} B'={b3:.2f}  修正带 zone={zone_of(inp['price'], *band3)}")
    print(f"  推导：动力 {inp['vol_power_fy2025']:.2f} GWh × 单位毛利差 "
          f"{opt['gap']:.1f} 元/kWh（宁德 {inp['ugm_catl_power']:.1f} − 亿纬 "
          f"{inp['ugm_eve_power']:.1f}）= {opt['delta_gp']:.2f} 亿，税后 "
          f"{opt['delta_ni']:.2f} 亿")
    print(f"      → nic_h {inp['nic_h']:.2f} + {opt['delta_ni']:.2f} = "
          f"{opt['nic_conv']:.2f} 亿，ROEcore {opt['roe_conv']:.2%}、PE "
          f"{opt['pe_conv']:.2f} → 兑现后锚点 {opt['anchor_conv']:.2f}"
          f"（含 ROE 抬升带来的倍数重估）")
    if inp["price"] > H:
        print(f"      市价隐含 p = ({inp['price']:.2f} − {H:.2f}) / "
              f"{opt['v_opt']:.2f} = {(inp['price'] - H) / opt['v_opt']:.2f}"
              f" —— 与「市场用更低的 r」互斥，MUST NOT 叠加")
    print(f"  p_M={P_K[1]:.2f} 的锚是**反向**的：2026H1 动力单位毛利 "
          f"{inp['ugm_eve_power_h1']:.2f} vs FY2025 {inp['ugm_eve_power']:.1f} 元/kWh"
          f"（{inp['ugm_eve_power_h1'] / inp['ugm_eve_power'] - 1:+.1%}）"
          f" —— 收敛证据当前为负（B15）")
    print(f"  储能腿未计入（B6 无口径拆分比例，A2e-7c-1）：若计入 V_opt 会到 "
          f"58.82、占 M 的 204%")

    # 显式歧义（AGENTS.md「ROE≈r」条）：两个读数 MUST 都报
    core_mv = inp["price"] * inp["shares"] / 1e8 - vb["m"]
    pe_imp = core_mv / inp["nic_m"]
    gi, ok = implied_g(pe_imp, roe["m"], r)
    r_alt = payout(inp["g_m"], roe["m"]) / pe_imp + inp["g_m"]
    print(f"  现价核心业务隐含 PE={pe_imp:.2f}×（市值 "
          f"{inp['price'] * inp['shares'] / 1e8:.1f} 亿 − 思摩尔 M 腿 {vb['m']:.1f} 亿）")
    print(f"  ⚠ 显式歧义，两个读数等价，MUST 都报：")
    print(f"      读数一 固定 r={r:.0%}      → g={gi:+.2%}")
    print(f"      读数二 固定 g={inp['g_m']:.0%}       → r={r_alt:+.2%}")
    print(f"      well_conditioned={ok}；|ROE−r|={abs(roe['m'] - r):.2%} (<3pp)、"
          f"r−g={r - gi:.2%} (<2pp) —— 双重病态，只作市价参照，不进任何一档")
    print(f"  三档 PE {pe['l']:.2f}/{pe['m']:.2f}/{pe['h']:.2f} **全部低于** "
          f"own-year 实测下沿 {inp['pe_own_lo']:g}× —— 与市场的实质分歧（B10）")
    print(f"  卖方一致 TP {inp['tp_street']:.2f} 高于 H {inp['tp_street'] / H - 1:+.1%}"
          f"，落 stretched（B11）")
    print(f"  整公司 FY2026E PE（归母口径）="
          f"{inp['price'] / inp['eps_fy2026e']:.2f}×")
    print(f"  稀释开关（B13，不进锚点）：激励 {inp['opt_outstanding'] / inp['shares']:.3%}"
          f"，行权价 {inp['opt_strike']:.2f} > H {H:.2f} "
          f"({inp['opt_strike'] / H - 1:+.1%}) 且 > 现价 "
          f"({inp['opt_strike'] / inp['price'] - 1:+.1%}) → 三档内全部价外 ✓")
    print(f"  SBC H1 {inp['sbc_h1']:.2f} 亿已含在扣非分子内，不重复扣（B14）；"
          f"经营现金流 {inp['ocf_h1']:+.2f} 亿、净债务 {inp['net_debt']:.2f} 亿（B8）")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
