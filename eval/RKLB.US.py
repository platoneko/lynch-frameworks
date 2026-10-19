#!/usr/bin/env python3
"""RKLB.US (Rocket Lab) valuation eval — recompute anchors from frameworks/RKLB.US.md.

frameworks/RKLB.US.md is the source of truth; this script re-derives L/M/H /
A/B, the Neutron option and the candidate band from its §3 Inputs table and
exits 1 on mismatch.  The doc carries no current price (AGENTS.md「现价 — 禁写契约」):
which zone a quote falls in is derived live by the daily digest and the app.

formula_id: rklb_sotp_fy27_mature_margin_iridium_evebit_v4

Pro-forma (Iridium closed) unlevered SOTP, USD bn → per share:

    Space + Electron  篮 4  (FY2027 consensus revenue − Neutron revenue)
                            × mature EBIT margin × (1 − tax), treated as FY2029
                            earnings (no growth credited FY27→29), ×
                            Gordon(g2, marginal ROIC → rs_steady path y1 → y2, r),
                            discounted n_arr + tau = 2.5 years (A19).
                            Marginal ROIC = margin × (1 − tax) / incremental capital
                            per $ of revenue (acquisition goodwill is sunk).
    Iridium           篮 4  FY2027 EBIT × Iridium's own EV/EBIT band (construction
                            §5b quasi-annuity branch) − assumed net debt − cash
                            consideration ($27 × Iridium shares); stock leg is in
                            the share count at the 0.40 collar-floor ratio.
    Closure                 6/30 cash + Sep-2026 ATM proceeds − debt.  Neutron spend
                            is NOT here: it sits with the option (A12).

Option (zone+V; valuation-rules「未建模期权」2026-10-03): no sell-side house
publishes a same-year Neutron launch count (only Morgan Stanley, one house), so
the count falls to Rocket Lab's own named quantity — the CFO's named fleet
capacity (≈4 vehicles × quarterly turnaround = neutron_cadence launches / yr)
× the stated price per launch; the ramp's stated floor (neutron_unit, "seven
and beyond") is one unit, so k = cadence / unit > 1.  No peer scale, no peer
multiple.  Unit economics are launch economics: the company-stated Neutron
gross margin (unit cost vs price) less the deck's H-tier opex ratio; the
multiple is this ticker's ruler (perpetual_pe at g2, marginal ROIC = option
margin × (1 − tax) / cap_int, basket r).  Valued in the fleet year and
discounted back to FY2027.  Capacity-option rule (valuation-rules「未建模期权」
2026-10-04): the option deducts its own unspent capital — the reusable booster
fleet that the named cadence needs (fleet_n boosters × booster_cost, one built
per year from t_fleet0, each discounted from its build year to FY2027).
Pre-first-flight spend (neutron_carry) is spent win or lose, so it stays
outside the option and is deducted in full (not probability-weighted) in
table 3.

Candidate band: growth-rate linear fade (self-derived, no sell-side source —
a recorded rule exception, A15) on the Space + Electron leg only; L′ = L.

Run:  python3 frameworks/eval/RKLB.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import check_g_cap, check_r, perpetual_pe  # noqa: E402
from lib.inputs import check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report  # noqa: E402
from lib.zones import cut_points  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "RKLB.US.md"
FORMULA_ID = "rklb_sotp_fy27_mature_margin_iridium_evebit_v4"
TIERS = ("l", "m", "h")
REQUIRED = [
    "shares_base", "shares_sep", "irdm_shares", "exch_ratio", "tax",
    *[f"{f}_{t}" for f in ("rev", "margin", "ir_ebit", "ir_mult") for t in TIERS],
    "neutron_rev", "cap_int", "g2", "r_legs", "n_arr",
    "ir_nd", "ir_cash_ps",
    "cash", "sep_raise", "debt",
    "neutron_price", "neutron_cadence", "neutron_unit", "t_unit", "t_opt", "neutron_carry",
    "neutron_gm", "neutron_opex", "fleet_n", "fleet_unit_n", "booster_cost", "t_fleet0",
    "g_fade0", "fade_step", "n_fade",
    "tau", "y1", "y2", "rs_steady", "opt_fall",
]
TOL = 0.05
NUM_YEAR = 2027  # numerator year; the option is discounted from t_opt back to here
LISTING_CCY = "USD"


def three_segment_pe(t0: int, y1: int, y2: int, rs: float, g2: float, roe: float, r: float) -> float:
    """Single-stage multiple on year-t0 earnings with the steady-return path (valuation-rules
    「经营价值与超额现金」② 稳态回报三段): RONIC = forward through calendar y1, linear to
    min(roe, rs) by y2, Gordon tail from y2.  With rs >= roe this equals perpetual_pe.
    (gordon.py helper is [待建].)"""
    rss = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rss
        return roe + (rss - roe) * (cal - y1) / (y2 - y1)

    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g2 / rss) / ((r - g2) * (1 + r) ** (t - 1))
        pv += e * min(1.0, 1.0 - g2 / ron(cal)) / (1 + r) ** t
        e *= 1 + g2
        t += 1


NARRATIVE_CAP = 0.30  # retention「叙事换代的腿」: steady = min(tier forward, 30%), no fallback floor


def steady_pe(inp: dict, t0: int, roic: float, r: float, g2: float | None = None,
              y1: int | None = None, fall: int | None = None) -> float:
    """This ticker's ruler on the steady-return path (A19): forward ROIC to y1, then `fall`
    years down to min(forward, rs_steady) — rs_steady is the 叙事换代 cap 30% (A19)."""
    y1 = int(inp["y1"]) if y1 is None else y1
    fall = int(inp["y2"] - inp["y1"]) if fall is None else fall
    return three_segment_pe(t0, y1, y1 + fall, inp["rs_steady"], inp["g2"] if g2 is None else g2, roic, r)


def legs_value(inp: dict, t: str, r: float, g2: float | None = None) -> tuple[float, float, float, float]:
    """Space + Electron leg (USD bn), its NOPAT, marginal ROIC and multiple.  Numerator = the
    FY2029 arrival year; value at 2029-01-01 discounted n_arr + tau years to the 2026-06-30
    book (A19)."""
    rev = inp[f"rev_{t}"] - inp["neutron_rev"]
    m = inp[f"margin_{t}"]
    nopat = rev * m * (1 - inp["tax"])
    roic = m * (1 - inp["tax"]) / inp["cap_int"]
    pe = steady_pe(inp, NUM_YEAR + int(inp["n_arr"]), roic, r, g2)
    return nopat * pe / (1 + r) ** (inp["n_arr"] + inp["tau"]), nopat, roic, pe


def legs_candidate(inp: dict, t: str, r: float) -> float:
    """Same leg on the faded-growth revenue path (USD bn).

    FY2027 is t=1.  Revenue grows g_fade0, g_fade0 − step, … for n_fade years;
    the mature margin is earned from t = 1 + n_arr on that path (same arrival as
    the deck), every year's growth is charged cap_int of new capital, and the
    tail after the fade is the ruler on the last year's NOPAT × (1 + g2) — on the
    steady-return path with the visible years extended to the fade end (Y1 2031,
    same fall length) — and the whole leg carries the deck's tau (A19).
    """
    tax, ci, m = inp["tax"], inp["cap_int"], inp[f"margin_{t}"]
    n = int(inp["n_fade"])
    rev = inp[f"rev_{t}"] - inp["neutron_rev"]
    pv = 0.0
    nopat = 0.0
    for k in range(n):
        year = k + 2
        new = rev * (1 + inp["g_fade0"] - inp["fade_step"] * k)
        pv -= (new - rev) * ci / (1 + r) ** year
        rev = new
        if year >= 1 + inp["n_arr"]:
            nopat = rev * m * (1 - tax)
            pv += nopat / (1 + r) ** year
    roic = m * (1 - tax) / ci
    pe = steady_pe(inp, NUM_YEAR + n + 1, roic, r, y1=NUM_YEAR + n)
    return (pv + nopat * (1 + inp["g2"]) * pe / (1 + r) ** (n + 1)) / (1 + r) ** inp["tau"]


def iridium_value(inp: dict, t: str) -> float:
    consideration = inp["ir_nd"] + inp["ir_cash_ps"] * inp["irdm_shares"]
    return inp[f"ir_ebit_{t}"] * inp[f"ir_mult_{t}"] - consideration


def stated(md: str, label: str) -> float | None:
    m = re.search(re.escape(label) + r"\s*=\s*\*\*([0-9.]+)\*\*", md)
    return float(m.group(1)) if m else None


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
    if "r_legs" not in baskets:
        errors.append("r_legs: no 篮 N in the Inputs source cell")
    errors += check_r(inp["r_legs"], "r_legs", baskets.get("r_legs"))
    r = inp["r_legs"]
    errors += check_g_cap(inp["g2"], r, "g2")
    # 叙事换代 (A19): own cycle unusable (never profitable), peer layer empty (user 2026-10-19:
    # the four defense primes are not the same business) → steady = min(forward, 30%).
    if abs(inp["rs_steady"] - NARRATIVE_CAP) > 1e-9:
        errors.append(f"rs_steady {inp['rs_steady']:g} must equal the 叙事换代 cap {NARRATIVE_CAP:g} (A19)")
    if inp["opt_fall"] not in (2, 4, 6):
        errors.append(f"opt_fall {inp['opt_fall']:g} must be an entry-barrier rung 2 / 4 / 6 (A11)")

    sh = inp["shares_base"] + inp["shares_sep"] + inp["irdm_shares"] * inp["exch_ratio"]
    closure = inp["cash"] + inp["sep_raise"] - inp["debt"]

    rows = {}
    for t in TIERS:
        lv, nopat, roic, pe = legs_value(inp, t, r)
        ir = iridium_value(inp, t)
        rows[t] = {"legs": lv, "nopat": nopat, "roic": roic, "pe": pe, "ir": ir,
                   "total": (lv + ir + closure) / sh}

    L, M, H = (rows[t]["total"] for t in TIERS)
    errors += ladder("L<M<H", L, M, H)
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # construction §2c: flat-multiple ladder — numerators must already climb.
    errors += ladder("legs NOPAT", *(rows[t]["nopat"] for t in TIERS))
    errors += ladder("Iridium EBIT", *(inp[f"ir_ebit_{t}"] for t in TIERS))
    flat = [(rows[t]["nopat"] * rows["m"]["pe"] / (1 + r) ** (inp["n_arr"] + inp["tau"])
             + inp[f"ir_ebit_{t}"] * inp["ir_mult_m"] - inp["ir_nd"] - inp["ir_cash_ps"] * inp["irdm_shares"]
             + closure) / sh for t in TIERS]
    errors += ladder("flat-multiple L<M<H", *flat)

    # Neutron option: own named fleet cadence × own price, launch economics, own ruler, discounted from t_opt.
    t_opt, t_unit = int(inp["t_opt"]), int(inp["t_unit"])
    if not NUM_YEAR < t_unit <= t_opt:
        errors.append("t_unit / t_opt must lie after the numerator year, unit year first (A11)")
    if inp["neutron_cadence"] < inp["neutron_unit"]:
        errors.append("neutron_cadence below the stated unit cadence: k must be ≥ 1 (A11)")
    k_units = inp["neutron_cadence"] / inp["neutron_unit"]

    # Option high-return period follows Neutron's own product stage, not the satellite leg's
    # calendar (retention「高回报期 MUST 对上该腿自己的产品阶段」, user 2026-10-19): forward
    # return held through the year the named capacity is reached (Y1 = realisation year),
    # then opt_fall years (entry barrier: high) down to the same 叙事换代 cap.  Valued in the
    # realisation year, folded to FY2027, then the deck's tau to the 2026-06-30 book.
    tau_df = (1 + r) ** (-inp["tau"])
    opt_fall = int(inp["opt_fall"])

    def opt_ruler(gm: float, year: int = t_opt) -> tuple[float, float, float]:
        m = gm - inp["neutron_opex"]
        roic = m * (1 - inp["tax"]) / inp["cap_int"]
        return m, roic, steady_pe(inp, year, roic, r, y1=year, fall=opt_fall)

    m_opt, roic_opt, pe_opt = opt_ruler(inp["neutron_gm"])

    def fleet_pv(n_boosters: float, cost: float | None = None) -> float:
        """Unspent booster capital, one per year from t_fleet0, PV at FY2027 (USD bn)."""
        c = inp["booster_cost"] if cost is None else cost
        return sum(c / (1 + r) ** (int(inp["t_fleet0"]) + i - NUM_YEAR) for i in range(int(n_boosters)))

    def v_gross(year: int, n: float, price: float | None = None, gm: float | None = None) -> float:
        m, _, pe = opt_ruler(inp["neutron_gm"] if gm is None else gm, year)
        rev = n * (inp["neutron_price"] if price is None else price)
        return rev * m * (1 - inp["tax"]) * pe / (1 + r) ** (year - NUM_YEAR) / sh

    def v_at(year: int, n: float, price: float | None = None, gm: float | None = None,
             boosters: float | None = None, cost: float | None = None) -> float:
        b = inp["fleet_n"] if boosters is None else boosters
        return (v_gross(year, n, price, gm) - fleet_pv(b, cost) / sh) * tau_df

    opt_rev = inp["neutron_price"] * inp["neutron_cadence"]
    opt_nopat = opt_rev * m_opt * (1 - inp["tax"])
    v_opt = v_at(t_opt, inp["neutron_cadence"])
    v_unit = v_at(t_unit, inp["neutron_unit"], boosters=inp["fleet_unit_n"])
    if int(inp["t_fleet0"]) < NUM_YEAR or int(inp["t_fleet0"]) + int(inp["fleet_n"]) - 1 >= t_opt:
        errors.append("booster builds must start in/after FY2027 and finish before t_opt (A11)")
    carry = inp["neutron_carry"] / sh
    said = stated(md, r"\(V_{opt}\)")
    if said is None:
        errors.append("V_opt not stated")
    elif abs(said - v_opt) > TOL:
        errors.append(f"V_opt stated {said} vs computed {v_opt:.2f}")
    # p_k live in the Outputs line, never in Inputs (construction §7a).
    pm = re.search(r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*=\s*\*{0,2}\s*([0-9.]+)\s*/\s*([0-9.]+)\s*/\s*([0-9.]+)", md)
    if not pm:
        return report(errors + ["p_L/p_M/p_H not stated"])
    ps = tuple(float(x) for x in pm.groups())
    if not all(0 <= p <= 1 for p in ps) or not ps[0] <= ps[1] <= ps[2]:
        errors.append(f"p_L/p_M/p_H must be in [0,1] and non-decreasing, got {ps}")
    plus_v = [rows[t]["total"] + p * v_opt - carry for t, p in zip(TIERS, ps)]

    # Candidate band: faded-growth path on the leg only; L′ copies the deck.
    cand = {"l": L}
    for t in ("m", "h"):
        cand[t] = rows[t]["total"] + (legs_candidate(inp, t, r) - rows[t]["legs"]) / sh
    errors += ladder("candidate L′<M′<H′", cand["l"], cand["m"], cand["h"])
    for label, t in (("L′", "l"), ("M′", "m"), ("H′", "h")):
        s = stated(md, label)
        if s is None:
            errors.append(f"candidate {label} not stated")
        elif abs(s - cand[t]) > TOL:
            errors.append(f"candidate {label} stated {s} vs computed {cand[t]:.2f}")

    print(f"formula_id={FORMULA_ID}  shares {sh:.5f}bn  tax {inp['tax']:.0%}  r_legs {r:g} (篮 {baskets.get('r_legs')})")
    for t in TIERS:
        row = rows[t]
        print(f"{t.upper()}: legs {row['legs'] / sh:.2f} (NOPAT {row['nopat']:.3f} ROIC {row['roic']:.1%} PE {row['pe']:.2f})"
              f" | Iridium {row['ir'] / sh:.2f} (EV {inp[f'ir_ebit_{t}'] * inp[f'ir_mult_{t}']:.2f})"
              f" | closure {closure / sh:.2f} → {row['total']:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  flat-multiple {['%.2f' % x for x in flat]}")
    nm = [rows[t]["nopat"] for t in TIERS]
    print(f"L/M={L / M:.3f} (legs 分子比 {nm[0] / nm[1]:.2f}) H/M={H / M:.3f} (分子比 {nm[2] / nm[1]:.2f})"
          f" width={(H - L) / (2 * M):.3f} V_opt/M={v_opt / M:.2f}")
    print(f"V_opt chain: {inp['neutron_cadence']:g}/yr (k = {k_units:.2f} × unit {inp['neutron_unit']:g}/yr) × {inp['neutron_price']:g}bn"
          f" = rev {opt_rev:.3f}bn × margin {m_opt:.3f} (GM {inp['neutron_gm']:g} − opex {inp['neutron_opex']:g}) × (1-t)"
          f" = NOPAT {opt_nopat:.4f} × PE {pe_opt:.2f} (g2 {inp['g2']:g}, ROIC {roic_opt:.1%}, r {r:g}) @{t_opt}"
          f" ÷ {(1 + r) ** (t_opt - NUM_YEAR):.4f} ÷ shares = {v_gross(t_opt, inp['neutron_cadence']):.2f}"
          f" − unspent fleet {inp['fleet_n']:g} × {inp['booster_cost']:g}bn from {int(inp['t_fleet0'])}"
          f" (PV {fleet_pv(inp['fleet_n']):.4f}bn = {fleet_pv(inp['fleet_n']) / sh:.2f}/sh)"
          f" = {v_gross(t_opt, inp['neutron_cadence']) - fleet_pv(inp['fleet_n']) / sh:.2f} × tau {tau_df:.4f} → {v_opt:.2f}"
          f"  (own product-stage path: ROIC to {t_opt}, {min(roic_opt, inp['rs_steady']):.1%} from {t_opt + opt_fall}; "
          f"no-fade PE {perpetual_pe(inp['g2'], roic_opt, r):.2f})")
    print(f"  booster cost 0.03 / 0.10 → {v_at(t_opt, inp['neutron_cadence'], cost=0.03):.2f}"
          f" / {v_at(t_opt, inp['neutron_cadence'], cost=0.10):.2f}")
    print(f"  unit ({inp['neutron_unit']:g}/yr @{t_unit}, {inp['fleet_unit_n']:g} boosters) → {v_unit:.2f};"
          f" one-year slip → {v_at(t_opt + 1, inp['neutron_cadence']):.2f};"
          f" Morgan Stanley 12/yr @{t_opt} → {v_at(t_opt, 12):.2f};"
          f" price 0.055 → {v_at(t_opt, inp['neutron_cadence'], price=0.055):.2f}")
    def v_path(y1_: int, fall_: int) -> float:
        pe_ = steady_pe(inp, t_opt, roic_opt, r, y1=y1_, fall=fall_)
        return (opt_nopat * pe_ / (1 + r) ** (t_opt - NUM_YEAR) - fleet_pv(inp["fleet_n"])) / sh * tau_df

    print(f"  option path: barrier medium (fall 4, Y2 {t_opt + 4}) → {v_path(t_opt, 4):.2f};"
          f" satellite-leg calendar {int(inp['y1'])}/{int(inp['y2'])} (old) → "
          f"{v_path(int(inp['y1']), int(inp['y2'] - inp['y1'])):.2f}")
    for gm in (0.408, 0.60):
        m, roic, pe = opt_ruler(gm)
        print(f"  GM {gm:g} (margin {m:.3f}, ROIC {roic:.1%}, PE {pe:.2f}) → V_opt {v_at(t_opt, inp['neutron_cadence'], gm=gm):.2f}")
    print(f"V_opt {v_opt:.2f} (PE {pe_opt:.2f}, t {t_opt}); carry {carry:.2f}/sh;"
          f" +V(net of carry) L/M/H {plus_v[0]:.2f}/{plus_v[1]:.2f}/{plus_v[2]:.2f}"
          f"  A' {(plus_v[0] + plus_v[1]) / 2:.2f} B' {(plus_v[1] + plus_v[2]) / 2:.2f}"
          f"  (+V gross {', '.join('%.2f' % (rows[t]['total'] + p * v_opt) for t, p in zip(TIERS, ps))})")
    print(f"candidate L′ {cand['l']:.2f} M′ {cand['m']:.2f} H′ {cand['h']:.2f}")
    for dg in (-0.01, 0.01):
        band = []
        for t in TIERS:
            band.append((legs_value(inp, t, r, g2=inp["g2"] + dg)[0] + rows[t]["ir"] + closure) / sh)
        print(f"g2 {inp['g2'] + dg:.0%}: L/M/H {band[0]:.2f}/{band[1]:.2f}/{band[2]:.2f}")
    for ci in (0.3, 0.5):
        alt = dict(inp, cap_int=ci)
        band = [(legs_value(alt, t, r)[0] + rows[t]["ir"] + closure) / sh for t in TIERS]
        print(f"cap_int {ci:g}: L/M/H {band[0]:.2f}/{band[1]:.2f}/{band[2]:.2f}")

    # r_f readings (_AXIS.rates): Δr_f moves the leg basket (multiple and the
    # arrival discount); Iridium's EV/EBIT band and the closure stay put.
    def band_rf(dr: float) -> tuple[float, float, float]:
        out = [(legs_value(inp, t, r + dr)[0] + rows[t]["ir"] + closure) / sh for t in TIERS]
        return out[0], out[1], out[2]

    rf = rf_block(LISTING_CCY, {"r_legs": r}, band_rf)
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    if not errors:
        write_rf_readings("RKLB.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
