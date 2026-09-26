#!/usr/bin/env python3
"""000933.SZ (Shenhuo Coal & Power) valuation eval.

frameworks/000933.SZ.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc states
no current price or zone (the digest and the app zone on live quotes).

formula_id: shenhuo_al_spread_gm_bridge_gordon_v5

Main ruler: the shared gross-margin bridge (eval/lib/al_bridge.py) on the
aluminium spread axis.  M is the 2026H1 filing annualised; L and H are M moved
by 151.9万吨 x the axis's spread steps (−4,629 / +1,028 元/吨) through the
marginal conversion rate.  L/H only move the aluminium-spread term; coal /
trade / processing are *not* scenario-modelled (no segment GM — there is no
measured "coal@M" to freeze).  Whatever those legs contributed to
consolidated NP_M stays inside NP_L/NP_H by omission (A6).  Each tier's
multiple is Gordon on the axis g rows (all 0%: L rung 4,250 is a GS 2027E
supply-glut *level* that may persist; IAI 3.3% is sensitivity only) at the
tier's own forward ROE, with r the basket the framework names for the single
leg (篮 6 周期商品, 13% → flat 1/r = 7.69×; valuation-rules「§r 篮子」,
gordon.BASKET_R).  The PB floor is disclosed, never max()'d into L.  The L
numerator (54.3亿) coincides with 2023H1 printed but is the axis regime —
g_L=0, not the 谷底档 recovery stage.  Open item: L may be optimistic vs a
world where coal also troughs (A6/A14).

Shenhuo carries a coal segment, and 2025H1 was a trough in *both* coal and
aluminium, on top of a high-alumina half for a company that buys its alumina —
its five-year H1 margin series runs 36.17 / 19.86 / 24.44 / 27.07 / 35.61, so
2023H1 and 2022H1 both sit *above* 2025H1 despite lower aluminium prices.  The
axis's L world moves only the smelting spread and freezes alumina low, so that
half-year is *worse* than L and is read back as the deep_discount reference,
not as the anchor.  The guard below asserts that ordering: if the k fitting
point ever stops being the worse corner, A4's story has changed and the
reference must be re-opened, not silently kept.

Run:  python3 frameworks/eval/000933.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.al_bridge import (  # noqa: E402
    REQUIRED, anchors, bridge, check_gordon, check_regression, flat_ladder,
    multiples, pb_floor,
)
from lib.axes import check_al_mount  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "000933.SZ.md"
FORMULA_ID = "shenhuo_al_spread_gm_bridge_gordon_v5"

GP_M_FILING = 179.3  # 亿 CNY, 2026H1 x2 at 36.17%
NP_M_FILING = 95.6   # 亿 CNY, 2026H1 归母 47.81 x2
SHARES_STATIC = 22.49  # 亿股, LB static total_shares 2,249,004,399 (A14)
CONSENSUS_TP = 32.05  # 一致目标价 = 7.5x M EPS ≈ M anchor at 1/r (A8)
NP_TROUGH_2023H1 = 54.78  # 亿 CNY, 2023H1 归母 27.39 x2 — deep_discount pressure coordinate only (A15)


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    baskets = parse_baskets(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    errors += ladder("smelting spread", inp["spread_l"], inp["spread_m"], inp["spread_h"])
    errors += check_al_mount((inp["spread_l"], inp["spread_m"], inp["spread_h"]))
    errors += check_regression(inp, GP_M_FILING, NP_M_FILING)
    # A16: r must be the basket the Inputs row names, not just any basket value.
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (AGENTS.md 篮子声明)")
    errors += check_gordon(inp, baskets.get("r_perp"))
    if abs(inp["shares"] - SHARES_STATIC) > 0.05:
        errors.append(f"shares {inp['shares']} != LB static total_shares {SHARES_STATIC}亿 (A14)")
    if errors:
        return report(errors)

    (L, M, H), eps = anchors(inp)
    pes, roes = multiples(inp)
    errors += flat_ladder(eps)

    br = bridge(inp)
    np_l = br["np"][0]
    # A4: the coal-and-alumina double trough must sit below the spread-only L
    # world.  Read straight from the bridge so a rolled fitting point is caught.
    if inp["np_ref"] >= np_l:
        errors.append(
            f"k fitting point {inp['np_ref']:.1f}亿 >= scenario L {np_l:.1f}亿 — "
            "2025H1 (coal + aluminium trough, high alumina) must be the worse "
            "corner; if it is not, A4's reference story must be re-opened"
        )

    # Floor is disclosed only (A10): scenario L must clear it, never max() with it.
    floor, floor_errors = pb_floor(inp, L)
    errors += floor_errors

    A, B = cut_points(L, M, H)
    errors += check_against_stated(
        md, {"L": L, "M": M, "H": H, "A": A, "B": B}, None
    )

    r = inp["r_perp"]
    flat = [e * pes[1] for e in eps]
    trough_perp = eps[0] / r
    print(f"000933.SZ  L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}")
    print(f"  r_perp {r:.1%} = 篮 {baskets['r_perp']}  "
          f"EPS {eps[0]:.3f}/{eps[1]:.3f}/{eps[2]:.3f}  k={br['k']:.4f}  "
          f"ROE {roes[0]:.1%}/{roes[1]:.1%}/{roes[2]:.1%}  "
          f"PE {pes[0]:.2f}/{pes[1]:.2f}/{pes[2]:.2f}  guardrail [{inp['pe_own_min']}, {inp['pe_own_max']}] OK")
    print(f"  Gordon g (axis rows) L {inp['g2_l']:.1%} | M {inp['g2_m']:.1%} | H {inp['g2_h']:.1%}; "
          f"L numerator {np_l:.1f}亿 = axis L rung (regime), coincides with printed 2023H1 {NP_TROUGH_2023H1:.1f}亿 (A15)")
    print(f"  L/M={L/M:.3f} = 分子比 {eps[0]/eps[1]:.3f} x 倍数比 {pes[0]/pes[1]:.3f} | "
          f"H/M={H/M:.3f} = 分子比 {eps[2]/eps[1]:.3f} x 倍数比 {pes[2]/pes[1]:.3f} | "
          f"width {(H-L)/(2*M):.1%} | V_opt/M 0")
    print(f"  flat-multiple ladder @PE_M {pes[1]:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    # 表1b：合并残差底座 = NP_L（未拆；非「煤@M」测值）；铝增量 = NP_x − NP_L
    base_np = np_l
    al_np = (0.0, br["np"][1] - base_np, br["np"][2] - base_np)
    base_px = tuple(base_np / inp["shares"] * pe for pe in pes)
    al_px = tuple(al_np[i] / inp["shares"] * pes[i] for i in range(3))
    print(f"  表1b 合并残差底座 {base_px[0]:.2f}/{base_px[1]:.2f}/{base_px[2]:.2f} + "
          f"铝价差 {al_px[0]:.2f}/{al_px[1]:.2f}/{al_px[2]:.2f} "
          f"(不对煤做情景; 底座≠煤@M测值)")
    coal_delta_np = 16.3 * br["k"]  # A4③ trough→M residual lower bound
    l_coal = (base_np - coal_delta_np) / inp["shares"] * pes[1]
    print(f"  A14 示意: 若扣A4③残差 {coal_delta_np:.1f}亿(非煤分部利润) → L≈{l_coal:.2f} "
          f"@PE_M (未升格; 无分部毛利)")
    print(f"  deep_discount 压力坐标: 轴 L 谷底永续 x 1/r = {trough_perp:.2f}; 印过的 2023H1 谷底 x 1/r = "
          f"{NP_TROUGH_2023H1 / inp['shares'] / r:.2f}; 2025H1 参照 归母 {inp['np_ref']:.1f}亿 → "
          f"{inp['np_ref']/inp['shares']*pes[1]:.2f} @PE_M")
    print(f"  地板（只披露）floor={floor:.2f} (5y low PB x 报表 bps) < L {L:.2f} (L 对应 PB {L/inp['bps']:.2f}); not max()'d")
    print(f"  锚点 PB {L/inp['bps']:.2f}/{M/inp['bps']:.2f}/{H/inp['bps']:.2f}")
    print(f"  M/TP={M/CONSENSUS_TP:.2f} — TP = 7.5x M EPS ≈ 1/r (A8)")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
