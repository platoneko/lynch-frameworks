#!/usr/bin/env python3
"""6655.HK (Huaxin Cement / Huaxin Building Materials) valuation eval.

frameworks/6655.HK.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: huaxin_dom_ovs_split_perpetual_g_hk_anchored_v3

Main ruler: split the NUMERATOR by leg, let each tier name a PERPETUAL GROWTH
RATE for each leg, price each leg on its own Gordon multiple at its BASKET r,
and add the legs up (SOTP).

  overseas NI = overseas EBITDA x k      (k = group's realised NI/EBITDA)
  domestic NI = group NI - overseas NI   (residual)
  PE_leg      = min(1, 1 - g_leg/ROE) / (r_leg - g_leg)
  V           = NI_dom x PE_dom + NI_ovs x PE_ovs

r comes from the basket each leg is assigned to (valuation-rules.md「§r 篮子」,
values in gordon.BASKET_R); the Inputs rows `r_dom` / `r_ovs` name the basket
in their source cell and `check_r` enforces that the value is that basket's.
Both legs sit in 篮 6 (13%), so a no-growth leg is worth 1/r = 7.69x.  The
company-wide forward ROE is shared by both legs (no per-region assets are
disclosed), so above zero growth the retention term is a penalty while
ROE < r — the framework discloses the 1/r alternative for the overseas leg
rather than deciding it.

The multiples are NOT quantiles of the ticker's own historical PE.  A realised
PE carries whatever growth the market was pricing at the time: a low-growth or
shrinking year prints a low PE, and a cyclical trough prints a high one because
the denominator collapsed.  Using those quantiles as tiers imports the past's
growth expectations into today's numerator.  This deviates from skill A2e-2b by
explicit user decision (2026-09-09); the measured band survives as a fence, and
every tier's company-level multiple (anchor / group EPS) has to land inside it.

Two guards carry most of the weight here:

  * the zero-growth floor on the overseas leg's H (A10).  "Modelled success"
    cannot shrink the growth leg forever, so g_ovs_H >= 0.
  * the historical fence (A9).  If a company-level multiple leaves
    [4.24, 12.78], the normative anchor has walked past any price this stock
    has ever printed and the construction goes back to the conversation.

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
from lib.gordon import basket_r, check_g_cap, check_r, payout, perpetual_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "6655.HK.md"
FORMULA_ID = "huaxin_dom_ovs_split_perpetual_g_hk_anchored_v3"

TIERS = ("l", "m", "h")
# Perpetual-g inputs carry the `g2_` prefix so scripts/calibration.py reports
# them in its g2 column (valuation-rules.md「永续增长口径」).  Each leg has its
# own basket r row.
LEGS = ("dom", "ovs")
R_ROWS = {"dom": "r_dom", "ovs": "r_ovs"}

REQUIRED = [
    "price", "price_a", "shares", "bps", "fx_hkdcny", "equity",
    "r_dom", "r_ovs",
    "ni_group_l", "ni_group_m", "ni_group_h",
    "ebitda_ovs_l", "ebitda_ovs_m", "ebitda_ovs_h", "k_ni_ebitda",
    "g2_dom_l", "g2_dom_m", "g2_dom_h",
    "g2_ovs_l", "g2_ovs_m", "g2_ovs_h",
    "pe_own_lo", "pe_own_hi", "pe_own_mid",
    "eps_consensus_low", "pe_a_mid",
]


def legs(inp: dict[str, float], tag: str) -> dict[str, float]:
    """{leg: net income} for one tier, in 亿元 CNY."""
    ovs = inp[f"ebitda_ovs_{tag}"] * inp["k_ni_ebitda"]
    return {"dom": inp[f"ni_group_{tag}"] - ovs, "ovs": ovs}


def blended_g(inp: dict[str, float], tag: str) -> float:
    """Profit-weighted g across legs — printed as an intermediate, never priced."""
    ni = legs(inp, tag)
    group = inp[f"ni_group_{tag}"]
    return sum(ni[leg] / group * inp[f"g2_{leg}_{tag}"] for leg in LEGS)


def forward_roe(inp: dict[str, float], tag: str) -> float:
    return inp[f"ni_group_{tag}"] / inp["equity"]


def leg_pe(inp: dict[str, float], leg: str, tag: str, r_shift: float = 0.0,
           g_override: float | None = None) -> float:
    g = inp[f"g2_{leg}_{tag}"] if g_override is None else g_override
    return perpetual_pe(g, forward_roe(inp, tag), inp[R_ROWS[leg]] + r_shift)


def value_cny(inp: dict[str, float], tag: str, pes: dict[str, float] | None = None) -> float:
    """Sum of legs, 亿元 CNY.  `pes` overrides the per-leg multiples (flat / sensitivity)."""
    ni = legs(inp, tag)
    pe = pes or {leg: leg_pe(inp, leg, tag) for leg in LEGS}
    return sum(ni[leg] * pe[leg] for leg in LEGS)


def per_share_cny(inp: dict[str, float], tag: str, pes: dict[str, float] | None = None) -> float:
    return value_cny(inp, tag, pes) * 1e8 / inp["shares"]


def anchor(inp: dict[str, float], tag: str, pes: dict[str, float] | None = None) -> float:
    """HKD per share."""
    return per_share_cny(inp, tag, pes) / inp["fx_hkdcny"]


def implied_r_shift(inp: dict[str, float], price_cny: float) -> float:
    """δ such that the M-tier SOTP with every leg at r_leg + δ equals the price.

    Both legs' basket r move together; the answer is the parallel shift the
    market is applying to the basket table, not a per-leg r.  Bisection on
    δ ∈ [-8%, +20%]: the SOTP is monotone decreasing in δ over that range.
    """
    lo, hi = -0.08, 0.20

    def f(delta: float) -> float:
        pes = {leg: leg_pe(inp, leg, "m", r_shift=delta) for leg in LEGS}
        return per_share_cny(inp, "m", pes) - price_cny

    if f(lo) < 0 or f(hi) > 0:
        raise ValueError("implied r shift outside bisection bracket")
    for _ in range(80):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def check_southbound_mount(md: str) -> list[str]:
    """Axis §3 rule 3: a mounted ticker reports the A-share companion band and live H/A.

    The southbound axis locks no numerator and, since valuation-rules.md
    「永续增长口径」took multiples away from historical quantiles, no multiple
    either (A16: it acts on the implied-g convergence).  What it still locks
    is the reporting contract its own §4 direction check depends on.
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

    lo, hi = inp["pe_own_lo"], inp["pe_own_hi"]
    r = {leg: inp[R_ROWS[leg]] for leg in LEGS}

    # --- Step 1: baskets — each leg's r must be the basket it names -----------
    baskets = parse_baskets(md)
    for leg in LEGS:
        row = R_ROWS[leg]
        if row not in baskets:
            errors.append(f"{row}: Inputs source cell names no 篮 N (AGENTS.md「篮子声明」)")
        errors += check_r(r[leg], row, baskets.get(row))
    if errors:
        return report(errors, "FAIL (baskets)")

    # --- Step 2: numerators -------------------------------------------------
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
    ni = {t: legs(inp, t) for t in TIERS}
    errors += ladder("ni_dom (residual)", *(ni[t]["dom"] for t in TIERS))
    errors += ladder("ni_ovs", *(ni[t]["ovs"] for t in TIERS))

    # --- Step 3: the growth ladders, per leg against its own basket r --------
    errors += ladder("g_dom", inp["g2_dom_l"], inp["g2_dom_m"], inp["g2_dom_h"])
    errors += ladder("g_ovs", inp["g2_ovs_l"], inp["g2_ovs_m"], inp["g2_ovs_h"])
    g_bar = {t: blended_g(inp, t) for t in TIERS}
    errors += ladder("g blended", *(g_bar[t] for t in TIERS))
    for leg in LEGS:
        for t in TIERS:
            g = inp[f"g2_{leg}_{t}"]
            if r[leg] - g <= 0:
                errors.append(f"g2_{leg}_{t}={g:.4f} >= r_{leg}={r[leg]} — perpetuity diverges")
            # valuation-rules.md 永续上限: min(6%, r − 4%) per leg.
            errors += check_g_cap(g, r[leg], f"g2_{leg}_{t}")
    if errors:
        return report(errors, "FAIL (ladders/convergence)")

    # --- Step 4: the overseas leg belongs to the Africa axis -----------------
    # Huaxin's African cement plants, Keda's ceramic lines and Jiayou's toll
    # corridors all sit on the same driver and overlap in Zambia / Tanzania /
    # Mozambique.  None of the three gets to write its own Africa case.
    errors += check_africa_mount(
        (inp["g2_ovs_l"], inp["g2_ovs_m"], inp["g2_ovs_h"])
    )
    errors += check_southbound_mount(md)
    if errors:
        return report(errors, "FAIL (shared axis)")

    # --- Step 5: the normative guards ----------------------------------------
    # A10: "modelled success" must not shrink the growth leg forever.
    if inp["g2_ovs_h"] < -1e-12:
        errors.append(
            f"H tier overseas g={inp['g2_ovs_h']:.2%} < 0 — the optimistic tier cannot "
            f"price perpetual decline on the growth leg (A10)"
        )
    pe = {t: {leg: leg_pe(inp, leg, t) for leg in LEGS} for t in TIERS}
    # A9: the company-level multiple (SOTP value / group NI) still has to be a
    # price this stock could print.
    pe_company = {t: value_cny(inp, t) / inp[f"ni_group_{t}"] for t in TIERS}
    for t in TIERS:
        if not (lo - 1e-9 <= pe_company[t] <= hi + 1e-9):
            errors.append(
                f"PE_{t.upper()} (company)={pe_company[t]:.2f} outside own-year measured band "
                f"[{lo}, {hi}] — the normative anchor left the ticker's history (A9)"
            )
    # A12: growth is paid for out of retained earnings, and a shrinking
    # business is not assumed to hand back more than it earns — per leg.
    for t in TIERS:
        roe = forward_roe(inp, t)
        for leg in LEGS:
            g = inp[f"g2_{leg}_{t}"]
            pay = payout(g, roe)
            if not 0.0 < pay <= 1.0 + 1e-12:
                errors.append(f"payout_{leg}_{t}={pay:.3f} outside (0, 1]")
            if g <= 0 and abs(pay - 1.0) > 1e-12:
                errors.append(f"payout_{leg}_{t}={pay:.3f} but g={g:.2%} <= 0 — cap not binding")
    # Comparison-only fields must stay out of the computation path.
    for key in ("pe_a_mid", "pe_own_mid"):
        if any(abs(inp[key] - pe["m"][leg]) < 1e-9 for leg in LEGS):
            errors.append(f"{key} leaked into the multiple path — it is a comparison field")
    if errors:
        return report(errors, "FAIL (guards)")

    # --- Step 6: anchors ----------------------------------------------------
    L, M, H = (anchor(inp, t) for t in TIERS)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    # flat-multiple: each leg held at its own PE_M across the three tiers.
    flat = {t: anchor(inp, t, pe["m"]) for t in TIERS}
    errors += ladder("flat-multiple", flat["l"], flat["m"], flat["h"])

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report --------------------------------------------------------------
    fx = inp["fx_hkdcny"]
    print(f"formula_id={FORMULA_ID}")
    print("篮子: " + "; ".join(
        f"{R_ROWS[leg]} 篮 {baskets[R_ROWS[leg]]} {basket_r(baskets[R_ROWS[leg]]):.0%}"
        f" (零增长 {1 / r[leg]:.2f}x)" for leg in LEGS))
    print(f"{'档':<3}{'集团归母':>10}{'海外NI':>9}{'国内NI':>9}{'海外权重':>10}"
          f"{'g_dom':>8}{'g_ovs':>8}{'ROE':>8}{'PE_dom':>8}{'PE_ovs':>8}{'派息ovs':>9}"
          f"{'合成g':>9}{'公司PE':>8}{'CNY价值':>10}{'锚点HKD':>10}")
    for t in TIERS:
        roe = forward_roe(inp, t)
        print(f"{t.upper():<3}{inp[f'ni_group_{t}']:10.2f}{ni[t]['ovs']:9.2f}{ni[t]['dom']:9.2f}"
              f"{ni[t]['ovs'] / inp[f'ni_group_{t}']:10.1%}{inp[f'g2_dom_{t}']:8.0%}"
              f"{inp[f'g2_ovs_{t}']:8.0%}{roe:8.2%}{pe[t]['dom']:8.2f}{pe[t]['ovs']:8.2f}"
              f"{payout(inp[f'g2_ovs_{t}'], roe):9.1%}{g_bar[t]:9.2%}{pe_company[t]:8.2f}"
              f"{value_cny(inp, t):10.2f}{anchor(inp, t):10.2f}")
    alt_l = inp["eps_consensus_low"] * inp["shares"] / 1e8
    print(f"L 分子 {inp['ni_group_l']:.2f} 亿 vs 共识下沿隐含 {alt_l:.2f} 亿 — "
          f"L {'低于' if inp['ni_group_l'] < alt_l else '高于'}街上最低预期")
    print(f"公司口径 PE {pe_company['l']:.2f}/{pe_company['m']:.2f}/{pe_company['h']:.2f} "
          f"落在 own-year 实测带 [{lo}, {hi}] 内 (p50={inp['pe_own_mid']:g}) ✓ — ③ 不出带")
    print(f"flat-multiple @PE_M (国内 {pe['m']['dom']:.2f}× / 海外 {pe['m']['ovs']:.2f}×): "
          f"L={flat['l']:.2f} M={flat['m']:.2f} H={flat['h']:.2f} — "
          f"带宽 {(flat['h'] - flat['l']) / (2 * flat['m']):.0%}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.1%}")
    num_l = inp["ni_group_l"] / inp["ni_group_m"]
    num_h = inp["ni_group_h"] / inp["ni_group_m"]
    print(f"分子比 L/M={num_l:.2f} H/M={num_h:.2f} | 公司口径倍数比 "
          f"L/M={pe_company['l'] / pe_company['m']:.2f} H/M={pe_company['h'] / pe_company['m']:.2f}")
    print(f"分腿分子比 海外 L/M={ni['l']['ovs'] / ni['m']['ovs']:.2f} H/M={ni['h']['ovs'] / ni['m']['ovs']:.2f} | "
          f"国内 L/M={ni['l']['dom'] / ni['m']['dom']:.2f} H/M={ni['h']['dom'] / ni['m']['dom']:.2f}")

    # Disclosure rows (never max()'d into the deck).
    print(f"地板（只披露）: BPS {inp['bps']:.2f} CNY = {inp['bps'] / fx:.2f} HKD; "
          f"锚点隐含 PB {L * fx / inp['bps']:.2f} / {M * fx / inp['bps']:.2f} / {H * fx / inp['bps']:.2f}")
    one_over_r = {t: {"dom": pe[t]["dom"], "ovs": 1 / r["ovs"]} for t in TIERS}
    alt = [anchor(inp, t, one_over_r[t]) for t in TIERS]
    print(f"海外腿按 1/r（项目 ROE ≥ r 的坐标）: {alt[0]:.2f} / {alt[1]:.2f} / {alt[2]:.2f}")
    naive = [anchor(inp, t, {leg: 1 / (r[leg] - inp[f"g2_{leg}_{t}"]) for leg in LEGS}) for t in TIERS]
    print(f"若按 100% 派息的 1/(r-g)：{naive[0]:.2f} / {naive[1]:.2f} / {naive[2]:.2f}"
          f" — H 档高估 {naive[2] / H - 1:.0%}（留存成本，A12）")
    for dg, label in ((0.01, "+1pp"), (-0.01, "−1pp")):
        band = [anchor(inp, t, {"dom": pe[t]["dom"],
                                "ovs": leg_pe(inp, "ovs", t, g_override=inp[f"g2_ovs_{t}"] + dg)})
                for t in TIERS]
        print(f"敏感区 g2_ovs_* {label}: {band[0]:.2f} / {band[1]:.2f} / {band[2]:.2f} "
              f"zone={zone_of(inp['price'], *band)}")
    for dr, label in ((-0.005, "12.5%"), (0.005, "13.5%")):
        band = [anchor(inp, t, {leg: leg_pe(inp, leg, t, r_shift=dr) for leg in LEGS}) for t in TIERS]
        print(f"敏感区 两腿 r {label}: {band[0]:.2f} / {band[1]:.2f} / {band[2]:.2f} "
              f"zone={zone_of(inp['price'], *band)}")

    # What the market, the street and book value each require in r terms:
    # a parallel shift δ of both baskets that makes the M-tier SOTP equal the
    # price, plus the single-segment g=0 approximation E_M / P.
    eps_m_cny = inp["ni_group_m"] * 1e8 / inp["shares"]
    print(f"price(H)={inp['price']} zone={zone}")
    for label, price_cny in (
        ("H 股现价", inp["price"] * fx),
        ("账面 PB=1.0", inp["bps"]),
        ("A 股现价", inp["price_a"]),
    ):
        delta = implied_r_shift(inp, price_cny)
        print(f"  {label:<10} 隐含 PE={price_cny / eps_m_cny:5.2f} → δ={delta:+.2%} "
              f"(两腿 r {r['dom'] + delta:.1%}) | g=0 近似 E_M/P={eps_m_cny / price_cny:.1%}")
    la, ma, ha = L * fx, M * fx, H * fx
    print(f"A股对照(CNY): L={la:.2f} M={ma:.2f} H={ha:.2f} A={(la + ma) / 2:.2f} B={(ma + ha) / 2:.2f} "
          f"| price_a={inp['price_a']} zone_a={zone_of(inp['price_a'], la, ma, ha)}")
    print(f"H/A = {inp['price'] * fx / inp['price_a']:.3f}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
