#!/usr/bin/env python3
"""600150.SH (China CSSC Holdings) valuation eval — recompute anchors from frameworks/600150.SH.md.

frameworks/600150.SH.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading.

formula_id: cssc_consensus_fy28_opvalue_gordon_v1

Main ruler: whole company (shipbuilding & offshore 86-89% of revenue, marine
equipment rides the same cycle; no sell-side SOTP), basket 4 r = 10%
(newbuilds are priced contract by contract; the rule puts equipment in basket
4).  Operating value + excess cash (valuation-rules「经营价值与超额现金」):
every earnings figure and RONIC is on the operating basis (excess cash and its
after-tax income taken out); the parent share of the excess cash is added back
per share at face value (lambda = 1) on every tier.

  numerator  FY2028 company consensus (Eastmoney F10, the 5 houses published
             on/after the 2026-08-31 interim report): M = mean, H = high.
             Demand-cycle manufacturing → the commodity「中枢」rule does not
             apply; the cycle risk sits in L.  Gordon value at 2028-01-01,
             discounted tau = 1.5 years to the 2026-06-30 balance sheet, plus
             the window distributable profit (2H26 + FY2027 unbooked operating
             EPS x (1 - g/RONIC)) at tau/2.
  g2         4% = named macro default (layer ④): no user judgement, peer
             cluster n <= 1 (CSSC Offshore in the flat zone, Songfa alone),
             no own same-earnings months (the company never earned this much).
  RONIC      FY2028 operating EPS over the start-of-2028 operating BPS
             (book − interim dividend − excess cash, rolled with b = g/RONIC);
             three-stage: forward through Y1 2028, linear to the steady return
             by Y2 2030 (low entry barrier), perpetual after.  Steady M 11%
             (business-model floor, commoditised heavy assets: own cycle and
             mature peers unusable), H 15% (low barrier → one floor row up).
  L          FY2025 measured parent profit (the digestion year: deliveries of
             2021-23 contracts) on the operating basis — FY2025's own excess
             cash income removed — at the M-tier multiple (cyclical flat), not
             time-aligned, plus the same excess cash per share.

V_opt = 0.  CNY segment of _AXIS.rates is [待建] → no r_f readings.

Run:  python3 frameworks/eval/600150.SH.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import (  # noqa: E402
    check_branch, check_g_cap, check_r, payout, payout_gap, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "600150.SH.md"
FORMULA_ID = "cssc_consensus_fy28_opvalue_gordon_v1"
YI = 1e8
NUM_YEAR = 2028
TODAY_FY = 2026
LEV_DEBT_EBITDA = 3.0
LEV_INT_EBIT = 1 / 3
COORD_TOL = 0.20          # 纠正对账门: new M within 20% of at least one independent coordinate

REQUIRED = [
    "shares", "bps", "equity", "minority_h1", "parent_ratio", "np_h1",
    "cons_np26_m", "cons_np26_h", "cons_np27_m", "cons_np27_h", "cons_np28_l", "cons_np28_m", "cons_np28_h",
    "np_l", "np_l_kf", "equity_25", "minority_25", "net_cash_ext_25", "rev_25",
    "np_fy22", "np_fy25", "np_ttm",
    "r_perp", "g2_m", "g2_h", "y1", "y2", "ronic_ss_m", "ronic_ss_h", "tau",
    "net_cash_ext_h1", "div_declared", "div_interim", "c_ex", "cash_yield", "tax_eff",
    "payout_obs", "payout_op", "k_l", "k_m", "k_h",
    "net_debt", "ebitda", "ebit", "interest", "pb_own_min", "contract_liab_h1",
]


def path_pe(g: float, roe: float, r: float, y1: int, y2: int, r_ss: float) -> float:
    """Three-stage retention Gordon (valuation-rules ② 稳态回报三段) at the start of NUM_YEAR per unit
    of NUM_YEAR earnings: RONIC = roe through y1, linear to min(roe, r_ss) by y2, perpetual after."""
    if r - g <= 0:
        raise ValueError("r <= g")
    ss = min(roe, r_ss)
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = NUM_YEAR + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * payout(g, ss) / ((r - g) * (1 + r) ** (t - 1))
        ro = roe if cal <= y1 else roe + (ss - roe) * (cal - y1) / (y2 - y1)
        pv += e * payout(g, ro) / (1 + r) ** t
        e *= 1 + g
        t += 1


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    baskets = parse_baskets(md)
    r, sh = inp["r_perp"], inp["shares"]

    # --- basket, g ----------------------------------------------------------------
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    if set(baskets) != {"r_perp"}:
        errors.append(f"only r_perp may carry a basket tag, got {sorted(baskets)}")
    for k in ("g2_m", "g2_h"):
        errors += check_g_cap(inp[k], r, k)
    tau = inp["tau"]
    if abs(tau - ((NUM_YEAR - TODAY_FY) * 12 - 6) / 12) > 1e-9:
        errors.append(f"tau {tau:g} != 2026-06-30 → {NUM_YEAR}-01-01 in years")
    y1, y2 = int(inp["y1"]), int(inp["y2"])
    if not (y1 == NUM_YEAR and y2 == y1 + 2):
        errors.append("Y1 must be the visible-year end FY2028 and Y2 = Y1 + 2 (low entry barrier)")
    # low barrier: M stays on the floor, H at most one floor row up (retention「上调看进入门槛」)
    if not (abs(inp["ronic_ss_m"] - 0.11) < 1e-9 and abs(inp["ronic_ss_h"] - 0.15) < 1e-9):
        errors.append("steady returns must be M 11% (commoditised heavy assets) / H 15% (one row up)")
    errors += ladder("FY2028 consensus", inp["cons_np28_l"], inp["cons_np28_m"], inp["cons_np28_h"])
    if not (inp["k_h"] >= inp["k_m"] >= inp["k_l"]):
        errors.append("cyclical k must satisfy k_H >= k_M >= k_L")
    # same-world gate: numerator year is the furthest consensus year → own >= 3y NP CAGR
    cagr = (inp["np_fy25"] / inp["np_fy22"]) ** (1 / 3) - 1
    if cagr > 0 and min(inp["g2_m"], inp["g2_h"]) <= 0:
        errors.append("同世界门: own FY2022→25 NP rises but a g2 <= 0")

    # --- excess cash (经营价值与超额现金 ①②) ------------------------------------------
    anchor = inp["rev_25"] * 2 / 12
    c_tot = inp["net_cash_ext_h1"] - inp["div_declared"] - inp["div_interim"] - anchor
    if abs(c_tot - inp["c_ex"]) > 1e6:
        errors.append(f"c_ex {inp['c_ex']:.4e} != net cash − dividends − anchor {c_tot:.4e}")
    pr = inp["equity"] / (inp["equity"] + inp["minority_h1"])
    if abs(pr - inp["parent_ratio"]) > 5e-5:
        errors.append(f"parent_ratio {inp['parent_ratio']} != recomputed {pr:.4f}")
    c_ex = c_tot * pr
    if c_ex < 0.15 * inp["equity"]:
        errors.append("c_ex below 15% of equity: the excess-cash line should not exist")
    c_inc = c_ex * inp["cash_yield"] * (1 - inp["tax_eff"])
    cps = c_ex / sh
    op = {t: tuple((inp[f"cons_np{y}_{t}"] - c_inc) / sh for y in (26, 27, 28)) for t in ("m", "h")}
    eps_h1 = (inp["np_h1"] - c_inc / 2) / sh
    unb = {t: (op[t][0] - eps_h1) + op[t][1] for t in ("m", "h")}
    if errors:
        return report(errors, "FAIL (basket / g / cash)")

    # --- M / H ---------------------------------------------------------------------
    disc, disc_w = (1 + r) ** tau, (1 + r) ** (tau / 2)
    obps = inp["bps"] - inp["div_interim"] / sh - cps   # operating book: equity − interim dividend − excess cash

    def tier(t: str, g: float, rs: float, y2_: int = y2, e28: float | None = None) -> dict:
        e28 = op[t][2] if e28 is None else e28
        roe = e28 / obps
        for _ in range(300):
            bps28 = obps + g / roe * unb[t]
            roe = e28 / bps28
        pe = path_pe(g, roe, r, y1, y2_, rs)
        w = max(unb[t] * (1 - g / roe), 0.0) / disc_w
        return dict(eps=e28, roe=roe, bps=bps28, pe=pe, w=w, pe_1=perpetual_pe(g, roe, r),
                    v=e28 * pe / disc, anchor=e28 * pe * (1 - inp[f"k_{t}"]) / disc + w + cps)

    rows = {t: tier(t, inp[f"g2_{t}"], inp[f"ronic_ss_{t}"]) for t in ("m", "h")}
    for t in ("m", "h"):
        if rows[t]["roe"] - r < 0.03:
            errors.append(f"{t.upper()}: RONIC {rows[t]['roe']:.1%} not in the monotone zone")
        errors += check_branch(inp[f"g2_{t}"], rows[t]["roe"], r, inp["payout_op"], f"g2_{t}")
        # ③ 约束 2: g <= (1 − d) x RONIC
        if inp[f"g2_{t}"] > (1 - inp["payout_obs"]) * min(rows[t]["roe"], inp[f"ronic_ss_{t}"]):
            errors.append(f"g2_{t} above (1 − d) x RONIC")

    # --- L: FY2025 measured (digestion year), operating basis, flat M multiple -------------
    cex25 = (inp["net_cash_ext_25"] - inp["rev_25"] / 6) * inp["equity_25"] / (inp["equity_25"] + inp["minority_25"])
    inc25 = cex25 * inp["cash_yield"] * (1 - inp["tax_eff"])
    e_l = (inp["np_l"] - inc25) / sh
    pe_l = rows["m"]["pe"]
    roe_l = (inp["np_l"] - inc25) / (inp["equity_25"] - cex25)
    L = e_l * pe_l * (1 - inp["k_l"]) + cps
    M, H = rows["m"]["anchor"], rows["h"]["anchor"]
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.3f} {M:.3f} {H:.3f}"])
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # shape (裁决顺序 ⑤): L flat on the M multiple; H's multiple sits above M only because its steady
    # return is one floor row up (low barrier, retention「三档各取各的稳态」) — disclosed, not a policy choice
    if abs(pe_l - rows["m"]["pe"]) > 1e-9:
        errors.append("L must carry the M-tier multiple (cyclical flat)")
    flat = [e_l * rows["m"]["pe"] + cps] + [rows[t]["eps"] * rows["m"]["pe"] / disc + rows[t]["w"] + cps for t in ("m", "h")]
    errors += ladder("flat-multiple", *flat)
    # ③ no same-earnings months → 纠正对账门 coordinates (out-of-band.md)
    coord = {
        "E_M/r + 现金": rows["m"]["eps"] / r + cps,
        "股息尺 D_M/(r−g)": inp["payout_obs"] * inp["cons_np28_m"] / sh / (r - inp["g2_m"]),
        "PB 低点 × BPS": inp["pb_own_min"] * inp["bps"],
    }
    if not any(abs(M / v - 1) <= COORD_TOL for v in coord.values()):
        errors.append("纠正对账门: M outside every independent coordinate by > 20% → BLOCKED")
    lev1, lev2 = inp["net_debt"] / inp["ebitda"], inp["interest"] / inp["ebit"]
    if lev1 > LEV_DEBT_EBITDA or lev2 > LEV_INT_EBIT:
        errors.append("leverage gate triggered — ROE decomposition / ROIC branch required")

    # --- report ------------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"basket: r_perp 篮 {baskets['r_perp']} r={r:g}; FY{NUM_YEAR} consensus ÷1.1^{tau:g} = ÷{disc:.3f} + window ÷1.1^{tau / 2:g}; "
          f"g2 {inp['g2_m']:.0%}（具名宏观默认）; 同世界门 own FY22→25 NP CAGR {cagr:+.0%}")
    print(f"超额现金: 扩展口径净现金 {inp['net_cash_ext_h1'] / YI:.2f}亿 − 已宣派 {inp['div_declared'] / YI:.2f} − 中期 {inp['div_interim'] / YI:.2f} "
          f"− 锚 {anchor / YI:.2f}（2 个月收入）− 缺口 0 = {c_tot / YI:.2f}亿 × 归母 {pr:.4f} = C_ex {c_ex / YI:.2f}亿"
          f"（每股 {cps:.3f}，占归母权益 {c_ex / inp['equity']:.1%}，λ 1）；税后收益 {c_inc / YI:.2f}亿")
    for t in ("m", "h"):
        x = rows[t]
        print(f"{t.upper()}: 经营EPS28 {x['eps']:.4f} 经营BPS28 {x['bps']:.3f} RONIC {x['roe']:.2%} → {inp[f'ronic_ss_{t}']:.0%} by {y2} "
              f"PE {x['pe']:.2f}（单段 {x['pe_1']:.2f}）| 经营价值 {x['v']:.2f} + 窗口 {x['w']:.2f} + 现金 {cps:.2f} -> {x['anchor']:.2f}")
    print(f"L: FY2025 归母 {inp['np_l'] / YI:.2f}亿 − 当年超额现金税后收益 {inc25 / YI:.2f}亿 = 经营 EPS {e_l:.4f} x PE_M {pe_l:.2f} "
          f"+ 现金 {cps:.2f} -> {L:.2f}（当年经营回报 {roe_l:.1%}，自身 Gordon {perpetual_pe(inp['g2_m'], roe_l, r):.2f}× 只披露）")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%} V_opt/M=0% | "
          f"分子比 L/M {e_l / rows['m']['eps']:.2f} H/M {rows['h']['eps'] / rows['m']['eps']:.3f} | "
          f"倍数 L/M/H {pe_l:.2f}/{rows['m']['pe']:.2f}/{rows['h']['pe']:.2f}")
    print(f"flat-multiple (M-tier PE): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print("对账门坐标: " + " · ".join(f"{k} {v:.2f}（M/坐标 {M / v - 1:+.0%}）" for k, v in coord.items()))
    print(f"中性带 [{A:.2f}, {B:.2f}) 对 TTM EPS {inp['np_ttm'] / sh:.3f}: {A / (inp['np_ttm'] / sh):.1f}–{B / (inp['np_ttm'] / sh):.1f}×; "
          f"对 FY2027E {inp['cons_np27_m'] / sh:.3f}: {A / (inp['cons_np27_m'] / sh):.1f}–{B / (inp['cons_np27_m'] / sh):.1f}×")

    def band(dg: float) -> str:
        rm = tier("m", inp["g2_m"] + dg, inp["ronic_ss_m"])
        rh = tier("h", inp["g2_h"] + dg, inp["ronic_ss_h"])
        ll = e_l * rm["pe"] + cps
        return f"{ll:.2f}/{rm['anchor']:.2f}/{rh['anchor']:.2f}"
    print(f"敏感性 g2 −1pp {band(-0.01)} | +1pp {band(0.01)}")
    for lab, sm, shh, yy in (("稳态 M 15% / H 18%", 0.15, 0.18, y2), ("门槛「中」Y2 2032", inp["ronic_ss_m"], inp["ronic_ss_h"], y1 + 4)):
        rm, rh = tier("m", inp["g2_m"], sm, yy), tier("h", inp["g2_h"], shh, yy)
        print(f"敏感性 {lab}: {e_l * rm['pe'] + cps:.2f}/{rm['anchor']:.2f}/{rh['anchor']:.2f}")
    print(f"敏感性 M 分子换 FY2028 下沿 {inp['cons_np28_l'] / YI:.2f}亿 -> M "
          f"{(inp['cons_np28_l'] - c_inc) / sh * rows['m']['pe'] / disc + rows['m']['w'] + cps:.2f}")
    print(f"敏感性 L 换扣非 {inp['np_l_kf'] / YI:.2f}亿 -> L {(inp['np_l_kf'] - inc25) / sh * pe_l + cps:.2f}")
    print(f"压力坐标 只剩超额现金（回到 2016–23 年经营口径亏损）= {cps:.2f}; PB {inp['pb_own_min']} x BPS = {coord['PB 低点 × BPS']:.2f}")
    mod, gap = payout_gap(inp["g2_m"], rows["m"]["roe"], inp["payout_op"])
    excess = (1 - inp["payout_obs"]) - inp["g2_m"] / rows["m"]["roe"]
    print(f"payout: model {mod:.1%} vs 经营口径 {inp['payout_op']:.1%} (gap {gap:+.1%}); 实付 {inp['payout_obs']:.1%}; "
          f"多留部分 {excess:.1%} x 窗口经营 EPS {unb['m']:.3f} = {excess * unb['m']:.2f}/sh（落在超额现金，λ 1，PV 不进锚点）")
    print(f"杠杆门: 净债/EBITDA {lev1:.2f}, 利息/EBIT {lev2:.1%} -> not triggered")
    print(f"证伪线: 合同负债 {inp['contract_liab_h1'] / YI:.0f}亿 降 30% 至 {0.7 * inp['contract_liab_h1'] / YI:.0f}亿")
    print("r_f: CNY segment of _AXIS.rates [待建] — no readings")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
