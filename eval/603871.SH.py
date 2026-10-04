#!/usr/bin/env python3
"""603871.SH (Jiayou International Logistics) valuation eval.

frameworks/603871.SH.md is the source of truth; this script re-derives
L/M/H / A/B and V_opt from its §3 Inputs table and exits 1 on mismatch.  The
doc states no current price or zone (the digest and the app zone on live
quotes).

formula_id: jiayou_mgl_afr_perpetual_fy2028_vopt_mokambo_kasa_v4

Main ruler: two legs, each on its own basket r and ADDED (SOTP), sharing the
company's forward ROE.  Both legs sit in 篮 4 (10%) after the ③ step-down
(A17, re-checked with step 1c on 2026-10-04).

  Mongolia / other leg  PE_mgl = payout(g_mgl, ROE) / (r_mgl - g_mgl)
  Africa corridor leg   PE_afr = payout(g_afr, ROE) / (r_afr - g_afr)   — perpetual
  value_x = NI_x × [(1 - w_afr) × PE_mgl + w_afr × PE_afr]

Since 2026-10-04 the Africa corridor leg is a plain perpetuity on the shared
axis g (user ruling: the 22-year concession is treated as perpetual; A5).  The
old window machinery (window g solved for PV parity, H cap, g_eq) is gone.

Numerator (valuation-rules 裁决表 ② / 数据优先级): L = FY2025 actual; M / H =
同花顺 FY2028 consensus mean / high (13 houses, the furthest year with ≥2
houses and a range).  FY2028 = FY+2 → discounted one year at each leg's r
(construction.md §3).  ROE denominator = start-of-FY2028 book: 2026-06-30
equity rolled through H2-2026 and FY2027 consensus at the model retention
b = Σ w_i g_i / ROE (valuation-rules ③ step 2).

V_opt (valuation-rules「未建模期权」): two named corridor items, each one
measured Kasa unit (FY2025 land-port GP × group NI/GP) priced on this ticker's
own Africa-leg H multiple and discounted from its realisation year to the
deck's basis (FY+1 undiscounted → exponent t - 2027), less the capital not
yet invested (valuation-rules 2026-10-04; Mokambo's announced budget, Kasa's
budget for the next corridor), discounted from its investment year:
  * Mokambo (signed, building; 2028; size = its investment ÷ Kasa's)  p = 0 / 0.25 / 1.0
  * next unsigned corridor (2030, 拍值)        p = 0 / 0    / 1.0
The Outputs bullet carries the summed V_opt and the value-weighted p.

Run:  python3 frameworks/eval/603871.SH.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import check_africa_mount  # noqa: E402
from lib.gordon import (  # noqa: E402
    annuity_factor, basket_r, check_g_cap, check_r, implied_g, payout, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

HERE = Path(__file__).resolve().parents[2]
FRAMEWORK = HERE / "frameworks" / "603871.SH.md"
FORMULA_ID = "jiayou_mgl_afr_perpetual_fy2028_vopt_mokambo_kasa_v4"

TIERS = ("l", "m", "h")
R_ROWS = ("r_mgl", "r_afr")
TOL = 0.05
BASIS_YEAR = 2027          # FY+1 relative to today (2026): undiscounted basis of the deck
# Table 3 only, never Inputs: (Mokambo, unsigned corridor)
P_MOKAMBO = (0.0, 0.25, 1.0)
P_UNSIGNED = (0.0, 0.0, 1.0)
# Pre-step-down baskets (A17) and the intermediate step, for the 1c re-check.
DESCENT = (("初分 篮 6 / 篮 7", 0.13, 0.15), ("非洲腿降篮 6", 0.13, 0.13), ("两腿篮 4", 0.10, 0.10))

REQUIRED = [
    "shares", "bps", "equity", "r_mgl", "r_afr", "concession_years",
    "ni_group_l", "ni_group_m", "ni_group_h", "num_year",
    "ni_2026_cons", "ni_h1_2026", "ni_2027_m", "ni_2027_h", "w_afr",
    "g2_mgl_l", "g2_mgl_m", "g2_mgl_h",
    "g2_afr_l", "g2_afr_m", "g2_afr_h",
    "ni_ttm", "net_cash", "tp_street", "pe_own_hi", "pe_own_lo",
    "trade_rev_fy25", "trade_gm_fy25", "logi_rev_fy25", "logi_gm_fy25",
    "lp_rev_fy25", "lp_gm_fy25", "t_mokambo", "t_unsigned",
    "inv_kasa_musd", "inv_mokambo_musd", "fx_usdcny", "t_inv_mokambo", "t_inv_unsigned",
]


def g_of(inp: dict[str, float], leg: str, tag: str) -> float:
    return inp[f"g2_{leg}_{tag}"]


def model_b(inp: dict[str, float], tag: str, roe: float) -> float:
    """Retention the model needs for its growth: Σ w_i g_i / ROE (g ≤ 0 legs retain 0)."""
    w = inp["w_afr"]
    return ((1 - w) * max(0.0, g_of(inp, "mgl", tag)) + w * max(0.0, g_of(inp, "afr", tag))) / roe


def book(inp: dict[str, float], tag: str) -> float:
    """Start-of-numerator-year 归母 book.  L = 2026-06-30 equity (FY2025 as the FY2026 case);
    M / H = 2026-06-30 equity + H2-2026 and FY2027 consensus profit × model b."""
    e = inp["equity"]
    if tag == "l":
        return e
    roe26 = inp["ni_2026_cons"] / e
    e += (inp["ni_2026_cons"] - inp["ni_h1_2026"]) * model_b(inp, tag, roe26)
    n27 = inp[f"ni_2027_{tag}"]
    e += n27 * model_b(inp, tag, n27 / e)
    return e


def forward_roe(inp: dict[str, float], tag: str) -> float:
    return inp[f"ni_group_{tag}"] / book(inp, tag)


def disc_years(inp: dict[str, float], tag: str) -> int:
    return 0 if tag == "l" else int(inp["num_year"]) - BASIS_YEAR


def leg_pes(inp: dict[str, float], tag: str, r_mgl: float | None = None,
            r_afr: float | None = None) -> tuple[float, float]:
    roe = forward_roe(inp, tag)
    rm = inp["r_mgl"] if r_mgl is None else r_mgl
    ra = inp["r_afr"] if r_afr is None else r_afr
    return (perpetual_pe(g_of(inp, "mgl", tag), roe, rm),
            perpetual_pe(g_of(inp, "afr", tag), roe, ra))


def leg_contrib(inp: dict[str, float], tag: str, pes: tuple[float, float] | None = None,
                r_mgl: float | None = None, r_afr: float | None = None) -> tuple[float, float]:
    """Per-share CNY from each leg, discounted from the numerator year at the leg's own r."""
    rm = inp["r_mgl"] if r_mgl is None else r_mgl
    ra = inp["r_afr"] if r_afr is None else r_afr
    pe_m, pe_a = pes if pes is not None else leg_pes(inp, tag, rm, ra)
    ni, w, n = inp[f"ni_group_{tag}"], inp["w_afr"], disc_years(inp, tag)
    return ((1 - w) * ni * pe_m * 1e8 / inp["shares"] / (1 + rm) ** n,
            w * ni * pe_a * 1e8 / inp["shares"] / (1 + ra) ** n)


def anchor(inp: dict[str, float], tag: str, **kw) -> float:
    return sum(leg_contrib(inp, tag, **kw))


def kasa_gp(inp: dict[str, float]) -> float:
    return inp["lp_rev_fy25"] * inp["lp_gm_fy25"]


def group_gp_fy25(inp: dict[str, float]) -> float:
    return (inp["trade_rev_fy25"] * inp["trade_gm_fy25"]
            + inp["logi_rev_fy25"] * inp["logi_gm_fy25"] + kasa_gp(inp))


def kasa_ni(inp: dict[str, float]) -> float:
    """FY2025 land-port GP × group NI/GP (Sakania was not tolling in FY2025)."""
    return kasa_gp(inp) * inp["ni_group_l"] / group_gp_fy25(inp)


def unit_value(inp: dict[str, float], t: float, pe_afr_h: float, r_afr: float | None = None,
               k: float = 1.0) -> float:
    """k × one measured Kasa unit on the Africa-leg H multiple, discounted to the deck basis."""
    ra = inp["r_afr"] if r_afr is None else r_afr
    return k * kasa_ni(inp) * pe_afr_h * 1e8 / inp["shares"] / (1 + ra) ** (t - BASIS_YEAR)


def capex_ps(inp: dict[str, float], musd: float, t_inv: float, r_afr: float | None = None) -> float:
    """Unspent capital per share (valuation-rules 2026-10-04: capacity options deduct it),
    discounted from its investment year to the deck basis.  100% basis: the stake in each
    corridor company is not disclosed (A14)."""
    ra = inp["r_afr"] if r_afr is None else r_afr
    return musd * inp["fx_usdcny"] / 100.0 * 1e8 / inp["shares"] / (1 + ra) ** (t_inv - BASIS_YEAR)


def net_options(inp: dict[str, float], pe_afr_h: float, r_afr: float | None = None) -> dict[str, float]:
    """{name: (gross, capex, net)} for Mokambo and the unsigned corridor (A14)."""
    mok_g = unit_value(inp, inp["t_mokambo"], pe_afr_h, r_afr, k=k_mokambo(inp))
    mok_c = capex_ps(inp, inp["inv_mokambo_musd"], inp["t_inv_mokambo"], r_afr)
    uns_g = unit_value(inp, inp["t_unsigned"], pe_afr_h, r_afr)
    uns_c = capex_ps(inp, inp["inv_kasa_musd"], inp["t_inv_unsigned"], r_afr)
    return {"mok": (mok_g, mok_c, mok_g - mok_c), "uns": (uns_g, uns_c, uns_g - uns_c)}


def k_mokambo(inp: dict[str, float]) -> float:
    """Mokambo's size in Kasa units = its announced investment ÷ Kasa's (capacity proxy)."""
    return inp["inv_mokambo_musd"] / inp["inv_kasa_musd"]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # --- Step 1: baskets ------------------------------------------------------
    baskets = parse_baskets(md)
    for row in R_ROWS:
        if row not in baskets:
            errors.append(f"{row}: no 篮 N in its Inputs source cell (valuation-rules.md「§r 篮子」)")
        errors += check_r(inp[row], row, baskets.get(row))
    if errors:
        return report(errors, "FAIL (baskets)")
    r_mgl, r_afr = inp["r_mgl"], inp["r_afr"]

    # --- Step 2: ladders, caps, payout -----------------------------------------
    errors += ladder("ni_group", inp["ni_group_l"], inp["ni_group_m"], inp["ni_group_h"])
    errors += ladder("ni_2027", inp["ni_2027_m"], inp["ni_2027_h"])
    errors += ladder("g_mgl", *(g_of(inp, "mgl", t) for t in TIERS))
    errors += ladder("g_afr", *(g_of(inp, "afr", t) for t in TIERS))
    if not 0.0 < inp["w_afr"] < 1.0:
        errors.append(f"w_afr={inp['w_afr']} outside (0, 1)")
    if inp["num_year"] - 2026 < 2:
        errors.append("num_year must be ≥ FY+2 for the one-year discount (construction.md §3)")
    if not 0 < inp["ni_h1_2026"] < inp["ni_2026_cons"]:
        errors.append("ni_h1_2026 must lie inside (0, ni_2026_cons)")
    for t in TIERS:
        roe = forward_roe(inp, t)
        for leg, r in (("mgl", r_mgl), ("afr", r_afr)):
            g = g_of(inp, leg, t)
            errors += check_g_cap(g, r, f"g2_{leg}_{t}")
            if r - g <= 0.02 - 1e-12:
                errors.append(f"g2_{leg}_{t}: r − g < 2%")
            pay = payout(g, roe)
            if not 0.0 < pay <= 1.0 + 1e-12:
                errors.append(f"payout_{leg}_{t}={pay:.3f} outside (0, 1]")
            if g <= 0 and abs(pay - 1.0) > 1e-12:
                errors.append(f"payout_{leg}_{t}={pay:.3f} but g={g:.2%} <= 0 — cap not binding")
        if roe > 0.60:
            errors.append(f"ROE_{t}={roe:.1%} > 60% (回对话)")
    if errors:
        return report(errors, "FAIL (inputs/ladders)")

    # --- Step 3: the Africa leg restates the shared axis, perpetual -------------
    errors += check_africa_mount(tuple(g_of(inp, "afr", t) for t in TIERS))  # type: ignore[arg-type]
    if errors:
        return report(errors, "FAIL (shared axis)")

    # --- Step 4: anchors ---------------------------------------------------------
    pes = {t: leg_pes(inp, t) for t in TIERS}
    L, M, H = (anchor(inp, t, pes=pes[t]) for t in TIERS)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # Band basis (A17 / ③ step 1): the own-year band prints price ÷ FY2026 EPS, so
    # the M per-share value is read on the FY2026 consensus EPS.
    eps26 = inp["ni_2026_cons"] * 1e8 / inp["shares"]
    co_pe = {t: px / eps26 for t, px in zip(TIERS, (L, M, H))}
    if co_pe["h"] > inp["pe_own_hi"] + 1e-9:
        errors.append(f"PE_H(FY26 EPS)={co_pe['h']:.2f} above own-year high {inp['pe_own_hi']}")

    # --- Step 5: V_opt (two named corridor units) --------------------------------
    pe_afr_h = pes["h"][1]
    opts = net_options(inp, pe_afr_h)
    v_mok, v_uns = opts["mok"][2], opts["uns"][2]
    if v_mok <= 0 or v_uns <= 0:
        errors.append(f"option net of unspent capital <= 0 (Mokambo {v_mok:.2f}, unsigned {v_uns:.2f}) — 回对话")
    v_opt = v_mok + v_uns
    p_eff = tuple(round((pm * v_mok + pu * v_uns) / v_opt, 2) for pm, pu in zip(P_MOKAMBO, P_UNSIGNED))
    adj = [a + pm * v_mok + pu * v_uns for a, pm, pu in zip((L, M, H), P_MOKAMBO, P_UNSIGNED)]
    gp_share = kasa_gp(inp) / group_gp_fy25(inp)
    if not 0.15 <= gp_share <= 0.30:
        errors.append(f"land-port GP share {gp_share:.1%} outside 15–30% — Kasa no longer one corridor")
    if inp["t_mokambo"] <= 2026 or inp["t_unsigned"] <= inp["t_mokambo"]:
        errors.append("option years must satisfy 2026 < t_mokambo < t_unsigned")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs: {leaked}")
    if not 0 < k_mokambo(inp) < 1:
        errors.append(f"Mokambo k={k_mokambo(inp):.3f} outside (0, 1) — check the investment rows")
    outs = md.split("### Outputs", 1)[-1]
    vm = re.search(r"V_\{?opt\}?\\?\)?\s*[≈=]\s*\*{0,2}\s*\+?([0-9]+(?:\.[0-9]+)?)", outs)
    if vm is None or abs(float(vm.group(1)) - v_opt) > TOL:
        errors.append(f"V_opt: stated {vm.group(1) if vm else None} vs recomputed {v_opt:.4f}")
    pm_ = re.search(r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*[≈=]\s*\*{0,2}\s*([0-9.]+)\s*/\s*([0-9.]+)\s*/\s*([0-9.]+)", outs)
    if pm_ is None or tuple(float(x) for x in pm_.groups()) != p_eff:
        errors.append(f"p_L/p_M/p_H stated {pm_.groups() if pm_ else None} vs value-weighted {p_eff}")
    eff_adj = [a + p * v_opt for a, p in zip((L, M, H), p_eff)]
    if any(abs(x - y) > TOL for x, y in zip(eff_adj, adj)):
        errors.append("value-weighted p does not reproduce the per-item table 3 within ±0.05")

    # --- Step 6: ③ / step 1c re-check of the basket step-down (A17) --------------
    # Band low (pe_own_lo, 2026-06) was printed while Mokambo (announced 2026-02)
    # was public: compare base + Mokambo at p = 1 against the band (step 1c).
    descent = []
    for label, rm, ra in DESCENT:
        pes_d = leg_pes(inp, "m", rm, ra)
        m_d = anchor(inp, "m", pes=pes_d, r_mgl=rm, r_afr=ra)
        mok_d = net_options(inp, leg_pes(inp, "h", rm, ra)[1], ra)["mok"][2]
        band_d = [anchor(inp, t, r_mgl=rm, r_afr=ra) for t in TIERS]
        descent.append((label, rm, ra, band_d, m_d / eps26, (m_d + mok_d) / eps26))
    final = descent[-1]
    if final[5] < inp["pe_own_lo"] - 1e-9:
        errors.append(f"M+Mokambo on 篮 4 = {final[5]:.2f}x below band low {inp['pe_own_lo']} — 篮 4 仍出带 (BLOCKED)")
    for label, *_rest in descent[:-1]:
        if _rest[-1] >= inp["pe_own_lo"]:
            errors.append(f"step 1c: {label} already back in band ({_rest[-1]:.2f}x) — the step-down to 篮 4 is no longer earned")

    # flat-multiple ladder
    flat = [anchor(inp, t, pes=pes["m"]) for t in TIERS]
    errors += ladder("flat-multiple", *flat)

    # 表1 leg contributions
    leg = {t: leg_contrib(inp, t, pes=pes[t]) for t in TIERS}
    for t in TIERS:
        row = re.search(
            rf"\|\s*{t.upper()}\s*\|[^|]*\|[^|]*\*\*([0-9]+(?:\.[0-9]+)?)\*\*[^|]*\|[^|]*\*\*([0-9]+(?:\.[0-9]+)?)\*\*",
            outs)
        if row is None:
            errors.append(f"表1 {t.upper()} leg contributions not found")
        elif abs(float(row.group(1)) - leg[t][0]) > TOL or abs(float(row.group(2)) - leg[t][1]) > TOL:
            errors.append(f"表1 {t.upper()}: stated {row.group(1)}+{row.group(2)} vs {leg[t][0]:.2f}+{leg[t][1]:.2f}")

    # --- report --------------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}  ("
          + "  ".join(f"{row} 篮 {baskets[row]} {basket_r(baskets[row]):.0%}" for row in R_ROWS) + ")")
    print(f"{'档':<3}{'归母':>8}{'期初账面':>9}{'ROE':>8}{'g_mgl':>7}{'PE_mgl':>8}{'g_afr':>7}{'PE_afr':>8}"
          f"{'派息mgl':>8}{'派息afr':>8}{'折年':>5}{'中蒙':>7}{'非洲':>7}{'锚点':>7}{'÷FY26EPS':>9}")
    for t, a in zip(TIERS, (L, M, H)):
        roe = forward_roe(inp, t)
        print(f"{t.upper():<3}{inp[f'ni_group_{t}']:8.2f}{book(inp, t):9.2f}{roe:8.2%}"
              f"{g_of(inp, 'mgl', t):7.1%}{pes[t][0]:8.2f}{g_of(inp, 'afr', t):7.1%}{pes[t][1]:8.2f}"
              f"{payout(g_of(inp, 'mgl', t), roe):8.1%}{payout(g_of(inp, 'afr', t), roe):8.1%}"
              f"{disc_years(inp, t):5d}{leg[t][0]:7.2f}{leg[t][1]:7.2f}{a:7.2f}{co_pe[t]:9.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.1%} V_opt/M={v_opt / M:.1%}")
    num = [inp[f"ni_group_{t}"] for t in TIERS]
    print(f"分子比 L/M={num[0] / num[1]:.2f} H/M={num[2] / num[1]:.2f}（分子年不同：L FY2025、M/H FY2028 折 1 年）")
    print(f"flat-multiple @PE_M: {flat[0]:.2f} / {flat[1]:.2f} / {flat[2]:.2f}")
    print(f"卡萨单位：陆港毛利 {kasa_gp(inp):.3f} 亿 / 集团毛利 {group_gp_fy25(inp):.3f} 亿 → 归母 {kasa_ni(inp):.3f} 亿"
          f" × PE_afr_H {pe_afr_h:.2f}")
    print(f"莫坎博份数 k = {inp['inv_mokambo_musd']:g} / {inp['inv_kasa_musd']:g} = {k_mokambo(inp):.3f} 个卡萨")
    for key, label in (("mok", "莫坎博"), ("uns", "未签约下一条")):
        g_, c_, n_ = opts[key]
        print(f"  {label}: 毛值 {g_:.2f} − 未投资本 {c_:.2f} = {n_:.2f}")
    print(f"V_opt：莫坎博 {v_mok:.2f}（{int(inp['t_mokambo'])}，折 {int(inp['t_mokambo']) - BASIS_YEAR} 年）"
          f" + 未签约下一条 {v_uns:.2f}（{int(inp['t_unsigned'])}，折 {int(inp['t_unsigned']) - BASIS_YEAR} 年）"
          f" = {v_opt:.2f}；价值加权 p = {p_eff[0]:g} / {p_eff[1]:g} / {p_eff[2]:g}")
    a2, b2 = cut_points(*adj)
    print(f"表3：{adj[0]:.2f} / {adj[1]:.2f} / {adj[2]:.2f}  A'={a2:.2f} B'={b2:.2f}")
    print("③ 降篮门 + 步 1c 复核（M ÷ FY2026 共识 EPS；带下沿 "
          f"{inp['pe_own_lo']}×；+莫坎博 p=1）:")
    for label, rm, ra, band_d, pe_d, pe_c in descent:
        print(f"  {label:<14} r {rm:.0%}/{ra:.0%}: L/M/H {band_d[0]:.2f}/{band_d[1]:.2f}/{band_d[2]:.2f}"
              f"  M {pe_d:.2f}×  +莫坎博 {pe_c:.2f}×  {'入带' if pe_c >= inp['pe_own_lo'] else '出带'}")
    for dr, label in ((-0.005, "−50bp"), (0.005, "+50bp")):
        b_ = [anchor(inp, t, r_mgl=r_mgl + dr, r_afr=r_afr + dr) for t in TIERS]
        print(f"敏感 两腿 r {label}: {b_[0]:.2f} / {b_[1]:.2f} / {b_[2]:.2f}")
    for dg in (0.01, -0.01):
        alt = dict(inp)
        for t in TIERS:
            alt[f"g2_afr_{t}"] = inp[f"g2_afr_{t}"] + dg
        b_ = [anchor(alt, t) for t in TIERS]
        print(f"敏感 g2_afr ±: {dg:+.0%} → {b_[0]:.2f} / {b_[1]:.2f} / {b_[2]:.2f}")
    for dg in (0.01, -0.01):
        alt = dict(inp)
        alt["g2_mgl_m"] = inp["g2_mgl_m"] + dg
        print(f"敏感 g2_mgl_m {dg:+.0%} → M {anchor(alt, 'm'):.2f}")
    for w in (0.30, 0.50):
        alt = dict(inp, w_afr=w)
        b_ = [anchor(alt, t) for t in TIERS]
        print(f"敏感 w_afr {w:.0%} → {b_[0]:.2f} / {b_[1]:.2f} / {b_[2]:.2f}")
    # Finite-life cross (A5): Africa leg as a concession_years annuity instead of a perpetuity.
    n = inp["concession_years"]
    fin = []
    for t in TIERS:
        roe = forward_roe(inp, t)
        g = g_of(inp, "afr", t)
        pe_fin = payout(g, roe) * annuity_factor(g, r_afr, n)
        fin.append(anchor(inp, t, pes=(pes[t][0], pe_fin)))
    print(f"有限期交叉（非洲腿 {n:g} 年年金）: {fin[0]:.2f} / {fin[1]:.2f} / {fin[2]:.2f}；"
          + "；".join(f"g {g:.0%} 窗口占永续 {1 - ((1 + g) / (1 + r_afr)) ** n:.1%}" for g in (0.0, 0.03, 0.05)))
    print(f"地板：BPS {inp['bps']:.2f} → PB {L / inp['bps']:.2f} / {M / inp['bps']:.2f} / {H / inp['bps']:.2f}；"
          f"净现金 {inp['net_cash'] * 1e8 / inp['shares']:.2f} 元/股")
    for label, px in (("卖方 TP", inp["tp_street"]), ("M 底牌", M), ("H 底牌", H)):
        gi, ok = implied_g(px / eps26, inp["ni_2026_cons"] / inp["equity"], r_afr)
        print(f"  {label:<8} ÷FY26EPS {px / eps26:6.2f} → 整公司永续 g {gi:+.2%}{'' if ok else ' ⚠'}")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
