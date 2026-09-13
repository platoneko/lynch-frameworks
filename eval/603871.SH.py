#!/usr/bin/env python3
"""603871.SH (Jiayou International Logistics) valuation eval.

frameworks/603871.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: jiayou_mgl_afr_window_pv_parity_concession_vopt_kasa_v3

Main ruler: the numerator is the whole company; the two legs live in the
GROWTH RATE.  Africa uses a *window* nominal g solved so that the 22-year
annuity PV equals the shared-axis perpetual factor 1/(r − g_axis); H is
capped below r (default 9%).  After the usual concession conversion,
g_eq matches the axis on L/M and sits just under it on H — Africa-leg
value aligns with Huaxin/Keda without assuming renewal.

Unsigned new corridors are V_opt (A2e-7), not a second g: the ceiling is
k=1 × Kasumbalesa's realised FY2025 land-port NI, capitalised as a 22-year
zero-growth annuity.  Count is unnamed ("稳步推进"); unit economics are not.
p_L = p_M = 0 (A7: M does not include unsigned concessions); p_H = 1.

  g_afr_window  ← PV-parity solve from axis rung (H ≤ africa_window_h_cap)
  g_afr_eq      = r - 1 / F(g_afr_window, r, n)
  g             = (1 - w_afr) * g_mgl + w_afr * g_afr_eq
  PE            = payout(g, ROE) / (r - g)

表1 also prints per-leg CNY/share (own-g PE × weight-split NI) as display;
zone still reads the blended-g base card.

The Africa *axis* ladder (0%/3%/5%) is SHARED via _AXIS.africa-corridor.md
with 6655.HK and 600499.SH.  Those two mount it as perpetual nominal g;
Jiayou mounts the window transform (axis §3).  Guard 3 checks Jiayou's
window rates against PV-parity + H cap — not against the raw axis rungs.

Run:  python3 eval/603871.SH.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import (  # noqa: E402
    africa_window_from_perp,
    check_africa_jiayou_window,
    load_africa_rungs,
)
from lib.gordon import annuity_factor, implied_g, payout, perpetual_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
FRAMEWORK = HERE / "frameworks" / "603871.SH.md"
FORMULA_ID = "jiayou_mgl_afr_window_pv_parity_concession_vopt_kasa_v3"

TIERS = ("l", "m", "h")

REQUIRED = [
    "price", "shares", "bps", "r_perp", "concession_years", "equity",
    "ni_group_l", "ni_group_m", "ni_group_h", "w_afr",
    "g_mgl_l", "g_mgl_m", "g_mgl_h",
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


def blended_g(inp: dict[str, float], tag: str) -> float:
    r, n = inp["r_perp"], inp["concession_years"]
    g_afr_eq = g_equivalent(inp[f"g_afr_{tag}"], r, n)
    return (1.0 - inp["w_afr"]) * inp[f"g_mgl_{tag}"] + inp["w_afr"] * g_afr_eq


def forward_roe(inp: dict[str, float], tag: str) -> float:
    return inp[f"ni_group_{tag}"] / inp["equity"]


def multiple(inp: dict[str, float], tag: str) -> float:
    return perpetual_pe(blended_g(inp, tag), forward_roe(inp, tag), inp["r_perp"])


def anchor(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    pe = flat_pe if flat_pe is not None else multiple(inp, tag)
    return inp[f"ni_group_{tag}"] * pe * 1e8 / inp["shares"]


def leg_contrib(inp: dict[str, float], tag: str) -> tuple[float, float, float, float]:
    """Per-share CNY from each leg (own g → own PE) and the two leg PEs.

    Display only — the base card still uses blended g → one PE (A10).
    """
    r, n = inp["r_perp"], inp["concession_years"]
    w = inp["w_afr"]
    ni = inp[f"ni_group_{tag}"]
    roe = forward_roe(inp, tag)
    g_mgl = inp[f"g_mgl_{tag}"]
    g_afr_eq = g_equivalent(inp[f"g_afr_{tag}"], r, n)
    pe_mgl = perpetual_pe(g_mgl, roe, r)
    pe_afr = perpetual_pe(g_afr_eq, roe, r)
    ps_mgl = (1.0 - w) * ni * pe_mgl * 1e8 / inp["shares"]
    ps_afr = w * ni * pe_afr * 1e8 / inp["shares"]
    return ps_mgl, ps_afr, pe_mgl, pe_afr


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
    gp = group_gp_fy25(inp)
    return kasa_gp(inp) * inp["ni_group_l"] / gp


def kasa_v_opt(inp: dict[str, float]) -> float:
    """1 × Kasa run-rate as a 22-year zero-growth annuity.  k=1 is the A2e-7c default."""
    f0 = annuity_factor(0.0, inp["r_perp"], inp["concession_years"])
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

    r, n = inp["r_perp"], inp["concession_years"]
    h_cap = inp["africa_window_h_cap"]

    # --- Step 1: numerator and growth ladders -------------------------------
    errors += ladder(
        "ni_group", inp["ni_group_l"], inp["ni_group_m"], inp["ni_group_h"]
    )
    errors += ladder("g_mgl", inp["g_mgl_l"], inp["g_mgl_m"], inp["g_mgl_h"])
    errors += ladder("g_afr_window", inp["g_afr_l"], inp["g_afr_m"], inp["g_afr_h"])
    if not 0.0 < inp["w_afr"] < 1.0:
        errors.append(f"w_afr={inp['w_afr']} outside (0, 1)")
    for t in TIERS:
        if abs(inp[f"g_afr_{t}"] - r) < 1e-9:
            errors.append(f"g_afr_{t} == r_perp — annuity factor undefined")
    if errors:
        return report(errors, "FAIL (inputs/ladders)")

    g_eq = {t: g_equivalent(inp[f"g_afr_{t}"], r, n) for t in TIERS}
    g = {t: blended_g(inp, t) for t in TIERS}
    errors += ladder("g_afr_eq", *(g_eq[t] for t in TIERS))
    errors += ladder("g blended", *(g[t] for t in TIERS))
    if inp["equity"] <= 0:
        errors.append(f"equity={inp['equity']} must be positive")
    for t in TIERS:
        if r - g[t] <= 0:
            errors.append(f"g_{t}={g[t]:.4f} >= r={r} — perpetuity diverges")
        pay = payout(g[t], forward_roe(inp, t))
        if not 0.0 < pay <= 1.0 + 1e-12:
            errors.append(f"payout_{t}={pay:.3f} outside (0, 1]")
        if g[t] <= 0 and abs(pay - 1.0) > 1e-12:
            errors.append(f"payout_{t}={pay:.3f} but g={g[t]:.2%} <= 0 — cap not binding")

    # --- Step 2: window g below r; H cap binds below the r singularity ------
    for t in TIERS:
        if inp[f"g_afr_{t}"] >= r - 1e-12:
            errors.append(f"g_afr_{t}={inp[f'g_afr_{t}']:.4f} must be < r={r}")
    if h_cap >= r - 1e-12:
        errors.append(f"africa_window_h_cap={h_cap:.4f} must be < r={r}")
    if errors:
        return report(errors, "FAIL (window/cap)")

    pe = {t: multiple(inp, t) for t in TIERS}
    if pe["h"] > inp["pe_own_hi"] + 1e-9:
        errors.append(
            f"PE_H={pe['h']:.2f} above own-year measured high {inp['pe_own_hi']} — "
            f"H is no longer a modelled world (A2e-2c-ex)"
        )

    # --- Step 3: Africa window = PV-parity vs shared axis (+ H cap) ---------
    errors += check_africa_jiayou_window(
        (inp["g_afr_l"], inp["g_afr_m"], inp["g_afr_h"]),
        r=r, n=n, h_cap=h_cap,
    )
    # L/M g_eq must land on the axis perpetual rungs; H sits under (cap).
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

    # --- Step 4: anchors ----------------------------------------------------
    L, M, H = (anchor(inp, t) for t in TIERS)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

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

    flat = {t: anchor(inp, t, flat_pe=pe["m"]) for t in TIERS}
    errors += ladder("flat-multiple", flat["l"], flat["m"], flat["h"])

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)
    vm = re.search(
        r"V_\{?opt\}?\\?\)?\s*[≈=]\s*\*{0,2}\s*\+?([0-9]+(?:\.[0-9]+)?)",
        md.split("### Outputs", 1)[-1],
    )
    if vm is None:
        errors.append("stated V_opt not found in Outputs")
    elif abs(float(vm.group(1)) - v_opt) > 0.05:
        errors.append(f"V_opt: stated {vm.group(1)} vs recomputed {v_opt:.4f}")

    # 表1 leg contributions (display): own-g PE × weight-split NI.
    outs = md.split("### Outputs", 1)[-1]
    leg = {t: leg_contrib(inp, t) for t in TIERS}
    for t, base in zip(TIERS, (L, M, H)):
        ps_m, ps_a, _, _ = leg[t]
        if abs(ps_m + ps_a - base) > 0.40:
            errors.append(
                f"表1 {t.upper()} 拆腿合计 {ps_m + ps_a:.2f} vs 底牌锚 {base:.2f} "
                f"(gap {ps_m + ps_a - base:+.3f} > 0.40)"
            )
        row = re.search(
            rf"\|\s*{t.upper()}\s*\|\s*\*\*([0-9]+(?:\.[0-9]+)?)\*\*.*?\|\s*\*\*([0-9]+(?:\.[0-9]+)?)\*\*",
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
    print(f"formula_id={FORMULA_ID}  (r={r:.0%}, 零增长={1 / r:.1f}x, 特许期 {n:g} 年, "
          f"H窗口封顶 {h_cap:.0%})")
    print(f"{'档':<3}{'归母(亿)':>10}{'g_mgl':>8}{'g_afr窗口':>11}{'年金因子':>10}"
          f"{'g_afr等效':>11}{'合成g':>9}{'ROE':>8}{'派息':>8}{'PE':>8}{'价值(亿)':>10}{'锚点CNY':>10}")
    for t in TIERS:
        print(f"{t.upper():<3}{inp[f'ni_group_{t}']:10.2f}{inp[f'g_mgl_{t}']:8.0%}"
              f"{inp[f'g_afr_{t}']:11.2%}"
              f"{annuity_factor(inp[f'g_afr_{t}'], r, n):10.3f}"
              f"{g_eq[t]:11.2%}{g[t]:9.2%}{forward_roe(inp, t):8.2%}"
              f"{payout(g[t], forward_roe(inp, t)):8.1%}{pe[t]:8.2f}"
              f"{inp[f'ni_group_{t}'] * pe[t]:10.2f}{anchor(inp, t):10.2f}")
    print(f"{'档':<3}{'中蒙贡献':>10}{'PE_mgl':>8}{'非洲贡献':>10}{'PE_afr':>8}"
          f"{'拆腿合计':>10}{'底牌锚':>10}{'Δ':>8}")
    for t, base in zip(TIERS, (L, M, H)):
        ps_m, ps_a, pe_m, pe_a = leg[t]
        print(f"{t.upper():<3}{ps_m:10.2f}{pe_m:8.2f}{ps_a:10.2f}{pe_a:8.2f}"
              f"{ps_m + ps_a:10.2f}{base:10.2f}{ps_m + ps_a - base:8.3f}")
    naive = {t: inp[f"ni_group_{t}"] / (r - g[t]) * 1e8 / inp["shares"] for t in TIERS}
    print(f"若按 100% 派息的 1/(r-g)：{naive['l']:.2f} / {naive['m']:.2f} / {naive['h']:.2f}"
          f" — H 档高估 {naive['h'] / anchor(inp, 'h') - 1:.0%}（留存成本，A15）")

    # Uncapped H window (=r) would fully match axis H perpetual value.
    print("若 H 窗口不封顶（反推至 r，非洲腿对齐轴永续 +5%）：", end="")
    g_h_full = africa_window_from_perp(axis["H"], r, n)
    if g_h_full >= r - 1e-12:
        # limit: F = n/(1+r), g_eq = axis H by construction of the solve target
        g_eq_full = axis["H"]
    else:
        g_eq_full = g_equivalent(g_h_full, r, n)
    g_perp_h = (1 - inp["w_afr"]) * inp["g_mgl_h"] + inp["w_afr"] * g_eq_full
    v_full = (inp["ni_group_h"] * perpetual_pe(g_perp_h, forward_roe(inp, "h"), r)
              * 1e8 / inp["shares"])
    print(f"  H={v_full:.2f}  → 封顶让 H 低 {1 - anchor(inp, 'h') / v_full:.1%}")

    print(f"flat-multiple @PE={pe['m']:.2f}: L={flat['l']:.2f} M={flat['m']:.2f} "
          f"H={flat['h']:.2f} — 带宽 {(flat['h'] - flat['l']) / (2 * flat['m']):.0%}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    num_l = inp["ni_group_l"] / inp["ni_group_m"]
    num_h = inp["ni_group_h"] / inp["ni_group_m"]
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}"
          f" V_opt/M={v_opt / M:.1%}")
    print(f"分子比 L/M={num_l:.2f} H/M={num_h:.2f} | "
          f"倍数比 L/M={pe['l'] / pe['m']:.2f} H/M={pe['h'] / pe['m']:.2f}")

    print(f"price={inp['price']} zone={zone}")
    for label, px in (
        ("现价", inp["price"]),
        ("卖方 TP", inp["tp_street"]),
        ("账面 PB=1.0", inp["bps"]),
    ):
        p = px * inp["shares"] / 1e8 / inp["ni_group_m"]
        gi, ok = implied_g(p, forward_roe(inp, "m"), r)
        flag = "" if ok else "  ⚠ ROE≈r，反解只能当方向读"
        print(f"  {label:<10} 隐含 PE={p:6.2f} → g={gi:+.2%}{flag}")
    print(f"  TTM 归母 {inp['ni_ttm']:.2f} 亿 → 现价 PE(TTM)="
          f"{inp['price'] * inp['shares'] / 1e8 / inp['ni_ttm']:.2f}"
          f" | 净现金 {inp['net_cash']:.2f} 亿 = {inp['net_cash'] * 1e8 / inp['shares']:.2f} 元/股")
    print(
        f"  非洲窗口 g 由轴永续 {axis['L']:.0%}/{axis['M']:.0%}/{axis['H']:.0%} "
        f"PV 反推（H 封顶 {h_cap:.0%}）→ "
        f"{inp['g_afr_l']:.2%}/{inp['g_afr_m']:.2%}/{inp['g_afr_h']:.2%}；"
        f"g_eq={g_eq['l']:.2%}/{g_eq['m']:.2%}/{g_eq['h']:.2%}"
    )
    print(
        f"卡萨单位 陆港毛利 {kasa_gp(inp):.3f}亿 / 集团毛利 {group_gp_fy25(inp):.3f}亿 "
        f"→ NI {kasa_ni(inp):.3f}亿 × F(g=0,n={n:g})="
        f"{annuity_factor(0.0, r, n):.3f}  →  V_opt={v_opt:.2f}"
    )
    print(f"表3  V_opt={v_opt:.2f} (1×卡萨)  p_k={p_k[0]:.0f}/{p_k[1]:.0f}/{p_k[2]:.0f}  "
          + "  ".join(
              f"{n}:{b:.2f}+{pk:.0f}xV={a:.2f}"
              for n, b, pk, a in zip("LMH", (L, M, H), p_k, adj_band)))
    print(f"V_opt/M={v_opt / M:.1%}")
    if v_opt > 0 and inp["price"] > H:
        print(f"     市价隐含 p = {(inp['price'] - H) / v_opt:.2f}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
