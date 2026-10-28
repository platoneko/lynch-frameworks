#!/usr/bin/env python3
"""002812.SZ (Yunnan Energy New Material / 恩捷股份) valuation eval — recompute anchors from frameworks/002812.SZ.md.

frameworks/002812.SZ.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading.

formula_id: enjie_consensus_fy28_three_stage_gordon_v1

Main ruler: whole company (separator 88% of revenue; the packaging segment
sits in the same basket, so no leg split), basket 4 r = 10% — demand-cycle
manufacturing by the user's ruling 2026-10-28 (initial basket 6 kept as a
comparison band in §0 only).

  numerator  FY2028 consensus (Eastmoney report list, 5 houses, latest version
             each, as of 2026-10-28): M = mean, H = high.  L = the same year
             as the first year of a renewed price war: mean x own FY2023/FY2022
             realised ratio 0.632, read as a regime (that profit persists).
  RONIC      FY2028 earnings over start-of-2028 parent equity rolled from
             2026-09-30 (less the declared interim dividend) with b = g/RONIC.
  path       forward RONIC through Y1 2028, linear to min(RONIC, steady) by
             Y2 2032, perpetual after; steady = own FY2020-24 trough-to-trough
             ROIC 11.1% converted to the equity basis at today's leverage.
  g2         3% on every tier — user judgement 2026-10-29 (same demand chain as
             300750.SZ, its M-tier g2).
  timing     value at 2028-01-01 discounted tau 1.25 to 2026-09-30, plus the
             unbooked window profit (4Q26 + FY2027 consensus) x (1 - b) at tau/2,
             less the growth funding gap x parent share and the declared
             interim dividend.
  cash       extended net cash negative -> no excess-cash line.

V_opt = 0 (solid-state electrolyte has no unit economics yet; the Zigong
capacity is paid for by g2 retention).  CNY segment of _AXIS.rates is [待建].

Run:  python3 frameworks/eval/002812.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import (  # noqa: E402
    check_branch, check_g_cap, check_r, payout, perpetual_pe, recovery_two_stage_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "002812.SZ.md"
FORMULA_ID = "enjie_consensus_fy28_three_stage_gordon_v1"
YI = 1e8
NUM_YEAR = 2028
LEV_DEBT_EBITDA = 3.0
LEV_INT_EBIT = 1 / 3
RECON_GATE = 0.20     # 纠正对账门: new M within 20% of at least one independent coordinate
N_REC_POINT = 3       # L point reading: 2023 first price-war year -> 2026 recovery, own realised

REQUIRED = [
    "shares", "shares_cons", "eps26_m", "eps27_m", "eps28_l", "eps28_m", "eps28_h", "np_9m",
    "np_fy22", "np_fy23", "l_factor", "equity", "minority", "parent_ratio",
    "cash", "st_loan", "ncl_1y", "lt_loan", "div_declared", "gap_g", "tau",
    "r_perp", "g2", "ronic_roic_cycle", "kd_at", "ronic_ss", "ronic_ss_floor", "y1", "y2",
    "payout_op", "net_debt_ext", "ebitda_28", "ebit_28", "interest_28",
    "ebitda_fy25", "ebit_fy25", "interest_fy25", "bps_now", "pb_trough",
    "pe_band_l_min", "pe_band_l_max",
]


def path_pe(g: float, roe: float, r: float, y1: int, y2: int, r_ss: float) -> float:
    """Three-stage retention Gordon (retention.md ② 稳态回报三段) at the start of NUM_YEAR per unit of
    NUM_YEAR earnings: RONIC = roe through y1, linear to min(roe, r_ss) by y2, perpetual after."""
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
    r, g2, sh, shc = inp["r_perp"], inp["g2"], inp["shares"], inp["shares_cons"]

    # --- basket, g, derived inputs ---------------------------------------------------
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(g2, r, "g2")
    if abs(inp["tau"] - 1.25) > 1e-9:
        errors.append(f"tau {inp['tau']} != 2026-09-30 -> 2028-01-01 (1.25)")
    y1, y2 = int(inp["y1"]), int(inp["y2"])
    if not (y1 == NUM_YEAR and y2 == y1 + 4):
        errors.append("Y1 must be FY2028 (visible-year end) and Y2 = Y1 + 4 (medium entry barrier)")
    errors += ladder("FY2028 consensus", inp["eps28_l"], inp["eps28_m"], inp["eps28_h"])
    if abs(inp["np_fy23"] / inp["np_fy22"] - inp["l_factor"]) > 5e-4:
        errors.append(f"l_factor {inp['l_factor']} != np_fy23/np_fy22 {inp['np_fy23'] / inp['np_fy22']:.4f}")
    pr = inp["equity"] / (inp["equity"] + inp["minority"])
    if abs(pr - inp["parent_ratio"]) > 5e-5:
        errors.append(f"parent_ratio {inp['parent_ratio']} != recomputed {pr:.4f}")
    debt = inp["st_loan"] + inp["ncl_1y"] + inp["lt_loan"]
    nd = debt + inp["div_declared"] - inp["cash"]
    if abs(nd - inp["net_debt_ext"]) > 0.01 * YI:
        errors.append(f"net_debt_ext {inp['net_debt_ext'] / YI:.2f} != recomputed {nd / YI:.2f}")
    if nd <= 0:
        errors.append("extended net cash is positive: the excess-cash test must be run")
    ss = inp["ronic_roic_cycle"] + (inp["ronic_roic_cycle"] - inp["kd_at"]) * nd / (inp["equity"] + inp["minority"])
    if abs(ss - inp["ronic_ss"]) > 5e-4:
        errors.append(f"ronic_ss {inp['ronic_ss']} != equity-basis conversion {ss:.4f}")
    if not inp["ronic_ss"] >= r:
        errors.append("steady return below r")
    if abs(inp["equity"] / sh - inp["bps_now"]) > 0.01:
        errors.append(f"bps_now {inp['bps_now']} != equity/shares {inp['equity'] / sh:.3f}")
    if errors:
        return report(errors, "FAIL (basket / inputs)")

    # --- tiers -----------------------------------------------------------------------
    tau = inp["tau"]
    disc, disc_w = (1 + r) ** tau, (1 + r) ** (tau / 2)
    unb = inp["eps26_m"] * shc - inp["np_9m"] + inp["eps27_m"] * shc   # 4Q26 + FY2027, all tiers
    b0 = inp["equity"] - inp["div_declared"]
    deduct = inp["gap_g"] * pr / sh + inp["div_declared"] / shc
    e_tier = {"m": inp["eps28_m"] * shc, "h": inp["eps28_h"] * shc}
    e_tier["l"] = inp["l_factor"] * e_tier["m"]

    def tier(e: float, g: float, rs: float, y2_: int = y2) -> dict:
        roe = 0.2
        for _ in range(300):   # start-of-2028 book roll, b = g/RONIC (③ 步 2)
            book = b0 + g / roe * unb
            roe = e / book
        pe = path_pe(g, roe, r, y1, y2_, rs)
        w = unb * (1 - g / roe) / disc_w
        val = (e * pe / disc + w) / sh - deduct
        return dict(e=e, roe=roe, book=book, pe=pe, w=w / sh, val=val, pe_1=perpetual_pe(g, roe, r))

    rows = {t: tier(e_tier[t], g2, inp["ronic_ss"]) for t in ("l", "m", "h")}
    L, M, H = (rows[t]["val"] for t in ("l", "m", "h"))
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.3f} {M:.3f} {H:.3f}"])
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})
    for t in ("m", "h"):
        if rows[t]["roe"] - r < 0.03:
            errors.append(f"{t.upper()}: RONIC {rows[t]['roe']:.1%} not in the monotone zone")
        errors += check_branch(g2, rows[t]["roe"], r, inp["payout_op"], f"g2 ({t.upper()})")
    # stationary constraints (retention ③): b <= 1 - d, g <= (1 - d) x RONIC
    b_ss = g2 / inp["ronic_ss"]
    if b_ss > 1 - inp["payout_op"] or g2 > (1 - inp["payout_op"]) * inp["ronic_ss"]:
        errors.append("steady-state retention exceeds what the company keeps (b <= 1 - d)")
    # flat ladder (A2e-2c): all tiers on the M multiple
    flat = [(rows[t]["e"] * rows["m"]["pe"] / disc + rows["m"]["w"] * sh) / sh - deduct for t in ("l", "m", "h")]
    errors += ladder("flat-multiple", *flat)
    # reconciliation gate coordinates (out-of-band.md 纠正对账门; L band distorted, M/H no months)
    c_er = (e_tier["m"] / r / disc + unb * (1 - g2 / rows["m"]["roe"]) / disc_w) / sh - deduct
    c_ddm = 0.40 * inp["eps28_m"] / (r - g2) / disc
    c_pb = inp["bps_now"] * inp["pb_trough"]
    near = min(abs(M / c - 1) for c in (c_er, c_ddm, c_pb))
    if near > RECON_GATE:
        errors.append(f"对账门: M {M:.2f} is >{RECON_GATE:.0%} from every coordinate "
                      f"({c_er:.2f} / {c_ddm:.2f} / {c_pb:.2f})")
    l_mult = (L + deduct) / (e_tier["l"] / sh)
    # leverage gate on the numerator year (cyclical), FY2025 actual as the flip reading
    lev1, lev2 = nd / inp["ebitda_28"], inp["interest_28"] / inp["ebit_28"]
    if lev1 > LEV_DEBT_EBITDA or lev2 > LEV_INT_EBIT:
        errors.append("leverage gate triggered on FY2028 — ROIC branch required")
    f1, f2 = nd / inp["ebitda_fy25"], inp["interest_fy25"] / inp["ebit_fy25"]

    # --- report ----------------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"basket: r_perp 篮 {baskets['r_perp']} r={r:g}; g2 {g2:.1%}; FY{NUM_YEAR} ÷1.1^{tau:g} = ÷{disc:.4f}, "
          f"window ÷1.1^{tau / 2:g}")
    print(f"稳态: 自身 FY2020–24 ROIC {inp['ronic_roic_cycle']:.2%} + ({inp['ronic_roic_cycle']:.2%} − {inp['kd_at']:.2%}) × "
          f"净债/权益 {nd / (inp['equity'] + inp['minority']):.3f} = {ss:.2%}；Y1 {y1} Y2 {y2}")
    print(f"窗口未入账利润 U = {unb / YI:.2f}亿（4Q26 {(inp['eps26_m'] * shc - inp['np_9m']) / YI:.2f} + FY2027 "
          f"{inp['eps27_m'] * shc / YI:.2f}）；扣项 每股 {deduct:.3f}（G {inp['gap_g'] / YI:.2f}亿 × {pr:.4f} + 中期股息）")
    for t in ("l", "m", "h"):
        x = rows[t]
        print(f"{t.upper()}: 归母 {x['e'] / YI:6.2f}亿 每股 {x['e'] / shc:.3f} | 2028 初权益 {x['book'] / YI:.2f}亿 "
              f"RONIC {x['roe']:.2%} 稳态 {min(x['roe'], inp['ronic_ss']):.2%} | PE {x['pe']:.2f}（单段 {x['pe_1']:.2f}）"
              f" payout {payout(g2, x['roe']):.1%} | 窗口 {x['w']:.2f} -> {x['val']:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.2f} V_opt/M=0 | 分子比 L/M "
          f"{e_tier['l'] / e_tier['m']:.3f} H/M {e_tier['h'] / e_tier['m']:.3f} | 倍数 "
          f"{rows['l']['pe']:.2f}/{rows['m']['pe']:.2f}/{rows['h']['pe']:.2f}（L 低于 M：L 档 RONIC 低，A6 披露）")
    print(f"flat-multiple (M PE): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"对账门坐标: E_M/r 折回+窗口−扣项 {c_er:.2f}（M 高 {M / c_er - 1:+.1%}）· 股息尺 40% {c_ddm:.2f} · "
          f"BPS×PB 谷底 {c_pb:.2f} -> 最近 {near:.1%}")
    print(f"③ L 今日价值/L 分子 {l_mult:.2f} vs 同等盈利月份 PE [{inp['pe_band_l_min']}, {inp['pe_band_l_max']}] "
          f"-> 低于带下沿；带失真（A10），不降篮")
    print(f"杠杆门 FY2028: 净债/EBITDA {lev1:.2f} 利息/EBIT {lev2:.1%} -> not triggered | FY2025 实测 {f1:.2f} / {f2:.1%}"
          f"（会触发，口径翻转，A9）")
    # L point reading: price-war year then own realised 3-year recovery back to the M numerator
    g1 = (e_tier["m"] / e_tier["l"]) ** (1 / N_REC_POINT) - 1
    pe_pt = recovery_two_stage_pe(g1, N_REC_POINT, g2, rows["m"]["roe"], r)
    l_pt = (e_tier["l"] * pe_pt / disc + rows["l"]["w"] * sh) / sh - deduct
    print(f"L point 读法（g1 {g1:+.1%} n {N_REC_POINT} 回到 M 分子，段二 RONIC {rows['m']['roe']:.1%}）: PE {pe_pt:.2f} -> {l_pt:.2f}")

    def band(**kw) -> str:
        g = kw.get("g", g2)
        rs = kw.get("rs", inp["ronic_ss"])
        yy = kw.get("y2_", y2)
        return "/".join(f"{tier(e_tier[t], g, rs, yy)['val']:.2f}" for t in ("l", "m", "h"))
    print(f"敏感性 g2 2% {band(g=g2 - 0.01)} | 4% {band(g=g2 + 0.01)}")
    print(f"敏感性 稳态兜底 {inp['ronic_ss_floor']:.0%} {band(rs=inp['ronic_ss_floor'])} | Y2 2030（低门槛）{band(y2_=y1 + 2)}")
    m_low = (inp["eps28_l"] * shc * rows["m"]["pe"] / disc + rows["m"]["w"] * sh) / sh - deduct
    print(f"M 分子换 FY2028 下沿 {inp['eps28_l']} -> {m_low:.2f}")
    print("r_f: CNY segment of _AXIS.rates [待建] — no readings")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
