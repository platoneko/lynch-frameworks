#!/usr/bin/env python3
"""600522.SH (Jiangsu Zhongtian Technology) valuation eval.

frameworks/600522.SH.md is the source of truth; this script re-derives
L/M/H / A/B and the candidate band from its §3 Inputs table and exits 1 on
mismatch.  The framework carries no current price (AGENTS.md「现价 — 禁写契约」):
no zone here.

formula_id: zhongtian_fiber_axis_core_gordon_v1

Main ruler: whole-company Gordon on OPERATING earnings (ex interest income and
investment income) + net cash + investments at book (valuation-rules「峰形区处理」
step 1: net cash depresses book ROE).  Net cash is after the declared-unpaid
dividend (应付股利, valuation-rules「经营价值与超额现金」① 类债项); the framework
already lists cash at face with interest stripped, so the structure is kept
(① 触发: 已单列保留结构) and no operating-cash anchor is cut.  r = 篮 4 10% (initial 篮 6 failed the
own-band guard ③ on a clean band; see A6).  g2 = 0 (retention goes to cash,
留存去向审计 B 桶).

Numerator = non-fiber legs (demand-cycle manufacturing, measured NF gross-profit
CAGR FY2023→25 extrapolated to FY2027) + fiber leg bridged from the shared
fiber-price axis (_AXIS.optical-fiber, CRU China G.652.D bare-fibre spot):

    fiber_opNI = a + b × price      (fit on FY2018–25, must replay ≥ 2 years ±20%)

    L = (NF_FY2024 + fiber(axis L)) × PE + cash            regime (glut persists)
    M = (NF_FY2027 + fiber(axis M)) × PE + cash
    H = M + PV(fiber excess FY2027, FY2028 at consensus high)   point (decays to M)

2026-10-16 framework correction (valuation-rules「经营价值与超额现金」): net cash x parent ratio;
the numerator strips only the parent share of interest; time alignment tau on the calendar parts
(non-fiber leg, H excess; the fiber leg at an axis regime / cycle-centre price is not aligned) plus
the 2H26 window distributable profit; the k on the deemed-retained cash is removed.

Run:  python3 frameworks/eval/600522.SH.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import basket_r, check_g_cap, check_r, perpetual_pe, recovery_two_stage_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FRAMEWORK = REPO / "frameworks" / "600522.SH.md"
AXIS = REPO / "frameworks" / "axes" / "optical-fiber.md"
FORMULA_ID = "zhongtian_fiber_axis_core_gordon_v1"

TIERS = ("l", "m", "h")
FIT_YEARS = range(2018, 2026)
RATIO_YEARS = (2016, 2017, 2018, 2019, 2020, 2022, 2023, 2024, 2025)   # FY2021: one-off trade-fraud loss
REPLAY_TOL = 0.20
TOL = 0.05

REQUIRED = [
    "shares", "eq_h1", "cash_h1", "cash_restricted", "debt_h1", "div_declared", "inv_h1",
    "r_perp", "g2", "payout_obs", "k_l", "k_m", "k_h", "ai_vol",
    "fiber_l", "fiber_m", "fiber_h", *(f"fiber_fy{y}" for y in FIT_YEARS),
    *(f"fib_gp_fy{y}" for y in range(2016, 2026)), *(f"gp_fy{y}" for y in range(2016, 2026)),
    *(f"ni_fy{y}" for y in RATIO_YEARS), *(f"nonop_fy{y}" for y in RATIO_YEARS),
    "cons27_lo", "cons27_mean", "cons27_hi", "cons28_mean", "cons28_hi",
    "pe_same_min", "pe_same_n", "pb_own_min", "ebitda_fy25", "ebit_fy25", "interest_fy25",
    "minority_h1", "int_fy2025", "int_fy2024", "tau", "cons26_mean", "ni_h1_2026",
]

_RUNG = re.compile(r"^\|\s*\*\*([LMH])\*\*\s*\|[^|]*\|\s*\*\*([0-9.]+)\*\*")
_SERIES = re.compile(r"^\|\s*FY(\d{4})\s*\|\s*\*\*([0-9.]+)\*\*")


def load_axis() -> tuple[dict[str, float], dict[int, float]]:
    rungs: dict[str, float] = {}
    series: dict[int, float] = {}
    for line in AXIS.read_text(encoding="utf-8").splitlines():
        if (m := _RUNG.match(line)) and m.group(1) not in rungs:
            rungs[m.group(1).lower()] = float(m.group(2))
        elif m := _SERIES.match(line):
            series[int(m.group(1))] = float(m.group(2))
    return rungs, series


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        return report([f"formula_id {FORMULA_ID} missing from framework"])
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    errors += [f"probability-looking input {k}" for k in inp if k.startswith("p_")]

    # --- Step 1: axis mount ---------------------------------------------------------
    rungs, series = load_axis()
    for t in TIERS:
        if abs(rungs.get(t, -1) - inp[f"fiber_{t}"]) > 1e-6:
            errors.append(f"fiber_{t} {inp[f'fiber_{t}']} != axis rung {rungs.get(t)}")
    for y in FIT_YEARS:
        if abs(series.get(y, -1) - inp[f"fiber_fy{y}"]) > 1e-6:
            errors.append(f"fiber_fy{y} {inp[f'fiber_fy{y}']} != axis series {series.get(y)}")
    m_window = float(np.mean([inp[f"fiber_fy{y}"] for y in FIT_YEARS]))
    if abs(m_window - inp["fiber_m"]) > 0.05:
        errors.append(f"axis M {inp['fiber_m']} != FY2018–25 mean {m_window:.2f}")

    # --- Step 2: fiber leg operating profit and the bridge ----------------------------
    ratio = {y: (inp[f"ni_fy{y}"] - inp[f"nonop_fy{y}"]) / inp[f"gp_fy{y}"] for y in RATIO_YEARS}
    ratio[2021] = (ratio[2019] + ratio[2020] + ratio[2022]) / 3
    fib = {y: inp[f"fib_gp_fy{y}"] * ratio[y] for y in range(2016, 2026)}
    x = np.array([inp[f"fiber_fy{y}"] for y in FIT_YEARS])
    yv = np.array([fib[y] for y in FIT_YEARS])
    b, a = np.polyfit(x, yv, 1)
    pred = a + b * x
    r2 = 1 - float(((yv - pred) ** 2).sum() / ((yv - yv.mean()) ** 2).sum())
    replay = {y: float(p / v - 1) for y, p, v in zip(FIT_YEARS, pred, yv)}
    if sum(abs(e) <= REPLAY_TOL for e in replay.values()) < 2:
        errors.append(f"bridge replays < 2 years within ±20% — BLOCKED on the axis: {replay}")
    fiber = {t: a + b * inp[f"fiber_{t}"] for t in TIERS}
    self_mid = float(np.mean([fib[y] for y in range(2016, 2026)]))

    # --- Step 3: baskets, caps ----------------------------------------------------------
    baskets = parse_baskets(md)
    r = inp["r_perp"]
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(inp["g2"], r, "g2")
    if errors:
        return report(errors, "FAIL (axis / bridge / baskets)")

    # --- Step 4: legs and anchors ----------------------------------------------------------
    sh = inp["shares"]
    netcash = inp["cash_h1"] - inp["cash_restricted"] - inp["debt_h1"] - inp["div_declared"]
    # Parent share (valuation-rules「经营价值与超额现金」① 归母份额): no subsidiary-level cash disclosure
    # -> parent equity / (parent + minority); applied to the net cash (investments are not cash) and to
    # the interest stripped from the numerator (parent NI only carries the parent share of it).
    pr = inp["eq_h1"] / (inp["eq_h1"] + inp["minority_h1"])
    cash_inv = netcash * pr + inp["inv_h1"]
    op_eq = inp["eq_h1"] - (netcash + inp["inv_h1"])
    int_minor25 = (1 - pr) * inp["int_fy2025"] * 0.85
    nonop = inp["nonop_fy2025"] - int_minor25
    nf25 = inp["ni_fy2025"] - nonop - fib[2025]
    g_nf = ((inp["gp_fy2025"] - inp["fib_gp_fy2025"]) / (inp["gp_fy2023"] - inp["fib_gp_fy2023"])) ** 0.5 - 1
    nf = {2027: nf25 * (1 + g_nf) ** 2, 2028: nf25 * (1 + g_nf) ** 3}
    nf_l = inp["ni_fy2024"] - (inp["nonop_fy2024"] - (1 - pr) * inp["int_fy2024"] * 0.85) - fib[2024]
    g2 = inp["g2"]
    tau = inp["tau"]
    # Window distributable profit (valuation-rules「经营价值与超额现金」③ 时点对齐): 2H26 unbooked
    # consensus 归母 (FY2026E - 1H26 actual) less half a year of non-operating items (numerator basis),
    # x (1 - b), b = g2 / RONIC = 0; discounted tau/2.
    win = max(0.0, inp["cons26_mean"] - inp["ni_h1_2026"] - 0.5 * inp["nonop_fy2025"]) / sh

    def anchors(rr: float, vol: float = 1.0) -> dict[str, float]:
        """Fiber leg sits at an axis regime / cycle-centre price -> no tau (周期中枢不适用); the
        non-fiber leg and H's FY27/FY28 excess are calendar values -> x (1+r)^-tau."""
        f = {t: fiber[t] * vol for t in TIERS}
        d = (1 + rr) ** -tau
        w = win * (1 + rr) ** -(tau / 2)
        e_m = nf[2027] + f["m"]
        e_l = nf_l + f["l"]
        roe_m, roe_l = e_m / op_eq, e_l / op_eq
        pe_m, pe_l = perpetual_pe(g2, roe_m, rr), perpetual_pe(g2, roe_l, rr)
        v_m = f["m"] * pe_m + nf[2027] * pe_m * d + cash_inv
        v_l = f["l"] * pe_l + nf_l * pe_l * d + cash_inv
        ex = {2027: inp["cons27_hi"] - nonop - nf[2027] - f["m"],
              2028: inp["cons28_hi"] - nonop - nf[2028] - f["m"]}
        pv_ex = (ex[2027] / (1 + rr) + ex[2028] / (1 + rr) ** 2) * d
        h_pre = (v_m + pv_ex) / sh + w
        deemed_h = (1 - inp["payout_obs"]) * (inp["cons27_hi"] + inp["cons28_hi"]) / sh
        g1 = (e_m / e_l) ** 0.5 - 1
        return {
            "L": v_l / sh + w, "M": v_m / sh + w, "H_pre": h_pre, "H": h_pre - inp["k_h"] * deemed_h,
            "deemed_h": deemed_h, "e_m": e_m, "e_l": e_l, "roe_m": roe_m, "roe_l": roe_l,
            "ex27": ex[2027], "ex28": ex[2028],
            "L_point": (e_l * recovery_two_stage_pe(g1, 2, g2, roe_m, rr) + cash_inv) / sh,
            "H_regime": ((inp["cons27_hi"] - nonop) * perpetual_pe(g2, (inp["cons27_hi"] - nonop) / op_eq, rr) + cash_inv) / sh,
        }

    base = anchors(r)
    L, M, H = base["L"], base["M"], base["H"]
    if not (L < M < H):
        return report(errors + [f"L<M<H violated {L:.2f} {M:.2f} {H:.2f}"])
    A, B = cut_points(L, M, H)
    eps = {"l": (base["e_l"] + nonop) / sh, "m": (base["e_m"] + nonop) / sh, "h": inp["cons27_hi"] / sh}
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])

    # --- Step 5: guards ---------------------------------------------------------------------
    if not (0.0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] <= 1.0):
        errors.append("k ladder 0 ≤ k_L ≤ k_M ≤ k_H ≤ 1 violated")
    # k on the 「多留部分」 is removed (2026-10-16 框架纠正: a k may only sit on a named transaction;
    # the retained-but-deemed-paid cash is carried by λ = 1).  Guard: no k on this ticker.
    k_top = 1 - M / base["H_pre"]
    if any(inp[k] != 0.0 for k in ("k_l", "k_m", "k_h")):
        errors.append("k must be 0: this ticker has no named transaction for a k to sit on (A12)")
    pe_m_equiv = M / eps["m"]
    if pe_m_equiv < inp["pe_same_min"]:
        errors.append(f"③: M equiv PE {pe_m_equiv:.2f} below same-earnings band floor {inp['pe_same_min']}")
    c27 = inp["cons27_mean"] / sh
    if not (eps["m"] <= c27 <= eps["h"]):
        errors.append(f"②-b (i): consensus FY27 mean EPS {c27:.3f} outside [EPS_M, EPS_H]")
    flat = [(base[k] if k != "H" else base["H"]) for k in ("L", "M", "H")]
    errors += ladder("flat", *flat)
    contrast13 = anchors(basket_r(6))
    if contrast13["M"] / eps["m"] >= inp["pe_same_min"]:
        errors.append("③ path: initial basket 13% no longer fails the band — basket-downgrade record stale (A6)")
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    cand = anchors(r, inp["ai_vol"])
    cm = re.search(r"L′ = \*\*([0-9.]+)\*\* · M′ = \*\*([0-9.]+)\*\* · H′ = \*\*([0-9.]+)\*\*", md)
    if not cm:
        errors.append("candidate band line not found")
    else:
        for said, got, k in zip(map(float, cm.groups()), (cand["L"], cand["M"], cand["H"]), ("L′", "M′", "H′")):
            if abs(said - got) > TOL:
                errors.append(f"{k}: stated {said} vs recomputed {got:.4f}")

    # --- report ---------------------------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"axis _AXIS.optical-fiber OK: L/M/H {inp['fiber_l']}/{inp['fiber_m']}/{inp['fiber_h']} 元/芯公里 (FY2018–25 均值 {m_window:.2f})")
    print(f"桥 fiber_opNI = {a:.3f} + {b:.4f} × price  R²={r2:.3f}; 复现 " + " ".join(f"FY{y} {e:+.0%}" for y, e in replay.items()))
    print(f"光纤腿 L/M/H(价) {fiber['l']:.2f}/{fiber['m']:.2f}/{fiber['h']:.2f} 亿 · 自身十年均值交叉 {self_mid:.2f} 亿")
    print(f"非光纤 NF FY25 {nf25:.2f} · 增速 {g_nf:.4f} · FY27 {nf[2027]:.2f} · FY28 {nf[2028]:.2f} · L(FY24) {nf_l:.2f}")
    print(f"①b 读数 1 − M/H(k 前) = {k_top:.3f}（只披露；k 已去掉）· 归母比例 {pr:.4f} · τ {tau:g} · 窗口可分配利润 {win:.3f}/股")
    print(f"净现金 {netcash:.2f}（已扣应付股利 {inp['div_declared']:.2f}）· 投资 {inp['inv_h1']:.2f} · 经营权益 {op_eq:.2f} · ROE_op L/M {base['roe_l']:.2%}/{base['roe_m']:.2%}")
    print(f"H 超额 FY27 {base['ex27']:.2f} · FY28 {base['ex28']:.2f} 亿; H k 前 {base['H_pre']:.2f}; 视同派出(H 窗口) {base['deemed_h']:.2f}/股 × k_H {inp['k_h']} = {inp['k_h'] * base['deemed_h']:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.1%} | EPS {eps['l']:.3f}/{eps['m']:.3f}/{eps['h']:.3f} 分子比 L {eps['l'] / eps['m']:.3f} H {eps['h'] / eps['m']:.3f}")
    print(f"③: M 等价 PE {pe_m_equiv:.2f} vs 同等盈利月份下沿 {inp['pe_same_min']} (n={inp['pe_same_n']:.0f}); 13% 对照 M {contrast13['M']:.2f} 等价 PE {contrast13['M'] / eps['m']:.2f}")
    print(f"对照带 13%: {contrast13['L']:.2f}/{contrast13['M']:.2f}/{contrast13['H']:.2f}; L point {base['L_point']:.2f}; H regime {base['H_regime']:.2f}")
    print(f"候选带 ×{inp['ai_vol']}: {cand['L']:.2f}/{cand['M']:.2f}/{cand['H']:.2f}")
    for dg in (-0.01, 0.01):
        g2_save = g2
        g2 = g2_save + dg
        s = anchors(r)
        g2 = g2_save
        print(f"敏感性 g2 {dg:+.0%}: {s['L']:.2f}/{s['M']:.2f}/{s['H']:.2f}")
    print(f"杠杆门: 净债/EBITDA {-netcash / inp['ebitda_fy25']:.2f} · 利息/EBIT {inp['interest_fy25'] / inp['ebit_fy25']:.1%} → 不触发")
    print(f"对账坐标: BPS×PB 下沿 {inp['eq_h1'] / sh * inp['pb_own_min']:.2f} (M {M / (inp['eq_h1'] / sh * inp['pb_own_min']) - 1:+.0%})")
    print(f"中性带 PE: 中枢 EPS {A / eps['m']:.1f}–{B / eps['m']:.1f}x · FY27 均值 {A / c27:.1f}–{B / c27:.1f}x")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
