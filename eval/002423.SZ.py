#!/usr/bin/env python3
"""002423.SZ (COFCO Capital) valuation eval — recompute anchors from frameworks/002423.SZ.md.

frameworks/002423.SZ.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading — the digest and the app zone on live quotes.

formula_id: cofco_capital_sotp_ev_v1

SOTP, legs added (no blended r), all in 亿元 then per share:
  * 中英人寿 (50%) — insurance EV ruler (valuation-rules「保险腿：内含价值尺」,
    2026-10-09): (EV_sh + NBV / (r - g_nbv) × (1 - k_x)) × hold.  EV_sh = disclosed
    EV less the perpetual capital bonds booked in equity.  k is measured, not
    picked: e = (Σ EV_{t-1}·RDR_t + Σ NBV_t − ΔEV_sh) / Σ NBV_t over the
    same-basis window; k_L = min(1, e), k_M = k_L / 2, k_H = 0.
  * 中粮信托 (80.51%) / 中粮期货 (70.42%) — Gordon, 篮 4, retention bucket E
    (regulatory capital grows with the book): b = 1 - payout, g = b × ROE_x
    capped at G_cap; a capped dividend payer (trim ≤ 2pp) switches to
    capped_payout_pe (valuation-rules「永续 g 上限」红利票截顶).
  * 龙江银行 (20%, equity method) — 篮 5 PB-ROE at g = 0 (NI fell 2024→2025),
    less k × the excess retention (it has paid nothing: payout 0) — the
    600036.SH shape.
  * 总部 — 2025 cost line capitalized at 1/r (g = 0).

Run:  python3 frameworks/eval/002423.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import (  # noqa: E402
    capped_payout_pe, check_g_cap, check_r, g_cap, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "002423.SZ.md"
FORMULA_ID = "cofco_capital_sotp_ev_v1"
TIERS = ("L", "M", "H")
CAP_TRIM_MAX = 0.02  # dividend-payer threshold for the capped-payout ruler

REQUIRED = [
    "shares", "r_op", "r_bank", "payout_obs",
    "ev_2021", "ev_2022", "ev_2023", "ev_2024_disc", "perp_2024", "ev_2025_disc", "perp_2025",
    "rdr_2022", "rdr_2023", "rdr_2024", "rdr_2025",
    "nbv_2022_old", "nbv_2023", "nbv_2024", "nbv_2025", "g_nbv", "hold_ins", "ins_book_2025",
    "trust_eq", "hold_trust", "roe_trust_l", "roe_trust_m", "roe_trust_h",
    "fut_eq", "hold_fut", "roe_fut_l", "roe_fut_m", "roe_fut_h",
    "lj_bv", "roe_lj_l", "roe_lj_m", "roe_lj_h", "k_lj_l", "k_lj_m", "k_lj_h",
    "hq_ni", "eps_ttm", "band_pe_lo",
]


def ev_series(inp: dict[str, float]) -> dict[int, float]:
    """Shareholder EV (亿): disclosed EV less perpetual bonds where they exist."""
    return {
        2021: inp["ev_2021"], 2022: inp["ev_2022"], 2023: inp["ev_2023"],
        2024: inp["ev_2024_disc"] - inp["perp_2024"],
        2025: inp["ev_2025_disc"] - inp["perp_2025"],
    }


def eaten_share(inp: dict[str, float], y0: int, y1: int, nbv: dict[int, float]) -> float:
    """e = (expected − actual EV growth) / Σ NBV over (y0, y1]."""
    ev = ev_series(inp)
    unwind = sum(ev[y - 1] * inp[f"rdr_{y}"] for y in range(y0 + 1, y1 + 1))
    s = sum(nbv[y] for y in range(y0 + 1, y1 + 1))
    return (unwind + s - (ev[y1] - ev[y0])) / s


def nbv_same_basis(inp: dict[str, float]) -> dict[int, float]:
    return {y: inp[f"nbv_{y}"] for y in (2023, 2024, 2025)}


def k_ins(inp: dict[str, float]) -> dict[str, float]:
    e = eaten_share(inp, 2022, 2025, nbv_same_basis(inp))
    kl = min(1.0, max(0.0, e))
    return {"L": kl, "M": kl / 2.0, "H": 0.0}


def ins_leg(inp: dict[str, float], k: float) -> float:
    ev = ev_series(inp)[2025]
    return (ev + inp["nbv_2025"] / (inp["r_op"] - inp["g_nbv"]) * (1.0 - k)) * inp["hold_ins"]


def gordon_leg(eq: float, roe: float, r: float, payout: float) -> tuple[float, float, float, str]:
    """(value 亿, PE, g, ruler) for a retaining leg at b = 1 - payout."""
    cap = g_cap(r)
    g_raw = (1.0 - payout) * roe
    if g_raw <= cap:
        return eq * roe * perpetual_pe(g_raw, roe, r), perpetual_pe(g_raw, roe, r), g_raw, "perpetual"
    if g_raw - cap > CAP_TRIM_MAX:
        raise ValueError(f"policy g {g_raw:.4f} over cap {cap:.4f} by > 2pp — not a dividend payer")
    pe = capped_payout_pe(g_raw, roe, r, payout)
    return eq * roe * pe, pe, cap, "capped_payout"


def bank_leg(inp: dict[str, float], roe: float, k: float) -> float:
    """g = 0 PB-ROE less k × excess retention; payout 0 → excess = E / r."""
    e = inp["lj_bv"] * roe
    return e / inp["r_bank"] * (1.0 - k)


def legs(inp: dict[str, float]) -> dict[str, dict[str, float]]:
    k = k_ins(inp)
    out: dict[str, dict[str, float]] = {}
    for lab in TIERS:
        lo = lab.lower()
        t, *_ = gordon_leg(inp["trust_eq"] * inp["hold_trust"], inp[f"roe_trust_{lo}"],
                           inp["r_op"], inp["payout_obs"])
        f, *_ = gordon_leg(inp["fut_eq"] * inp["hold_fut"], inp[f"roe_fut_{lo}"],
                           inp["r_op"], inp["payout_obs"])
        out[lab] = {
            "ins": ins_leg(inp, k[lab]),
            "trust": t,
            "fut": f,
            "lj": bank_leg(inp, inp[f"roe_lj_{lo}"], inp[f"k_lj_{lo}"]),
            "hq": inp["hq_ni"] / inp["r_op"],
        }
    return out


def anchors(inp: dict[str, float]) -> tuple[float, float, float]:
    lg = legs(inp)
    return tuple(sum(lg[lab].values()) / inp["shares"] for lab in TIERS)


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
    for field in ("r_op", "r_bank"):
        if field not in baskets:
            errors.append(f"{field}: no 篮 N in Inputs source cell")
        errors += check_r(inp[field], field, baskets.get(field))
    errors += check_g_cap(inp["g_nbv"], inp["r_op"], "g_nbv")
    for name in ("trust", "fut", "lj"):
        errors += ladder(f"roe_{name}", *(inp[f"roe_{name}_{t.lower()}"] for t in TIERS))
    # Worse world, more of the bank's retention wasted: 0 ≤ k_H ≤ k_M ≤ k_L ≤ 1.
    kl = {t: inp[f"k_lj_{t.lower()}"] for t in TIERS}
    if not (0.0 <= kl["H"] <= kl["M"] <= kl["L"] <= 1.0):
        errors.append(f"k_lj must satisfy 0 <= h <= m <= l <= 1, got {kl}")
    if not (0.0 < inp["payout_obs"] < 1.0):
        errors.append(f"payout_obs={inp['payout_obs']} must be in (0, 1)")
    if errors:
        return report(errors, "FAIL (inputs/guards)")

    try:
        lg = legs(inp)
    except ValueError as e:
        return report([str(e)], "FAIL (inputs/guards)")
    L, M, H = anchors(inp)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    sh = inp["shares"]
    ev = ev_series(inp)
    e3 = eaten_share(inp, 2022, 2025, nbv_same_basis(inp))
    e4 = eaten_share(inp, 2021, 2025, {**nbv_same_basis(inp), 2022: inp["nbv_2022_old"]})
    k = k_ins(inp)
    roev = (ev[2025] / ev[2022]) ** (1 / 3) - 1
    stress = ev[2025] * inp["hold_ins"] * ((1 + roev) / (1 + inp["r_op"])) ** 3 / sh
    vif = ev[2025] - inp["ins_book_2025"]

    print(f"formula_id={FORMULA_ID}")
    print("EV_sh (亿): " + " ".join(f"{y}:{v:.2f}" for y, v in ev.items()))
    print(f"e (2022→2025 同口径 3 年) = {e3:.2f}；e (2021→2025 含 2022 旧口径 NBV) = {e4:.2f}"
          f" → k_ins L/M/H = {k['L']:.2f}/{k['M']:.2f}/{k['H']:.2f}")
    print(f"{'档':<3}{'中英':>8}{'信托':>8}{'期货':>8}{'龙江':>8}{'总部':>8}{'合计':>8}  (元/股)")
    for lab, a in zip(TIERS, (L, M, H)):
        v = lg[lab]
        print(f"{lab:<3}{v['ins'] / sh:8.2f}{v['trust'] / sh:8.2f}{v['fut'] / sh:8.2f}"
              f"{v['lj'] / sh:8.2f}{v['hq'] / sh:8.2f}{a:8.2f}")
    for lab in TIERS:
        lo = lab.lower()
        for name, eq, hold in (("信托", "trust_eq", "hold_trust"), ("期货", "fut_eq", "hold_fut")):
            key = "trust" if name == "信托" else "fut"
            _, pe, g, ruler = gordon_leg(inp[eq] * inp[hold], inp[f"roe_{key}_{lo}"],
                                         inp["r_op"], inp["payout_obs"])
            print(f"  {lab} {name}: ROE {inp[f'roe_{key}_{lo}']:.2%} g {g:.2%} PE {pe:.2f} ({ruler})")
    print(f"③ 整票 M ÷ TTM EPS = {M / inp['eps_ttm']:.1f}x vs 同等盈利月份带下沿 {inp['band_pe_lo']}x"
          f" → {'入带' if M / inp['eps_ttm'] >= inp['band_pe_lo'] else '出带'}；"
          f"L {L / inp['eps_ttm']:.1f}x / H {H / inp['eps_ttm']:.1f}x（只披露）")
    if M / inp["eps_ttm"] < inp["band_pe_lo"]:
        errors.append("③: M multiple below own same-earnings band")
    print(f"压力坐标（e>1，EV 按实测 ROEV {roev:.2%} 续滚 3 年）：中英 {stress:.2f} 元/股"
          f"（底牌 L 中英 {lg['L']['ins'] / sh:.2f}）→ 整票 {L - lg['L']['ins'] / sh + stress:.2f}")
    print(f"VIF 推算 = EV_sh − 普通股账面 = {vif:.1f} 亿；RDR −1pp 敏感（D=10 拍值）"
          f"≈ ±{vif * 10 * 0.01 * inp['hold_ins'] / sh:.2f} 元/股")
    for dg in (-0.01, 0.01):
        alt = dict(inp, payout_obs=inp["payout_obs"])
        # g ±1pp on the Gordon legs: shift b so that g moves by dg at each tier's ROE.
        vals = []
        for lab in TIERS:
            lo = lab.lower()
            tot = lg[lab]["ins"] + lg[lab]["lj"] + lg[lab]["hq"]
            for key, eq, hold in (("trust", "trust_eq", "hold_trust"), ("fut", "fut_eq", "hold_fut")):
                roe = inp[f"roe_{key}_{lo}"]
                g = min((1 - alt["payout_obs"]) * roe, g_cap(inp["r_op"])) + dg
                tot += inp[eq] * inp[hold] * roe * perpetual_pe(g, roe, inp["r_op"])
            vals.append(tot / sh)
        print(f"敏感 信托/期货 g {dg:+.0%}: " + " / ".join(f"{v:.2f}" for v in vals))
    for kv in (0.25, 0.75):
        vals = [(sum(lg[lab].values()) - lg[lab]["ins"]
                 + ins_leg(inp, k[lab] if lab != "M" else kv)) / sh for lab in TIERS]
        print(f"敏感 k_ins_M={kv}: " + " / ".join(f"{v:.2f}" for v in vals))
    alt = dict(inp, nbv_2025=inp["nbv_2025"] * 1.2)
    print("敏感 NBV +20%: " + " / ".join(f"{v:.2f}" for v in anchors(alt)))
    # A2e-2c flat ladder in PE space on group TTM EPS: no per-tier group EPS exists
    # (the EV leg has no earnings numerator), so report the leg numerators instead.
    print("2c 分子阶梯：信托 / 期货 / 龙江 ROE 三档递增（见上）；中英腿档差来自 k（实测 e）")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.1%}")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
