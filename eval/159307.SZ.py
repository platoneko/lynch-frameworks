#!/usr/bin/env python3
"""159307.SZ (Bosera CSI Dividend Low-Vol 100 ETF) valuation eval.

formula_id: etf_tr_trend_channel_v1  (primary)
cross-check: bosera_div_lowvol_gordon_named_zero_bandedge_v6

A passive basket has no fair value apart from its NAV (price ≡ NAV; the fund
retains nothing, allocates nothing), and index PE / PB / ROE are snapshots of
the current basket.  So the ruler is the underlying index's total-return trend
channel (valuation-rules.md「§ETF 例外」, eval/lib/etf.py): M = log-linear
trend (outliers > 2σ dropped and refit), L / H = residual p10 / p90, mapped to
the ETF price by k = nav_ref / index level on the same as-of date.  Dividend
ETF → the rate-neutral cross-read (joint fit on the CNY 10Y) is mandatory; its
L′/M′/H′ are printed next to the deck, never replace it.

The framework states no current price (AGENTS.md「现价 — 禁写契约」): no zone,
no distance-to-anchor, no market-implied r / g; the digest and the app zone
the live quote themselves.

The basket r (look-through → 篮 4, A11) does not enter the channel.  It is a
disclosure-only `r_perp` row, checked against the basket table, and it drives
the company-ruler cross-check: whole-basket Gordon with named g2 = 0 (the
retention branch fails the same-world gate, the full-payout shrink branch
fails the payout fact), 1/r = 10x truncated at the index's own 5y band top
9.71x flat.  That ruler's guards (payout range, A9 gate, A10 dividend
triggers, own-band / same-earnings band) stay hard errors — they are the
framework's 回对话 triggers — but its band is compared with the Outputs 对照
line, not with the deck.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.etf import (  # noqa: E402
    REGIME_GAP, RF_MID, SUBWINDOWS, channel, history, rate_neutral, rates, slope_since,
)
from lib.etf_lookthrough import scale  # noqa: E402
from lib.gordon import (  # noqa: E402
    NEAR_FULL_PAYOUT, check_branch, check_g_cap, check_r, implied_g_retaining, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "159307.SZ.md"
FORMULA_ID = "etf_tr_trend_channel_v1"
CROSS_FORMULA_ID = "bosera_div_lowvol_gordon_named_zero_bandedge_v6"

# Index declaration (was the `_local/ab/etf.py` ETF table entry): 930955 红利低波100 total return.
INDEX_SRC, INDEX_CODE = "csi", "H20955"
INDEX_LABEL = "930955 红利低波100 全收益"
DIVIDEND_ETF = True   # rate-neutral cross-read mandatory
CCY = "CNY"
DY_PRIOR = 0.048      # prior β = −1/DY (ETF TTM yield)
REGIME = None         # no nameable break: sub-window slopes within REGIME_GAP of the full window

REQUIRED = [
    "nav_ref", "pe_now", "r_perp", "roe_idx", "roe_l", "roe_h",
    "dps_ttm", "dps_ttm_prev", "payout_etf", "payout_evid_min", "payout_evid_max",
    "g2_l", "g2_m", "g2_h", "pe_l", "pe_m", "pe_h", "pe_own_min", "pe_own_max", "g_edge_full",
    "pe_v4", "pe_same_min", "pe_same_med", "pe_same_max", "idx_dy", "fee_drag",
    "idx_eps_2023", "idx_eps_2025", "idx_eps_now", "eps_k_l", "eps_k_m",
    "g_cov_fwd", "cov_w", "eps_k_h",
    "chan_slope", "chan_slope_2019", "chan_slope_2021", "chan_sigma",
    "chan_l_idx", "chan_m_idx", "chan_h_idx", "idx_cur",
    "beta_rate_prior", "rf_ccy_mid", "rf_start", "rf_now",
    "beta_rate_level", "beta_rate_diff", "chan_slope_rn", "chan_m_rn_idx",
    "pe_band_2018_23_lo", "pe_band_2018_23_hi", "eps_pt_from_peak", "dps_pt_2025_yoy",
]
PAYOUT_TOL = 0.005
G2_TOL = 0.0005
ROE_TOL = 0.0005
PE_TOL = 0.05
K_TOL = 0.005
SLOPE_TOL = 0.0015     # channel slopes stated to 0.1pp
SIGMA_TOL = 0.0015
IDX_TOL = 0.002        # channel levels in index points, stated to the point
BETA_TOL = 0.1
RF_TOL = 0.0001
DPS_CUT_TRIGGER = -0.05   # A10: TTM DPS down >5% YoY → re-decide
PAYOUT_TRIGGER = 0.50     # A10: payout above 50% → re-decide
_CROSS_STATED = re.compile(r"对照（整篮 Gordon 公司尺）\*\*：`" + CROSS_FORMULA_ID
                           + r"` \*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*")


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    for fid in (FORMULA_ID, CROSS_FORMULA_ID):
        if fid not in md:
            print(f"FAIL: formula_id {fid} missing", file=sys.stderr)
            return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    nav_ref, fee = inp["nav_ref"], inp["fee_drag"]

    # --- Step 1: basket r (disclosure only; the channel has no r) -------------
    baskets = parse_baskets(md)
    r = inp["r_perp"]
    if "r_perp" not in baskets:
        errors.append("r_perp row names no 篮 N (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    for key_g in ("g2_l", "g2_m", "g2_h"):
        errors += check_g_cap(inp[key_g], r, key_g)
    if errors:
        return report(errors, "FAIL (basket)")

    # --- Step 2: primary ruler — total-return trend channel -------------------
    s = history(INDEX_SRC, INDEX_CODE)
    full = channel(s)
    subs = {w[:4]: slope_since(s, w) for w in SUBWINDOWS}
    ch = full
    if REGIME:
        start, _why = REGIME
        ch = channel(s[s.index >= start])
        if abs(ch["slope"] - full["slope"]) < REGIME_GAP:
            errors.append(f"regime declared but slope gap < {REGIME_GAP:.0%}")
    else:
        for yr, sl in subs.items():
            if abs(sl - full["slope"]) >= REGIME_GAP:
                errors.append(f"sub-window {yr} slope {sl:+.1%} is ≥ {REGIME_GAP:.0%} from full {full['slope']:+.1%} — "
                              f"regime break candidate; name it or keep the full window (re-decide)")
    if abs(ch["cur"] - inp["idx_cur"]) > IDX_TOL * inp["idx_cur"]:
        errors.append(f"idx_cur {inp['idx_cur']} != cached index last close {ch['cur']:.2f} ({ch['end']})")
    for key, val, tol in (("chan_slope", ch["slope"], SLOPE_TOL), ("chan_slope_2019", subs["2019"], SLOPE_TOL),
                          ("chan_slope_2021", subs["2021"], SLOPE_TOL), ("chan_sigma", ch["sigma"], SIGMA_TOL)):
        if abs(val - inp[key]) > tol:
            errors.append(f"{key} {inp[key]} != recomputed {val:.4f}")
    for key, val in (("chan_l_idx", ch["L"]), ("chan_m_idx", ch["M"]), ("chan_h_idx", ch["H"])):
        if abs(val - inp[key]) > IDX_TOL * inp[key]:
            errors.append(f"{key} {inp[key]} != recomputed {val:.0f}")
    # channel levels are index points; NAV tracks TR, so map by NAV / index on the as-of date
    k = nav_ref / ch["cur"]
    L, M, H = ch["L"] * k, ch["M"] * k, ch["H"] * k
    errors += ladder("channel", L, M, H)
    if errors:
        return report(errors, "FAIL (channel)")
    A, B = cut_points(L, M, H)

    # --- Step 3: rate-neutral cross-read (dividend ETF → mandatory) -----------
    rn = None
    if DIVIDEND_ETF:
        if abs(RF_MID[CCY] - inp["rf_ccy_mid"]) > RF_TOL:
            errors.append(f"rf_ccy_mid {inp['rf_ccy_mid']} != etf.RF_MID[{CCY}] {RF_MID[CCY]}")
        rn = rate_neutral(s, rates(CCY), RF_MID[CCY], DY_PRIOR)
        for key, val, tol in (("rf_start", rn["rf_start"], RF_TOL), ("rf_now", rn["rf_now"], RF_TOL),
                              ("chan_slope_rn", rn["slope"], SLOPE_TOL), ("beta_rate_level", rn["beta"], BETA_TOL),
                              ("beta_rate_diff", rn["beta_diff"], BETA_TOL), ("beta_rate_prior", rn["beta_prior"], 0.5)):
            if abs(val - inp[key]) > tol:
                errors.append(f"{key} {inp[key]} != recomputed {val:.4f}")
        if abs(rn["M"] - inp["chan_m_rn_idx"]) > IDX_TOL * inp["chan_m_rn_idx"]:
            errors.append(f"chan_m_rn_idx {inp['chan_m_rn_idx']} != recomputed {rn['M']:.0f}")
        rn["chan"] = tuple(v * k for v in (rn["L"], rn["M"], rn["H"]))
        if errors:
            return report(errors, "FAIL (rate-neutral)")

    # --- Step 4: company-ruler cross-check (guards stay hard; band is 对照) ----
    roe = inp["roe_idx"]
    eps = nav_ref / inp["pe_now"]
    ks = (inp["eps_k_l"], inp["eps_k_m"], inp["eps_k_h"])

    # Branch facts: payout (A4) + dividend trend (A10)
    payout_etf = inp["dps_ttm"] / eps
    if abs(payout_etf - inp["payout_etf"]) > PAYOUT_TOL:
        errors.append(f"payout_etf {inp['payout_etf']} != dps_ttm / (nav_ref / pe_now) = {payout_etf:.4f}")
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
    if not (0.97 <= fee <= 0.99):
        errors.append(f"fee_drag={fee} expected ~0.98 for 0.20% fee")

    # Same-world gate (A9): whole-basket realised path DOWN
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

    # Named g2 = 0, truncated at own band edge (裁决顺序 #3).  The retention
    # branch at book ROE would want positive g — check_branch is printable
    # only; the live g2 is forced to 0.
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
    if not (inp["pe_own_min"] - PE_TOL <= pe_edge <= inp["pe_own_max"] + PE_TOL):
        errors.append(f"cross-check PE {pe_edge:.2f} outside own band [{inp['pe_own_min']}, {inp['pe_own_max']}]")
    if not (inp["pe_same_min"] - PE_TOL <= pe_edge <= inp["pe_same_max"] + PE_TOL):
        errors.append(f"cross-check PE {pe_edge:.2f} outside same-earnings paid range [{inp['pe_same_min']}, {inp['pe_same_max']}]")
    g_edge_full = r - 1.0 / pe_edge
    if abs(g_edge_full - inp["g_edge_full"]) > G2_TOL:
        errors.append(f"g_edge_full {inp['g_edge_full']} != r - 1/pe_edge = {g_edge_full:.4f}")
    if abs(inp["pe_v4"] - pe_edge) < 1e-9:
        errors.append("pe_v4 must remain the v4 retention multiple (~8.63), not leak into the cross-check path")
    roe_l, roe_h = roe * ks[0], roe * ks[2]
    if abs(roe_l - inp["roe_l"]) > ROE_TOL:
        errors.append(f"roe_l {inp['roe_l']} != roe_idx x eps_k_l = {roe_l:.4f}")
    if abs(roe_h - inp["roe_h"]) > ROE_TOL:
        errors.append(f"roe_h {inp['roe_h']} != roe_idx x eps_k_h = {roe_h:.4f}")
    if errors:
        return report(errors, "FAIL (named zero / band edge)")

    def band(pe: float, kk: tuple[float, float, float] = ks) -> tuple[float, float, float]:
        return tuple(scale(eps, fee, kx * pe) for kx in kk)  # type: ignore[return-value]

    Lc, Mc, Hc = band(pe_edge)
    errors += ladder("cross-check", Lc, Mc, Hc)
    m = _CROSS_STATED.search(md)
    if not m:
        errors.append("Outputs 对照（整篮 Gordon 公司尺）line not found")
    else:
        for lab, said, got in zip("LMH", (float(x) for x in m.groups()), (Lc, Mc, Hc)):
            if abs(said - got) > 0.002:
                errors.append(f"cross-check {lab}: stated {said} vs recomputed {got:.4f}")
    if errors:
        return report(errors, "FAIL (cross-check band)")

    # --- Step 5: deck must equal the Outputs line -----------------------------
    errors = check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, None, tol=0.002)
    if errors:
        return report(errors)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}  index={INDEX_LABEL} ({INDEX_SRC}:{INDEX_CODE}) {ch['start']}..{ch['end']}")
    print(f"篮子: r_perp={r:.1%} 篮 {baskets['r_perp']}（look-through 加权粗算 10.3–10.8%，只披露；通道无 r）; "
          f"g2 cap = min(6%, r−4%) = {min(0.06, r - 0.04):.1%}, 公司尺具名 g2=0")
    print(f"通道: 斜率 {ch['slope']:+.1%}（全窗）· 子窗 2019 起 {subs['2019']:+.1%} / 2021 起 {subs['2021']:+.1%} "
          f"(gap {max(abs(v - full['slope']) for v in subs.values()):.1%} < {REGIME_GAP:.0%}, regime 不触发) · σ {ch['sigma']:.1%}")
    print(f"指数点 L/M/H = {ch['L']:,.0f} / {ch['M']:,.0f} / {ch['H']:,.0f}; k = nav_ref {nav_ref} / {ch['cur']:,.2f} = {k:.3e}")
    print(f"L/M {L / M:.3f} | H/M {H / M:.3f} | width {(H - L) / (2 * M):.3f} | V_opt/M 0.000 (残差 p10 {L / M - 1:+.1%} / p90 {H / M - 1:+.1%})")
    print(f"L={L:.4f} M={M:.4f} H={H:.4f} A={A:.4f} B={B:.4f}")
    if rn:
        Lr, Mr, Hr = rn["chan"]
        print(f"去利率化对照版: CNY 10Y {rn['rf_start']:.2%} → {rn['rf_now']:.2%} / 中枢 {rn['rf_mid']:.1%}; 去利率化斜率 {rn['slope']:+.1%} "
              f"(利率顺风 {rn['rate_drift']:+.2%}/yr); β level {rn['beta']:+.1f} / 差分 {rn['beta_diff']:+.1f} (ρ {rn['rho_diff']:+.2f}) / 先验 {rn['beta_prior']:+.0f}; "
              f"L′/M′/H′ {Lr:.4f} / {Mr:.4f} / {Hr:.4f}; 利率中枢化使 M 移动 {Mr / M - 1:+.1%}")
        print(f"先验 β 压力行: 斜率 {rn['prior']['slope']:+.1%}, M′ {rn['prior']['M'] * k:.4f}（纯永续世界，不出带）")
    c19 = channel(s[s.index >= SUBWINDOWS[0]])
    b19 = tuple(c19[key] * k for key in ("L", "M", "H"))
    print(f"敏感性 通道窗 2019 起 (斜率 {c19['slope']:+.1%}): {'/'.join(f'{x:.4f}' for x in b19)}（只披露，不改窗）")
    print(f"E 侧护栏（只打印）: PE {inp['pe_now']} vs 自身带 [{inp['pe_own_min']}, {inp['pe_own_max']}] / 2018–23 带 [{inp['pe_band_2018_23_lo']}, {inp['pe_band_2018_23_hi']}]; "
          f"EPS/点 自 2023 顶 {inp['eps_pt_from_peak']:+.0%}; 每点分红 2025 {inp['dps_pt_2025_yoy']:+.0%}; 派息率 {payout_etf:.1%} (TTM DPS YoY {dps_yoy:+.1%})")
    print(f"地板: 不设（被动篮子无独立于净值的公允价）; 不 max()")

    # company-ruler cross-check (was the v1 primary) — printed, compared with the Outputs 对照 line
    print(f"对照 {CROSS_FORMULA_ID}: 透视 EPS = nav_ref {nav_ref} / {inp['pe_now']} = {eps:.5f}; 派息率 {payout_etf:.2%} (< {NEAR_FULL_PAYOUT:.0%} 仍留存; "
          f"证据区间 [{ev_lo:.1%}, {ev_hi:.1%}])")
    print(f"  同世界门: 3y 透视 EPS 因子 {k_3y:.4f} ({k_3y - 1:+.1%}/yr), 1y {k_1y:.4f} ({k_1y - 1:+.1%}) DOWN; "
          f"覆盖共识 {inp['g_cov_fwd']:+.2%} on {inp['cov_w']:.1%} weight → DOWN 赢 → 留存正 g 不可用")
    print(f"  反事实留存分支 g=(1−{payout_etf:.1%})×ROE {roe:.1%} = {g_retention_m:+.2%} → PE {perpetual_pe(g_retention_m, roe, r):.2f}x (v4); "
          f"check_branch: {branch_msgs[0] if branch_msgs else '符号/幅度通过（挡住的是同世界门）'}")
    print(f"  具名 g2=0 → 1/r = {pe_zero:.2f}x; 自身带顶 {inp['pe_own_max']} 截断 → {pe_edge:.2f}x flat "
          f"(边缘残余 g 全派息 {g_edge_full:+.2%} / 留存 {implied_g_retaining(pe_edge, roe, r)[0]:+.2%}，只披露)")
    print(f"  对照带 L/M/H = {Lc:.4f} / {Mc:.4f} / {Hc:.4f}; 通道 vs 公司尺 M {M / Mc - 1:+.1%}, H {H / Hc - 1:+.1%}")
    for lab, pe in (("v5 具名零不截断", pe_zero), ("v4 留存分支", inp["pe_v4"]),
                    ("同等盈利实测 med", inp["pe_same_med"])):
        b = band(pe)
        print(f"  对照 {lab} {pe:.2f}x: {'/'.join(f'{x:.4f}' for x in b)}")
    print(f"OK  L={L:.4f} M={M:.4f} H={H:.4f} A={A:.4f} B={B:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
