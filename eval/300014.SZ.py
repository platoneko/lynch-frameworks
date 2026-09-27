#!/usr/bin/env python3
"""300014.SZ (EVE Energy) valuation eval.

frameworks/300014.SZ.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading — the digest and the app zone on live quotes.  The
one own-price row left, `px_low_2026`, is a dated historical coordinate (the
2026 low close) and never reaches the anchor path.

formula_id: eve_core_excl_smoore_perpetual_g_plus_listed_stake_v1

Main ruler: an asymmetric SOTP.

  A leg   core net profit (扣非 minus Smoore equity income, so the stake is not
          counted twice) x Gordon:  PE = min(1, 1 - g/ROE) / (r - g), r from the
          leg's basket (篮 4 龙头制造, 10%; B17).  L reads FY2025 realised core
          profit on the 2026-06-30 core equity; M/H read the FY2027E consensus
          mean / top (裁决顺序 ②) on core equity rolled to end-2027
          (`equity_core_fwd`), so ROE and numerator sit on the same date.
  B leg   30.25% of Smoore International (6969.HK) at market, discounted:
          L = EVE's own carrying value, M = 70% of market, H = 90%
  anchor  (V_A + V_B) * 1e8 / shares          <- the base band
  V_opt   power-cell unit gross margin converging on CATL's — NOT in the base

The other half of the turnaround does not fit in H.  H's ROE of 15.87% buys
"the most optimistic FY2027E house is right" — the unit economics do not
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
cells, and B6 never split that gap into 口径 vs pricing power.

Why the B leg gets a price and not a growth rate: Smoore is listed, so its value
is quoted every day.  Keda's Lanke Lithium (600499.SH) had to be folded into a
leg's g because it publishes no standalone accounts and its value could only be
reverse-engineered from Keda's own investment income — the same data twice.
Smoore has no such problem, and its driver (vaping / HNB regulation) has nothing
to do with batteries, so blending it into a composite g would be wrong.

Why ROE carries this framework: EVE's group net income sat at 40.50 / 40.76 /
41.34亿 for three straight years while revenue grew 26%, and ROE slid 14.52% ->
10.35% — landing on the basket r.  At ROE = r the Gordon multiple is 1/r for
ANY g, which is the whole explanation for those three years of flat valuation.
So `turnaround` here is computable and does not mean "returning from a loss"
(EVE never lost money); it means ROE climbing back above r.  The three tiers'
core ROE — 6.43% / 13.68% / 15.87% — straddle r deliberately.

The realised trailing PE bands (own-year low 15.0x, 5y monthly TTM low 16.26x)
are printed on a shrunken trailing EPS and the numerator is FY2027E; the two
are not on the same basis, so 裁决顺序 ③ does not apply (B16).  They are
disclosed, not enforced.  r is the basket value and MUST NOT be tuned per
ticker; re-basketing goes through the ③ 出带 process with a paper trail.

Run:  python3 frameworks/eval/300014.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import check_g_cap, check_r, g_cap, payout, perpetual_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.tiers import flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "300014.SZ.md"
FORMULA_ID = "eve_core_excl_smoore_perpetual_g_plus_listed_stake_v1"

TIERS = ("l", "m", "h")

FORMULA_FIELDS = frozenset({
    "shares", "equity_core", "equity_core_fwd", "r_perp",
    "nic_l", "nic_m", "nic_h",
    "g2_l", "g2_m", "g2_h",
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
    "px_low_2026", "bps",
    "pe_own_hi", "pe_own_lo", "pe_own_ttm_lo", "pe_own_ttm_hi", "eps_fy2027e",
    "ni_group_fy2025", "ni_excl_fy2025",
    "smoore_equity_fy2025", "smoore_equity_h1", "eps_fy2026e",
    "tp_street", "net_debt", "ocf_h1",
    "opt_outstanding", "opt_strike", "sbc_h1",
    "px_low_2025", "px_low_2024",
    "ugm_eve_power_h1",
})


def core_equity(inp: dict[str, float], tag: str) -> float:
    """L has no incremental retention (turnaround unrealised) so it reads the
    2026-06-30 book; M/H read the book rolled to end-2027 (B3)."""
    return inp["equity_core"] if tag == "l" else inp["equity_core_fwd"]


def core_roe(inp: dict[str, float], tag: str) -> float:
    return inp[f"nic_{tag}"] / core_equity(inp, tag)


def multiple(inp: dict[str, float], tag: str) -> float:
    return perpetual_pe(inp[f"g2_{tag}"], core_roe(inp, tag), inp["r_perp"])


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
    multiplying the delta by PE_H: the extra profit lifts core ROE from 15.87%
    to 20.93%, and at the basket r that lifts the multiple too.  Pricing the
    delta at the old multiple would understate the option by about a fifth.
    """
    gap = inp["ugm_catl_power"] - inp["ugm_eve_power"]      # CNY/kWh
    delta_gp = inp["vol_power_fy2025"] * gap / 100.0        # GWh x CNY/kWh -> 亿
    delta_ni = delta_gp * (1.0 - inp["tax_conv"])
    nic_conv = inp["nic_h"] + delta_ni
    roe_conv = nic_conv / core_equity(inp, "h")
    pe_conv = perpetual_pe(inp["g2_h"], roe_conv, inp["r_perp"])
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
    baskets = parse_baskets(md)

    # --- Step 1: ladders and the basket -------------------------------------
    errors += ladder("nic", inp["nic_l"], inp["nic_m"], inp["nic_h"])
    errors += ladder("g2", inp["g2_l"], inp["g2_m"], inp["g2_h"])
    if "r_perp" not in baskets:
        errors.append("r_perp: source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    for k in ("equity_core", "equity_core_fwd"):
        if inp[k] <= 0:
            errors.append(f"{k}={inp[k]} must be positive")
    if errors:
        return report(errors, "FAIL (inputs/ladders)")

    roe = {t: core_roe(inp, t) for t in TIERS}

    # --- Step 2: convergence and retention (B5) -----------------------------
    for t in TIERS:
        if roe[t] <= 0:
            errors.append(f"ROE_core_{t}={roe[t]:.4f} must be positive")
        g = inp[f"g2_{t}"]
        errors += check_g_cap(g, r, f"g2_{t}")  # cap = min(6%, r - 4%)
        if r - g <= 0:
            errors.append(f"g2_{t}={g:.4f} >= r={r} — perpetuity diverges")
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

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # --- report -------------------------------------------------------------
    cap = g_cap(r)
    print(f"formula_id={FORMULA_ID}  (r={r:.0%} 篮 {baskets['r_perp']}, 零增长={1 / r:.1f}x, g2 cap={cap:.1%})")
    print(f"思摩尔 30.25%：账面 {inp['smoore_book']:.2f} 亿 / 市值口径 "
          f"{inp['smoore_mv']:.2f} 亿（{inp['smoore_mv'] * 1e8 / inp['shares']:.2f} 元/股）")
    print(f"{'档':<3}{'核心扣非':>10}{'权益':>9}{'ROEcore':>10}{'g':>7}{'派息':>8}{'PE':>8}"
          f"{'V_A':>9}{'V_B':>9}{'合计':>10}{'锚点CNY':>10}")
    for t in TIERS:
        g = inp[f"g2_{t}"]
        print(f"{t.upper():<3}{inp[f'nic_{t}']:10.2f}{core_equity(inp, t):9.2f}{roe[t]:10.2%}{g:7.1%}"
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
    print(f"倍数从 L 到 H 走 {pe['h'] / pe['l'] - 1:+.1%}，分子走 "
          f"{inp['nic_h'] / inp['nic_l'] - 1:+.1%} —— 价带主要由分子决定")

    # 表3 · zone+V（B15 / A2e-7d）——不参与任何判定
    a3, b3 = cut_points(*band3)
    print(f"表3 V_opt={opt['v_opt']:.2f}（V_opt/M={opt['v_opt'] / M:.1%}）"
          f"  p_k={P_K[0]:.2f}/{P_K[1]:.2f}/{P_K[2]:.2f}"
          f"  → {band3[0]:.2f} / {band3[1]:.2f} / {band3[2]:.2f}"
          f"  A'={a3:.2f} B'={b3:.2f}")
    print(f"  推导：动力 {inp['vol_power_fy2025']:.2f} GWh × 单位毛利差 "
          f"{opt['gap']:.1f} 元/kWh（宁德 {inp['ugm_catl_power']:.1f} − 亿纬 "
          f"{inp['ugm_eve_power']:.1f}）= {opt['delta_gp']:.2f} 亿，税后 "
          f"{opt['delta_ni']:.2f} 亿")
    print(f"      → nic_h {inp['nic_h']:.2f} + {opt['delta_ni']:.2f} = "
          f"{opt['nic_conv']:.2f} 亿，ROEcore {opt['roe_conv']:.2%}、PE "
          f"{opt['pe_conv']:.2f} → 兑现后锚点 {opt['anchor_conv']:.2f}"
          f"（含 ROE 抬升带来的倍数重估）")
    print(f"  p_M={P_K[1]:.2f} 的锚是**反向**的：2026H1 动力单位毛利 "
          f"{inp['ugm_eve_power_h1']:.2f} vs FY2025 {inp['ugm_eve_power']:.1f} 元/kWh"
          f"（{inp['ugm_eve_power_h1'] / inp['ugm_eve_power'] - 1:+.1%}）"
          f" —— 收敛证据当前为负（B15）")
    print(f"  储能腿未计入（B6 无口径拆分比例，A2e-7c-1）")

    # 校验步骤 12 (B16): 裁决顺序 ③ 状态.  Printed, not enforced — the realised
    # trailing bands sit on a shrunken trailing EPS while the numerator is
    # FY2027E; they are not on the same basis, so ③ does not apply.
    at_cap = {t: perpetual_pe(cap, roe[t], r) for t in ("m", "h")}
    fwd_low = inp["px_low_2026"] / inp["eps_fy2027e"]
    print(f"  裁决顺序 ③ (B16): trailing 带 own-year [{inp['pe_own_lo']:g}, {inp['pe_own_hi']:g}] / "
          f"5y 月频 TTM [{inp['pe_own_ttm_lo']}, {inp['pe_own_ttm_hi']}] 与 FY2027E 分子不同基 → 只披露，不构成 ③；"
          f"g=cap {cap:.0%} 时 PE M {at_cap['m']:.2f} / H {at_cap['h']:.2f}")
    print(f"      同基坐标：2026 年内最低收盘 {inp['px_low_2026']:.2f} ÷ FY2027E {inp['eps_fy2027e']:.3f} = {fwd_low:.2f}×（序列最新月份，带下沿退化，不反推）；"
          f"整公司 M {M / inp['eps_fy2027e']:.2f}× / H {H / inp['eps_fy2027e']:.2f}× ÷ FY2027E")
    print(f"  卖方一致 TP {inp['tp_street']:.2f} 高于 H {inp['tp_street'] / H - 1:+.1%}"
          f"、高于表3 H 行 {inp['tp_street'] / band3[2] - 1:+.1%}（B11）")
    print(f"  稀释开关（B13，不进锚点）：激励 {inp['opt_outstanding'] / inp['shares']:.3%}"
          f"，行权价 {inp['opt_strike']:.2f} > H {H:.2f} "
          f"({inp['opt_strike'] / H - 1:+.1%}) → 三档内全部价外 ✓")
    print(f"  SBC H1 {inp['sbc_h1']:.2f} 亿已含在扣非分子内，不重复扣（B14）；"
          f"经营现金流 {inp['ocf_h1']:+.2f} 亿、净债务 {inp['net_debt']:.2f} 亿（B8）")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
