#!/usr/bin/env python3
"""600111.SH (China Northern Rare Earth) valuation eval.

frameworks/600111.SH.md is the source of truth.
formula_id: nre_consensus_fy28_disc_gordon_bandedge_v1

Numerator = the FY2028 sell-side range (two houses, low/mean/high), discounted
one year (FY+2 → t=1, construction §3).  This is the ②-b fallback of
valuation-rules: the 5-year NdPr-price mid-cycle numerator (A8) sits 57% below
the consensus mean, only half of which the one measured structural variable
(phase-2 smelting capacity) explains, so the framework swaps to the consensus
three points and hangs falsifiers on them (A1).

Multiples are Gordon-generated (valuation-rules「永续增长口径」): ROE per tier =
EPS28 / forward BPS, PE_x = perpetual_pe(g2, ROE_x, r) with ONE flat g2.  g2 is
the own same-earnings band edge reverse-solved at the M-tier ROE (tier 4,
「自身实测带反解」): the GS demand-CAGR value (4.4%, tier 3) generated a multiple
below what the market paid on TTM EPS 1.48–1.83 (8 months, 2023-01→08), so
裁决顺序 ③ pushes it to the band's lower edge (A3).

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
    check_branch,
    check_g_cap,
    check_r,
    implied_g_retaining,
    payout_gap,
    perpetual_pe,
)
from lib.inputs import check_against_stated, check_missing, ladder, parse_inputs  # noqa: E402
from lib.tiers import flat_multiple_ladder, report as tier_report  # noqa: E402
from lib.zones import zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "600111.SH.md"
FORMULA_ID = "nre_consensus_fy28_disc_gordon_bandedge_v1"
MIN_R_MINUS_G = 0.02
TOL = 0.05
G2_TOL = 1e-4

# A2 bridge reproduction: (NdPr oxide annual average 万/吨, reported EPS).  The
# bridge was fitted on four points; the two full formula-regime years that are
# not the trough are the reproduction gate (±20%).
BRIDGE_GATE = {"FY2023": (53.0, 0.6558), "FY2025": (51.45, 0.6227)}
BRIDGE_TOL = 0.20
# Bridge worlds: consensus EPS28 read back into NdPr price at today's volume and
# at the phase-2 run-rate (31 万吨 vs ~20 → ×1.55); printed, not anchors.
PHASE2_VOLUME_X = 1.55

REQUIRED = [
    "price", "shares", "bps", "bps_fwd",
    "eps28_l", "eps28_m", "eps28_h",
    "r_disc", "n_disc", "r_perp",
    "g2_macro", "pe_band_lo", "pe_band_hi", "g2",
    "payout_obs", "pb_floor",
    "bridge_a", "bridge_b", "ndpr_mid", "ndpr_now", "eps_trough",
]


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

    r = inp["r_perp"]
    eps28 = (inp["eps28_l"], inp["eps28_m"], inp["eps28_h"])
    errors += ladder("eps28", *eps28)
    errors += check_r(r, "r_perp")
    for k in ("g2", "g2_macro"):
        errors += check_g_cap(inp[k], k)
    if r - inp["g2"] < MIN_R_MINUS_G:
        errors.append(f"r − g2 = {r - inp['g2']:.4f} < {MIN_R_MINUS_G} (pole)")
    for k in inp:
        if k.startswith("p_"):
            errors.append(f"probability-style input {k} in Inputs")

    # --- Gordon multiples --------------------------------------------------------
    roe = tuple(e / inp["bps_fwd"] for e in eps28)
    # g2 must be exactly the band-edge reverse-solve at ROE_M (A3), and the
    # dividend branch must agree with the observed payout.
    g2_edge, conditioned = implied_g_retaining(inp["pe_band_lo"], roe[1], r)
    if not conditioned:
        errors.append(f"band-edge reverse-solve ill-conditioned at ROE_M {roe[1]:.3f}")
    if abs(inp["g2"] - g2_edge) > G2_TOL:
        errors.append(f"g2={inp['g2']} vs band-edge reverse-solve {g2_edge:.5f}")
    errors += check_branch(inp["g2"], roe[1], r, inp["payout_obs"], "M")
    pes = tuple(perpetual_pe(inp["g2"], x, r) for x in roe)
    # Guardrail (裁决顺序 ③): M and H must sit inside the same-earnings band.  L
    # carries the M-tier g by rule (L 世界不含回归) and may fall just under the edge.
    for tag, pe in (("M", pes[1]), ("H", pes[2])):
        if not (inp["pe_band_lo"] - 1e-6 <= pe <= inp["pe_band_hi"] + 1e-6):
            errors.append(
                f"guardrail: PE_{tag}={pe:.2f} outside same-earnings band "
                f"[{inp['pe_band_lo']}, {inp['pe_band_hi']}] — BLOCKED, do not twist g"
            )

    disc = (1.0 + inp["r_disc"]) ** (-inp["n_disc"])
    eps_d = tuple(e * disc for e in eps28)
    scen = tuple(e * pe for e, pe in zip(eps_d, pes))
    floor = inp["pb_floor"] * inp["bps"]
    scenario_L = scen[0]
    L, M, H = max(scenario_L, floor), scen[1], scen[2]
    A, B = (L + M) / 2, (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)
    if not (L < M < H):
        errors.append(f"L<M<H violated ({L:.2f}/{M:.2f}/{H:.2f})")
    flat_err, flat = flat_multiple_ladder(eps_d, pes[1])
    errors += flat_err
    flat = (max(flat[0], floor), flat[1], flat[2])
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken at PE_M={pes[1]:.2f}: {flat}")

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
    print(f"eps28 L/M/H = {eps28[0]:g}/{eps28[1]:g}/{eps28[2]:g}  × disc {disc:.4f} → {eps_d[0]:.3f}/{eps_d[1]:.3f}/{eps_d[2]:.3f}")
    print(f"L/M/H = {L:.2f}/{M:.2f}/{H:.2f}  A/B = {A:.2f}/{B:.2f}")
    winner = "floor" if floor > scenario_L else "scenario_L"
    print(f"floor={floor:.2f} scenario_L={scenario_L:.2f} winner={winner}")
    modelled, gap = payout_gap(inp["g2"], roe[1], inp["payout_obs"])
    print(
        f"gordon: r={r:g} g2={inp['g2']:g} flat (band-edge reverse-solve at ROE_M, tier 4; "
        f"g2_macro {inp['g2_macro']:g} referenced, superseded) "
        f"roe={roe[0]:.3f}/{roe[1]:.3f}/{roe[2]:.3f} -> pe={pes[0]:.2f}/{pes[1]:.2f}/{pes[2]:.2f} "
        f"vs same-earnings band [{inp['pe_band_lo']}, {inp['pe_band_hi']}] (spread = ROE term only); "
        f"payout_gap modelled {modelled:.0%} vs paid {inp['payout_obs']:.0%} = {gap:+.0%}"
    )
    for dg in (-0.01, 0.01):
        g = min(inp["g2"] + dg, 0.06)
        alt = [e * perpetual_pe(g, x, r) for e, x in zip(eps_d, roe)]
        z = zone_of(inp["price"], max(alt[0], floor), alt[1], alt[2])
        print(f"  g2 {g:.2%} -> M {alt[1]:.2f}, H {alt[2]:.2f}, zone {z}")
    for year, (p, e) in BRIDGE_GATE.items():
        print(f"bridge {year}: fit {a + b * p:.3f} vs reported {e} ({(a + b * p) / e - 1:+.1%})")
    for tag, e in zip("LMH", eps28):
        print(
            f"  world {tag}: EPS28 {e:g} ↔ NdPr {(e - a) / b:.0f} 万/吨 at today's volume, "
            f"{(e / PHASE2_VOLUME_X - a) / b:.0f} 万/吨 at phase-2 volume (×{PHASE2_VOLUME_X})"
        )
    eps_mid = a + b * inp["ndpr_mid"]
    pe_mid = perpetual_pe(inp["g2"], eps_mid / inp["bps"], r)
    print(
        f"对照坐标（A8）: 5y mid {inp['ndpr_mid']:g} 万 -> EPS {eps_mid:.3f}, ROE {eps_mid / inp['bps']:.1%} (≈ r, ill-conditioned) "
        f"-> {pe_mid:.2f}x -> {eps_mid * pe_mid:.2f}; trough × 1/r = {inp['eps_trough'] / r:.2f}; spot {inp['ndpr_now']:g} 万"
    )
    pay_m = 1.0 - inp["g2"] / roe[1]
    rg = eps_d[1] * pay_m / inp["price"]
    print(f"market-implied on the same numerator: r − g = {rg:.2%} -> r ≈ {rg + inp['g2']:.1%} at g2 {inp['g2']:g}")
    for line in tier_report((scenario_L, M, H), pes, eps_d):
        print(line)
    print(
        f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.2%} V_opt/M=0 "
        f"numerator L/M={eps_d[0] / eps_d[1]:.2f} H/M={eps_d[2] / eps_d[1]:.2f} "
        f"| multiple ratio L/M={pes[0] / pes[1]:.2f} H/M={pes[2] / pes[1]:.2f}"
    )
    print(f"price={inp['price']:g} → zone={zone}")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
