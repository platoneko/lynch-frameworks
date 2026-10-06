#!/usr/bin/env python3
"""CCJ.US (Cameco) valuation eval — recompute anchors from frameworks/CCJ.US.md.

frameworks/CCJ.US.md is the source of truth; this script re-derives
L/M/H / A/B and the AP1000 option from its §3 Inputs table and exits 1 on
mismatch.  The doc states no current price or zone.

formula_id: ccj_uranium_axis_fuel_plus_wec_ev_sotp_v1

Legs (per share, USD; valuation-rules「腿归篮」— no blended r):
  fuel   uranium + fuel services + Inkai equity, net of corporate costs.
         篮 6 r 13%, g2 2.5% (commodity-leg default: USD inflation, real
         price drift ≈ 0).  Uranium price = _AXIS.uranium tier (flat).
         2027–2030 realized price = Cameco's own realized-vs-spot table
         (Q2-2026 MD&A) at the tier price; from 2031 realized = k_conv × tier.
         ANE_fuel = ane_a × (U_GP + FS_GP + Inkai) − ane_b − xs_capex, where
         U_GP = deliveries × (realized × fx − unit cost) and
         unit cost = [prod × c_prod + (deliv − prod) × buy_ratio × price × fx] / deliv.
         Value = Σ_{2027..2030} payout × E_t / (1+r)^t + PE(g2, ROE_2031, r) × E_2031 / (1+r)^4,
         payout = 1 − g2/ROE_2031; ROE_2031 = E_2031 / fuel equity rolled with b = g2/ROE.
  wec    Westinghouse core (49%), equity-accounted with its own debt →
         valuation-rules「权益法被投资方自带债务」EV construction:
         (EBITDA − maint capex) × (1 − t) × PE(g2, ROIC, r) + tax-shield PV − net debt.
         篮 4 r 10%; ROIC ex acquisition goodwill/intangibles.
  cash   Cameco net cash (2025-12-31).
V_opt   AP1000 new build (WEC 49%): per unit PV at FID of the construction
        margin (rev × margin × (1−t) × 49%, spread evenly over build years)
        plus the 80-year fuel/service tail, discounted from FID year to t0 at
        the WEC leg r.  p_k = named-unit value per tier ÷ full (H) value.

Run:  python3 frameworks/eval/CCJ.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import check_g_cap, check_r, perpetual_pe  # noqa: E402
from lib.inputs import check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report  # noqa: E402

sys.path.insert(1, str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FRAMEWORK = ROOT / "frameworks" / "CCJ.US.md"
AXIS = ROOT / "frameworks" / "axes" / "uranium.md"
FORMULA_ID = "ccj_uranium_axis_fuel_plus_wec_ev_sotp_v1"
LISTING_CCY = "USD"
TOL = 0.05
TIERS = ("l", "m", "h")
YEARS = (2027, 2028, 2029, 2030)

# Cameco realized-vs-spot table, Q2-2026 MD&A (US$/lb; committed contracts as of 2026-06-30).
REALIZED_TABLE = {
    2027: {40: 46, 60: 58, 80: 69, 100: 74, 120: 76, 140: 78, 160: 80},
    2028: {40: 49, 60: 60, 80: 72, 100: 80, 120: 84, 140: 89, 160: 92},
    2029: {40: 53, 60: 62, 80: 75, 100: 85, 120: 91, 140: 96, 160: 101},
    2030: {40: 53, 60: 63, 80: 76, 100: 88, 120: 94, 140: 100, 160: 106},
}

REQUIRED = [
    "u_l", "u_m", "u_h", "fx", "shares", "net_cash",
    "deliv", "prod_l", "prod_m", "prod_h", "c_prod", "buy_ratio", "k_conv",
    "fs_gp", "inkai_base", "inkai_spot0", "inkai_slope", "ane_a", "ane_b", "xs_capex", "eq_fuel",
    "r_fuel", "g2_fuel",
    "wec_ebitda_l", "wec_ebitda_m", "wec_ebitda_h", "wec_maint", "wec_tax", "wec_shield", "wec_nd",
    "roic_wec", "r_wec", "g2_wec_l", "g2_wec_m", "g2_wec_h", "wec_int",
    "ap_rev", "ap_margin", "ap_years", "ap_om_rev", "ap_om_margin", "ap_om_life", "ap_own",
    "n_pol", "n_bul", "n_ukr", "n_vcs", "n_fermi", "n_kor",
    "t_pol", "t_bul", "t_ukr", "t_vcs", "t_fermi", "t_kor",
    "deal_paid", "deal_dist",
]


def interp(table: dict[int, float], x: float) -> float:
    ks = sorted(table)
    if not ks[0] <= x <= ks[-1]:
        raise ValueError(f"price {x} outside the company table")
    for a, b in zip(ks, ks[1:]):
        if a <= x <= b:
            return table[a] + (table[b] - table[a]) * (x - a) / (b - a)
    raise AssertionError


def unit_cost(inp: dict, price: float, prod: float) -> float:
    buy = (inp["deliv"] - prod) * inp["buy_ratio"] * price * inp["fx"]
    return (prod * inp["c_prod"] + buy) / inp["deliv"]


def fuel_ane(inp: dict, price: float, prod: float, realized_usd: float) -> float:
    ugp = inp["deliv"] * (realized_usd * inp["fx"] - unit_cost(inp, price, prod))
    inkai = inp["inkai_base"] + inp["inkai_slope"] * (price - inp["inkai_spot0"])
    return inp["ane_a"] * (ugp + inp["fs_gp"] + inkai) - inp["ane_b"] - inp["xs_capex"]


def fuel_leg(inp: dict, t: str, r_shift: float = 0.0) -> dict:
    price, prod = inp[f"u_{t}"], inp[f"prod_{t}"]
    r, g = inp["r_fuel"] + r_shift, inp["g2_fuel"]
    E = {y: fuel_ane(inp, price, prod, interp(REALIZED_TABLE[y], price)) for y in YEARS}
    E[2031] = fuel_ane(inp, price, prod, inp["k_conv"] * price)
    # fuel equity rolled to 2031 with the model retention b = g/ROE (fixed point)
    eq = inp["eq_fuel"]
    for _ in range(50):
        roe = E[2031] / eq
        b = g / roe
        eq_new = inp["eq_fuel"] + b * sum(E[y] for y in YEARS)
        if abs(eq_new - eq) < 1e-6:
            break
        eq = eq_new
    roe = E[2031] / eq
    pe = perpetual_pe(g, roe, r)
    payout = 1 - g / roe
    pv_cad = sum(payout * E[y] / (1 + r) ** (i + 1) for i, y in enumerate(YEARS)) + pe * E[2031] / (1 + r) ** len(YEARS)
    return {"E": E, "roe": roe, "pe": pe, "payout": payout, "eq31": eq,
            "ps": pv_cad / inp["fx"] / inp["shares"]}


def wec_leg(inp: dict, t: str, r_shift: float = 0.0) -> dict:
    r, g = inp["r_wec"] + r_shift, inp[f"g2_wec_{t}"]
    e = inp[f"wec_ebitda_{t}"]
    pe = perpetual_pe(g, inp["roic_wec"], r)
    nopat = (e - inp["wec_maint"]) * (1 - inp["wec_tax"])
    ev = nopat * pe + inp["wec_shield"]
    eq = ev - inp["wec_nd"]
    levered = (e - inp["wec_maint"] - inp["wec_int"]) * (1 - inp["wec_tax"]) * pe + inp["wec_shield"]
    return {"pe": pe, "nopat": nopat, "ev": ev, "eq": eq, "ps": eq / inp["shares"],
            "levered": levered, "gap": levered - eq}


def ap_unit_pv(inp: dict, fid_t: float, r: float) -> float:
    """US$ mn PV at t0 of one AP1000 unit to Cameco (49% of WEC)."""
    own, tax = inp["ap_own"], inp["wec_tax"]
    n = int(inp["ap_years"])
    build = inp["ap_rev"] * inp["ap_margin"] * (1 - tax) * own / n
    pv_build = sum(build / (1 + r) ** (i + 1) for i in range(n))
    om = inp["ap_om_rev"] * inp["ap_om_margin"] * (1 - tax) * own
    life = inp["ap_om_life"]
    pv_om = om / r * (1 - (1 + r) ** -life) / (1 + r) ** n
    return (pv_build + pv_om) / (1 + r) ** (fid_t - 1)


PROJECTS = {
    "l": ("pol",),
    "m": ("pol", "bul", "ukr", "vcs", "fermi"),
    "h": ("pol", "bul", "ukr", "vcs", "fermi", "kor"),
}


def v_opt(inp: dict, t: str) -> float:
    r = inp["r_wec"]
    return sum(inp[f"n_{p}"] * ap_unit_pv(inp, inp[f"t_{p}"], r) for p in PROJECTS[t]) / inp["shares"]


def anchors(inp: dict, r_shift: float = 0.0) -> tuple[float, float, float]:
    cash = inp["net_cash"] / inp["fx"] / inp["shares"]
    return tuple(fuel_leg(inp, t, r_shift)["ps"] + wec_leg(inp, t, r_shift)["ps"] + cash for t in TIERS)


def bridge_backtest(inp: dict) -> list[str]:
    """valuation-rules「桥 MUST 复现实测年」: own segment inputs → fuel ANE, ±20%."""
    errors = []
    # (year, uranium GP, FS GP, Inkai equity, fuel ANE actual) — MD&A 2023–2025; fuel ANE = ANE − WEC ANE
    rows = [(2025, 803, 173.8, 158.9, 521), (2024, 681, 105.9, 207.6, 438), (2023, 444, 124, 178.8, 377)]
    for y, ugp, fs, ink, act in rows:
        est = inp["ane_a"] * (ugp + fs + ink) - inp["ane_b"]
        dev = est / act - 1
        print(f"bridge {y}: est {est:.0f} vs fuel ANE {act} ({dev:+.0%})")
        if abs(dev) > 0.20:
            errors.append(f"bridge {y} off by {dev:+.0%}")
    # unit-cost back-test: 2025 (prod 21.0 / deliv 33.0, purchase price 82 CAD)
    uc25 = (21.0 * inp["c_prod"] + 12.0 * 82.0) / 33.0
    print(f"unit cost 2025: model {uc25:.2f} vs actual 62.71 ({uc25 / 62.71 - 1:+.0%})")
    if abs(uc25 / 62.71 - 1) > 0.20:
        errors.append("unit cost back-test off")
    return errors


def check_axis(inp: dict) -> list[str]:
    if not AXIS.exists():
        return [f"axis file missing: {AXIS.name}"]
    md = AXIS.read_text(encoding="utf-8")
    errors = []
    for t, label in zip(TIERS, ("L", "M", "H")):
        row = next((ln for ln in md.splitlines() if ln.startswith(f"| **{label}**")), None)
        if row is None:
            errors.append(f"axis tier {label} row missing")
            continue
        cells = [c.strip().strip("*") for c in row.strip("|").split("|")]
        if float(cells[2]) != inp[f"u_{t}"]:
            errors.append(f"axis {label}: {cells[2]} vs stated u_{t} {inp[f'u_{t}']:g}")
    if "CCJ.US" not in md.split("\n", 4)[2]:
        errors.append("axis header does not mount CCJ.US")
    return errors


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    baskets = parse_baskets(md)
    errors += check_r(inp["r_fuel"], "r_fuel", baskets.get("r_fuel"))
    errors += check_r(inp["r_wec"], "r_wec", baskets.get("r_wec"))
    errors += check_g_cap(inp["g2_fuel"], inp["r_fuel"], "g2_fuel")
    for t in TIERS:
        errors += check_g_cap(inp[f"g2_wec_{t}"], inp["r_wec"], f"g2_wec_{t}")
    errors += check_axis(inp)
    errors += bridge_backtest(inp)
    if errors:
        return report(errors, "FAIL (guards)")

    F = {t: fuel_leg(inp, t) for t in TIERS}
    W = {t: wec_leg(inp, t) for t in TIERS}
    cash = inp["net_cash"] / inp["fx"] / inp["shares"]
    L, M, H = anchors(inp)
    A, B = (L + M) / 2, (M + H) / 2
    errors += ladder("anchors", L, M, H)
    errors += ladder("fuel E2031", *(F[t]["E"][2031] for t in TIERS))

    for t in TIERS:
        f, w = F[t], W[t]
        print(f"{t.upper()}: U {inp[f'u_{t}']:g} prod {inp[f'prod_{t}']:g} | fuel ANE 27–31 "
              + "/".join(f"{f['E'][y]:.0f}" for y in (*YEARS, 2031))
              + f" ROE31 {f['roe']:.1%} PE {f['pe']:.2f} payout {f['payout']:.0%} → {f['ps']:.2f}"
              f" | WEC NOPAT {w['nopat']:.0f} PE {w['pe']:.2f} EV {w['ev']:.0f} − ND {inp['wec_nd']:.0f} → {w['ps']:.2f}"
              f" (扣息口径 {w['levered'] / inp['shares']:.2f}, 差 {w['gap']:.0f}) | cash {cash:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M {L / M:.3f} | H/M {H / M:.3f} | width {(H - L) / (2 * M):.3f}")

    # flat-multiple ladder (construction §2c): fuel PE and WEC PE held at M
    flat = tuple(
        (F[t]["ps"] * F["m"]["pe"] / F[t]["pe"]) + (W[t]["nopat"] * W["m"]["pe"] + inp["wec_shield"] - inp["wec_nd"]) / inp["shares"] + cash
        for t in TIERS)
    print(f"flat-multiple ladder: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    errors += ladder("flat-multiple", *flat)

    V = v_opt(inp, "h")
    p = tuple(v_opt(inp, t) / V for t in TIERS)
    band3 = (L + p[0] * V, M + p[1] * V, H + V)
    print(f"V_opt {V:.2f}  p {p[0]:.2f}/{p[1]:.2f}/{p[2]:.2f}  表3 {band3[0]:.2f}/{band3[1]:.2f}/{band3[2]:.2f}"
          f"  A′ {(band3[0] + band3[1]) / 2:.2f} B′ {(band3[1] + band3[2]) / 2:.2f}  V/M {V / M:.1%}")

    # 独立成交价护栏 (equity basis, 49%, US$ mn)
    deal = inp["deal_paid"] - inp["deal_dist"]
    for t, pk in (("h", 1.0), ("m", p[1])):
        tot = W[t]["eq"] + pk * V * inp["shares"]
        print(f"成交价护栏 {t.upper()}: WEC equity {W[t]['eq']:.0f} + V_opt×{pk:.2f} {pk * V * inp['shares']:.0f} = {tot:.0f} vs {deal:.0f}")
        if t == "h" and tot < deal:
            errors.append("transaction guard: H + V_opt below adjusted deal price")

    # 10% contrast (fuel leg at 篮 4, disclosure only)
    contrast = tuple(fuel_leg(dict(inp, r_fuel=0.10), t)["ps"] + W[t]["ps"] + cash for t in TIERS)
    print(f"对照（燃料腿 r 10%，不进锚点）: {contrast[0]:.2f}/{contrast[1]:.2f}/{contrast[2]:.2f}")
    # g2 ±1pp on the fuel leg
    for d in (-0.01, 0.01):
        s = tuple(fuel_leg(dict(inp, g2_fuel=inp["g2_fuel"] + d), t)["ps"] + W[t]["ps"] + cash for t in TIERS)
        print(f"敏感 g2_fuel {inp['g2_fuel'] + d:.1%}: {s[0]:.2f}/{s[1]:.2f}/{s[2]:.2f}")
    # 2027 fuel EPS (CAD, before xs_capex) for the consensus cross-check
    print("2027 fuel ANE/sh (CAD, accounting): " + " / ".join(
        f"{t.upper()} {(F[t]['E'][2027] + inp['xs_capex']) / inp['shares']:.2f}" for t in TIERS))

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)

    def band_rf(dr: float) -> tuple[float, float, float]:
        return anchors(inp, dr)

    rf = rf_block(LISTING_CCY, {"r_fuel": inp["r_fuel"], "r_wec": inp["r_wec"]}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: dr = 0 does not reproduce L/M/H")
    if not errors:
        write_rf_readings("CCJ.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
