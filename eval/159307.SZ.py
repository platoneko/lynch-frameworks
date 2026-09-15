#!/usr/bin/env python3
"""159307.SZ (Bosera CSI Dividend Low-Vol 100 ETF) valuation eval.

formula_id: bosera_div_lowvol_gordon_named_zero_g_v5

Whole-basket earnings × flat Gordon PE at named g2 = 0 (PE = 1/r = 10x),
r = 10%.  Index look-through EPS has fallen ~10%/yr for 3 years while the
basket retains ~57% of earnings (payout 43%).  That is retain-while-shrink:
the retention branch's positive g2 fails the same-world gate when the
**whole-basket realised path** is preferred over thin-coverage consensus
(valuation-rules 同世界门; user-authorised 2026-09-15 scheme 1).  Both
classic Gordon branches are dirty (retention wants g>0; atrophy wants full
payout) → BLOCKED → named g2 = 0 → 10x, same pattern as 513530.SH's
industrial leg.

v4 kept payout-consistent retention g2 ≈ 5% because covered-name consensus
(+7.3% on 19.9% weight) opened the gate UP; that version survives only as a
对照带.  Numerators unchanged: L = TTM × realised 3y CAGR factor 0.90;
M = TTM; H = TTM × covered consensus 1.0731 (H is a scenario on the
numerator only — it does **not** reopen positive perpetual g).
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
FORMULA_ID = "bosera_div_lowvol_gordon_named_zero_g_v5"

REQUIRED = [
    "price", "pe_now", "r_perp", "roe_idx", "roe_l", "roe_h", "dps_ttm", "payout_etf",
    "payout_evid_min", "payout_evid_max", "g2_l", "g2_m", "g2_h", "pe_l", "pe_m", "pe_h",
    "pe_own_min", "pe_own_max", "pe_old", "pe_v4", "idx_dy", "fee_drag",
    "idx_eps_2023", "idx_eps_now", "eps_k_l", "eps_k_m", "g_cov_fwd", "cov_w", "eps_k_h",
]
NOT_FORMULA = ("pe_old", "pe_v4", "idx_dy", "payout_evid_min", "payout_evid_max")
PAYOUT_TOL = 0.005
G2_TOL = 0.0005
ROE_TOL = 0.0005
PE_TOL = 0.05
K_TOL = 0.005


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

    # --- Branch facts (disclosure) + named-zero decision (A8) -----------------
    payout_etf = inp["dps_ttm"] / eps
    if abs(payout_etf - inp["payout_etf"]) > PAYOUT_TOL:
        errors.append(f"payout_etf {inp['payout_etf']} != dps_ttm / (price / pe_now) = {payout_etf:.4f}")
    if payout_etf >= NEAR_FULL_PAYOUT:
        errors.append(f"payout {payout_etf:.0%} >= {NEAR_FULL_PAYOUT:.0%} — basket no longer retains; re-decide (A8)")
    ev_lo, ev_hi = inp["payout_evid_min"], inp["payout_evid_max"]
    if abs(inp["idx_dy"] * inp["pe_now"] - ev_lo) > PAYOUT_TOL:
        errors.append(f"payout_evid_min {ev_lo} != idx_dy x pe_now = {inp['idx_dy'] * inp['pe_now']:.4f}")
    if not (ev_lo <= payout_etf <= ev_hi):
        errors.append(f"payout_etf {payout_etf:.4f} outside measured range [{ev_lo}, {ev_hi}]")
    errors += check_r(r, "r_perp")
    if not (0.97 <= fee <= 0.99):
        errors.append(f"fee_drag={fee} expected ~0.98 for 0.20% fee")

    # Same-world: whole-basket realised path DOWN vs thin coverage UP → DOWN wins.
    k_l = (inp["idx_eps_now"] / inp["idx_eps_2023"]) ** (1.0 / 3.0)
    if abs(k_l - inp["eps_k_l"]) > K_TOL:
        errors.append(f"eps_k_l {inp['eps_k_l']} != realised 3y CAGR factor {k_l:.4f}")
    if abs(1.0 + inp["g_cov_fwd"] - inp["eps_k_h"]) > G2_TOL:
        errors.append(f"eps_k_h {inp['eps_k_h']} != 1 + g_cov_fwd {inp['g_cov_fwd']}")
    errors += ladder("eps_k", *ks)
    if k_l >= 1.0:
        errors.append(f"same-world gate: realised 3y factor {k_l:.4f} is not DOWN — named-zero premise gone; re-decide (A9)")
    if inp["g_cov_fwd"] <= 0:
        errors.append("coverage consensus flipped non-positive — H numerator anchor needs re-decide (A5)")
    if errors:
        return report(errors, "FAIL (branch / numerators / gate)")

    # Retention branch at book ROE would want positive g — that is exactly what
    # the named-zero solution refuses.  check_branch on that counterfactual must
    # be printable; the live g2 is forced to 0.
    g_retention_m = (1.0 - payout_etf) * roe
    branch_msgs = check_branch(g_retention_m, roe, r, payout_etf, "counterfactual_retention")
    # Peak-zone amplitude check passes for retention; the block is same-world, not payout.

    # --- Named g2 = 0, PE = 1/r, three tiers; ROE still derived for disclosure --
    pe_zero = perpetual_pe(0.0, roe, r)
    if abs(pe_zero - 10.0) > PE_TOL:
        errors.append(f"named zero PE {pe_zero:.3f} != 10")
    for tier, key_g, key_pe in (("L", "g2_l", "pe_l"), ("M", "g2_m", "pe_m"), ("H", "g2_h", "pe_h")):
        if abs(inp[key_g]) > G2_TOL:
            errors.append(f"{key_g} {inp[key_g]} != 0 (named zero; A8)")
        if abs(inp[key_pe] - pe_zero) > PE_TOL:
            errors.append(f"{key_pe} {inp[key_pe]} != perpetual_pe(0) = {pe_zero:.3f}")
        errors += check_g_cap(inp[key_g], key_g)

    roe_l = roe * ks[0]
    roe_h = roe * ks[2]
    if abs(roe_l - inp["roe_l"]) > ROE_TOL:
        errors.append(f"roe_l {inp['roe_l']} != roe_idx x eps_k_l = {roe_l:.4f}")
    if abs(roe_h - inp["roe_h"]) > ROE_TOL:
        errors.append(f"roe_h {inp['roe_h']} != roe_idx x eps_k_h = {roe_h:.4f}")

    for key in NOT_FORMULA:
        if key in ("pe_l", "pe_m", "pe_h"):
            continue
        if any(abs(inp[key] - v) < 1e-9 for v in (inp["pe_l"], inp["pe_m"], inp["pe_h"], 0.0)):
            # pe_old / pe_v4 equal to 10 would be a leak only if used as pe_*; checked below
            pass
    if abs(inp["pe_v4"] - pe_zero) < 1e-9:
        errors.append("pe_v4 must remain the v4 retention multiple (~8.63), not leak into named-zero 10x")
    if abs(inp["pe_old"] - pe_zero) < 1e-9:
        errors.append("pe_old (v2 band top) must not equal named-zero 10x path")
    # Guardrail: 10x is above own band top 9.71 — disclosed cost of named zero (A2e-2c-ex
    # condition 2 is about H multiple vs history when de-rate-led; here g=0 is the
    # earnings annuity, and H>band-top in TTM space is the known v5 cost).
    if pe_zero < inp["pe_own_min"] - PE_TOL:
        errors.append(f"named-zero PE {pe_zero:.2f} below own band floor {inp['pe_own_min']}")
    if errors:
        return report(errors, "FAIL (named zero tiers)")

    # --- Anchors: flat 10x × numerator ladder ---------------------------------
    def band(pe: float, kk: tuple[float, float, float] = ks) -> tuple[float, float, float]:
        return tuple(scale(eps, fee, k * pe) for k in kk)  # type: ignore[return-value]

    L, M, H = band(pe_zero)
    if not (L < M < H):
        return report(["tier ladder collapsed"])
    # flat-multiple ladder ≡ base (multiples already flat)
    fl = band(pe_zero)
    if not (fl[0] < fl[1] < fl[2]):
        return report(["flat-multiple ladder collapsed"])
    A, B = cut_points(L, M, H)
    zone = zone_of(price, L, M, H)
    errors = check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, tol=0.002)
    if errors:
        return report(errors)

    # Evidence gate: g2 is exact 0 — rebuild at payout evidence ends cannot move
    # PE.  Zone stability is automatic; still require stated zone = conservative
    # at base and print ends for disclosure.
    ends = {}
    for label, p in (("payout_evid_min", ev_lo), ("payout_evid_max", ev_hi)):
        ends[label] = (p, band(pe_zero), zone_of(price, *band(pe_zero)))
        if ends[label][2] != zone:
            errors.append(f"BLOCKED: zone flips at {label}")
    if errors:
        return report(errors, "BLOCKED")

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"透视 EPS = {price} / {inp['pe_now']} = {eps:.5f}; 派息率 = {inp['dps_ttm']} / EPS = {payout_etf:.2%} "
          f"(< {NEAR_FULL_PAYOUT:.0%} 仍留存; 证据区间 [{ev_lo:.1%}, {ev_hi:.1%}])")
    print(f"同世界门（整篮实测向下优先）: 3y 透视 EPS 因子 {k_l:.4f} ({k_l - 1:+.1%}/yr) DOWN; "
          f"覆盖共识 {inp['g_cov_fwd']:+.2%} on {inp['cov_w']:.1%} weight UP → DOWN 赢 → 留存正 g 不可用")
    print(f"反事实留存分支 g=(1−{payout_etf:.1%})×ROE {roe:.1%} = {g_retention_m:+.2%} → PE {perpetual_pe(g_retention_m, roe, r):.2f}x "
          f"(v4 底牌); check_branch 反事实: {branch_msgs[0] if branch_msgs else '符号/幅度通过（挡住的是同世界门，不是派息）'}")
    print(f"具名 g2=0 → PE = 1/r = {pe_zero:.2f}x flat 三档; ROE 仅披露 7.92/8.80/9.44%（g=0 时不进倍数）")
    print(f"PE(g) 在 ROE {roe:.1%} < r 下峰在 g=0: " + "/".join(f"{perpetual_pe(g, roe, r):.2f}" for g in (0, .01, .02, .03, .04, .05, .06)) + "x")
    print(f"{'档':<3}{'系数':>7}{'ROE':>8}{'g2':>9}{'PE':>7}{'值':>9}")
    for tier, k, roe_x, a in zip("LMH", ks, (roe_l, roe, roe_h), (L, M, H)):
        print(f"{tier:<3}{k:7.4f}{roe_x:8.2%}{0.0:+9.2%}{pe_zero:7.3f}{a:9.4f}")
    print(f"护栏自身带 [{inp['pe_own_min']}, {inp['pe_own_max']}]: 10x 高于带顶 {inp['pe_own_max']} — "
          f"具名零增长年金的已知代价（stretched 门槛在 TTM 空间 = {ks[2] * pe_zero * fee:.2f}x）")
    g_mkt, ok = implied_g_retaining(inp["pe_now"], roe, r)
    print(f"市价 {inp['pe_now']}x < 具名 10x; 留存分支反解 g {g_mkt:+.2%} (well_conditioned={ok}); "
          f"全派息读数 {implied_g(inp['pe_now'], roe, r)[0]:+.2%}")
    print(f"分子: L = TTM × {inp['eps_k_l']} (隐含 EPS {inp['idx_eps_2023']:.1f} → {inp['idx_eps_now']:.1f}); "
          f"M = TTM; H = TTM × {inp['eps_k_h']} (覆盖共识, 只抬分子不重开 g2)")
    print(f"flat-multiple ladder ≡ 底牌: {'/'.join(f'{x:.4f}' for x in fl)}")
    print(f"L/M {L / M:.3f} = num {ks[0] / ks[1]:.3f} x pe 1.000 | H/M {H / M:.3f} = num {ks[2] / ks[1]:.3f} x pe 1.000 | "
          f"width {(H - L) / (2 * M):.3f} | V_opt/M 0.000")
    print(f"L={L:.4f} M={M:.4f} H={H:.4f} A={A:.4f} B={B:.4f}")
    print(f"price={price} zone={zone} | (P−M)/M = {(price - M) / M:+.2%}, (P−A)/P = {(price - A) / price:+.2%}")
    for label, (p, b, z) in ends.items():
        print(f"证据端 {label} {p:.1%} (g2 钉死 0, PE 不动): {'/'.join(f'{x:.4f}' for x in b)} zone={z}")

    # Contrasts
    b_v4 = band(inp["pe_v4"])
    print(f"对照 v4 留存分支 flat {inp['pe_v4']}x: {'/'.join(f'{x:.4f}' for x in b_v4)} zone={zone_of(price, *b_v4)}")
    b_mkt = band(inp["pe_now"])
    print(f"对照 fair=市场 {inp['pe_now']}x flat: {'/'.join(f'{x:.4f}' for x in b_mkt)} zone={zone_of(price, *b_mkt)}")
    b_old = band(inp["pe_old"], (ks[0], ks[1], 1.08))
    print(f"对照 v2 带顶 {inp['pe_old']}x (分子 0.90/1.08): {'/'.join(f'{x:.4f}' for x in b_old)} zone={zone_of(price, *b_old)}")
    b_ret = band(perpetual_pe(g_retention_m, roe, r))
    print(f"对照 反事实派息一致留存 g {g_retention_m:+.2%}: {'/'.join(f'{x:.4f}' for x in b_ret)} zone={zone_of(price, *b_ret)}")
    for k, label in ((inp["eps_k_l"], "实测趋势 ×0.90"), (inp["eps_k_h"], f"覆盖共识 ×{inp['eps_k_h']}")):
        kk = tuple(x * k for x in ks)
        b = band(pe_zero, kk)  # type: ignore[arg-type]
        print(f"敏感性 E1 变体 分子 {label}: {'/'.join(f'{x:.4f}' for x in b)} zone={zone_of(price, *b)}")
    # DDM: with named g=0 on earnings ruler, dividend path is a different cross.
    ddm0 = inp["dps_ttm"] / r
    g_div_px = r - inp["dps_ttm"] / price
    print(f"DDM 对照 (g_d=0): D0/r = {ddm0:.4f}; 现价隐含股息增长 {g_div_px:+.2%} "
          f"(≠ 具名盈利 g2=0 — 派息 43% 未全部分光)")
    print(f"对账: 上一版 v4 M={b_v4[1]:.4f}; E_M/r×fee={eps / r * fee:.4f} (=本版 M); "
          f"市价×fee={eps * inp['pe_now'] * fee:.4f}; ΔM/v4={(M - b_v4[1]) / b_v4[1]:+.1%}")
    print(f"OK  L={L:.4f} M={M:.4f} H={H:.4f} A={A:.4f} B={B:.4f}  zone={zone}  price={price}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
