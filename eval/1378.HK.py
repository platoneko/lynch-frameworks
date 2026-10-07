#!/usr/bin/env python3
"""1378.HK (China Hongqiao) valuation eval.

frameworks/1378.HK.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading — the digest and the app zone on live quotes.

formula_id: hongqiao_al_spread_gm_bridge_gordon_v5

Main ruler: the shared gross-margin bridge (eval/lib/al_bridge.py) on the
aluminium spread axis.  M is the 2026H1 filing annualised; L and H are M moved
by 562.2万吨 x the axis's spread steps (−4,006 / +1,028 元/吨) through the
marginal conversion rate.  Each tier's multiple is Gordon on the axis's shared
g rows (0% / 0% / 0% → flat 1/r) at the tier's own forward ROE (NP_x / 中报归母权益),
with r the basket the framework names for the single leg (篮 6 周期商品, 13% →
7.69×; valuation-rules「§r 篮子」, gordon.BASKET_R).
The L numerator is the axis's L rung — MS 2027 supply-glut level that may
persist, not a trough that mean-reverts, and not this company's own trough year
(2023H1 本公司擁有人應佔溢利 24.57亿 was far lower) — so g_L = 0 with g_M/g_H;
IAI/CRU 3.3% is sensitivity / stretched only.  A v4 that ran the 谷底档 recovery
stage on the axis rung let L converge on M and was rolled back (valuation-rules
「谷底档」适用范围); the later g_L 3.3%「谷底回归中枢」overlay is also retired.
The printed 2023H1 trough x 1/r is only the deep_discount pressure coordinate.
The H-share cluster median that used to be typed in as `pe` is only a cross
coordinate.  The PB floor is disclosed, never max()'d into L.  Anchors are HKD:
CNY earnings ÷ fx_hkd_cny (1/1.1668).

What is specific to this ticker is the shape of its integration.  Hongqiao's
alumina is *sold outward*, so a high-alumina year pays the upstream leg while
it squeezes the smelter — 2026H1 ran +88亿 on aluminium against **-49亿** on
alumina.  But the axis's L world is the supply-glut one, with alumina frozen
low: there is nothing for the upstream leg to catch, and Hongqiao's k (0.72)
is the highest of the four mounts, so its L/M is the *deepest*, not the
shallowest.  The guard below asserts that ordering against Tianshan, whose
alumina is captive: if the two ever invert, one framework has treated the
L world's alumina differently from the axis.

Run:  python3 frameworks/eval/1378.HK.py
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

# rf_report / bands_io import eval.lib.*, so the repo root must be importable too.
sys.path.append(str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "1378.HK.md"
PEER_CAPTIVE = Path(__file__).resolve().parents[2] / "frameworks" / "002532.SZ.md"
FORMULA_ID = "hongqiao_al_spread_gm_bridge_gordon_v5"
LISTING_CCY = "HKD"

GP_M_FILING = 551.3  # 亿 CNY, 2026H1 x2 at the stated 31.5% margin
NP_M_FILING = 344.2  # 亿 CNY, 2026H1 归母 172.1 x2
SHARES_INTERIM = 98.194  # 亿股, issued at 2026-06-30 (interim note 16) — A14
NP_TROUGH_2023H1 = 49.13  # 亿 CNY, 2023H1 本公司擁有人應佔溢利 2,456,623 千元 x2 — pressure coordinate only (A16)


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    baskets = parse_baskets(md)
    errors = check_missing(inp, REQUIRED + ["fx_hkd_cny"])
    if errors:
        return report(errors)

    errors += ladder("smelting spread", inp["spread_l"], inp["spread_m"], inp["spread_h"])
    errors += check_al_mount((inp["spread_l"], inp["spread_m"], inp["spread_h"]))
    errors += check_regression(inp, GP_M_FILING, NP_M_FILING)
    # A18: r must be the basket the Inputs row names, not just any basket value.
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (AGENTS.md 篮子声明)")
    errors += check_gordon(inp, baskets.get("r_perp"))
    # A14: the per-share denominator is the interim's issued count, not a
    # number backed out of a mis-stated EPS (the old 107.9亿 was).
    if abs(inp["shares"] - SHARES_INTERIM) > 0.05:
        errors.append(f"shares {inp['shares']} != interim issued {SHARES_INTERIM}亿 (A14)")

    (L, M, H), eps = anchors(inp, fx=inp["fx_hkd_cny"])
    pes, roes = multiples(inp)
    errors += flat_ladder(eps)

    # Same L world for both mounts (alumina frozen), so the ordering is set by
    # k and by tonnes per yuan of profit — both higher here.  Tianshan's ratio
    # is recomputed from its own Inputs table so the two cannot drift apart.
    peer = parse_inputs(PEER_CAPTIVE.read_text(encoding="utf-8"))
    if REQUIRED_PEER <= peer.keys():
        peer_eps = anchors(peer)[1]
        mine, theirs = eps[0] / eps[1], peer_eps[0] / peer_eps[1]
        if mine >= theirs:
            errors.append(
                f"numerator ratio L {mine:.3f} >= 002532.SZ's {theirs:.3f} — "
                "in the frozen-alumina L world the outward alumina leg has no "
                "cushion and Hongqiao's higher k makes its downside the deeper "
                "one (§1 属性 A)"
            )

    # H is a price scenario, not a re-rating: the multiple it implies on M-tier
    # EPS must stay inside the multiple this stock has actually printed.
    pe_at_h = H / (eps[1] / inp["fx_hkd_cny"])
    if pe_at_h > inp["pe_own_max"]:
        errors.append(f"H implies {pe_at_h:.2f}x on M EPS, above own realised high {inp['pe_own_max']}")

    # Floor is disclosed only (A10): scenario L must clear it, never max() with it.
    floor, floor_errors = pb_floor(inp, L)
    errors += floor_errors

    A, B = cut_points(L, M, H)
    errors += check_against_stated(
        md, {"L": L, "M": M, "H": H, "A": A, "B": B}
    )

    br = bridge(inp)
    fx = inp["fx_hkd_cny"]
    r = inp["r_perp"]
    flat = [e * pes[1] / fx for e in eps]
    print(f"1378.HK  L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}")
    print(f"  r_perp {r:.1%} = 篮 {baskets['r_perp']}  "
          f"EPS(CNY) {eps[0]:.3f}/{eps[1]:.3f}/{eps[2]:.3f}  k={br['k']:.4f}  "
          f"ROE {roes[0]:.1%}/{roes[1]:.1%}/{roes[2]:.1%}  "
          f"PE {pes[0]:.2f}/{pes[1]:.2f}/{pes[2]:.2f}  guardrail [{inp['pe_own_min']}, {inp['pe_own_max']}] OK")
    print(f"  Gordon g (axis rows) L {inp['g2_l']:.1%} | M {inp['g2_m']:.1%} | H {inp['g2_h']:.1%}; "
          f"L numerator {br['np'][0]:.1f}亿 = axis L rung (regime), printed 2023H1 trough {NP_TROUGH_2023H1:.1f}亿 far below (A16)")
    print(f"  L/M={L/M:.3f} = 分子比 {eps[0]/eps[1]:.3f} x 倍数比 {pes[0]/pes[1]:.3f} | "
          f"H/M={H/M:.3f} = 分子比 {eps[2]/eps[1]:.3f} x 倍数比 {pes[2]/pes[1]:.3f} | "
          f"width {(H-L)/(2*M):.1%} | V_opt/M 0")
    print(f"  flat-multiple ladder @PE_M {pes[1]:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"  地板（只披露）floor={floor:.2f} (5y low PB x 报表 bps) < L {L:.2f} (L 对应 PB {L/inp['bps']:.2f}); not max()'d")
    print(f"  deep_discount 压力坐标: L = 低位 regime x 1/r = {eps[0] / r / fx:.2f} (flat@1/r, =底牌L); "
          f"印过的 2023H1 x 1/r = {NP_TROUGH_2023H1 / inp['shares'] / r / fx:.2f}; "
          f"2025H1 参照 {inp['np_ref'] / inp['shares'] * pes[1] / fx:.2f} @PE_M (conservative 带内坐标)")
    print(f"  交叉尺 (A17): 锚点 PB {L/inp['bps']:.2f}/{M/inp['bps']:.2f}/{H/inp['bps']:.2f}")
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_perp 1:1; the spread ladder, g rows, k and fx stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        return tuple(anchors(dict(inp, r_perp=r + dr), fx=fx)[0])

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    # Only a clean run feeds the daily digest.
    if not errors:
        write_rf_readings("1378.HK", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


REQUIRED_PEER = frozenset(REQUIRED)

if __name__ == "__main__":
    raise SystemExit(main())
