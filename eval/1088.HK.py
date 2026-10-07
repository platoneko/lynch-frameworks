#!/usr/bin/env python3
"""1088.HK (China Shenhua Energy) valuation eval.

frameworks/1088.HK.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The
framework carries no current price (AGENTS.md「现价 — 禁写契约」): no zone here.

formula_id: shenhua_hk_coal_axis_leg_sum_v1

Main ruler: a leg SUM on the H share (valuation-rules「归篮触发分腿」): the
commodity legs (coal + shipping + coal chemicals) at 篮 6 13%, power (with the
coal-power JV associates) at 篮 4 10%, rail + port at 篮 4 10%; each leg at
1/r (g = 0: forward retention repays the 2026 acquisition debt, A7).

Numerator FY2027 on the 2026 post-acquisition base (12 parent companies
bought in 2026H1, 2025 restated): segment profit before tax rides the shared
coal axis (_AXIS.coal-price, miner side, 703 / 830 / 965) through the company's
OWN 2019-25 segment regression on the axis base series:

    coal_x  = coal_pf  + slope_coal x vol_scale x (q_x - 703)
    power_x = power_pf + (slope_power + slope_unalloc) x power_scale x (q_x - 703)
    NI_x    = (legs + residual) x conv

The bridge must replay >= 2 realised years within ±20% (axis 4c-1), anchored
on FY2025 reported NI with each year's own NI / PBT.

Run:  python3 frameworks/eval/1088.HK.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import check_coal_mount, load_coal_series  # noqa: E402
from lib.gordon import basket_r, check_r  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.tiers import decompose  # noqa: E402
from lib.zones import cut_points, zone_of  # noqa: E402

sys.path.append(str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FRAMEWORK = REPO / "frameworks" / "1088.HK.md"
FORMULA_ID = "shenhua_hk_coal_axis_leg_sum_v1"
TICKER = "1088.HK"
LISTING_CCY = "HKD"

TIERS = ("l", "m", "h")
YEARS = range(2019, 2026)
REPLAY_YEARS = (2022, 2023, 2024)
REPLAY_TOL = 0.20
CONS_DEV_MAX = 0.20
GATE_OUT = 0.20
LEGS = ("r_coal", "r_power", "r_rail")
ASP_TOL = 0.5

REQUIRED = [
    "shares", "fx_hkdcny", "bps", "net_debt", "conv",
    "coal_l", "coal_m", "coal_h", *(f"coal_fy{y}" for y in YEARS),
    "asp_l", "asp_m", "asp_h", "asp_a", "asp_b",
    *(f"seg_{s}_fy{y}" for s in ("coal", "power", "unalloc") for y in YEARS),
    *(f"pbt_fy{y}" for y in REPLAY_YEARS + (2025,)), *(f"ni_fy{y}" for y in REPLAY_YEARS + (2025,)),
    "pbt_coal_pf", "pbt_power_pf", "pbt_power_fy25_exassoc", "pbt_rail_pf", "pbt_shipchem", "pbt_resid_pf",
    "vol_scale", *LEGS,
    "payout_fy25", "pe_own_min", "pe_own_max",
    "px_same_p25", "px_same_med", "px_same_p75", "pb_own_med",
    "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi", "tp_cons_h",
]
NOT_FORMULA = ("bps", "net_debt", "payout_fy25", "pe_own_min", "pe_own_max", "px_same_p25", "px_same_med",
               "px_same_p75", "pb_own_med", "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean",
               "eps_cons_fy27_hi", "tp_cons_h", "asp_l", "asp_m", "asp_h", "asp_a", "asp_b")


def slope(inp: dict[str, float], seg: str) -> float:
    x = [inp[f"coal_fy{y}"] for y in YEARS]
    y = [inp[f"seg_{seg}_fy{y}"] for y in YEARS]
    return float(np.polyfit(x, y, 1)[0])


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    errors += [f"probability-looking input {k}" for k in inp if k.startswith("p_")]

    # --- Step 1: axis mount (miner side), base series, own coordinate ---------
    q = {t: inp[f"coal_{t}"] for t in TIERS}
    errors += check_coal_mount((q["l"], q["m"], q["h"]), "miner")
    series = load_coal_series()
    for y in YEARS:
        if abs(series.get(y, -1) - inp[f"coal_fy{y}"]) > 0.5:
            errors.append(f"coal_fy{y} {inp[f'coal_fy{y}']} != axis base series {series.get(y)}")
    for t in TIERS:   # axis §4a 神华自产煤线 330.99 + 0.2147 x (disclosure coordinate)
        line = inp["asp_a"] + inp["asp_b"] * q[t]
        if abs(line - inp[f"asp_{t}"]) > ASP_TOL:
            errors.append(f"asp_{t} {inp[f'asp_{t}']} != axis §4a self-produced line {line:.1f}")

    # --- Step 2: bridge slopes and replay (axis 4c-1) --------------------------
    s_coal, s_pow, s_un = slope(inp, "coal"), slope(inp, "power"), slope(inp, "unalloc")
    s_used = s_coal + s_pow + s_un
    replay = {}
    for y in REPLAY_YEARS:
        conv_y = inp[f"ni_fy{y}"] / inp[f"pbt_fy{y}"]
        pred = inp["ni_fy2025"] + s_used * (inp[f"coal_fy{y}"] - inp["coal_fy2025"]) * conv_y
        replay[y] = pred / inp[f"ni_fy{y}"] - 1.0
    if sum(abs(e) <= REPLAY_TOL for e in replay.values()) < 2:
        errors.append(f"bridge replays < 2 realised years within ±{REPLAY_TOL:.0%}: {replay} — BLOCKED on the axis (4c-1)")

    # --- Step 3: baskets ----------------------------------------------------------
    baskets = parse_baskets(md)
    for leg in LEGS:
        if leg not in baskets:
            errors.append(f"{leg}: no 篮 N in its Inputs source cell")
        errors += check_r(inp[leg], leg, baskets.get(leg))
    if errors:
        return report(errors, "FAIL (axis / bridge / baskets)")

    # --- Step 4: legs and anchors ---------------------------------------------------
    power_scale = inp["pbt_power_fy25_exassoc"] / inp["seg_power_fy2025"]   # pro-forma power ex-associates / FY2025 reported

    def legs(t: str, r: dict[str, float], qx: float | None = None, vol: float | None = None) -> dict[str, float]:
        dq = (q[t] if qx is None else qx) - inp["coal_fy2025"]
        coal = inp["pbt_coal_pf"] + s_coal * (inp["vol_scale"] if vol is None else vol) * dq
        power = inp["pbt_power_pf"] + (s_pow + s_un) * power_scale * dq
        rail = inp["pbt_rail_pf"]
        sc = inp["pbt_shipchem"]
        base = coal + power + rail + sc
        k = 1.0 + inp["pbt_resid_pf"] / base
        hk = inp["conv"] * k / inp["shares"] / inp["fx_hkdcny"]
        return {
            "pbt": base + inp["pbt_resid_pf"],
            "coal": (coal + sc) * hk / r["r_coal"],
            "power": power * hk / r["r_power"],
            "rail": rail * hk / r["r_rail"],
        }

    r0 = {leg: inp[leg] for leg in LEGS}

    def band(r: dict[str, float] = r0, **kw) -> tuple[float, float, float]:
        return tuple(sum(v for k, v in legs(t, r, **kw).items() if k != "pbt") for t in TIERS)  # type: ignore[return-value]

    lg = {t: legs(t, r0) for t in TIERS}
    ni = {t: lg[t]["pbt"] * inp["conv"] for t in TIERS}
    eps = {t: ni[t] / inp["shares"] for t in TIERS}
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    L, M, H = band()
    if not (L < M < H):
        return report(errors + [f"L<M<H violated {L:.2f} {M:.2f} {H:.2f}"])
    A, B = cut_points(L, M, H)
    pe_eff = {t: a * inp["fx_hkdcny"] / eps[t] for t, a in zip(TIERS, (L, M, H))}

    # --- Step 5: guards ---------------------------------------------------------------
    in_band = all(inp["pe_own_min"] <= pe_eff[t] <= inp["pe_own_max"] for t in TIERS)
    cons = inp["eps_cons_fy27_mean"]
    dev = eps["m"] / cons - 1.0
    if cons > eps["h"]:
        errors.append(f"②-b: consensus FY27 mean {cons} above EPS_H {eps['h']:.3f}")
    if abs(dev) > CONS_DEV_MAX:
        errors.append(f"②-b: M deviates {dev:+.1%} from consensus mean (> {CONS_DEV_MAX:.0%})")
    if cons < eps["m"] and "②-b" not in md:
        errors.append("②-b: consensus mean below EPS_M without the named-variable row (A6)")
    bps_hkd = inp["bps"] / inp["fx_hkdcny"]
    zero_r = band({leg: inp["r_coal"] for leg in LEGS})
    coords = {
        "E_M/r 整篮 13%": zero_r[1],
        "D_M/(r̄)": inp["payout_fy25"] * eps["m"] / inp["fx_hkdcny"] / (
            (lg["m"]["coal"] * inp["r_coal"] + lg["m"]["power"] * inp["r_power"] + lg["m"]["rail"] * inp["r_rail"]) / M),
        "同等盈利月份中位": inp["px_same_med"],
        "BPS × 5 年 PB 中位": bps_hkd * inp["pb_own_med"],
    }
    if all(abs(M / v - 1.0) > GATE_OUT for v in coords.values()):
        errors.append(f"对账: M {M:.2f} outside every coordinate by > {GATE_OUT:.0%} — BLOCKED")
    for k in NOT_FORMULA:
        if k not in inp:
            errors.append(f"reference row missing: {k}")
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # --- report -------------------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"axis _AXIS.coal-price (miner) OK: {q['l']:g}/{q['m']:g}/{q['h']:g}; 自产煤坐标 {inp['asp_l']}/{inp['asp_m']}/{inp['asp_h']} 元/吨 (§4a 线, 披露)")
    print(f"斜率 (2019–25 分部利润总额对轴基准序列, 百万元 / 元·吨): 煤炭 {s_coal:.2f} · 发电 {s_pow:.2f} · 未分配 {s_un:.2f} → 合计 {s_used:.2f}")
    print("桥复现 (锚 FY2025 归母, 各年 NI/PBT): " + " · ".join(f"FY{y} {e:+.1%}" for y, e in replay.items()))
    print(f"重组后: vol_scale {inp['vol_scale']:.3f} (自产煤销量 2026H1 年化 / FY2025) · power_scale {power_scale:.3f} (备考发电 / FY2025) · conv {inp['conv']}")
    print("篮子: " + "; ".join(f"{leg} 篮 {baskets[leg]} {basket_r(baskets[leg]):.0%}" for leg in LEGS))
    print(f"{'档':<3}{'煤价':>6}{'PBT':>9}{'NI':>9}{'EPS':>7}{'商品腿':>8}{'发电':>7}{'铁港':>7}{'HKD':>8}{'有效PE':>8}")
    for t, a in zip(TIERS, (L, M, H)):
        print(f"{t.upper():<3}{q[t]:6.0f}{lg[t]['pbt']:9,.0f}{ni[t]:9,.0f}{eps[t]:7.3f}{lg[t]['coal']:8.2f}{lg[t]['power']:7.2f}{lg[t]['rail']:7.2f}{a:8.2f}{pe_eff[t]:8.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    d = decompose((L, M, H), (pe_eff["l"], pe_eff["m"], pe_eff["h"]))
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.1%} | 分子比 L={d['num_lm']:.3f} H={d['num_hm']:.3f} | 有效倍数比 L={d['pe_lm']:.3f} H={d['pe_hm']:.3f}")
    print(f"护栏 ③: 有效 PE {'/'.join(f'{pe_eff[t]:.2f}' for t in TIERS)} vs 同等盈利月份带 [{inp['pe_own_min']}, {inp['pe_own_max']}] → {'不触发' if in_band else '出带 (披露)'}")
    print(f"②-b: 共识 FY27 {inp['eps_cons_fy27_lo']}/{cons}/{inp['eps_cons_fy27_hi']} vs EPS {eps['l']:.3f}/{eps['m']:.3f}/{eps['h']:.3f}: M dev {dev:+.1%}; FY26E 均值 {inp['eps_cons_fy26_mean']}")
    print("对账坐标: " + "; ".join(f"{k} {v:.2f} (M {M / v - 1:+.0%})" for k, v in coords.items())
          + f"; 同等盈利月份 IQR {inp['px_same_p25']}–{inp['px_same_p75']}")
    a_cny, b_cny = A * inp["fx_hkdcny"], B * inp["fx_hkdcny"]
    print(f"中性带 PE 读数: 中枢 EPS {a_cny / eps['m']:.1f}–{b_cny / eps['m']:.1f}x · FY26E {a_cny / inp['eps_cons_fy26_mean']:.1f}–{b_cny / inp['eps_cons_fy26_mean']:.1f}x")
    for qm in (821.0, 855.0):
        print(f"轴 M 窗口 {qm:g}: M = {sum(v for k, v in legs('m', r0, qx=qm).items() if k != 'pbt'):.2f}")
    for label, kw in (
        ("铁路 / 港口 篮 2 7.5%", dict(r={**r0, "r_rail": 0.075})),
        ("煤炭等商品腿 篮 4 10%", dict(r={**r0, "r_coal": 0.10})),
        ("发电 篮 6 13%", dict(r={**r0, "r_power": 0.13})),
        ("vol_scale = 1 (不按重组放大)", dict(vol=1.0)),
    ):
        print(f"敏感性 {label}: {'/'.join(f'{x:.2f}' for x in band(**kw))}")
    tp = inp["tp_cons_h"]
    print(f"卖方 TP 均值 {tp} 落 {zone_of(tp, L, M, H)}; H/TP {H / tp:.2f} (交叉, 不反解)")
    print(f"净负债 (只披露): {inp['net_debt']:,.0f} mn = {inp['net_debt'] / inp['shares'] / inp['fx_hkdcny']:.2f} HKD/股; BPS {bps_hkd:.2f} HKD, 锚点 PB {L / bps_hkd:.2f}/{M / bps_hkd:.2f}/{H / bps_hkd:.2f}")
    print(f"A股对照(CNY): L={L * inp['fx_hkdcny']:.2f} M={M * inp['fx_hkdcny']:.2f} H={H * inp['fx_hkdcny']:.2f}")

    def band_rf(dr: float) -> tuple[float, float, float]:
        return band({leg: v + dr for leg, v in r0.items()})

    rf = rf_block(LISTING_CCY, dict(r0), band_rf)
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: dr = 0 does not reproduce L/M/H")
    if not errors:
        write_rf_readings(TICKER, rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
