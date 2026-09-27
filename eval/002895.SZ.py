#!/usr/bin/env python3
"""002895.SZ (Chuanheng) valuation eval.

frameworks/002895.SZ.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc states
no current price or zone (the digest and the app zone on live quotes).

formula_id: chuanheng_map_ladder_margin_bridge_flat_pe_v1

Main ruler: the 2026H1 revenue/cost split is shifted along the MAP ladder from
_AXIS.phosphate-chain.  Revenue moves by (price delta x expo), cost by
(price delta x expo x pass_through); the resulting half-year gross-profit delta
is annualised, converted to net profit via conv, and added to the M-scenario
net profit — which itself is 2026H1 net profit divided by FY2025's H1 share
(42.54%), not H1 x2, because this company earns more in the second half.

This is the *direct-drive* mount on the phosphate axis; its peer 600096.SH
measures an elasticity of only 0.049 to the same ladder.  That divergence is
the point of the axis, so the ladder is checked against both the axis file and
the peer framework: editing one side alone turns this eval red.

pass_through = 0.5 is the framework's weakest single input (A5) — it puts the
L-scenario gross margin at 19.26%, below any year this company has actually
printed.  The guard here cannot validate a judgement call, so it does the next
best thing: it asserts the H scenario stays under the FY2022 peak margin of
44.44%, which is where an over-optimistic pass-through would first show up.

The basket r (篮 6, 13%) does not enter the flat-PE deck (A14).  It is a
disclosure-only `r_perp` row: the script checks the basket tag and value agree
(`check_r`), prints the 篮 6 contrast band at 1/r and the PB=1 floor (disclosed, never max()-ed into L).

Run:  python3 frameworks/eval/002895.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import check_phosphate_mount  # noqa: E402
from lib.gordon import check_r, g_cap  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "002895.SZ.md"
PEER = Path(__file__).resolve().parents[2] / "frameworks" / "600096.SH.md"
FORMULA_ID = "chuanheng_map_ladder_margin_bridge_flat_pe_v1"
YI = 1e8

NP_M_SEASONAL_YI = 13.1287  # 2026H1 归母 5.5849亿 ÷ FY2025 H1 share 42.54%
NP_M_TOL_YI = 0.05
GM_PEAK_FY2022 = 0.4444  # FY2022 gross margin — the ceiling for H

REQUIRED = [
    "shares", "rev_h1", "gm_rate_h1", "op_h1", "eps_h1",
    "h1_share_fy", "map_l", "map_m", "map_h",
    "expo", "pass_through", "conv", "pe_l", "pe_m", "pe_h",
    "bps", "r_perp",
]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    errors += ladder("MAP", inp["map_l"], inp["map_m"], inp["map_h"])
    errors += check_phosphate_mount(
        (inp["map_l"], inp["map_m"], inp["map_h"]),
        peer_md=PEER.read_text(encoding="utf-8"),
    )
    if not (0.0 < inp["expo"] <= 1.0):
        errors.append(f"expo={inp['expo']} outside (0,1]")
    if not (0.0 <= inp["pass_through"] <= 1.0):
        errors.append(f"pass_through={inp['pass_through']} outside [0,1]")
    if not (0.0 < inp["conv"] < 1.0):
        errors.append(f"conv={inp['conv']} outside (0,1)")
    if not (inp["pe_l"] == inp["pe_m"] == inp["pe_h"]):
        errors.append(
            f"PE band must be flat (A6): {inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']}"
        )
    # A14: r is disclosure only (flat PE deck), but the basket tag and the value must agree.
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N in the Inputs source cell (valuation-rules.md「§r 篮子」)")
    r = inp["r_perp"]
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    if errors:
        return report(errors)

    # --- the ruler -------------------------------------------------------------
    gp_h1 = inp["rev_h1"] * inp["gm_rate_h1"]
    cost_h1 = inp["rev_h1"] - gp_h1
    np_h1 = inp["eps_h1"] * inp["shares"] / YI
    np_m = np_h1 / inp["h1_share_fy"]

    def scenario(map_px: float, pe: float):
        d = (map_px - inp["map_m"]) / inp["map_m"]
        rev = inp["rev_h1"] * (1.0 + d * inp["expo"])
        cost = cost_h1 * (1.0 + d * inp["expo"] * inp["pass_through"])
        gp = rev - cost
        dgp_yr = 2.0 * (gp - gp_h1)
        npp = np_m + dgp_yr * inp["conv"]
        eps = npp * YI / inp["shares"]
        return rev, gp, gp / rev, dgp_yr, npp, eps, eps * pe

    sc_l = scenario(inp["map_l"], inp["pe_l"])
    sc_m = scenario(inp["map_m"], inp["pe_m"])
    sc_h = scenario(inp["map_h"], inp["pe_h"])

    if abs(sc_m[4] - NP_M_SEASONAL_YI) > NP_M_TOL_YI:
        errors.append(
            f"baseline closure broken: M net profit {sc_m[4]:.4f}亿 vs seasonal "
            f"restatement {NP_M_SEASONAL_YI}亿"
        )
    if sc_h[2] > GM_PEAK_FY2022:
        errors.append(
            f"H gross margin {sc_h[2]:.4f} exceeds FY2022 peak {GM_PEAK_FY2022} — "
            "no longer a modelled upper edge"
        )

    L, M, H = sc_l[6], sc_m[6], sc_h[6]
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}"])

    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # --- report ----------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(
        f"axis OK vs _AXIS.phosphate-chain and peer 600096.SH: MAP "
        f"{inp['map_l']:g}/{inp['map_m']:g}/{inp['map_h']:g} 元/吨"
    )
    print(
        f"expo={inp['expo']:g} pass_through={inp['pass_through']:g} "
        f"np_M={np_m:.4f}亿 (H1 {np_h1:.4f} ÷ {inp['h1_share_fy']:.4f})"
    )
    for tag, sc, px in (("L", sc_l, inp["map_l"]), ("M", sc_m, inp["map_m"]), ("H", sc_h, inp["map_h"])):
        print(
            f"{tag}: map={px:>6.0f}元/吨  rev_h1={sc[0]:6.2f}  gp_h1={sc[1]:6.2f}  "
            f"gm={sc[2]:7.2%}  Δgp_yr={sc[3]:+7.2f}  np={sc[4]:6.2f}亿  "
            f"eps={sc[5]:.4f}  anchor={sc[6]:.4f}"
        )
    per_100 = (
        2.0 * (100.0 / inp["map_m"])
        * (inp["rev_h1"] * inp["expo"] - cost_h1 * inp["expo"] * inp["pass_through"])
        * inp["conv"] * YI / inp["shares"] * inp["pe_m"]
    )
    print(f"sensitivity: +100元/吨 MAP -> anchor {per_100:+.2f} CNY")
    print(f"pe={inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']} (flat)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"ratios: L/M={L / M:.4f} H/M={H / M:.4f} (H-L)/2M={(H - L) / (2 * M):.4f} "
        f"| 分子比 L={sc_l[5] / sc_m[5]:.4f} H={sc_h[5] / sc_m[5]:.4f}"
    )
    # A14: 篮 6 contrast band at 1/r, ROE per tier vs r; floor disclosed only.
    peak_pe = 1 / r
    eps_l, eps_m, eps_h = sc_l[5], sc_m[5], sc_h[5]
    roe_m = eps_m / inp["bps"]
    print(
        f"r_perp {r:g} (篮 {baskets.get('r_perp')}), disclosure only; g_cap={g_cap(r):.2f} (no g2 row); "
        f"1/r={peak_pe:.2f}x contrast band "
        f"{eps_l * peak_pe:.2f}/{eps_m * peak_pe:.2f}/{eps_h * peak_pe:.2f} "
        f"ROE {eps_l / inp['bps']:.1%}/{roe_m:.1%}/{eps_h / inp['bps']:.1%}"
    )
    print(f"floor(PB=1.0)={inp['bps']:.2f} (disclosure only, L stays {L:.2f})")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
