#!/usr/bin/env python3
"""6655.HK (Huaxin Cement / Huaxin Building Materials) valuation eval.

frameworks/6655.HK.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: huaxin_dom_ovs_split_perpetual_g_hk_anchored_v3

Main ruler: split the NUMERATOR by leg, then let each tier name a PERPETUAL
GROWTH RATE for each leg and read the multiple off Gordon.

  overseas NI = overseas EBITDA x k      (k = group's realised NI/EBITDA)
  domestic NI = group NI - overseas NI   (residual)
  g           = weighted mean of the two legs' perpetual g
  PE          = 1 / (r - g),  r = 10%  ->  a no-growth business is worth 10x

The multiples are NOT quantiles of the ticker's own historical PE.  A realised
PE carries whatever growth the market was pricing at the time: a low-growth or
shrinking year prints a low PE, and a cyclical trough prints a high one because
the denominator collapsed.  Using those quantiles as tiers imports the past's
growth expectations into today's numerator.  This deviates from skill A2e-2b by
explicit user decision (2026-09-09); the measured band survives as a fence, in
`HK_PE_BAND` below, and every tier's generated PE has to land inside it.

Two guards carry most of the weight here:

  * the zero-growth floor on H (A10).  "Modelled success" cannot be a business
    that shrinks forever, so g_H >= 0, i.e. PE_H >= 1/r.
  * the historical fence (A9).  If a generated multiple leaves [4.24, 12.78],
    the normative anchor has walked past any price this stock has ever printed
    and the construction goes back to the conversation.

The L numerator is FY2025's realised group net income — domestic already sits
at its measured trough (16.49 -> 15.23 once the overseas leg is stripped out)
and the overseas leg freezes at what it has already earned, because plants that
are running cannot un-ramp.  It comes in below the consensus low (1.437 x
shares = 29.88), so the tier is not merely "last year".

Run:  python3 eval/6655.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import AXIS_SOUTHBOUND, check_africa_mount  # noqa: E402
from lib.gordon import check_g_cap, implied_g, payout, perpetual_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "6655.HK.md"
FORMULA_ID = "huaxin_dom_ovs_split_perpetual_g_hk_anchored_v3"

TIERS = ("l", "m", "h")
# Perpetual-g inputs carry the `g2_` prefix so scripts/calibration.py reports
# them in its g2 column (AGENTS.md「永续增长口径」).
G2_LEGS = ("dom", "ovs")

REQUIRED = [
    "price", "price_a", "shares", "bps", "fx_hkdcny", "r_perp", "equity",
    "ni_group_l", "ni_group_m", "ni_group_h",
    "ebitda_ovs_l", "ebitda_ovs_m", "ebitda_ovs_h", "k_ni_ebitda",
    "g2_dom_l", "g2_dom_m", "g2_dom_h",
    "g2_ovs_l", "g2_ovs_m", "g2_ovs_h",
    "pe_own_lo", "pe_own_hi", "pe_own_mid",
    "eps_consensus_low", "pe_a_mid",
]


def legs(inp: dict[str, float], tag: str) -> tuple[float, float]:
    """(domestic, overseas) net income for one tier, in 亿元 CNY."""
    ovs = inp[f"ebitda_ovs_{tag}"] * inp["k_ni_ebitda"]
    return inp[f"ni_group_{tag}"] - ovs, ovs


def blended_g(inp: dict[str, float], tag: str) -> float:
    dom, ovs = legs(inp, tag)
    group = inp[f"ni_group_{tag}"]
    return (dom / group) * inp[f"g2_dom_{tag}"] + (ovs / group) * inp[f"g2_ovs_{tag}"]


def forward_roe(inp: dict[str, float], tag: str) -> float:
    return inp[f"ni_group_{tag}"] / inp["equity"]


def multiple(inp: dict[str, float], tag: str) -> float:
    return perpetual_pe(blended_g(inp, tag), forward_roe(inp, tag), inp["r_perp"])


def value_cny(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    pe = flat_pe if flat_pe is not None else multiple(inp, tag)
    return inp[f"ni_group_{tag}"] * pe


def anchor(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    """HKD per share."""
    per_share = value_cny(inp, tag, flat_pe) * 1e8 / inp["shares"]
    return per_share / inp["fx_hkdcny"]


def check_southbound_mount(md: str) -> list[str]:
    """Axis §3 rule 3: a mounted ticker reports the A-share companion band and live H/A.

    The southbound axis locks no numerator and, since AGENTS.md「永续增长口径」
    took multiples away from historical quantiles, no multiple either (A16: it
    acts on the implied-g convergence).  What it still locks is the reporting
    contract its own §4 direction check depends on.
    """
    if not AXIS_SOUTHBOUND.exists():
        return [f"axis file missing: {AXIS_SOUTHBOUND.name}"]
    errors: list[str] = []
    if "6655.HK" not in AXIS_SOUTHBOUND.read_text(encoding="utf-8"):
        errors.append("6655.HK is not declared on _AXIS.southbound-repricing.md — "
                      "a mount has to exist on both sides")
    if "A 股对照带" not in md:
        errors.append("framework lacks the A-share companion band (axis §3 rule 3)")
    if not re.search(r"H/A\s*=\s*\*{0,2}[01]\.\d+", md):
        errors.append("framework does not state the current H/A reading (axis §3 rule 3)")
    return errors


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
    lo, hi = inp["pe_own_lo"], inp["pe_own_hi"]

    # --- Step 1: numerators -------------------------------------------------
    errors += ladder(
        "ni_group", inp["ni_group_l"], inp["ni_group_m"], inp["ni_group_h"]
    )
    errors += ladder(
        "ebitda_ovs", inp["ebitda_ovs_l"], inp["ebitda_ovs_m"], inp["ebitda_ovs_h"]
    )
    if not 0.0 < inp["k_ni_ebitda"] < 1.0:
        errors.append(f"k_ni_ebitda={inp['k_ni_ebitda']} outside (0, 1)")
    if inp["equity"] <= 0:
        errors.append(f"equity={inp['equity']} must be positive")

    # Both legs must ladder on their own.  The domestic leg is a residual, so a
    # reversal there means the split is fighting the cycle rather than showing
    # it — a construction failure, not a scenario.
    dom = [legs(inp, t)[0] for t in TIERS]
    ovs = [legs(inp, t)[1] for t in TIERS]
    errors += ladder("ni_dom (residual)", *dom)
    errors += ladder("ni_ovs", *ovs)

    # --- Step 2: the growth ladders -----------------------------------------
    errors += ladder("g_dom", inp["g2_dom_l"], inp["g2_dom_m"], inp["g2_dom_h"])
    errors += ladder("g_ovs", inp["g2_ovs_l"], inp["g2_ovs_m"], inp["g2_ovs_h"])
    g = {t: blended_g(inp, t) for t in TIERS}
    errors += ladder("g blended", *(g[t] for t in TIERS))
    for t in TIERS:
        if r - g[t] <= 0:
            errors.append(f"g_{t}={g[t]:.4f} >= r={r} — perpetuity diverges")
    # AGENTS.md 永续上限 6%: every named perpetual g, per leg and blended.
    for leg in G2_LEGS:
        for t in TIERS:
            errors += check_g_cap(inp[f"g2_{leg}_{t}"], f"g2_{leg}_{t}")
    for t in TIERS:
        errors += check_g_cap(g[t], f"g_blended_{t}")
    if errors:
        return report(errors, "FAIL (ladders/convergence)")

    # --- Step 3: the overseas leg belongs to the Africa axis -----------------
    # Huaxin's African cement plants, Keda's ceramic lines and Jiayou's toll
    # corridors all sit on the same driver and overlap in Zambia / Tanzania /
    # Mozambique.  None of the three gets to write its own Africa case.
    errors += check_africa_mount(
        (inp["g2_ovs_l"], inp["g2_ovs_m"], inp["g2_ovs_h"])
    )
    errors += check_southbound_mount(md)
    if errors:
        return report(errors, "FAIL (shared axis)")

    # --- Step 4: the two normative guards -----------------------------------
    # A10: "modelled success" must not be a perpetually shrinking business.
    if g["h"] < -1e-12:
        errors.append(
            f"H tier implies g={g['h']:.2%} < 0 — the optimistic tier cannot "
            f"price perpetual decline (A10)"
        )
    # A9: the generated multiples still have to be prices this stock could print.
    pe = {t: multiple(inp, t) for t in TIERS}
    for t in TIERS:
        if not (lo - 1e-9 <= pe[t] <= hi + 1e-9):
            errors.append(
                f"PE_{t.upper()}={pe[t]:.2f} outside own-year measured band "
                f"[{lo}, {hi}] — the normative anchor left the ticker's history (A9)"
            )
    # A12: growth is paid for out of retained earnings, and a shrinking
    # business is not assumed to hand back more than it earns.
    for t in TIERS:
        pay = payout(g[t], forward_roe(inp, t))
        if not 0.0 < pay <= 1.0 + 1e-12:
            errors.append(f"payout_{t}={pay:.3f} outside (0, 1]")
        if g[t] <= 0 and abs(pay - 1.0) > 1e-12:
            errors.append(f"payout_{t}={pay:.3f} but g={g[t]:.2%} <= 0 — cap not binding")
    # Comparison-only fields must stay out of the computation path.
    for key in ("pe_a_mid", "pe_own_mid"):
        if abs(inp[key] - pe["m"]) < 1e-9:
            errors.append(f"{key} leaked into the multiple path — it is a comparison field")
    if errors:
        return report(errors, "FAIL (guards)")

    # --- Step 5: anchors ----------------------------------------------------
    L, M, H = (anchor(inp, t) for t in TIERS)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    flat = {t: anchor(inp, t, flat_pe=pe["m"]) for t in TIERS}
    errors += ladder("flat-multiple", flat["l"], flat["m"], flat["h"])

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}  (r={r:.0%}, 零增长={1 / r:.1f}x)")
    print(f"{'档':<3}{'集团归母':>10}{'海外NI':>9}{'国内NI':>9}{'海外权重':>10}"
          f"{'g_dom':>8}{'g_ovs':>8}{'g':>9}{'ROE':>8}{'派息':>8}{'PE':>8}"
          f"{'CNY价值':>10}{'锚点HKD':>10}")
    for i, t in enumerate(TIERS):
        roe = forward_roe(inp, t)
        print(f"{t.upper():<3}{inp[f'ni_group_{t}']:10.2f}{ovs[i]:9.2f}{dom[i]:9.2f}"
              f"{ovs[i] / inp[f'ni_group_{t}']:10.1%}{inp[f'g2_dom_{t}']:8.0%}"
              f"{inp[f'g2_ovs_{t}']:8.0%}{g[t]:9.2%}{roe:8.2%}"
              f"{payout(g[t], roe):8.1%}{pe[t]:8.2f}"
              f"{value_cny(inp, t):10.2f}{anchor(inp, t):10.2f}")
    naive = {t: inp[f"ni_group_{t}"] / (r - g[t]) * 1e8 / inp["shares"] / inp["fx_hkdcny"]
             for t in TIERS}
    print(f"若按 100% 派息的 1/(r-g)：{naive['l']:.2f} / {naive['m']:.2f} / {naive['h']:.2f}"
          f" — H 档高估 {naive['h'] / anchor(inp, 'h') - 1:.0%}（留存成本，A12）")
    alt_l = inp["eps_consensus_low"] * inp["shares"] / 1e8
    print(f"L 分子 {inp['ni_group_l']:.2f} 亿 vs 共识下沿隐含 {alt_l:.2f} 亿 — "
          f"L {'低于' if inp['ni_group_l'] < alt_l else '高于'}街上最低预期")
    print(f"三档 PE {pe['l']:.2f}/{pe['m']:.2f}/{pe['h']:.2f} 落在 own-year 实测带 "
          f"[{lo}, {hi}] 内 (p50={inp['pe_own_mid']:g}) ✓")
    num_l = inp["ni_group_l"] / inp["ni_group_m"]
    num_h = inp["ni_group_h"] / inp["ni_group_m"]
    print(f"flat-multiple @PE={pe['m']:.2f}: L={flat['l']:.2f} M={flat['m']:.2f} "
          f"H={flat['h']:.2f} — 带宽 {(flat['h'] - flat['l']) / (2 * flat['m']):.0%}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}")
    print(f"分子比 L/M={num_l:.2f} H/M={num_h:.2f} | "
          f"倍数比 L/M={pe['l'] / pe['m']:.2f} H/M={pe['h'] / pe['m']:.2f}")
    print(f"分腿分子比 海外 L/M={ovs[0] / ovs[1]:.2f} H/M={ovs[2] / ovs[1]:.2f} | "
          f"国内 L/M={dom[0] / dom[1]:.2f} H/M={dom[2] / dom[1]:.2f}")

    # What the market, the street and book value are each paying for, in g terms.
    fx = inp["fx_hkdcny"]
    mcap = inp["price"] * inp["shares"] / 1e8 * fx
    print(f"price(H)={inp['price']} zone={zone}")
    for label, cny_value in (
        ("H 股现价", mcap),
        ("账面 PB=1.0", inp["bps"] * inp["shares"] / 1e8),
        ("A 股现价", inp["price_a"] * inp["shares"] / 1e8),
    ):
        p = cny_value / inp["ni_group_m"]
        gi, ok = implied_g(p, forward_roe(inp, "m"), r)
        flag = "" if ok else "  ⚠ ROE≈r，反解只能当方向读"
        print(f"  {label:<10} 隐含 PE={p:5.2f} → g={gi:+.2%}{flag}")
    la, ma, ha = L * fx, M * fx, H * fx
    print(f"A股对照(CNY): L={la:.2f} M={ma:.2f} H={ha:.2f} "
          f"| price_a={inp['price_a']} zone_a={zone_of(inp['price_a'], la, ma, ha)}")
    print(f"H/A = {inp['price'] * fx / inp['price_a']:.3f} "
          f"| BPS {inp['bps']:.2f} CNY = {inp['bps'] / fx:.2f} HKD")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
