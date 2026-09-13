#!/usr/bin/env python3
"""000338.SZ (Weichai Power) valuation eval — recompute anchors from frameworks/000338.SZ.md.

frameworks/000338.SZ.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: weichai_asymmetric_sotp_runrate_v2

Main ruler: an asymmetric three-leg SOTP.
  * core     = attributable NP - KION equity NP - large-bore engine NP,
               valued on a *reverse* cycle PE (trough earnings get the high
               multiple — Lynch's rule, and Weichai's own 2022 print: profit
               collapsed to 49.1亿 while own-year PE hit its 18.42 peak)
  * KION     = KION's own net income x 45.23% x KION's own forward PE, because
               that leg is priced in Frankfurt, not by China's truck cycle
  * M-series = units x realized unit price x net margin, on a growth multiple;
               the L scenario zeroes it out — it is an option, not a business
               line, at 3% of group revenue

V_opt is two named options, neither of which enters the base:
  * unverified M-series volume (16k) + growth PE, vs the measured 13.4k x core PE
  * SOFC at the 2027 200 MW capacity ceiling x Bloom's realised NI/MW, discounted
    one year.  Aftermarket 5x and the 2030 1 GW plan stay in stretched.

All three numerators come from the same distribution: Weichai's own realised
run-rates (FY2022 trough / TTM / 2Q26 quarter annualised).  The sell-side
consensus is deliberately unused — Longbridge's range has degenerated to a
single estimate, which cannot supply the two ends A2e-2a requires.

Guards beyond the anchor comparison:
  * reverse-multiple guard — pe_core must strictly decrease L->M->H.  A cyclical
    that discounts both the numerator and the multiple counts the cycle twice.
  * flat-multiple guard — with every multiple pinned at pe_core_m the ladder
    must still hold, proving the three tiers separate on numerators.
  * KION-share guard — the leg that motivates the whole SOTP must actually be
    ~10% of profit; if it drifts out of 8-12% the asymmetry claim needs redoing.
  * SOFC cross-check — bloom_ni_fy26 must sit within 10% of BE.US
    eps_fy0 x shares_diluted, and Weichai's 200 MW ceiling must be below
    Bloom's current plant.

Run:  python3 eval/000338.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report, reverse_ladder,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "000338.SZ.md"
BE_FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "BE.US.md"
FORMULA_ID = "weichai_asymmetric_sotp_runrate_v2"
YI = 1e8

# The KION leg is the reason this ticker is not valued on a group PE.
# If it stops being ~10% of profit, §1 属性 A has to be rewritten.
KION_SHARE_BAND = (0.08, 0.12)
BLOOM_NI_TOL = 0.10
# Diesel option's M-world credit, before blending with SOFC (which is 0 at M).
P_MS_M = 0.501

REQUIRED = [
    "price", "price_h", "shares", "bps", "fx_hkdcny", "fx_eurcny",
    "np_l", "np_m", "np_h",
    "kion_np_h1_eur", "kion_stake", "kion_l_factor", "pe_kion",
    "ms_units_l", "ms_units_m", "ms_units_h", "ms_price", "ms_npm",
    "pe_core_l", "pe_core_m", "pe_core_h",
    "pe_ms_l", "pe_ms_m", "pe_ms_h",
    "sofc_mw_h", "bloom_ni_fy26", "bloom_cap_mw", "fx_usdcny",
    "r_disc", "sofc_lag",
]


def legs(
    inp: dict[str, float],
    tag: str,
    flat_pe: float | None = None,
    *,
    base: bool = False,
) -> dict[str, float]:
    """One scenario -> three legs -> market value -> per-share anchor.

    flat_pe pins the core and M-series multiples for the flat-multiple guard;
    the KION leg keeps its own multiple because it is an external market price,
    not a policy choice of this framework.

    base=True: measured units × core PE (pe_ms_l). H volume is frozen at the
    last measured run-rate (ms_units_m). The unverified 16k + growth PE is
    V_opt, not the base (A2e-7).
    """
    kion = (
        inp["kion_np_h1_eur"] * 2.0 * inp["kion_stake"] * inp["fx_eurcny"]
        * (inp["kion_l_factor"] if tag == "l" else 1.0)
    )
    units = inp["ms_units_l"] if tag == "l" else inp["ms_units_m"] if base else inp[f"ms_units_{tag}"]
    ms_np = units * inp["ms_price"] * inp["ms_npm"]
    core = inp[f"np_{tag}"] - kion - ms_np

    pe_core = flat_pe if flat_pe is not None else inp[f"pe_core_{tag}"]
    if base and flat_pe is None:
        pe_ms = inp["pe_ms_l"]
    else:
        pe_ms = flat_pe if flat_pe is not None else inp[f"pe_ms_{tag}"]
    mv = core * pe_core + kion * inp["pe_kion"] + ms_np * pe_ms
    return {"kion": kion, "ms_np": ms_np, "core": core, "mv": mv,
            "anchor": mv / inp["shares"], "units": units, "pe_ms": pe_ms}


def sofc_v_opt(inp: dict[str, float]) -> float:
    """2027 200 MW ceiling x Bloom FY26 NI/MW, discounted sofc_lag years."""
    ni_usd = inp["sofc_mw_h"] * (inp["bloom_ni_fy26"] / inp["bloom_cap_mw"])
    v_t = ni_usd * inp["fx_usdcny"] * inp["pe_ms_h"] / inp["shares"]
    return v_t / (1.0 + inp["r_disc"]) ** inp["sofc_lag"]


def bloom_ni_crosscheck(inp: dict[str, float]) -> list[str]:
    """bloom_ni_fy26 must be the same FactSet FY26 NI that BE.US is sitting on."""
    if not BE_FRAMEWORK.exists():
        return [f"missing {BE_FRAMEWORK.name} — SOFC ceiling has no peer trajectory"]
    be = parse_inputs(BE_FRAMEWORK.read_text(encoding="utf-8"))
    missing = [k for k in ("eps_fy0", "shares_diluted") if k not in be]
    if missing:
        return [f"BE.US missing {missing} — cannot cross-check bloom_ni_fy26"]
    peer = be["eps_fy0"] * be["shares_diluted"]
    if abs(peer - inp["bloom_ni_fy26"]) > BLOOM_NI_TOL * inp["bloom_ni_fy26"]:
        return [
            f"bloom_ni_fy26 {inp['bloom_ni_fy26']:.3e} vs BE.US "
            f"eps_fy0×shares_diluted {peer:.3e} (>{BLOOM_NI_TOL:.0%})"
        ]
    return []


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # --- Step 1: ladders and the cyclical multiple policy --------------------
    errors += ladder("numerator (np)", inp["np_l"], inp["np_m"], inp["np_h"])
    if not (inp["ms_units_l"] <= inp["ms_units_m"] <= inp["ms_units_h"]):
        errors.append("M-series unit ladder violated")
    # A2/A2e-5: cyclical multiples run *against* the numerator.
    errors += reverse_ladder(
        "pe_core", inp["pe_core_l"], inp["pe_core_m"], inp["pe_core_h"]
    )
    errors += ladder("pe_ms", inp["pe_ms_l"], inp["pe_ms_m"], inp["pe_ms_h"])
    if errors:
        return report(errors, "FAIL (ladders)")

    S = {t: legs(inp, t, base=True) for t in ("l", "m", "h")}
    full = {t: legs(inp, t) for t in ("l", "m", "h")}

    # --- Step 2: the asymmetry claim must still hold -------------------------
    kion_share = S["m"]["kion"] / inp["np_m"]
    lo, hi = KION_SHARE_BAND
    if not (lo <= kion_share <= hi):
        errors.append(
            f"KION leg is {kion_share:.1%} of M numerator, outside {lo:.0%}-{hi:.0%} "
            "— §1 属性 A (35% revenue / ~10% profit) no longer holds"
        )
    if S["l"]["core"] <= 0:
        errors.append("L-scenario core profit <= 0 — check 口径")

    # --- Step 3: flat-multiple ladder ---------------------------------------
    flat = {t: legs(inp, t, flat_pe=inp["pe_core_m"], base=True)["anchor"]
            for t in ("l", "m", "h")}
    errors += ladder("flat-multiple", flat["l"], flat["m"], flat["h"])

    # --- Step 4: anchors (base = measured run-rate × core PE) ----------------
    L, M, H = (S[t]["anchor"] for t in ("l", "m", "h"))
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    v_ms = full["h"]["anchor"] - S["h"]["anchor"]
    v_sofc = sofc_v_opt(inp)
    v_opt = v_ms + v_sofc
    # SOFC is 0 in the M world (still MW-scale verification).  The diesel
    # option keeps its 0.501 credit; p_M is the value-weighted blend.
    p_ms_m = ((full["m"]["anchor"] - S["m"]["anchor"]) / v_ms) if v_ms else 0.0
    if abs(p_ms_m - P_MS_M) > 0.02:
        errors.append(f"diesel p_M {p_ms_m:.3f} drifted from {P_MS_M}")
    p_m = (p_ms_m * v_ms / v_opt) if v_opt else 0.0
    p_k = (0.0, p_m, 1.0)
    adj_band = [S[t]["anchor"] + pk * v_opt for t, pk in zip(("l", "m", "h"), p_k)]
    if abs(adj_band[0] - L) > 1e-9:
        errors.append(f"p leaked into the base: 表3 L {adj_band[0]:.4f} != {L:.4f}")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")
    if inp["bloom_cap_mw"] <= 0 or inp["sofc_mw_h"] <= 0:
        errors.append("SOFC capacity inputs must be positive")
    if inp["sofc_mw_h"] >= inp["bloom_cap_mw"]:
        errors.append(
            f"sofc_mw_h {inp['sofc_mw_h']:.0f} MW is not below Bloom's "
            f"{inp['bloom_cap_mw']:.0f} MW plant — the ceiling is no longer a "
            "fraction of a realised trajectory"
        )
    errors += bloom_ni_crosscheck(inp)

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"{'档':<3}{'归母':>10}{'凯傲腿':>9}{'大缸径台数':>12}{'大缸径净利':>11}"
          f"{'核心盘':>10}{'核心PE':>8}{'市值':>11}{'锚点':>8}")
    for t in ("l", "m", "h"):
        s = S[t]
        print(f"{t.upper():<3}{inp[f'np_{t}'] / YI:10.1f}{s['kion'] / YI:9.2f}"
              f"{s['units']:12.0f}{s['ms_np'] / YI:11.2f}{s['core'] / YI:10.1f}"
              f"{inp[f'pe_core_{t}']:8.2f}{s['mv'] / YI:11.0f}{s['anchor']:8.2f}")
    print(f"KION leg = {kion_share:.1%} of M numerator (band {lo:.0%}-{hi:.0%}) — "
          f"35% of revenue, so the SOTP is warranted")
    print(f"flat-multiple @pe={inp['pe_core_m']:g}: "
          f"L={flat['l']:.2f} M={flat['m']:.2f} H={flat['h']:.2f}")

    num_l, num_h = inp["np_l"] / inp["np_m"], inp["np_h"] / inp["np_m"]
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}"
          f" V_opt/M={v_opt / M:.1%}")
    ni_usd = inp["sofc_mw_h"] * (inp["bloom_ni_fy26"] / inp["bloom_cap_mw"])
    print(f"SOFC  {inp['sofc_mw_h']:.0f} MW x ${inp['bloom_ni_fy26'] / inp['bloom_cap_mw']:,.0f}/MW"
          f" = ${ni_usd / 1e6:.0f}M NI  ->  V_sofc={v_sofc:.2f}  (lag {inp['sofc_lag']:.0f}y)")
    print(f"表3  V_opt={v_opt:.2f} (ms {v_ms:.2f} + sofc {v_sofc:.2f})"
          f"  p_k={p_k[0]:.2f}/{p_k[1]:.3f}/{p_k[2]:.2f}  "
          + "  ".join(
              f"{n}:{S[t]['anchor']:.2f}+{pk:.3f}xV={a:.2f}"
              for n, t, pk, a in zip("LMH", ("l", "m", "h"), p_k, adj_band)))
    if v_opt > 0 and inp["price"] > H:
        print(f"     市价隐含 p = {(inp['price'] - H) / v_opt:.2f}")
    print(f"分子比 L/M={num_l:.2f} H/M={num_h:.2f} | "
          f"倍数比 L/M={(L / M) / num_l:.2f} H/M={(H / M) / num_h:.2f}")
    print(f"price={inp['price']} zone={zone}")
    fx = inp["fx_hkdcny"]
    print(f"H股对照(HKD): L={L / fx:.2f} M={M / fx:.2f} H={H / fx:.2f} "
          f"| price_h={inp['price_h']} zone_h={zone_of(inp['price_h'], L / fx, M / fx, H / fx)}")
    print(f"H/A = {inp['price_h'] * fx / inp['price']:.3f}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
