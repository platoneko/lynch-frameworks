#!/usr/bin/env python3
"""600111.SH (China Northern Rare Earth) valuation eval.

frameworks/600111.SH.md is the source of truth.
formula_id: nre_consensus_fy28_disc_two_stage_gordon_v2

Numerator = the FY2028 sell-side range (two houses, low/mean/high), discounted
one year (FY+2 → t=1, construction §3).  This is the ②-b fallback of
valuation-rules: the 5-year NdPr-price mid-cycle numerator (A8) sits 57% below
the consensus mean, only half of which the one measured structural variable
(phase-2 smelting capacity) explains, so the framework swaps to the consensus
three points and hangs falsifiers on them (A1).

Multiples are two-stage Gordon (valuation-rules「永续增长口径」「两段式过渡」):
r is the whole-company basket (篮 6 周期商品, A10), ROE per tier = EPS28 /
forward BPS, a GS demand-CAGR window g1 for n years after the numerator year,
then the CNY-inflation tail g2.  Nothing is reverse-solved from the
same-earnings band any more: at the basket r the generated PE_M sits below
that band's lower edge, which is formally a ③ out-of-band, but the band failed
the 1b validity check (2023-01→08 was priced on FY23E consensus that later
collapsed), so the framework records「不可判定」and keeps the initial basket.
This eval asserts that the out-of-band fact and the framework's declaration
agree, and never lowers the basket or twists g.

The NdPr-price → EPS bridge (A2) never enters the anchors; it names the three
worlds in price terms, must reproduce the measured years within ±20%, and
prints the mid-cycle / trough coordinates that the `deep_discount` row reads.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.gordon import (  # noqa: E402
    basket_r,
    check_branch,
    check_g_cap,
    check_r,
    payout,
    payout_gap,
    perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_baskets,
    parse_inputs,
)
from lib.tiers import flat_multiple_ladder, report as tier_report  # noqa: E402
from lib.zones import zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "600111.SH.md"
FORMULA_ID = "nre_consensus_fy28_disc_two_stage_gordon_v2"
MIN_R_MINUS_G = 0.02
TOL = 0.05
# 纠正对账门 coordinate ②: the new M must sit within this of E_M / r.
RECONCILE_TOL = 0.20
# The framework's ③ verdict when the band is distorted (A10); the guardrail
# asserts this wording is present iff the generated multiple is out of band.
UNDECIDABLE = "不可判定"

# A2 bridge reproduction: (NdPr oxide annual average 万/吨, reported EPS).  The
# bridge was fitted on four points; the two full formula-regime years that are
# not the trough are the reproduction gate (±20%).
BRIDGE_GATE = {"FY2023": (53.0, 0.6558), "FY2025": (51.45, 0.6227)}
BRIDGE_TOL = 0.20
# Bridge worlds: consensus EPS28 read back into NdPr price at today's volume and
# at the phase-2 run-rate (31 万吨 vs ~20 → ×1.55); printed, not anchors.
PHASE2_VOLUME_X = 1.55
# Pre-control market centre (2023-11 → 2025H1, 属性 E) and the regime mid-cycle
# NdPr price (A8) — implied-r / coordinate disclosures only.
PRE_CONTROL_PRICE = 21.0
NDPR_REGIME_MID = 70.0

REQUIRED = [
    "price", "shares", "bps", "bps_fwd",
    "eps28_l", "eps28_m", "eps28_h",
    "r_disc", "n_disc", "r_perp",
    "g1_window", "n_window", "g2",
    "pe_band_lo", "pe_band_hi",
    "payout_obs", "pb_floor",
    "bridge_a", "bridge_b", "ndpr_mid", "ndpr_now", "eps_trough",
    "eps28_ths",
]


def window_pe(g1: float, n: int, g2: float, roe: float, r: float) -> float:
    """Two-stage multiple on next-period earnings, as the framework writes it.

    Numerator year is t=1.  E_1..E_n grow at g1 (E_t = E_1 (1+g1)^(t-1)) and
    pay out 1 - g1/ROE; E_{n+1} = E_n (1+g2) starts the Gordon tail, valued at
    t=n.  This differs from lib.gordon.two_stage_pe only in the first tail
    year growing at g2 rather than g1 — the framework's stated construction,
    which the deck numbers reproduce.
    """
    if r - g2 <= 0:
        raise ValueError(f"perpetuity diverges: g2={g2} >= r={r}")
    p1, p2 = payout(g1, roe), payout(g2, roe)
    stage1 = sum(p1 * (1.0 + g1) ** (t - 1) / (1.0 + r) ** t for t in range(1, n + 1))
    tail = p2 * (1.0 + g1) ** (n - 1) * (1.0 + g2) / ((r - g2) * (1.0 + r) ** n)
    return stage1 + tail


def solve_r(target_pe_fn, lo: float = 0.02, hi: float = 0.30, iters: int = 80) -> float:
    """Bisect r on a monotone-decreasing function f(r) = value(r) - target."""
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        if target_pe_fn(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    # --- r / g inputs against the basket table -------------------------------------
    baskets = parse_baskets(md)
    r = inp["r_perp"]
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N tag in its Inputs source cell (AGENTS.md「篮子声明」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    g1, n_win, g2 = inp["g1_window"], int(inp["n_window"]), inp["g2"]
    errors += check_g_cap(g2, r, "g2")
    errors += check_g_cap(g1, r, "g1_window")
    if r - g2 < MIN_R_MINUS_G:
        errors.append(f"r − g2 = {r - g2:.4f} < {MIN_R_MINUS_G} (pole)")
    eps28 = (inp["eps28_l"], inp["eps28_m"], inp["eps28_h"])
    errors += ladder("eps28", *eps28)
    for k in inp:
        if k.startswith("p_"):
            errors.append(f"probability-style input {k} in Inputs")

    # --- two-stage Gordon multiples --------------------------------------------------
    roe = tuple(e / inp["bps_fwd"] for e in eps28)
    errors += check_branch(g2, roe[1], r, inp["payout_obs"], "M")
    pes = tuple(window_pe(g1, n_win, g2, x, r) for x in roe)
    # Guardrail (裁决顺序 ③): M and H against the same-earnings band.  Out of
    # band is allowed only when the framework declares the band distorted (1b)
    # and the verdict 不可判定; in band with that verdict is a stale framework.
    out_of_band = any(
        not (inp["pe_band_lo"] - 1e-6 <= pe <= inp["pe_band_hi"] + 1e-6) for pe in pes[1:]
    )
    declared = UNDECIDABLE in md.split("### Outputs", 1)[-1]
    if out_of_band and not declared:
        errors.append(
            f"guardrail: PE_M/H={pes[1]:.2f}/{pes[2]:.2f} outside same-earnings band "
            f"[{inp['pe_band_lo']}, {inp['pe_band_hi']}] and the framework does not declare {UNDECIDABLE} "
            f"— run the ③ 出带处理流程, do not twist g / r"
        )
    if declared and not out_of_band:
        errors.append(
            f"framework declares ③ {UNDECIDABLE} but PE_M/H={pes[1]:.2f}/{pes[2]:.2f} sit inside the band "
            f"[{inp['pe_band_lo']}, {inp['pe_band_hi']}] — drop the verdict"
        )

    disc = (1.0 + inp["r_disc"]) ** (-inp["n_disc"])
    eps_d = tuple(e * disc for e in eps28)
    L, M, H = (e * pe for e, pe in zip(eps_d, pes))
    scenario_L = L
    floor = inp["pb_floor"] * inp["bps"]   # disclosure only, never max()-ed into L (A5)
    A, B = (L + M) / 2, (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)
    if not (L < M < H):
        errors.append(f"L<M<H violated ({L:.2f}/{M:.2f}/{H:.2f})")
    flat_err, flat = flat_multiple_ladder(eps_d, pes[1])
    errors += flat_err
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken at PE_M={pes[1]:.2f}: {flat}")
    # 纠正对账门 ②: M within 20% of E_M / r (the coordinate the framework passes on).
    em_over_r = eps_d[1] / r
    if abs(M / em_over_r - 1.0) > RECONCILE_TOL:
        errors.append(f"对账门 ②: M {M:.2f} vs E_M/r {em_over_r:.2f} ({M / em_over_r - 1:+.0%} > {RECONCILE_TOL:.0%})")

    # --- A2 bridge reproduction gate ----------------------------------------------
    a, b = inp["bridge_a"], inp["bridge_b"]
    for year, (p, e) in BRIDGE_GATE.items():
        fit = a + b * p
        if abs(fit / e - 1.0) > BRIDGE_TOL:
            errors.append(f"bridge {year}: fit {fit:.3f} vs reported {e} (>{BRIDGE_TOL:.0%})")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)
    out_sec = md.split("### Outputs", 1)[-1]
    for label, want_v, rx in (
        ("floor", floor, r"`floor` = \*\*([0-9.]+)\*\*"),
        ("scenario_L", scenario_L, r"`scenario_L` = \*\*([0-9.]+)\*\*"),
    ):
        m = re.search(rx, out_sec)
        got = float(m.group(1)) if m else None
        if got is None or abs(got - want_v) > TOL:
            errors.append(f"{label}: stated {got} vs recomputed {want_v:.4f}")
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print(f"formula_id={FORMULA_ID}")
    print(f"basket: r_perp 篮 {baskets['r_perp']} = {r:g}; r_disc {inp['r_disc']:g} (numerator drift, no basket)")
    print(f"eps28 L/M/H = {eps28[0]:g}/{eps28[1]:g}/{eps28[2]:g}  × disc {disc:.4f} → {eps_d[0]:.3f}/{eps_d[1]:.3f}/{eps_d[2]:.3f}")
    print(f"L/M/H = {L:.2f}/{M:.2f}/{H:.2f}  A/B = {A:.2f}/{B:.2f}")
    print(f"floor={floor:.2f} (PB {inp['pb_floor']:g} × bps, disclosure only, not max()-ed) scenario_L={scenario_L:.2f} = L; "
          f"tier PB on today's bps = {L / inp['bps']:.2f}/{M / inp['bps']:.2f}/{H / inp['bps']:.2f}")
    modelled, gap = payout_gap(g2, roe[1], inp["payout_obs"])
    print(
        f"two-stage gordon: r={r:g} g1={g1:g} n={n_win} g2={g2:g} "
        f"roe={roe[0]:.3f}/{roe[1]:.3f}/{roe[2]:.3f} -> pe={pes[0]:.2f}/{pes[1]:.2f}/{pes[2]:.2f} "
        f"vs same-earnings band [{inp['pe_band_lo']}, {inp['pe_band_hi']}] "
        f"(1/r {1 / r:.2f}, perpetual g1 {perpetual_pe(g1, roe[1], r):.2f}); "
        f"payout_gap modelled {modelled:.0%} vs paid {inp['payout_obs']:.0%} = {gap:+.0%}"
    )
    print(f"③: out_of_band={out_of_band}, framework declares {UNDECIDABLE}={declared} "
          f"(band distorted per 1b — basket kept, no band-edge reverse-solve)")
    print(f"对账门 ②: E_M/r = {em_over_r:.2f}, M {M / em_over_r - 1:+.1%}")

    def band(g1_=g1, n_=n_win, g2_=g2, r_=r, disc_=disc):
        return [e * disc_ * window_pe(g1_, n_, g2_, x, r_) for e, x in zip(eps28, roe)]

    for tag, alt in (
        ("g2 0%", band(g2_=0.0)), ("g2 3%", band(g2_=0.03)),
        ("n 10", band(n_=10)), ("g1 6% (cap)", band(g1_=0.06)),
        ("r_perp 篮 5 11%", band(r_=basket_r(5))), ("r_perp 篮 4 10%", band(r_=basket_r(4))),
        ("r_disc 13%", band(disc_=(1 + r) ** (-inp["n_disc"]))), ("undiscounted", band(disc_=1.0)),
    ):
        print(f"  {tag:>18}: {alt[0]:.2f}/{alt[1]:.2f}/{alt[2]:.2f}  zone {zone_of(inp['price'], *alt)}")
    for year, (p, e) in BRIDGE_GATE.items():
        print(f"bridge {year}: fit {a + b * p:.3f} vs reported {e} ({(a + b * p) / e - 1:+.1%})")
    for tag, e in zip("LMH", eps28):
        print(
            f"  world {tag}: EPS28 {e:g} ↔ NdPr {(e - a) / b:.0f} 万/吨 at today's volume, "
            f"{(e / PHASE2_VOLUME_X - a) / b:.0f} 万/吨 at phase-2 volume (×{PHASE2_VOLUME_X})"
        )
    for tag, p in (("5y mid", inp["ndpr_mid"]), ("regime mid", NDPR_REGIME_MID)):
        eps_mid = a + b * p
        pe_mid = window_pe(g1, n_win, g2, eps_mid / inp["bps_fwd"], r)
        print(f"对照坐标（A8）: {tag} {p:g} 万 -> EPS {eps_mid:.3f}, ROE {eps_mid / inp['bps_fwd']:.1%} "
              f"-> {pe_mid:.2f}x -> {eps_mid * disc * pe_mid:.2f}")
    print(f"对照坐标（A8）: trough × 1/r = {inp['eps_trough'] / r:.2f}; spot {inp['ndpr_now']:g} 万")
    ths = inp["eps28_ths"] * disc * window_pe(g1, n_win, g2, inp["eps28_ths"] / inp["bps_fwd"], r)
    print(f"numerator upgrade (同花顺 2028E {inp['eps28_ths']:g}): {ths:.2f} -> zone {zone_of(ths, L, M, H)}")
    r_imp = solve_r(lambda rr: eps_d[1] * window_pe(g1, n_win, g2, roe[1], rr) - inp["price"])
    eps_mid = a + b * inp["ndpr_mid"]
    print(f"market-implied r (M = price {inp['price']:g}, same numerator & growth structure) ≈ {r_imp:.2%} "
          f"({r_imp - r:+.1%} vs 篮 {baskets['r_perp']}); EPS needed at r={r:g}: {inp['price'] / (disc * pes[1]):.2f}; "
          f"pre-control centre {PRE_CONTROL_PRICE:g} on mid-cycle EPS {eps_mid:.3f}: E/P (g=0 single-stage) ≈ {eps_mid / PRE_CONTROL_PRICE:.1%}")
    for line in tier_report((scenario_L, M, H), pes, eps_d):
        print(line)
    print(
        f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.2%} V_opt/M=0 "
        f"numerator L/M={eps_d[0] / eps_d[1]:.2f} H/M={eps_d[2] / eps_d[1]:.2f} "
        f"| multiple ratio L/M={pes[0] / pes[1]:.3f} H/M={pes[2] / pes[1]:.3f}"
    )
    print(f"price={inp['price']:g} → zone={zone}")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
