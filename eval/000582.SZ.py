#!/usr/bin/env python3
"""000582.SZ (Beibu Gulf Port / 北部湾港) valuation eval.

frameworks/000582.SZ.md is the source of truth; this script re-derives
L/M/H / A/B, V_opt and the disclosure coordinates from its §3 Inputs table
and exits 1 on mismatch.  The doc carries no current price (AGENTS.md「现价 —
禁写契约」), so nothing here computes a zone or a market-implied reading.

formula_id: bbgport_cons2028_utility_gordon_v1

Main ruler: one company-wide leg, Gordon full form on the 2028 consensus.

    W     = (np_cons_2026 - np_h1_2026) + np_cons_2027      window profit
    B0    = equity_parent / (1 - W * g2 / E_M)               2028 opening equity
    RONIC = E_x / B0,  b = g2 / RONIC
    V_x   = E_x (1 - b) / (r - g2)                           L, M (RONIC < r: held)
    V_H   = three-stage: RONIC_H fades linearly 2028 -> 2034 to ret_ss
    D     = sum capex (1 - irr / r) / (1+r)^1.5              named low-return berths
    x     = V_x / sh / (1+r)^1.5 + W (1 - b) / sh / (1+r)^0.75 - D / sh

r is basket 2 by the user's ruling (A1); basket 4 is printed as a contrast.

Run:  python3 frameworks/eval/000582.SZ.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import basket_r, check_branch, check_g_cap, check_r  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, outputs_section, parse_baskets,
    parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval.lib.frameworks import load_framework  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "000582.SZ.md"
FORMULA_ID = "bbgport_cons2028_utility_gordon_v1"
YI = 1e8
TOL = 0.05

# Valuation date 2026-06-30 -> numerator-year start 2028-01-01 (A3), and the H-tier
# fade 2028 -> 2034 (high entry barrier, 6 years, A5).  Changing them is a framework
# correction, so they live here rather than in Inputs.
TAU = 1.5
FADE_YEARS = 6
BASKET = 2
CONTRAST_BASKET = 4

REQUIRED = [
    "shares_total", "equity_parent", "np_h1_2026", "np_cons_2026", "np_cons_2027",
    "np_2028_l", "np_2028_m", "np_2028_h", "np_2028_mean", "np_2028_h2",
    "r_perp", "g2", "ret_ss", "ronic_roic_m", "payout_obs", "dps_fy25",
    "capex_sanya", "irr_sanya", "capex_qz68", "irr_qz68", "capex_shawei", "irr_shawei",
    "pe_band_min", "pe_band_median", "pe_band_max",
]


def stated_triple(md: str, label: str) -> tuple[float, float, float] | None:
    """`<label> x / y / z` on one Outputs line (contrast and sensitivity rows)."""
    num = r"(-?[0-9]+(?:\.[0-9]+)?)"
    m = re.search(re.escape(label) + r"[^\n0-9]*?" + num + r"\s*/\s*" + num + r"\s*/\s*" + num,
                  outputs_section(md))
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def check_triple(md: str, label: str, computed: tuple[float, float, float]) -> list[str]:
    said = stated_triple(md, label)
    if said is None:
        return [f"stated triple '{label}' not found in Outputs"]
    bad = [f"{s} vs {c:.4f}" for s, c in zip(said, computed) if abs(s - c) > TOL]
    return [f"'{label}': {', '.join(bad)}"] if bad else []


def stated_value(md: str, label: str) -> float | None:
    m = re.search(re.escape(label) + r"[^\n0-9]*?(-?[0-9]+(?:\.[0-9]+)?)", outputs_section(md))
    return float(m.group(1)) if m else None


def check_value(md: str, label: str, computed: float) -> list[str]:
    said = stated_value(md, label)
    if said is None:
        return [f"stated value '{label}' not found in Outputs"]
    return [f"'{label}': {said} vs {computed:.4f}"] if abs(said - computed) > TOL else []


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # --- basket, g guards -----------------------------------------------------------------
    baskets = parse_baskets(md)
    r = inp["r_perp"]
    if baskets.get("r_perp") != BASKET:
        errors.append(f"r_perp: Inputs source cell must name 篮 {BASKET} first, got {baskets.get('r_perp')} (A1)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    extra = sorted(k for k in baskets if k != "r_perp")
    if extra:
        errors.append(f"only r_perp may carry a 篮 N tag; also found {extra} (AGENTS.md 篮子声明)")
    g2 = inp["g2"]
    errors += check_g_cap(g2, r, "g2")

    sh = inp["shares_total"] / YI
    E = {"L": inp["np_2028_l"], "M": inp["np_2028_m"], "H": inp["np_2028_h"]}
    win = inp["np_cons_2026"] - inp["np_h1_2026"] + inp["np_cons_2027"]

    def band(r_: float = r, g: float = g2, e: dict[str, float] = E, deduct: bool = True,
             ronic_m: float | None = None) -> dict[str, float]:
        """Per-tier value today; also returns PE / RONIC under 'pe_*' / 'ron_*' keys."""
        b0 = inp["equity_parent"] / (1 - win * g / e["M"])
        ded = (inp["capex_sanya"] * max(0.0, 1 - inp["irr_sanya"] / r_)
               + inp["capex_qz68"] * max(0.0, 1 - inp["irr_qz68"] / r_)) / sh / (1 + r_) ** TAU
        out: dict[str, float] = {"b0": b0, "ded": ded}
        for k, ek in e.items():
            ron = ronic_m if (ronic_m is not None and k == "M") else ek / b0
            b = g / ron
            if k == "H" and ron > r_:
                def rt(t: int) -> float:
                    if t <= 1:
                        return ron
                    if t <= 1 + FADE_YEARS:
                        return ron + (inp["ret_ss"] - ron) * (t - 1) / FADE_YEARS
                    return inp["ret_ss"]
                n = 1 + FADE_YEARS
                v = sum(ek * (1 + g) ** (t - 1) * (1 - g / rt(t)) / (1 + r_) ** t for t in range(1, n + 1))
                v += ek * (1 + g) ** n * (1 - g / inp["ret_ss"]) / ((r_ - g) * (1 + r_) ** n)
            else:
                v = ek * (1 - b) / (r_ - g)
            out[k] = (v / sh / (1 + r_) ** TAU + win * (1 - b) / sh / (1 + r_) ** (TAU / 2)
                      - (ded if deduct else 0.0))
            out[f"pe_{k}"] = v / ek
            out[f"ron_{k}"] = ron
        return out

    base = band()
    L, M, H = base["L"], base["M"], base["H"]
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}"])
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # --- branch / retention constraints (A4 / A6) -------------------------------------------
    ron_m = base["ron_M"]
    errors += check_branch(g2, ron_m, r, inp["payout_obs"], "M")
    if g2 / ron_m > 1 - inp["payout_obs"]:
        errors.append(f"b_M {g2 / ron_m:.1%} > 1 - payout {1 - inp['payout_obs']:.1%} (retention constraint 1)")
    if base["ron_L"] >= r or ron_m >= r:
        errors.append("L / M RONIC no longer below r — 'persistent failure' hold no longer applies (A5)")
    if not (r <= inp["ret_ss"] <= base["ron_H"]):
        errors.append(f"ret_ss {inp['ret_ss']} must sit in [r, RONIC_H {base['ron_H']:.4f}] (A5)")

    # 2c flat ladder and ②-b (A2).
    errors += ladder("2028 numerator", E["L"], E["M"], E["H"])
    mean = inp["np_2028_mean"]
    if not (E["M"] <= mean <= E["H"]):
        errors.append(f"②-b: consensus mean {mean} outside [E_M, E_H]")
    if abs(E["M"] / mean - 1) > 0.20:
        errors.append(f"②-b: E_M deviates {E['M'] / mean - 1:+.1%} from the mean (> 20%)")

    # ③ band (A10).
    pe_m = base["pe_M"]
    if not (inp["pe_band_min"] <= pe_m <= inp["pe_band_max"]):
        errors.append(f"③: M PE {pe_m:.2f} outside the equal-earnings band "
                      f"[{inp['pe_band_min']}, {inp['pe_band_max']}] (A10)")

    # --- V_opt (A8) ---------------------------------------------------------------------------
    v_opt = inp["capex_shawei"] * (inp["irr_shawei"] / r - 1) / sh / (1 + r) ** TAU
    meta = load_framework(FRAMEWORK)
    if meta.v_opt is None or abs(meta.v_opt - v_opt) > TOL:
        errors.append(f"V_opt stated {meta.v_opt} vs recomputed {v_opt:.4f}")
    p = meta.p_tiers or (0.0, 0.0, 0.0)
    plus = (L + p[0] * v_opt, M + p[1] * v_opt, H + p[2] * v_opt)
    a2, b2 = cut_points(*plus)
    errors += check_value(md, "修正带切点 A' =", a2)
    errors += check_value(md, "B' =", b2)

    # --- disclosure coordinates -----------------------------------------------------------------
    c4 = band(r_=basket_r(CONTRAST_BASKET))
    c4t = (c4["L"], c4["M"], c4["H"])
    errors += check_triple(md, "篮 4 值（10%）同式对照 →", c4t)
    gdn = band(g=g2 - 0.01)
    gdn_t = (gdn["L"], gdn["M"], gdn["H"])
    errors += check_triple(md, "g2 −1pp（2.5%）→", gdn_t)
    m_mean = band(e={**E, "M": mean})["M"]
    errors += check_value(md, "2028 均值分子 M =", m_mean)
    h2 = band(e={**E, "H": inp["np_2028_h2"]})["H"]
    errors += check_value(md, "次高家路径 H =", h2)
    h_nod = band(deduct=False)["H"]
    errors += check_value(md, "H 不扣具名项目 =", h_nod)
    m_roic = band(ronic_m=inp["ronic_roic_m"])["M"]
    errors += check_value(md, "ROIC 口径 M 档回报 5.6% 时 M =", m_roic)
    ddm = inp["dps_fy25"] * (1 + g2) / (r - g2)
    errors += check_value(md, "DDM（\\(g_d = g\\)）=", ddm)

    # --- report ----------------------------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"shares {sh:.4f}亿; window W {win:.2f}; B0 {base['b0']:.2f}; project deduction "
          f"{base['ded']:.3f}/sh")
    print(f"basket: r_perp 篮 {baskets.get('r_perp')} r={r:g}; g2={g2:g}")
    print("RONIC " + " / ".join(f"{base['ron_' + k]:.2%}" for k in "LMH")
          + " | PE " + " / ".join(f"{base['pe_' + k]:.2f}" for k in "LMH"))
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"V_opt {v_opt:.3f} p {p} -> +V " + " / ".join(f"{v:.2f}" for v in plus)
          + f"  A'={a2:.2f} B'={b2:.2f}")
    print(f"ratios: L/M={L / M:.4f} H/M={H / M:.4f} (H-L)/2M={(H - L) / (2 * M):.4f} V_opt/M={v_opt / M:.4f}")
    print(f"③: M PE {pe_m:.2f} in [{inp['pe_band_min']}, {inp['pe_band_max']}] (median {inp['pe_band_median']})")
    print("contrast 篮 4 10%: " + " / ".join(f"{v:.2f}" for v in c4t))
    print("g2 -1pp: " + " / ".join(f"{v:.2f}" for v in gdn_t))
    print(f"mean-numerator M {m_mean:.2f}; second-highest H {h2:.2f}; H no deduction {h_nod:.2f}; "
          f"ROIC-basis M {m_roic:.2f}; DDM {ddm:.2f}")
    print("rf block: CNY segment of _AXIS.rates is [待建] — no rates readings")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
