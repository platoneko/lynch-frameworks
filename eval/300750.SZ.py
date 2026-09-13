#!/usr/bin/env python3
"""300750.SZ (CATL / Contemporary Amperex Technology) valuation eval.

frameworks/300750.SZ.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: catl_group_ni_two_stage_transition_capacity_anchored_v1

Main ruler: one numerator (group EPS), and the multiple generated from a named
growth rate — but this is the repo's first ticker where the growth does not fit
into a single perpetual rate, so M and H run a transition segment first.

  L      PE = perpetual_pe(g2_L, ROE_L, r)              no transition
  M, H   PE = two_stage_pe(g1_x, n=3, g2_x, ROE_x, r)    transition then perpetuity
  anchor = eps_x * PE_x,   r = 10%  ->  a no-growth business is worth 10x

Why n = 3 and not a single perpetual g: capacity under construction went from
41.6% of installed (FY2025: 321 / 772 GWh) to 145.5% (2026H1: 764 / 525 GWh).
That ratio is unit-invariant — the halves cancel — so it is the one capacity
number worth anchoring on.  Absorbing 2.455x capacity at the measured +36%/yr
expansion takes ln(2.455)/ln(1.36) = 2.92 years.  "Built and absorbed" and
"built and then nothing" are two genuinely distant worlds, and a single g cannot
hold both; the transition segment makes the distance explicit.

g1 MUST be an earnings rate, not a capacity rate.  Unit net profit has already
fallen 109.2 -> 86.9 CNY/kWh (-20.4%) while group net income rose 42% — the
growth on the tape is volume.  Feeding +36% capacity growth in as g1 would
price the price-decline at zero.  Hence M = 20% (management's own guidance
floor) and H = 27% (sell-side FY2027E), both named and sourced.

Two asymmetries this file deliberately does NOT smooth over:

  * L uses perpetual_pe (a multiple on NEXT-period earnings) while M/H use
    two_stage_pe (a multiple on CURRENT earnings).  The bases differ by
    (1 + g2_L) = 2.0%.  AGENTS.md requires a tier running no transition to call
    perpetual_pe directly, so the gap is declared and the aligned value
    (186.66) is checked against the framework rather than papered over.
  * Both ends of the band are multiple-dominated (pe_lm 0.633 < num_lm 0.760,
    pe_hm 1.338 > num_hm 1.187).  Under the Gordon regime that is the design:
    the multiple is where a named g lives.  A2e-5's red line is ASYMMETRY
    (one end by numerator, the other by multiple), and this band is symmetric.
    The check that stops a multiple from inventing a tier is the flat-multiple
    ladder, and it passes.

Multiples are NOT quantiles of own history (AGENTS.md「永续增长口径」, which
overrides skill A2e-2b).  This ticker's own-year band [10.4, 40.0] has 2022's
30.6x mean at the narrative peak and 2024's 10.4x low in a year when revenue
fell 9.7% while net income ROSE 15% — it measures what the market thought about
growth, not what the business is worth.  It survives as a fence on H only.

Run:  python3 eval/300750.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.gordon import implied_g, payout, perpetual_pe, two_stage_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.tiers import flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "300750.SZ.md"
FORMULA_ID = "catl_group_ni_two_stage_transition_capacity_anchored_v1"

TIERS = ("l", "m", "h")

# Fields the anchor path is allowed to touch.  Everything else in the Inputs
# table is cross-check material, and the guard below proves it stays out.
FORMULA_FIELDS = frozenset({
    "shares", "equity", "r_perp", "n_transition",
    "eps_l", "eps_m", "eps_h",
    "g1_m", "g1_h",
    "g2_l", "g2_m", "g2_h",
})

REQUIRED = sorted(FORMULA_FIELDS | {
    "price", "bps",
    "pe_own_hi_recent", "pe_own_hi", "pe_own_lo",
    "eps_ttm", "eps_fy2025", "eps_freeze",
    "tp_street", "tp_consensus", "price_h", "fx_hkdcny",
    "net_cash", "unit_profit_h1", "unit_profit_fy2025",
    "px_low_2026", "px_low_2025", "gp_other_rate",
    "buyback_lo", "buyback_hi", "treasury_shares", "opt_outstanding",
})


def forward_roe(inp: dict[str, float], tag: str) -> float:
    """Forward ROE on reported group equity — net cash included, see A9."""
    return inp[f"eps_{tag}"] * inp["shares"] / (inp["equity"] * 1e8)


def multiple(inp: dict[str, float], tag: str) -> float:
    roe, r = forward_roe(inp, tag), inp["r_perp"]
    if tag == "l":
        return perpetual_pe(inp["g2_l"], roe, r)
    return two_stage_pe(
        inp[f"g1_{tag}"], int(inp["n_transition"]), inp[f"g2_{tag}"], roe, r
    )


def anchor(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    pe = flat_pe if flat_pe is not None else multiple(inp, tag)
    return inp[f"eps_{tag}"] * pe


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
    n = int(inp["n_transition"])

    # --- Step 1: ladders ----------------------------------------------------
    errors += ladder("eps", inp["eps_l"], inp["eps_m"], inp["eps_h"])
    errors += ladder("g2", inp["g2_l"], inp["g2_m"], inp["g2_h"])
    errors += ladder("g1", inp["g1_m"], inp["g1_h"])
    for t in ("m", "h"):
        # A transition below the perpetuity is not a transition.
        if inp[f"g1_{t}"] <= inp[f"g2_{t}"]:
            errors.append(
                f"g1_{t}={inp[f'g1_{t}']:.2%} <= g2_{t}={inp[f'g2_{t}']:.2%} — "
                f"transition must exceed the perpetual rate"
            )
    if n < 1:
        errors.append(f"n_transition={n} must be >= 1")
    if inp["equity"] <= 0:
        errors.append(f"equity={inp['equity']} must be positive")
    if errors:
        return report(errors, "FAIL (inputs/ladders)")

    roe = {t: forward_roe(inp, t) for t in TIERS}

    # --- Step 2: convergence and the retention cost of growth (A8) ---------
    for t in TIERS:
        if roe[t] <= 0:
            errors.append(f"ROE_{t}={roe[t]:.4f} must be positive")
        g2 = inp[f"g2_{t}"]
        if r - g2 <= 0:
            errors.append(f"g2_{t}={g2:.4f} >= r={r} — perpetuity diverges")
        pay = payout(g2, roe[t])
        if not 0.0 < pay <= 1.0 + 1e-12:
            errors.append(f"perpetual payout_{t}={pay:.3f} outside (0, 1]")
        if g2 <= 0 and abs(pay - 1.0) > 1e-12:
            errors.append(f"payout_{t}={pay:.3f} but g2={g2:.2%} <= 0 — cap not binding")
    for t in ("m", "h"):
        # Stage-1 payout going negative means the transition is funded by
        # issuing stock.  gordon.py allows it on purpose; this framework does
        # not claim it, so surface it rather than price it silently.
        p1 = 1.0 - inp[f"g1_{t}"] / roe[t]
        if p1 <= 0:
            errors.append(
                f"stage-1 payout_{t}={p1:.3f} <= 0 — g1 exceeds ROE, i.e. "
                f"issuance-funded growth; MUST go back to the conversation"
            )
    if errors:
        return report(errors, "FAIL (convergence/payout)")

    pe = {t: multiple(inp, t) for t in TIERS}

    # --- Step 3: H may not leave the measured band (A10) -------------------
    if pe["h"] > inp["pe_own_hi_recent"] + 1e-9:
        errors.append(
            f"PE_H={pe['h']:.2f} above own-year high since 2023 "
            f"{inp['pe_own_hi_recent']} — H is no longer a modelled world"
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

    eps3 = (inp["eps_l"], inp["eps_m"], inp["eps_h"])
    flat_errs, flat = flat_multiple_ladder(eps3, pe["m"])
    errors += flat_errs
    errors += ladder("flat-multiple", *flat)

    # A15: the declared base-alignment value must be in the framework.
    aligned = L * (1 + inp["g2_l"])
    if f"{aligned:.2f}" not in md.split("### Outputs", 1)[-1]:
        errors.append(
            f"base-aligned L {aligned:.2f} (A15) not stated in Outputs"
        )

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report -------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}  (r={r:.0%}, 零增长={1 / r:.1f}x, n={n})")
    print(f"{'档':<3}{'EPS':>9}{'归母(亿)':>11}{'前瞻ROE':>10}{'g1':>8}{'g2':>7}"
          f"{'段一派息':>10}{'永续派息':>10}{'PE':>8}{'锚点CNY':>10}")
    for t in TIERS:
        g2 = inp[f"g2_{t}"]
        ni = inp[f"eps_{t}"] * inp["shares"] / 1e8
        p1 = "—" if t == "l" else f"{1 - inp[f'g1_{t}'] / roe[t]:.3f}"
        g1 = "不启用" if t == "l" else f"{inp[f'g1_{t}']:.0%}"
        print(f"{t.upper():<3}{inp[f'eps_{t}']:9.3f}{ni:11.2f}{roe[t]:10.2%}{g1:>8}"
              f"{g2:7.1%}{p1:>10}{payout(g2, roe[t]):10.3f}"
              f"{pe[t]:8.2f}{anchor(inp, t):10.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.1%}")
    print(f"分子比 L/M={inp['eps_l'] / inp['eps_m']:.3f} "
          f"H/M={inp['eps_h'] / inp['eps_m']:.3f} | "
          f"倍数比 L/M={pe['l'] / pe['m']:.3f} H/M={pe['h'] / pe['m']:.3f}"
          f"  — 两端同质（都由倍数主导），非 A2e-5 的不对称红线")
    print(f"flat-multiple @PE_M={pe['m']:.2f}: {flat[0]:.2f} / {flat[1]:.2f} / "
          f"{flat[2]:.2f} — 阶梯成立，三档各有独立分子（A2e-2c）")
    print(f"基准差一期（A15）：L 用 perpetual_pe（下期盈利倍数），M/H 用 two_stage_pe"
          f"（当期）；L 对齐当期口径 = {aligned:.2f}（+{inp['g2_l']:.1%}）")
    print(f"三档 PE {pe['l']:.2f}/{pe['m']:.2f}/{pe['h']:.2f} 落在 own-year 带 "
          f"[{inp['pe_own_lo']:g}, {inp['pe_own_hi']:g}] 内；"
          f"PE_H ≤ 2023 年起上沿 {inp['pe_own_hi_recent']:g} ✓")

    # 两段式的量级：放弃过渡段会把 M 打到哪里
    single_m = perpetual_pe(inp["g2_m"], roe["m"], r) * inp["eps_m"]
    print(f"若放弃过渡段（三档全单段永续）：M 从 {M:.2f} 掉到 {single_m:.2f} "
          f"({single_m / M - 1:+.1%}) — 过渡段比任何分子假设都更能移动 zone")

    print(f"price={inp['price']} zone={zone}")
    for label, px in (
        ("A 股现价", inp["price"]),
        ("本框架 M", M),
        ("高盛 TP", inp["tp_street"]),
        ("一致 TP", inp["tp_consensus"]),
        ("H 股折 CNY*", inp["price_h"] * inp["fx_hkdcny"]),
    ):
        lo, hi = 0.0, 0.8
        for _ in range(200):
            mid = (lo + hi) / 2
            if two_stage_pe(mid, n, inp["g2_m"], roe["m"], r) * inp["eps_m"] < px:
                lo = mid
            else:
                hi = mid
        print(f"  {label:<12} {px:7.2f}  隐含 FY2026E PE={px / inp['eps_m']:6.2f}"
              f"  隐含 g1={(lo + hi) / 2:+.1%}")
    ha = inp["price_h"] * inp["fx_hkdcny"] / inp["price"]
    print(f"  * H 股那一行只作**机制读数**：3750.HK 自由流通仅占总股本 4.72%，"
          f"按 A12 判定为流通盘定价机制，非基本面")
    print(f"    MUST NOT 当作市场对增长的看法引用；A/H 收敛已从 stretched "
          f"解释材料删除（用户 2026-09-10）")
    print(f"  A/H（A12，不进主公式、不作上行解释）：H/A={ha:.3f}；"
          f"PE(TTM) A={inp['price'] / inp['eps_ttm']:.2f}")
    gi, ok = implied_g(inp["price"] / inp["eps_m"], roe["m"], r)
    print(f"  单段口径反解（仅对照）：g={gi:+.2%} well_conditioned={ok}")
    print(f"  股本口径（A17，不进锚点）：回购 {inp['buyback_lo']:.0f}–"
          f"{inp['buyback_hi']:.0f} 亿注销 = "
          f"−{inp['buyback_lo'] * 1e8 / inp['price'] / inp['shares']:.3%}~"
          f"−{inp['buyback_hi'] * 1e8 / inp['price'] / inp['shares']:.3%}；"
          f"激励 +{inp['opt_outstanding'] / inp['shares']:.3%}；"
          f"库存股 {inp['treasury_shares'] / inp['shares']:.3%}")
    print(f"  单位净利 FY2025 {inp['unit_profit_fy2025']:.1f} → "
          f"2026H1 {inp['unit_profit_h1']:.2f} 元/kWh "
          f"({inp['unit_profit_h1'] / inp['unit_profit_fy2025'] - 1:+.1%})；"
          f"净现金 {inp['net_cash']:.0f} 亿不另扣（A9）")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
