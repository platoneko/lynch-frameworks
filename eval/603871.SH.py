#!/usr/bin/env python3
"""603871.SH (Jiayou International Logistics) valuation eval.

frameworks/603871.SH.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc states
no current price or zone (the digest and the app zone on live quotes).

formula_id: jiayou_mgl_afr_window_pv_parity_concession_vopt_kasa_v3

Main ruler: two legs, each discounted at its own basket r and ADDED
(SOTP), sharing the company's forward ROE.  The Inputs table names each
leg's basket in the source cell (`篮 N`) and `check_r` enforces that the
value is that basket's; both legs currently sit in 篮 4 (10%) after the
③-out-of-band step-down (A17).

  Mongolia / other leg  PE_mgl = payout(g_mgl, ROE) / (r_mgl - g_mgl)
  Africa corridor leg   g_afr_window ← PV-parity solve from axis rung at
                        r_afr (H ≤ africa_window_h_cap)
                        g_afr_eq = r_afr - 1 / F(g_afr_window, r_afr, n)
                        PE_afr = payout(g_afr_eq, ROE) / (r_afr - g_afr_eq)
  anchor = NI × [(1 - w_afr) × PE_mgl + w_afr × PE_afr] / shares

Unsigned new corridors are V_opt (A2e-7), not a second g: the ceiling is
k=1 × Kasumbalesa's realised FY2025 land-port NI, capitalised as a 22-year
zero-growth annuity at r_afr.  p_L = p_M = 0; p_H = 1.

The Africa *axis* ladder (0%/3%/5%) is SHARED via _AXIS.africa-corridor.md
with 6655.HK and 600499.SH.  Those two mount it as perpetual nominal g;
Jiayou mounts the window transform (axis §3).  Guard 3 checks Jiayou's
window rates against PV-parity + H cap — not against the raw axis rungs.

Run:  python3 frameworks/eval/603871.SH.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import (  # noqa: E402
    africa_window_from_perp,
    check_africa_jiayou_window,
    load_africa_rungs,
)
from lib.gordon import (  # noqa: E402
    annuity_factor, basket_r, check_g_cap, check_r, implied_g, payout, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

HERE = Path(__file__).resolve().parents[2]
FRAMEWORK = HERE / "frameworks" / "603871.SH.md"
FORMULA_ID = "jiayou_mgl_afr_window_pv_parity_concession_vopt_kasa_v3"

TIERS = ("l", "m", "h")
R_ROWS = ("r_mgl", "r_afr")

REQUIRED = [
    "shares", "bps", "r_mgl", "r_afr", "concession_years", "equity",
    "ni_group_l", "ni_group_m", "ni_group_h", "w_afr",
    "g2_mgl_l", "g2_mgl_m", "g2_mgl_h",
    "g_afr_l", "g_afr_m", "g_afr_h",
    "africa_window_h_cap",
    "ni_ttm", "net_cash", "tp_street", "pe_own_hi", "pe_own_lo",
    "trade_rev_fy25", "trade_gm_fy25",
    "logi_rev_fy25", "logi_gm_fy25",
    "lp_rev_fy25", "lp_gm_fy25",
]


def g_equivalent(g: float, r: float, n: float) -> float:
    """The perpetual growth rate that would be worth the same as n years of g."""
    return r - 1.0 / annuity_factor(g, r, n)


def forward_roe(inp: dict[str, float], tag: str) -> float:
    return inp[f"ni_group_{tag}"] / inp["equity"]


def leg_pes(inp: dict[str, float], tag: str) -> tuple[float, float]:
    """(PE_mgl, PE_afr) for one tier — each leg at its own basket r, shared ROE."""
    roe = forward_roe(inp, tag)
    g_afr_eq = g_equivalent(inp[f"g_afr_{tag}"], inp["r_afr"], inp["concession_years"])
    return (
        perpetual_pe(inp[f"g2_mgl_{tag}"], roe, inp["r_mgl"]),
        perpetual_pe(g_afr_eq, roe, inp["r_afr"]),
    )


def leg_contrib(inp: dict[str, float], tag: str,
                pes: tuple[float, float] | None = None) -> tuple[float, float]:
    """Per-share CNY from each leg: weight-split NI × own-basket PE."""
    pe_mgl, pe_afr = pes if pes is not None else leg_pes(inp, tag)
    ni, w = inp[f"ni_group_{tag}"], inp["w_afr"]
    return (
        (1.0 - w) * ni * pe_mgl * 1e8 / inp["shares"],
        w * ni * pe_afr * 1e8 / inp["shares"],
    )


def anchor(inp: dict[str, float], tag: str, pes: tuple[float, float] | None = None) -> float:
    return sum(leg_contrib(inp, tag, pes))


def company_pe(inp: dict[str, float], tag: str, px: float) -> float:
    """Whole-company implied PE of a per-share value on that tier's numerator."""
    return px * inp["shares"] / 1e8 / inp[f"ni_group_{tag}"]


def kasa_gp(inp: dict[str, float]) -> float:
    return inp["lp_rev_fy25"] * inp["lp_gm_fy25"]


def group_gp_fy25(inp: dict[str, float]) -> float:
    return (
        inp["trade_rev_fy25"] * inp["trade_gm_fy25"]
        + inp["logi_rev_fy25"] * inp["logi_gm_fy25"]
        + kasa_gp(inp)
    )


def kasa_ni(inp: dict[str, float]) -> float:
    """FY2025 land-port GP × group NI/GP.  Sakania was not tolling in FY2025."""
    return kasa_gp(inp) * inp["ni_group_l"] / group_gp_fy25(inp)


def kasa_v_opt(inp: dict[str, float]) -> float:
    """1 × Kasa run-rate as a 22-year zero-growth annuity at r_afr.  k=1 is the A2e-7c default."""
    f0 = annuity_factor(0.0, inp["r_afr"], inp["concession_years"])
    return kasa_ni(inp) * f0 * 1e8 / inp["shares"]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # --- Step 1: baskets — each leg's r must be the basket its source cell names
    baskets = parse_baskets(md)
    for row in R_ROWS:
        if row not in baskets:
            errors.append(f"{row}: no 篮 N in its Inputs source cell (valuation-rules.md「§r 篮子」)")
        errors += check_r(inp[row], row, baskets.get(row))
    if errors:
        return report(errors, "FAIL (baskets)")

    r_mgl, r_afr, n = inp["r_mgl"], inp["r_afr"], inp["concession_years"]
    h_cap = inp["africa_window_h_cap"]

    # --- Step 2: numerator and growth ladders -------------------------------
    errors += ladder(
        "ni_group", inp["ni_group_l"], inp["ni_group_m"], inp["ni_group_h"]
    )
    errors += ladder("g_mgl", inp["g2_mgl_l"], inp["g2_mgl_m"], inp["g2_mgl_h"])
    errors += ladder("g_afr_window", inp["g_afr_l"], inp["g_afr_m"], inp["g_afr_h"])
    if not 0.0 < inp["w_afr"] < 1.0:
        errors.append(f"w_afr={inp['w_afr']} outside (0, 1)")
    for t in TIERS:
        if abs(inp[f"g_afr_{t}"] - r_afr) < 1e-9:
            errors.append(f"g_afr_{t} == r_afr — annuity factor undefined")
    if errors:
        return report(errors, "FAIL (inputs/ladders)")

    g_eq = {t: g_equivalent(inp[f"g_afr_{t}"], r_afr, n) for t in TIERS}
    errors += ladder("g_afr_eq", *(g_eq[t] for t in TIERS))
    # Perpetual cap g_cap(r) = min(6%, r − 4%) applies to perpetual rates only,
    # each at its own leg's r: the Mongolia leg and the Africa leg's *equivalent*
    # perpetual g.  `g_afr_*` are 22-year annuity window rates, not
    # perpetuities — the H window sits at 9% by construction and is fenced by
    # the < r_afr check below.
    for t in TIERS:
        errors += check_g_cap(inp[f"g2_mgl_{t}"], r_mgl, f"g2_mgl_{t}")
        errors += check_g_cap(g_eq[t], r_afr, f"g_afr_eq_{t}")
    if inp["equity"] <= 0:
        errors.append(f"equity={inp['equity']} must be positive")
    for t in TIERS:
        roe = forward_roe(inp, t)
        for leg, g, r in (("mgl", inp[f"g2_mgl_{t}"], r_mgl), ("afr", g_eq[t], r_afr)):
            if r - g <= 0:
                errors.append(f"{leg} g_{t}={g:.4f} >= r={r} — perpetuity diverges")
                continue
            pay = payout(g, roe)
            if not 0.0 < pay <= 1.0 + 1e-12:
                errors.append(f"payout_{leg}_{t}={pay:.3f} outside (0, 1]")
            if g <= 0 and abs(pay - 1.0) > 1e-12:
                errors.append(f"payout_{leg}_{t}={pay:.3f} but g={g:.2%} <= 0 — cap not binding")

    # --- Step 3: window g below r_afr; H cap binds below the r singularity --
    for t in TIERS:
        if inp[f"g_afr_{t}"] >= r_afr - 1e-12:
            errors.append(f"g_afr_{t}={inp[f'g_afr_{t}']:.4f} must be < r_afr={r_afr}")
        if g_eq[t] >= inp[f"g_afr_{t}"]:
            errors.append(f"g_afr_eq_{t}={g_eq[t]:.4%} not below window {inp[f'g_afr_{t}']:.4%}")
    if h_cap >= r_afr - 1e-12:
        errors.append(f"africa_window_h_cap={h_cap:.4f} must be < r_afr={r_afr}")
    if errors:
        return report(errors, "FAIL (window/cap)")

    # --- Step 4: Africa window = PV-parity vs shared axis (+ H cap) ---------
    errors += check_africa_jiayou_window(
        (inp["g_afr_l"], inp["g_afr_m"], inp["g_afr_h"]),
        r=r_afr, n=n, h_cap=h_cap,
    )
    axis = load_africa_rungs()
    for t, axis_g in (("l", axis["L"]), ("m", axis["M"])):
        if abs(g_eq[t] - axis_g) > 5e-4:
            errors.append(
                f"g_afr_eq_{t}={g_eq[t]:+.4%} vs axis {axis_g:+.4%} — "
                f"PV-parity conversion missed"
            )
    if g_eq["h"] > axis["H"] + 5e-4:
        errors.append(
            f"g_afr_eq_h={g_eq['h']:+.4%} above axis H {axis['H']:+.4%}"
        )
    if errors:
        return report(errors, "FAIL (guards/shared axis window)")

    # --- Step 5: anchors (SOTP) and the own-year band guards ----------------
    pes = {t: leg_pes(inp, t) for t in TIERS}
    L, M, H = (anchor(inp, t, pes[t]) for t in TIERS)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)

    co_pe = {t: company_pe(inp, t, px) for t, px in zip(TIERS, (L, M, H))}
    if co_pe["h"] > inp["pe_own_hi"] + 1e-9:
        errors.append(
            f"PE_H={co_pe['h']:.2f} above own-year measured high {inp['pe_own_hi']} — "
            f"H is no longer a modelled world (A2e-2c-ex)"
        )
    # 降篮门 (A17): the M multiple must sit inside the ticker's own measured
    # band; falling below the low edge is the ③-out-of-band signal that says
    # the r, not the ticker — back to the conversation, never printed as-is.
    if co_pe["m"] < inp["pe_own_lo"] - 1e-9:
        errors.append(
            f"PE_M={co_pe['m']:.2f} below own-year measured low {inp['pe_own_lo']} — "
            f"③ 出带，降篮门未过 (A17)"
        )

    v_opt = kasa_v_opt(inp)
    p_k = (0.0, 0.0, 1.0)
    adj_band = [base + pk * v_opt for base, pk in zip((L, M, H), p_k)]
    if v_opt <= 0:
        errors.append(f"V_opt={v_opt:.4f} — 1× Kasa ceiling must be positive")
    gp_share = kasa_gp(inp) / group_gp_fy25(inp)
    if not (0.15 <= gp_share <= 0.30):
        errors.append(
            f"land-port GP share {gp_share:.1%} outside 15–30% of FY2025 GP — "
            "the Kasa analog may no longer be a single operating corridor"
        )
    if abs(adj_band[0] - L) > 1e-9 or abs(adj_band[1] - M) > 1e-9:
        errors.append(
            f"p leaked into the base: 表3 L/M {adj_band[0]:.4f}/{adj_band[1]:.4f} "
            f"!= {L:.4f}/{M:.4f}"
        )
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")

    # flat-multiple ladder: each leg held at its own M-tier PE.
    flat = {t: anchor(inp, t, pes["m"]) for t in TIERS}
    errors += ladder("flat-multiple", flat["l"], flat["m"], flat["h"])

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})
    outs = md.split("### Outputs", 1)[-1]
    vm = re.search(
        r"V_\{?opt\}?\\?\)?\s*[≈=]\s*\*{0,2}\s*\+?([0-9]+(?:\.[0-9]+)?)",
        outs,
    )
    if vm is None:
        errors.append("stated V_opt not found in Outputs")
    elif abs(float(vm.group(1)) - v_opt) > 0.05:
        errors.append(f"V_opt: stated {vm.group(1)} vs recomputed {v_opt:.4f}")

    # 表1 leg contributions: the two legs ARE the base card.
    leg = {t: leg_contrib(inp, t, pes[t]) for t in TIERS}
    for t, base in zip(TIERS, (L, M, H)):
        ps_m, ps_a = leg[t]
        row = re.search(
            rf"\|\s*{t.upper()}\s*\|[^|]*\|[^|]*\*\*([0-9]+(?:\.[0-9]+)?)\*\*[^|]*\|[^|]*\*\*([0-9]+(?:\.[0-9]+)?)\*\*",
            outs,
        )
        if row is None:
            errors.append(f"表1 {t.upper()} 中蒙/非洲股价贡献未找到")
        else:
            sm, sa = float(row.group(1)), float(row.group(2))
            if abs(sm - ps_m) > 0.05 or abs(sa - ps_a) > 0.05:
                errors.append(
                    f"表1 {t.upper()}: stated {sm:.2f}+{sa:.2f} vs "
                    f"recomputed {ps_m:.2f}+{ps_a:.2f}"
                )

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}  ("
          + "  ".join(f"{row} 篮 {baskets[row]} {basket_r(baskets[row]):.0%}" for row in R_ROWS)
          + f", 特许期 {n:g} 年, H窗口封顶 {h_cap:.0%})")
    print(f"{'档':<3}{'归母(亿)':>10}{'g_mgl':>8}{'PE_mgl':>8}{'g_afr窗口':>11}{'年金因子':>10}"
          f"{'g_afr等效':>11}{'PE_afr':>8}{'ROE':>8}{'派息mgl':>9}{'派息afr':>9}"
          f"{'中蒙CNY':>9}{'非洲CNY':>9}{'锚点CNY':>9}{'公司PE':>8}")
    for t, base in zip(TIERS, (L, M, H)):
        roe = forward_roe(inp, t)
        pe_m, pe_a = pes[t]
        ps_m, ps_a = leg[t]
        print(f"{t.upper():<3}{inp[f'ni_group_{t}']:10.2f}{inp[f'g2_mgl_{t}']:8.0%}{pe_m:8.2f}"
              f"{inp[f'g_afr_{t}']:11.2%}"
              f"{annuity_factor(inp[f'g_afr_{t}'], r_afr, n):10.3f}"
              f"{g_eq[t]:11.2%}{pe_a:8.2f}{roe:8.2%}"
              f"{payout(inp[f'g2_mgl_{t}'], roe):9.1%}{payout(g_eq[t], roe):9.1%}"
              f"{ps_m:9.2f}{ps_a:9.2f}{base:9.2f}{co_pe[t]:8.2f}")
    naive = {
        t: inp[f"ni_group_{t}"] * (
            (1 - inp["w_afr"]) / (r_mgl - inp[f"g2_mgl_{t}"])
            + inp["w_afr"] * annuity_factor(inp[f"g_afr_{t}"], r_afr, n)
        ) * 1e8 / inp["shares"]
        for t in TIERS
    }
    print(f"若按 100% 派息（中蒙 1/(r-g)、非洲纯年金因子）：{naive['l']:.2f} / {naive['m']:.2f} / {naive['h']:.2f}"
          f" — H 档高估 {naive['h'] / H - 1:.0%}（留存成本，A15）")

    # Uncapped H window (=r_afr) would fully match axis H perpetual value.
    g_h_full = africa_window_from_perp(axis["H"], r_afr, n)
    g_eq_full = axis["H"] if g_h_full >= r_afr - 1e-12 else g_equivalent(g_h_full, r_afr, n)
    pe_afr_full = perpetual_pe(g_eq_full, forward_roe(inp, "h"), r_afr)
    v_full = anchor(inp, "h", (pes["h"][0], pe_afr_full))
    print(f"若 H 窗口不封顶（反推至 r_afr，非洲腿对齐轴永续 {axis['H']:.0%}）：H={v_full:.2f}"
          f"  → 封顶让 H 低 {1 - H / v_full:.1%}")

    print(f"flat-multiple @PE_M 中蒙 {pes['m'][0]:.2f} / 非洲 {pes['m'][1]:.2f}: "
          f"L={flat['l']:.2f} M={flat['m']:.2f} H={flat['h']:.2f} — 带宽 "
          f"{(flat['h'] - flat['l']) / (2 * flat['m']):.0%}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    num_l = inp["ni_group_l"] / inp["ni_group_m"]
    num_h = inp["ni_group_h"] / inp["ni_group_m"]
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}"
          f" V_opt/M={v_opt / M:.1%}")
    print(f"分子比 L/M={num_l:.2f} H/M={num_h:.2f} | "
          f"公司口径倍数比 L/M={co_pe['l'] / co_pe['m']:.2f} H/M={co_pe['h'] / co_pe['m']:.2f}")
    print(f"③ 护栏：整公司隐含 PE {co_pe['l']:.2f} / {co_pe['m']:.2f} / {co_pe['h']:.2f} "
          f"vs own-year 带 [{inp['pe_own_lo']}, {inp['pe_own_hi']}]（降篮门：M ≥ 下沿）")
    print(f"地板（只披露，不 max）：BPS {inp['bps']:.2f} CNY → 三档 PB "
          f"{L / inp['bps']:.2f} / {M / inp['bps']:.2f} / {H / inp['bps']:.2f}；"
          f"净现金 {inp['net_cash'] * 1e8 / inp['shares']:.2f} 元/股")

    for label, px in (
        ("卖方 TP", inp["tp_street"]),
        ("M 底牌", M),
        ("H 底牌", H),
        ("账面 PB=1.0", inp["bps"]),
    ):
        p = company_pe(inp, "m", px)
        gi, ok = implied_g(p, forward_roe(inp, "m"), r_afr)
        flag = "" if ok else "  ⚠ ROE≈r，反解只能当方向读"
        print(f"  {label:<10} 隐含 PE={p:6.2f} → 整公司永续 g={gi:+.2%}{flag}")
    print(f"  TTM 归母 {inp['ni_ttm']:.2f} 亿（对照，不入锚点）")
    print(
        f"  非洲窗口 g 由轴永续 {axis['L']:.0%}/{axis['M']:.0%}/{axis['H']:.0%} "
        f"在 r_afr {r_afr:.0%} 下 PV 反推（H 封顶 {h_cap:.0%}）→ "
        f"{inp['g_afr_l']:.2%}/{inp['g_afr_m']:.2%}/{inp['g_afr_h']:.2%}；"
        f"g_eq={g_eq['l']:.2%}/{g_eq['m']:.2%}/{g_eq['h']:.2%}"
    )
    print(
        f"卡萨单位 陆港毛利 {kasa_gp(inp):.3f}亿 / 集团毛利 {group_gp_fy25(inp):.3f}亿 "
        f"→ NI {kasa_ni(inp):.3f}亿 × F(g=0,r_afr,n={n:g})="
        f"{annuity_factor(0.0, r_afr, n):.3f}  →  V_opt={v_opt:.2f}"
    )
    print(f"表3  V_opt={v_opt:.2f} (1×卡萨)  p_k={p_k[0]:.0f}/{p_k[1]:.0f}/{p_k[2]:.0f}  "
          + "  ".join(
              f"{k}:{b:.2f}+{pk:.0f}xV={a:.2f}"
              for k, b, pk, a in zip("LMH", (L, M, H), p_k, adj_band)))

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
