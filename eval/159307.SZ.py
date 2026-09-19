#!/usr/bin/env python3
"""159307.SZ (Bosera CSI Dividend Low-Vol 100 ETF) valuation eval.

formula_id: bosera_div_lowvol_gordon_named_zero_bandedge_v6

Whole-basket look-through earnings × flat multiple, r = 10%.  The basket
retains ~57% (payout 43%) while its look-through EPS has fallen every year
since 2024 (3y −10%/yr, 1y −12.5%) and TTM DPS is flat (−2%): retain-while-
shrink.  The retention branch's positive g2 fails the same-world gate (the
whole-basket realised path DOWN beats +7.3% consensus on 19.9% weight); the
full-payout shrink branch fails the payout fact → BLOCKED → named g2 = 0
(valuation-rules 反解分支; user-authorised 2026-09-15 scheme 1).

v6: the named-zero annuity 1/r = 10x sits above the index's own 5y band top
9.71x, so 裁决顺序 #3 truncates it at the band edge — live pe = min(1/r,
pe_own_max) = 9.71x flat (9.71x is also the top of what the market paid at
this earnings level, 2025-09..2026-09).  The reverse-solved residual g at
the edge (full-payout branch, −0.30%) is disclosure only.  H numerator is
coverage-weighted: 1 + g_cov_fwd × cov_w — covered names deliver consensus,
the uncovered 80% stay flat (v5 applied +7.3% to the whole basket while
saying the opposite).  v5 (10x) and v4 (retention 8.63x) survive as 对照.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.etf_lookthrough import scale  # noqa: E402
from lib.gordon import (  # noqa: E402
    NEAR_FULL_PAYOUT, check_branch, check_g_cap, check_r, implied_g, implied_g_retaining,
    perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "159307.SZ.md"
FORMULA_ID = "bosera_div_lowvol_gordon_named_zero_bandedge_v6"

REQUIRED = [
    "price", "pe_now", "r_perp", "roe_idx", "roe_l", "roe_h",
    "dps_ttm", "dps_ttm_prev", "payout_etf", "payout_evid_min", "payout_evid_max",
    "g2_l", "g2_m", "g2_h", "pe_l", "pe_m", "pe_h", "pe_own_min", "pe_own_max", "g_edge_full",
    "pe_v4", "pe_same_min", "pe_same_med", "pe_same_max", "idx_dy", "fee_drag",
    "idx_eps_2023", "idx_eps_2025", "idx_eps_now", "eps_k_l", "eps_k_m",
    "g_cov_fwd", "cov_w", "eps_k_h",
]
PAYOUT_TOL = 0.005
G2_TOL = 0.0005
ROE_TOL = 0.0005
PE_TOL = 0.05
K_TOL = 0.005
DPS_CUT_TRIGGER = -0.05   # A10: TTM DPS down >5% YoY → re-decide
PAYOUT_TRIGGER = 0.50     # A10: payout above 50% → re-decide
SAME_EPS_TOL = 0.12       # 裁决顺序 ④ same-earnings months: TTM EPS within ±12%


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r, roe, fee = inp["r_perp"], inp["roe_idx"], inp["fee_drag"]
    price = inp["price"]
    eps = price / inp["pe_now"]
    ks = (inp["eps_k_l"], inp["eps_k_m"], inp["eps_k_h"])

    # --- Branch facts: payout (A4) + dividend trend (A10) ---------------------
    payout_etf = inp["dps_ttm"] / eps
    if abs(payout_etf - inp["payout_etf"]) > PAYOUT_TOL:
        errors.append(f"payout_etf {inp['payout_etf']} != dps_ttm / (price / pe_now) = {payout_etf:.4f}")
    if payout_etf >= NEAR_FULL_PAYOUT:
        errors.append(f"payout {payout_etf:.0%} >= {NEAR_FULL_PAYOUT:.0%} — basket no longer retains; re-decide (A8)")
    if payout_etf > PAYOUT_TRIGGER:
        errors.append(f"payout {payout_etf:.1%} > {PAYOUT_TRIGGER:.0%} — dividends outrunning earnings; re-decide (A10)")
    ev_lo, ev_hi = inp["payout_evid_min"], inp["payout_evid_max"]
    if abs(inp["idx_dy"] * inp["pe_now"] - ev_lo) > PAYOUT_TOL:
        errors.append(f"payout_evid_min {ev_lo} != idx_dy x pe_now = {inp['idx_dy'] * inp['pe_now']:.4f}")
    if not (ev_lo <= payout_etf <= ev_hi):
        errors.append(f"payout_etf {payout_etf:.4f} outside measured range [{ev_lo}, {ev_hi}]")
    dps_yoy = inp["dps_ttm"] / inp["dps_ttm_prev"] - 1.0
    if dps_yoy < DPS_CUT_TRIGGER:
        errors.append(f"TTM DPS {dps_yoy:+.1%} YoY — dividend being cut; re-decide L (A10)")
    errors += check_r(r, "r_perp")
    if not (0.97 <= fee <= 0.99):
        errors.append(f"fee_drag={fee} expected ~0.98 for 0.20% fee")

    # --- Same-world gate (A9): whole-basket realised path DOWN ---------------
    k_3y = (inp["idx_eps_now"] / inp["idx_eps_2023"]) ** (1.0 / 3.0)
    k_1y = inp["idx_eps_now"] / inp["idx_eps_2025"]
    if abs(k_3y - inp["eps_k_l"]) > K_TOL:
        errors.append(f"eps_k_l {inp['eps_k_l']} != realised 3y CAGR factor {k_3y:.4f}")
    if k_3y >= 1.0:
        errors.append(f"same-world gate: realised 3y factor {k_3y:.4f} is not DOWN — named-zero premise gone; re-decide (A9)")
    if k_1y >= 1.0:
        errors.append(f"same-world gate: latest-year factor {k_1y:.4f} turned up — DOWN premise weakening; re-decide (A9)")
    if inp["g_cov_fwd"] <= 0:
        errors.append("coverage consensus flipped non-positive — H numerator anchor needs re-decide (A5)")
    k_h = 1.0 + inp["g_cov_fwd"] * inp["cov_w"]
    if abs(k_h - inp["eps_k_h"]) > G2_TOL:
        errors.append(f"eps_k_h {inp['eps_k_h']} != 1 + g_cov_fwd x cov_w = {k_h:.4f} (covered deliver, uncovered flat)")
    errors += ladder("eps_k", *ks)
    if errors:
        return report(errors, "FAIL (branch / numerators / gate)")

    # --- Named g2 = 0, truncated at own band edge (裁决顺序 #3) ----------------
    # Retention branch at book ROE would want positive g — the counterfactual
    # check_branch is printable; the live g2 is forced to 0.
    g_retention_m = (1.0 - payout_etf) * roe
    branch_msgs = check_branch(g_retention_m, roe, r, payout_etf, "counterfactual_retention")
    pe_zero = perpetual_pe(0.0, roe, r)
    if abs(pe_zero - 1.0 / r) > PE_TOL:
        errors.append(f"named zero PE {pe_zero:.3f} != 1/r")
    pe_edge = min(pe_zero, inp["pe_own_max"])
    for key_g, key_pe in (("g2_l", "pe_l"), ("g2_m", "pe_m"), ("g2_h", "pe_h")):
        if abs(inp[key_g]) > G2_TOL:
            errors.append(f"{key_g} {inp[key_g]} != 0 (named zero; A8)")
        if abs(inp[key_pe] - pe_edge) > PE_TOL:
            errors.append(f"{key_pe} {inp[key_pe]} != min(perpetual_pe(0), pe_own_max) = {pe_edge:.3f}")
        errors += check_g_cap(inp[key_g], key_g)
    # Guardrail both ways: the live multiple must sit inside the own 5y band.
    if not (inp["pe_own_min"] - PE_TOL <= pe_edge <= inp["pe_own_max"] + PE_TOL):
        errors.append(f"live PE {pe_edge:.2f} outside own band [{inp['pe_own_min']}, {inp['pe_own_max']}]")
    if not (inp["pe_same_min"] - PE_TOL <= pe_edge <= inp["pe_same_max"] + PE_TOL):
        errors.append(f"live PE {pe_edge:.2f} outside same-earnings paid range [{inp['pe_same_min']}, {inp['pe_same_max']}]")
    # Residual g implied by the truncation (full-payout branch) — disclosure only.
    g_edge_full = r - 1.0 / pe_edge
    if abs(g_edge_full - inp["g_edge_full"]) > G2_TOL:
        errors.append(f"g_edge_full {inp['g_edge_full']} != r - 1/pe_edge = {g_edge_full:.4f}")
    if abs(inp["pe_v4"] - pe_edge) < 1e-9:
        errors.append("pe_v4 must remain the v4 retention multiple (~8.63), not leak into the live path")
    roe_l = roe * ks[0]
    roe_h = roe * ks[2]
    if abs(roe_l - inp["roe_l"]) > ROE_TOL:
        errors.append(f"roe_l {inp['roe_l']} != roe_idx x eps_k_l = {roe_l:.4f}")
    if abs(roe_h - inp["roe_h"]) > ROE_TOL:
        errors.append(f"roe_h {inp['roe_h']} != roe_idx x eps_k_h = {roe_h:.4f}")
    if errors:
        return report(errors, "FAIL (named zero / band edge)")

    # --- Anchors: flat band-edge × numerator ladder --------------------------
    def band(pe: float, kk: tuple[float, float, float] = ks) -> tuple[float, float, float]:
        return tuple(scale(eps, fee, k * pe) for k in kk)  # type: ignore[return-value]

    L, M, H = band(pe_edge)
    if not (L < M < H):
        return report(["tier ladder collapsed"])
    fl = band(pe_edge)  # flat-multiple ladder ≡ base (multiples already flat)
    if not (fl[0] < fl[1] < fl[2]):
        return report(["flat-multiple ladder collapsed"])
    A, B = cut_points(L, M, H)
    zone = zone_of(price, L, M, H)
    errors = check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, tol=0.002)
    if errors:
        return report(errors)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"透视 EPS = {price} / {inp['pe_now']} = {eps:.5f}; 派息率 = {inp['dps_ttm']} / EPS = {payout_etf:.2%} "
          f"(< {NEAR_FULL_PAYOUT:.0%} 仍留存; 证据区间 [{ev_lo:.1%}, {ev_hi:.1%}]); TTM DPS YoY {dps_yoy:+.1%}")
    print(f"同世界门（整篮实测向下优先）: 3y 透视 EPS 因子 {k_3y:.4f} ({k_3y - 1:+.1%}/yr), 1y {k_1y:.4f} ({k_1y - 1:+.1%}) DOWN; "
          f"覆盖共识 {inp['g_cov_fwd']:+.2%} on {inp['cov_w']:.1%} weight UP → DOWN 赢 → 留存正 g 不可用")
    print(f"反事实留存分支 g=(1−{payout_etf:.1%})×ROE {roe:.1%} = {g_retention_m:+.2%} → PE {perpetual_pe(g_retention_m, roe, r):.2f}x "
          f"(v4); check_branch 反事实: {branch_msgs[0] if branch_msgs else '符号/幅度通过（挡住的是同世界门，不是派息）'}")
    print(f"具名 g2=0 → 1/r = {pe_zero:.2f}x; 自身带 [{inp['pe_own_min']}, {inp['pe_own_max']}] 截断 → 活倍数 {pe_edge:.2f}x flat 三档 "
          f"(边缘残余 g 全派息 {g_edge_full:+.2%} / 留存 {implied_g_retaining(pe_edge, roe, r)[0]:+.2%}，都只披露)")
    print(f"PE(g) 在 ROE {roe:.1%} 下 g=0..6%: " + "/".join(f"{perpetual_pe(g, roe, r):.2f}" for g in (0, .01, .02, .03, .04, .05, .06)) + "x")
    print(f"{'档':<3}{'系数':>7}{'ROE':>8}{'g2':>9}{'PE':>7}{'值':>9}")
    for tier, k, roe_x, a in zip("LMH", ks, (roe_l, roe, roe_h), (L, M, H)):
        print(f"{tier:<3}{k:7.4f}{roe_x:8.2%}{0.0:+9.2%}{pe_edge:7.3f}{a:9.4f}")
    print(f"同等盈利实测月份 (TTM EPS ±{SAME_EPS_TOL:.0%}) PE [{inp['pe_same_min']}, {inp['pe_same_med']}, {inp['pe_same_max']}]: "
          f"活倍数 = 其上沿; H 在 TTM 空间 = {ks[2] * pe_edge * fee:.2f}x ≤ 自身带顶")
    g_mkt, ok = implied_g_retaining(inp["pe_now"], roe, r)
    print(f"市价 {inp['pe_now']}x < 活倍数 {pe_edge:.2f}x; 留存分支反解 g {g_mkt:+.2%} (well_conditioned={ok}); "
          f"全派息读数 {implied_g(inp['pe_now'], roe, r)[0]:+.2%}")
    print(f"分子: L = TTM × {inp['eps_k_l']} (隐含 EPS {inp['idx_eps_2023']:.1f} → {inp['idx_eps_2025']:.1f} → {inp['idx_eps_now']:.1f}); "
          f"M = TTM; H = TTM × {inp['eps_k_h']} (= 1 + {inp['g_cov_fwd']:.2%} × {inp['cov_w']:.1%}, 未覆盖走平)")
    print(f"flat-multiple ladder ≡ 底牌: {'/'.join(f'{x:.4f}' for x in fl)}")
    print(f"L/M {L / M:.3f} = num {ks[0] / ks[1]:.3f} x pe 1.000 | H/M {H / M:.3f} = num {ks[2] / ks[1]:.3f} x pe 1.000 | "
          f"width {(H - L) / (2 * M):.3f} | V_opt/M 0.000")
    print(f"L={L:.4f} M={M:.4f} H={H:.4f} A={A:.4f} B={B:.4f}")
    print(f"price={price} zone={zone} | (P−M)/M = {(price - M) / M:+.2%}, (P−A)/P = {(price - A) / price:+.2%}")

    # 对账 (纠正对账门 coordinates) + neutral band as PE readings
    b_v4 = band(inp["pe_v4"])
    b_zero = band(pe_zero)
    b_same = {lab: band(inp[key]) for lab, key in (("min", "pe_same_min"), ("med", "pe_same_med"), ("max", "pe_same_max"))}
    ddm0 = inp["dps_ttm"] / r
    print(f"对账: ① v4 M={b_v4[1]:.4f} (ΔM {(M - b_v4[1]) / b_v4[1]:+.1%}); ② E_M/r×fee={b_zero[1]:.4f} (ΔM {(M - b_zero[1]) / b_zero[1]:+.1%}); "
          f"③ DDM D0/r={ddm0:.4f} (不同质); ④ 同等盈利实测价 中位 {inp['pe_same_med']}x → {b_same['med'][1]:.4f} (ΔM {(M - b_same['med'][1]) / b_same['med'][1]:+.1%}), "
          f"区间 [{b_same['min'][1]:.4f}, {b_same['max'][1]:.4f}]; ⑥ M 隐含 PB {M / price * 0.78:.3f} vs 现 0.78 (自身 PB 带待补)")
    print(f"中性带 [{A:.4f}, {B:.4f}) 的 PE 读数: TTM {A / eps:.2f}–{B / eps:.2f}x (÷fee {A / eps / fee:.2f}–{B / eps / fee:.2f}x); "
          f"FY+1 (×{ks[2]:.4f}) {A / eps / ks[2]:.2f}–{B / eps / ks[2]:.2f}x; 中枢 = TTM (slow_grower)")

    # Sensitivity / contrasts
    print(f"对照 v4 留存分支 flat {inp['pe_v4']}x (本版分子): {'/'.join(f'{x:.4f}' for x in b_v4)} zone={zone_of(price, *b_v4)}")
    print(f"对照 v5 具名零不截断 {pe_zero:.2f}x: {'/'.join(f'{x:.4f}' for x in b_zero)} zone={zone_of(price, *b_zero)}")
    b_mkt = band(inp["pe_now"])
    print(f"对照 fair=市场 {inp['pe_now']}x flat: {'/'.join(f'{x:.4f}' for x in b_mkt)} zone={zone_of(price, *b_mkt)}")
    for lab, b in b_same.items():
        print(f"对照 同等盈利实测 {lab} {inp['pe_same_' + lab]}x: {'/'.join(f'{x:.4f}' for x in b)} zone={zone_of(price, *b)}")
    g_dn = g_edge_full - 0.01
    b_dn = band(perpetual_pe(g_dn, roe, r))
    print(f"敏感性 边缘残余 g −1pp ({g_dn:+.2%}, 全派息) → {perpetual_pe(g_dn, roe, r):.2f}x: {'/'.join(f'{x:.4f}' for x in b_dn)} zone={zone_of(price, *b_dn)}; "
          f"+1pp 两分支 ({1 / (r - g_edge_full - 0.01):.2f}x / {perpetual_pe(g_edge_full + 0.01, roe, r):.2f}x) 皆越带顶 → 截回 {pe_edge:.2f}x 不变")
    for k, label in ((inp["eps_k_l"], "实测趋势 ×0.90"), (inp["eps_k_h"], f"覆盖加权 ×{inp['eps_k_h']}")):
        kk = tuple(x * k for x in ks)
        b = band(pe_edge, kk)  # type: ignore[arg-type]
        print(f"敏感性 E1 变体 分子 {label}: {'/'.join(f'{x:.4f}' for x in b)} zone={zone_of(price, *b)}")
    b_full = band(pe_edge, (ks[0], ks[1], 1.0 + inp["g_cov_fwd"]))
    print(f"敏感性 H 改整篮外推 ×{1 + inp['g_cov_fwd']:.4f} (v5 写法): {'/'.join(f'{x:.4f}' for x in b_full)} zone={zone_of(price, *b_full)}")
    print(f"DDM 对照 (g_d=0): D0/r = {ddm0:.4f}; 现价隐含股息增长 {r - inp['dps_ttm'] / price:+.2%} "
          f"(≠ 具名盈利 g2=0 — 派息 43% 未全部分光)")
    print(f"OK  L={L:.4f} M={M:.4f} H={H:.4f} A={A:.4f} B={B:.4f}  zone={zone}  price={price}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
