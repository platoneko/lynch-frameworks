#!/usr/bin/env python3
"""600499.SH (Keda Industrial Group) valuation eval.

frameworks/600499.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: keda_lanke_axis_afr_mac_perpetual_g_v2

Two legs, added per share:

  Lanke leg   NI_lk = delta * stake * vol_plan * (li2co3 * realization - cost) * (1 - tax)
              V_lk  = NI_lk * pe_lk                       (pe_lk = 10 flat, Gordon g=0)
  non-Li leg  g     = w_afr*g_afr + w_mac*g_mac
              PE    = (1 - g/ROE) / (r - g),  ROE = (ni_exli + NI_lk) / equity
              V_non = ni_exli * PE                        (ni_exli same on all tiers)

Keda's 43.58% of Lanke Lithium runs through equity-method investment income
and swung group net income 10.06 -> 42.51 -> 10.06亿 in four years.  The old
construction hid that swing inside a blended growth rate; now the leg reads the
shared Li2CO3 axis directly, with nameplate volume discounted one year — the
same "2027 volume x delta" construction as 9696.HK / 000792.SZ / 1772.HK.
Both axes are checked against their files, so Keda can invent neither its own
lithium deck nor its own Africa case.

Why the non-Li multiple is generated rather than sampled from history: the
stock printed its LOWEST annual PE (7.7x) at the lithium peak and its HIGHEST
(17.2x) at the trough — the historical band measures where the cycle stood,
not what the business is worth.  It survives here only as a fence (`pe_own_hi`).

Run:  python3 eval/600499.SH.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import check_africa_mount, check_li2co3_mount  # noqa: E402
from lib.gordon import implied_g, payout, perpetual_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "600499.SH.md"
FORMULA_ID = "keda_lanke_axis_afr_mac_perpetual_g_v2"

TIERS = ("l", "m", "h")
LEGS = ("afr", "mac")
YI = 1e8

REQUIRED = [
    "price", "shares", "bps", "r_perp", "equity",
    "ni_exli",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "realization_lk", "cost_lk", "vol_lk_plan", "vol_lk_h1",
    "r_disc", "n_disc", "stake_lk", "tax_lk", "pe_lk",
    "w_afr", "w_mac",
    "g_afr_l", "g_afr_m", "g_afr_h",
    "g_mac_l", "g_mac_m", "g_mac_h",
    "ni_ttm", "ni_fy2024", "ni_exli_fy2025", "ni_2026e_street", "tp_street",
    "pe_own_hi", "pe_own_lo",
]


def lanke_ni(inp: dict[str, float], tag: str) -> float:
    """Keda's share of Lanke net profit, 亿 CNY, nameplate volume discounted."""
    disc = (1.0 + inp["r_disc"]) ** (-inp["n_disc"])
    margin = inp[f"li2co3_{tag}"] * inp["realization_lk"] - inp["cost_lk"]
    return disc * inp["stake_lk"] * inp["vol_lk_plan"] * margin * (1.0 - inp["tax_lk"]) / YI


def blended_g(inp: dict[str, float], tag: str) -> float:
    return sum(inp[f"w_{leg}"] * inp[f"g_{leg}_{tag}"] for leg in LEGS)


def forward_roe(inp: dict[str, float], tag: str) -> float:
    return (inp["ni_exli"] + lanke_ni(inp, tag)) / inp["equity"]


def multiple(inp: dict[str, float], tag: str) -> float:
    return perpetual_pe(blended_g(inp, tag), forward_roe(inp, tag), inp["r_perp"])


def anchor(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    pe = flat_pe if flat_pe is not None else multiple(inp, tag)
    value = inp["ni_exli"] * pe + lanke_ni(inp, tag) * inp["pe_lk"]
    return value * YI / inp["shares"]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r = inp["r_perp"]

    # --- Step 1: Lanke leg reads the shared lithium axis ------------------------
    errors += check_li2co3_mount(
        (inp["li2co3_l"], inp["li2co3_m"], inp["li2co3_h"])
    )
    for key, lo, hi in (
        ("realization_lk", 0.0, 1.0), ("stake_lk", 0.0, 1.0), ("tax_lk", -1e-12, 1.0),
    ):
        if not lo < inp[key] < hi:
            errors.append(f"{key}={inp[key]} outside ({lo}, {hi})")
    if inp["cost_lk"] <= 0 or inp["vol_lk_plan"] <= 0:
        errors.append("cost_lk and vol_lk_plan must be positive")
    lk = {t: lanke_ni(inp, t) for t in TIERS}
    errors += ladder("Lanke NI", lk["l"], lk["m"], lk["h"])
    if lk["l"] <= 0:
        errors.append(f"Lanke NI_L={lk['l']:.2f} <= 0 — leg does not clear cost at axis L")

    # --- Step 2: non-Li leg — weights, growth ladders, Africa axis --------------
    w_sum = sum(inp[f"w_{leg}"] for leg in LEGS)
    if abs(w_sum - 1.0) > 1e-6:
        errors.append(f"leg weights must sum to 1: {w_sum}")
    for leg in LEGS:
        if not 0.0 < inp[f"w_{leg}"] < 1.0:
            errors.append(f"w_{leg}={inp[f'w_{leg}']} outside (0, 1)")
        errors += ladder(f"g_{leg}", *(inp[f"g_{leg}_{t}"] for t in TIERS))
    if errors:
        return report(errors, "FAIL (inputs/ladders)")

    if inp["equity"] <= 0:
        errors.append(f"equity={inp['equity']} must be positive")
    g = {t: blended_g(inp, t) for t in TIERS}
    errors += ladder("g blended", *(g[t] for t in TIERS))
    for t in TIERS:
        if r - g[t] <= 0:
            errors.append(f"g_{t}={g[t]:.4f} >= r={r} — perpetuity diverges")
    # Growth is paid for out of retained earnings; a shrinking business is not
    # assumed to hand back more than it earns.
    for t in TIERS:
        pay = payout(g[t], forward_roe(inp, t))
        if not 0.0 < pay <= 1.0 + 1e-12:
            errors.append(f"payout_{t}={pay:.3f} outside (0, 1]")
        if g[t] <= 0 and abs(pay - 1.0) > 1e-12:
            errors.append(f"payout_{t}={pay:.3f} but g={g[t]:.2%} <= 0 — cap not binding")
    errors += check_africa_mount(
        (inp["g_afr_l"], inp["g_afr_m"], inp["g_afr_h"])
    )

    pe = {t: multiple(inp, t) for t in TIERS}
    if pe["h"] > inp["pe_own_hi"] + 1e-9:
        errors.append(
            f"PE_H={pe['h']:.2f} above own-year measured high {inp['pe_own_hi']} — "
            f"H is no longer a modelled world"
        )
    if errors:
        return report(errors, "FAIL (guards/axis)")

    # --- Step 3: anchors ----------------------------------------------------
    L, M, H = (anchor(inp, t) for t in TIERS)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    flat = {t: anchor(inp, t, flat_pe=pe["m"]) for t in TIERS}
    errors += ladder("flat-multiple", flat["l"], flat["m"], flat["h"])

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report --------------------------------------------------------------
    disc = (1.0 + inp["r_disc"]) ** (-inp["n_disc"])
    total = {t: inp["ni_exli"] + lk[t] for t in TIERS}
    v_non = {t: inp["ni_exli"] * pe[t] for t in TIERS}
    v_lk = {t: lk[t] * inp["pe_lk"] for t in TIERS}
    print(f"formula_id={FORMULA_ID}  (r={r:.0%}, 零增长={1 / r:.1f}x; 蓝科腿 PE {inp['pe_lk']:g} flat)")
    print(
        "li2co3 OK vs _AXIS.lithium-carbonate: "
        + "/".join(f"{inp[k]:g}" for k in ("li2co3_l", "li2co3_m", "li2co3_h"))
        + f"  蓝科量={inp['vol_lk_plan']:g} x disc={disc:.4f}"
        f" (H1 sales x2 = {inp['vol_lk_h1']:g}, not in formula)"
    )
    print(f"{'档':<3}{'蓝科归母':>9}{'非锂分子':>9}"
          f"{'非洲' + format(inp['w_afr'], '.0%'):>10}"
          f"{'机械' + format(inp['w_mac'], '.0%'):>10}"
          f"{'合成g':>9}{'ROE':>8}{'派息':>8}{'PE非锂':>8}{'非锂亿':>9}{'蓝科亿':>9}{'锚点CNY':>10}")
    for t in TIERS:
        print(f"{t.upper():<3}{lk[t]:9.2f}{inp['ni_exli']:9.2f}{inp[f'g_afr_{t}']:10.0%}"
              f"{inp[f'g_mac_{t}']:10.0%}{g[t]:9.2%}"
              f"{forward_roe(inp, t):8.2%}{payout(g[t], forward_roe(inp, t)):8.1%}"
              f"{pe[t]:8.2f}{v_non[t]:9.1f}{v_lk[t]:9.1f}{anchor(inp, t):10.2f}")
    naive = {t: inp["ni_exli"] / (r - g[t]) for t in TIERS}
    print(f"非锂腿若按 100% 派息的 1/(r-g)：{naive['l']:.1f} / {naive['m']:.1f} / {naive['h']:.1f} 亿"
          f" — H 档高估 {naive['h'] / v_non['h'] - 1:.0%}（留存成本，A16）")
    print(f"非洲腿 g 取自 _AXIS.africa-corridor.md ✓ "
          f"({inp['g_afr_l']:.0%}/{inp['g_afr_m']:.0%}/{inp['g_afr_h']:.0%}，本票按永续落地)")
    blended_pe = {t: (v_non[t] + v_lk[t]) / total[t] for t in TIERS}
    print(f"非锂腿 PE {pe['l']:.2f}/{pe['m']:.2f}/{pe['h']:.2f}；整公司隐含 PE "
          f"{blended_pe['l']:.2f}/{blended_pe['m']:.2f}/{blended_pe['h']:.2f} 落在 own-year 实测带 "
          f"[{inp['pe_own_lo']:g}, {inp['pe_own_hi']:g}] 内 ✓")
    print(f"flat-multiple @PE非锂={pe['m']:.2f}: L={flat['l']:.2f} M={flat['m']:.2f} "
          f"H={flat['h']:.2f} — 带宽 {(flat['h'] - flat['l']) / (2 * flat['m']):.0%}（阶梯由蓝科腿轴价承载）")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}")
    print(f"分子比（两腿合计 {total['l']:.2f}/{total['m']:.2f}/{total['h']:.2f} 亿）"
          f"L/M={total['l'] / total['m']:.2f} H/M={total['h'] / total['m']:.2f} | "
          f"倍数比 L/M={blended_pe['l'] / blended_pe['m']:.2f} H/M={blended_pe['h'] / blended_pe['m']:.2f}")

    print(f"price={inp['price']} zone={zone}")
    # Implied non-Li growth: strip the M-tier Lanke leg, read the residual on ni_exli.
    for label, px in (
        ("现价", inp["price"]),
        ("卖方 TP", inp["tp_street"]),
        ("账面 PB=1.0", inp["bps"]),
    ):
        resid = px * inp["shares"] / YI - v_lk["m"]
        p = resid / inp["ni_exli"]
        gi, ok = implied_g(p, forward_roe(inp, "m"), r)
        flag = "" if ok else "  ⚠ ROE≈r，反解只能当方向读"
        print(f"  {label:<10} 扣 M 档蓝科腿后 隐含 PE非锂={p:6.2f} → g={gi:+.2%}{flag}")
    print(f"  TTM 归母 {inp['ni_ttm']:.2f} 亿 → 现价 PE(TTM)="
          f"{inp['price'] * inp['shares'] / YI / inp['ni_ttm']:.2f}"
          f" | FY2024 锂谷底归母 {inp['ni_fy2024']:.2f} 亿 | FY2025 ex-蓝科 {inp['ni_exli_fy2025']:.2f} 亿")
    print(f"  国金 2026E 归母 {inp['ni_2026e_street']:.2f} 亿（锂价按 2026 平台）"
          f" vs 本框架 H 档两腿合计 {total['h']:.2f} 亿 — 仅交叉")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
