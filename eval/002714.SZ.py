#!/usr/bin/env python3
"""002714.SZ (Muyuan Foods) valuation eval.

frameworks/002714.SZ.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading — the digest and the app zone on live quotes.

formula_id: muyuan_margin_per_kg_point_gordon_v1

Main ruler: one company-wide leg.  EPS_x = parent net profit per kg sold (m_x)
x kg sold (policy-locked 7,800万头 x 125 kg) / shares outstanding.

    M = EPS_M x perpetual_pe(g2 = 0, ROE_M, r)       center margin forever
    L = (EPS_L + M) / (1 + r)                         trough lasts one 12-month
                                                      period, then valued at M
    H = EPS_H/(1+r) + EPS_H/(1+r)^2 + M/(1+r)^2       peak lasts two years, then M

Both ends are point semantics (valuation-rules「周期票 regime / point 双口径」):
the measured worst / best rolling four quarters, recovering to the center in
one year (2018->2019, 2023->2024) and decaying after two (the consensus deck
years 2027-28).  The library cannot express either path here —
`recovery_two_stage_pe` needs a positive trough EPS (this trough is a loss)
and `decay_two_stage_pe` is [待建] — so both are written as explicit
discounted cash-flow lines.

r is basket 4 (reached from the initial basket 6 by the ③ step-down; M at
basket 4 still sits below the clean equal-earnings band floor, and the user
approved landing on 2026-09-27 — the ③ row, the band-edge-r table 表2′ and the
recheck conditions are disclosures, not a status).

Run:  python3 frameworks/eval/002714.SZ.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import BASKET_R, basket_r, check_g_cap, check_r, perpetual_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, outputs_section, parse_baskets,
    parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "002714.SZ.md"
FORMULA_ID = "muyuan_margin_per_kg_point_gordon_v1"
YI = 1e8
WAN = 1e4
TOL = 0.05

# Measured recovery / decay lengths (A3, A15).  Changing them is a framework
# correction, not a parameter tweak, so they live here rather than in Inputs.
N_RECOVERY_L = 1
N_DECAY_H = 2
FROM_BASKET = 6  # initial basket before the ③ step-down (A10)

REQUIRED = [
    "shares_total", "shares_treasury", "heads_m", "kg_per_head",
    "m_l", "np_l_4q", "kg_l_4q",
    "m_center_total", "np_parent_fy25", "np_total_fy25",
    "m_h", "np_h_4q", "kg_h_4q",
    "bps", "r_perp", "g2", "pe_band_min", "pe_band_max",
    "k_l", "k_m", "k_h", "m_consensus_2027",
]


def band(eps: dict[str, float], roe_m: float, r: float, g2: float) -> tuple[float, float, float, float]:
    """(L, M, H, PE_M) at discount rate r — the one formula every band here uses."""
    pe_m = perpetual_pe(g2, roe_m, r)
    m = eps["M"] * pe_m
    # Trough: one year of the loss, then the business is worth M again.
    ell = (eps["L"] + m) / (1 + r) ** N_RECOVERY_L
    # Peak: two years of peak earnings, then back to M.
    h = sum(eps["H"] / (1 + r) ** t for t in range(1, N_DECAY_H + 1)) + m / (1 + r) ** N_DECAY_H
    return ell, m, h, pe_m


def stated_triple(md: str, label: str) -> tuple[float, float, float] | None:
    """`<label> x / y / z` on one Outputs line (table 2′, contrast, sensitivity rows)."""
    num = r"(-?[0-9]+(?:\.[0-9]+)?)"
    m = re.search(re.escape(label) + r"[^\n0-9]*?" + num + r"\s*/\s*" + num + r"\s*/\s*" + num,
                  outputs_section(md))
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def check_triple(md: str, label: str, computed: tuple[float, float, float]) -> list[str]:
    said = stated_triple(md, label)
    if said is None:
        return [f"stated triple '{label}' not found in Outputs"]
    bad = [f"{s} vs {c:.4f}" for s, c in zip(said, computed) if abs(s - c) > TOL]
    return [f"'{label}': {', '.join(bad)}"] if bad else []


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # --- basket, g, retention guards ---------------------------------------------
    baskets = parse_baskets(md)
    r = inp["r_perp"]
    if baskets.get("r_perp") != 4:
        errors.append(f"r_perp: Inputs source cell must name 篮 4 first, got {baskets.get('r_perp')} (A10)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    extra = sorted(k for k in baskets if k != "r_perp")
    if extra:
        errors.append(f"only r_perp may carry a 篮 N tag; also found {extra} (AGENTS.md 篮子声明)")
    errors += check_g_cap(inp["g2"], r, "g2")
    ks = (inp["k_l"], inp["k_m"], inp["k_h"])
    if not (ks[2] >= ks[1] >= ks[0]):
        errors.append(f"cyclical k must satisfy k_H >= k_M >= k_L, got {ks}")

    # --- numerator: margin per kg x kg / shares -------------------------------------
    shares = inp["shares_total"] - inp["shares_treasury"]
    kg = inp["heads_m"] * WAN * inp["kg_per_head"]
    conv = inp["np_parent_fy25"] / inp["np_total_fy25"]
    m = {"L": inp["m_l"], "M": inp["m_center_total"] * conv, "H": inp["m_h"]}
    # m_l / m_h are the measured rolling-four-quarter margins; keep them tied to the sums.
    for tag, np4, kg4 in (("L", "np_l_4q", "kg_l_4q"), ("H", "np_h_4q", "kg_h_4q")):
        measured = inp[np4] / inp[kg4]
        if abs(measured - m[tag]) > 0.01:
            errors.append(f"m_{tag.lower()}={m[tag]} vs measured {inp[np4]}/{inp[kg4]} = {measured:.4f}")
    eps = {t: m[t] * kg / shares for t in "LMH"}
    errors += ladder("EPS", eps["L"], eps["M"], eps["H"])

    roe_m = eps["M"] / inp["bps"]
    if roe_m - r < 0.03:
        errors.append(f"ROE_M {roe_m:.2%} not in the monotone zone at r {r:.0%} — 1/r form not allowed (A6)")

    # --- anchors ---------------------------------------------------------------------
    L, M, H, pe_m = band(eps, roe_m, r, inp["g2"])
    k_after = (L * (1 - ks[0]), M * (1 - ks[1]), H * (1 - ks[2]))
    L, M, H = k_after
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}"])
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # 2c flat-multiple ladder: every tier at PE_M.
    flat = tuple(eps[t] * pe_m for t in "LMH")
    errors += ladder("flat-multiple anchors", *flat)

    # --- ③: clean equal-earnings band, step-down path, band-edge r ------------------
    if pe_m >= inp["pe_band_min"]:
        errors.append(
            f"PE_M {pe_m:.2f} is back inside the band floor {inp['pe_band_min']} — the ③ disclosure "
            "row, 表2′ and A11 are stale; rewrite them"
        )
    path = {b: perpetual_pe(inp["g2"], roe_m, basket_r(b)) for b in range(FROM_BASKET, 3, -1)}
    b6 = band(eps, roe_m, basket_r(FROM_BASKET), inp["g2"])[:3]
    errors += check_triple(md, f"初分篮 {FROM_BASKET}（13%）→", b6)
    r_edge = 1 / inp["pe_band_min"]
    edge = band(eps, roe_m, r_edge, inp["g2"])[:3]
    errors += check_triple(md, "带边带", edge)
    ea, eb = cut_points(*edge)

    # --- sensitivity g2 ±1pp (L/M/H only) ---------------------------------------------
    g_up = band(eps, roe_m, r, inp["g2"] + 0.01)[:3]
    g_dn = band(eps, roe_m, r, inp["g2"] - 0.01)[:3]
    errors += check_triple(md, "g2 +1pp →", g_up)
    errors += check_triple(md, "g2 −1pp →", g_dn)

    # --- ②-b consensus check -----------------------------------------------------------
    c27 = inp["m_consensus_2027"]
    if not (m["M"] <= c27 <= m["H"]):
        errors.append(f"②-b: 2027 consensus margin {c27} outside [M {m['M']:.3f}, H {m['H']:.3f}] — H must be rebuilt")
    dev = 1 - m["M"] / c27

    # --- report ------------------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"shares {shares:,.0f} (total - treasury); kg sold {kg / YI:.2f}亿; 归母转化 {conv:.4f}")
    print(f"basket: r_perp 篮 {baskets.get('r_perp')} {BASKET_R[4][0]} r={r:g}; g2={inp['g2']:g}; "
          f"ROE_M {roe_m:.2%} (monotone, ROE-r {roe_m - r:+.1%}); PE_M {pe_m:.3f}x")
    for t, lab in (("L", "worst 4Q 2023Q2-2024Q1"), ("M", "center 2.0/kg x 归母转化"), ("H", "best 4Q 2024Q3-2025Q2")):
        print(f"{t}: {lab:26} m={m[t]:+.4f}/kg  EPS={eps[t]:+.4f}")
    print(f"k L/M/H = {ks[0]:g}/{ks[1]:g}/{ks[2]:g} (retention bucket A)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"ratios: L/M={L / M:.4f} H/M={H / M:.4f} (H-L)/2M={(H - L) / (2 * M):.4f} V_opt/M 0 | "
          f"分子比 L={eps['L'] / eps['M']:.3f} H={eps['H'] / eps['M']:.3f}")
    print("flat-multiple ladder @PE_M: " + " / ".join(f"{v:.2f}" for v in flat) + " (2c OK)")
    print(f"regime contrast (no normalisation): L {flat[0]:.2f} (loss -> n/a) / H {flat[2]:.2f} (stretched pressure)")
    print(f"③ step-down path (g2 {inp['g2']:g}): " + " / ".join(f"篮 {b} {pe:.2f}x" for b, pe in path.items())
          + f" — all below clean band floor {inp['pe_band_min']} (band [{inp['pe_band_min']}, {inp['pe_band_max']}]);"
          " user-approved landing 2026-09-27 (A11)")
    print(f"contrast 初分篮 {FROM_BASKET} 13%: " + " / ".join(f"{v:.2f}" for v in b6))
    print(f"表2′ band-edge r {r_edge:.4%}: " + " / ".join(f"{v:.2f}" for v in edge) + f"  A′={ea:.2f} B′={eb:.2f}")
    print("g2 +1pp: " + " / ".join(f"{v:.2f}" for v in g_up) + " | g2 -1pp: " + " / ".join(f"{v:.2f}" for v in g_dn))
    print(f"②-b: 2027 consensus margin {c27} in [M {m['M']:.3f}, H {m['H']:.3f}]; M sits {dev:.0%} below it "
          "(>20% -> measured structural explanation + trigger, A13/A16)")
    print("rf block: CNY segment of _AXIS.rates is [待建] — no rates readings")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
