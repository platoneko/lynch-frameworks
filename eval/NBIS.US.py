#!/usr/bin/env python3
"""NBIS.US (Nebius Group) valuation eval — recompute anchors from frameworks/NBIS.US.md.

frameworks/NBIS.US.md is the source of truth; this script re-derives
L / M / H / A / B from the §3 Inputs table and exits 1 on mismatch.  The doc
carries no current price (AGENTS.md「现价 — 禁写契约」), so nothing here reads one.

formula_id: nbis_dbucket_fleet_split_v1

Main ruler: 留存去向审计 D-bucket project value on gross capital, one leg
(AI cloud, basket 4, r 10%), unlevered, closed by net debt and investments:

    in-service fleet   K_in x ROIC_book / r           (measured book economics:
                                                       June ARR / in-service gross)
    CIP + window       K x (ROIC_new / r) at t + lag, minus K at t
                       (CIP is already spent: no -K; H2'26 capex + 2027-28 at
                       1 GW/yr are still to be spent)
    ROIC = (revenue per $ capital x EBITDA margin - depreciation per $ capital)
           x (1 - tax); depreciation from the 6/30/26 PP&E mix and the tier's
           server life.
    closure            + cash + non-marketable investments - non-convert debt
                       - deferred revenue (prepaid service still owed);
                       converts: holder takes the better of carrying value
                       and shares (valuation-rules 杠杆门「归类」).

Tier ladder: server life 4 / 5 / 6 years, new-deal revenue per MW 20 / 22.5 /
25 $M (Q2'26 signed range), EBITDA margin L 44.6% (Q1'26) and M = H 49.7%
(Q2'26); L builds no 2027-28 window.  The L scenario falls below book equity
per share; the floor (BPS) wins and both are printed (construction §1, A20).

V_opt: the 2029-30 capacity to reach the 5 GW end-2030 target named with
NVIDIA (6-K 2026-03-11), at H economics, net of its capital.

Run:  python3 frameworks/eval/NBIS.US.py [framework.md]
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.gordon import check_r  # noqa: E402
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_baskets,
    parse_inputs,
    report,
)
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "NBIS.US.md"
FORMULA_ID = "nbis_dbucket_fleet_split_v1"
LISTING_CCY = "USD"
TOL = 0.05
TIERS = ("l", "m", "h")
# Converts outstanding at 6/30/26 (Q2'26 interim statements, note 12):
# (Inputs field prefix, conversion price).  Carrying value and original
# principal come from Inputs; shares on conversion = original / price.
CONVERTS = (
    ("cv_jun29", 51.45),
    ("cv_jun31", 51.45),
    ("cv_sep30", 138.75),
    ("cv_sep32", 138.75),
    ("cv_mar33", 180.31),
    ("cv_mar31", 183.22),
)
# V_opt tranches: 2029 and 2030 mid-year, years from the 6/30/26 valuation date.
VOPT_YEARS = (3.0, 4.0)
CAPEX_MW_SENSITIVITY = (25.0, 35.0, 40.0)

REQUIRED = [
    "r_perp", "tax_rate", "lag_yr",
    "k_srv", "k_bld", "k_inf", "k_oth", "k_cip",
    "life_bld", "life_inf", "life_oth",
    "life_srv_l", "life_srv_m", "life_srv_h",
    "arr_jun26",
    "ebitda_l", "ebitda_m", "ebitda_h",
    "rev_mw_l", "rev_mw_m", "rev_mw_h",
    "capex_2026_mid", "mw_connected_2025", "mw_connected_2026_mid",
    "capex_h1_2026", "window_gw_yr",
    "cash", "debt_other", "investments", "investments_h", "deferred_revenue",
    "shares_basic", "warrants_nvda", "equity_book",
    "vopt_gw", "p_l", "p_m", "p_h", "k_l", "k_m", "k_h", "rev_2027_cons",
] + [f"{c}_{x}" for c, _ in CONVERTS for x in ("carry", "orig")]


def build(inp: dict[str, float]) -> Callable[..., dict[str, float]]:
    k_in = inp["k_srv"] + inp["k_bld"] + inp["k_inf"] + inp["k_oth"]
    turn_book = inp["arr_jun26"] / k_in
    capex_mw = inp["capex_2026_mid"] / (inp["mw_connected_2026_mid"] - inp["mw_connected_2025"])
    h2 = inp["capex_2026_mid"] - inp["capex_h1_2026"]
    tax, lag = inp["tax_rate"], inp["lag_yr"]

    def dep(life_srv: float) -> float:
        return (inp["k_srv"] / life_srv + inp["k_bld"] / inp["life_bld"]
                + inp["k_inf"] / inp["life_inf"] + inp["k_oth"] / inp["life_oth"]) / k_in

    def roic(t: str, cm: float = capex_mw, life: float | None = None) -> tuple[float, float]:
        d = dep(life or inp[f"life_srv_{t}"])
        book = (turn_book * inp[f"ebitda_{t}"] - d) * (1 - tax)
        new = (inp[f"rev_mw_{t}"] / cm * inp[f"ebitda_{t}"] - d) * (1 - tax)
        return book, new

    def per_share(eq_pre: float) -> tuple[float, float]:
        """Holder's choice on each convert: carrying value as debt, or shares."""
        eq = eq_pre - sum(inp[f"{c}_carry"] for c, _ in CONVERTS)
        sh = inp["shares_basic"] + inp["warrants_nvda"]
        for c, px in sorted(CONVERTS, key=lambda x: x[1]):
            n = inp[f"{c}_orig"] / px
            c_val = inp[f"{c}_carry"]
            if n * (eq + c_val) / (sh + n) > c_val:  # shares worth more than the claim
                eq += c_val
                sh += n
        return eq / sh, sh

    def value(t: str, dr: float = 0.0, g: float = 0.0, cm: float = capex_mw,
              life: float | None = None, window: bool | None = None,
              defrev_mult: float = 1.0) -> dict[str, float]:
        r = inp["r_perp"] + dr
        book, new = roic(t, cm, life)

        def cap(roic_: float) -> float:  # value per $ of gross capital, steady state
            return (roic_ - g) / (r - g)

        v_in = k_in * cap(book)
        v_cip = inp["k_cip"] * cap(new) / (1 + r) ** lag
        tranches = [(h2, 0.25)]
        if window if window is not None else t != "l":
            gw = inp["window_gw_yr"] * 1000 * cm
            tranches += [(gw, 1.0), (gw, 2.0)]
        v_win = sum(k * (cap(new) / (1 + r) ** lag - 1) / (1 + r) ** ts for k, ts in tranches)
        ev = v_in + v_cip + v_win
        inv = inp["investments_h"] if t == "h" else inp["investments"]
        eq_pre = ev + inp["cash"] + inv - inp["debt_other"] - defrev_mult * inp["deferred_revenue"]
        ps, sh = per_share(eq_pre)
        ps *= 1 - inp[f"k_{t}"]
        # V_opt: 2029-30 capacity toward the 5 GW end-2030 target, H economics.
        _, new_h = roic("h", cm)
        kv = inp["vopt_gw"] / len(VOPT_YEARS) * 1000 * cm
        v_opt = sum(kv * (cap(new_h) / (1 + r) ** lag - 1) / (1 + r) ** ts for ts in VOPT_YEARS)
        return {"roic_book": book, "roic_new": new, "v_in": v_in, "v_cip": v_cip, "v_win": v_win,
                "ev": ev, "eq_pre": eq_pre, "ps": ps, "sh": sh, "v_opt_total": v_opt}

    value.k_in, value.turn_book, value.capex_mw, value.h2 = k_in, turn_book, capex_mw, h2  # type: ignore[attr-defined]
    return value


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else FRAMEWORK
    md = path.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    baskets = parse_baskets(md)
    errors += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))

    value = build(inp)
    floor = inp["equity_book"] / (inp["shares_basic"] + inp["warrants_nvda"])

    def band_at(dr: float = 0.0, **kw) -> tuple[float, float, float]:
        return max(value("l", dr, **kw)["ps"], floor), value("m", dr, **kw)["ps"], value("h", dr, **kw)["ps"]

    res = {t: value(t) for t in TIERS}
    scen_l = res["l"]["ps"]
    L, M, H = band_at()
    A, B = (L + M) / 2, (M + H) / 2
    errors += ladder("anchors", L, M, H)
    errors += ladder("roic_new", *(res[t]["roic_new"] for t in TIERS))
    errors += ladder("roic_book", *(res[t]["roic_book"] for t in TIERS))
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    v_opt = res["h"]["v_opt_total"] / res["h"]["sh"]

    print(f"formula_id={FORMULA_ID}")
    print(f"K in service {value.k_in:,.1f}  turnover(book) {value.turn_book:.3f}  capex/MW {value.capex_mw:.2f}$M"
          f"  H2'26 capex {value.h2:,.1f}")
    print("  tier  ROIC_book  ROIC_new   in-svc     CIP   window      EV   equity_pre   $/sh   shares")
    for t in TIERS:
        x = res[t]
        print(f"  {t.upper()}    {x['roic_book']:7.2%}  {x['roic_new']:7.2%}  {x['v_in']:7.0f} {x['v_cip']:7.0f}"
              f" {x['v_win']:8.0f} {x['ev']:8.0f}  {x['eq_pre']:9.0f}  {x['ps']:7.2f}  {x['sh']:6.1f}")
    print("  $/sh layers: in-service + CIP + window + closure(cash+investments-other debt-deferred rev) + converts = total")
    for t in TIERS:
        x = res[t]
        sh = x["sh"]
        inv = inp["investments_h"] if t == "h" else inp["investments"]
        clo = inp["cash"] + inv - inp["debt_other"] - inp["deferred_revenue"]
        cv = x["ps"] * sh - (x["ev"] + clo)
        print(f"  {t.upper()}  {x['v_in'] / sh:7.2f} + {x['v_cip'] / sh:6.2f} + {x['v_win'] / sh:7.2f} + {clo / sh:6.2f}"
              f" + {cv / sh:7.2f} = {x['ps']:7.2f}   EV / 2027E revenue {x['ev'] / inp['rev_2027_cons']:.2f}x")
    print(f"floor (book equity / basic+warrants) {floor:.2f}; scenario_L {scen_l:.2f} -> "
          f"{'floor wins' if floor > scen_l else 'scenario wins'}; scenario_L/M {scen_l / M:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"comparability: L/M {L / M:.3f}  H/M {H / M:.3f}  (H-L)/2M {(H - L) / (2 * M):.3f}  V_opt/M {v_opt / M:.3f}")
    print(f"V_opt (2029-30, {inp['vopt_gw']:.0f} GW at H economics) {res['h']['v_opt_total']:,.0f} -> {v_opt:.2f}/sh;"
          f" zone+V: L {L + inp['p_l'] * v_opt:.2f} M {M + inp['p_m'] * v_opt:.2f} H {H + inp['p_h'] * v_opt:.2f}")
    # construction 2c: the spread lives entirely in the ROIC ladder; equal ROIC collapses L=M=H.
    print("flat check: tiers differ only through ROIC (numerator); no multiple carries the spread")

    def fmt(b: tuple[float, float, float]) -> str:
        return f"{b[0]:.2f} / {b[1]:.2f} / {b[2]:.2f}"

    print("sensitivity (L/M/H, other inputs fixed):")
    for cm in CAPEX_MW_SENSITIVITY:
        print(f"  capex/MW {cm:.0f}$M: {fmt(band_at(cm=cm))}")
    print(f"  g2 +1pp: {fmt(band_at(g=0.01))}   g2 -1pp: {fmt(band_at(g=-0.01))}")
    print(f"  deferred revenue at 0.8x face: {fmt(band_at(defrev_mult=0.8))}")
    print(f"  M with window off: {value('m', window=False)['ps']:.2f}   H with window off: {value('h', window=False)['ps']:.2f}")
    print(f"  M with 4y servers: {value('m', life=4)['ps']:.2f}   M with 6y servers: {value('m', life=6)['ps']:.2f}")
    print("  +100bp rates: only the $775M SOFR loan (post 6/30) floats -> ~$7.8M/yr pre-tax; converts fixed; anchors unchanged")

    rf = rf_block(LISTING_CCY, {"r_perp": inp["r_perp"]}, band_at)
    if any(abs(a - b) > 1e-9 for a, b in zip(band_at(0.0), (L, M, H))):
        errors.append("rf_block dr=0 row does not reproduce anchors")
    if not errors and path == FRAMEWORK:
        write_rf_readings("NBIS.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
