#!/usr/bin/env python3
"""1810.HK (Xiaomi) valuation eval — recompute anchors from frameworks/1810.HK.md.

frameworks/1810.HK.md is the human-facing source of truth for inputs; this
script is the enforcement layer that keeps its number chain honest:

    parse §3 Inputs table -> rebuild the four SOTP legs from components
                          -> diff against the numbers printed in §3 Outputs
                          -> exit 1 on any mismatch or invariant violation

formula_id: xiaomi_sotp_phone_eco_ev_ps_cash_v3

Main ruler (four legs, summed — no hand-written total is ever consumed):
  1. phone leg  : ni_phone_L x (gm_k / gm_L) x PE flat 11
                  x (1+r_disc)^(-n_k). Volume and ASP are frozen; only
                  phone gross margin moves across FY26/27/28 (A7/A17).
                  w_phone = gp_phone_h1 / gp_core_h1 for the L split (A16).
  2. eco leg    : core_np x (1 - w_phone) x PE 12/17.5/19.5
                  (IoT + internet + other; no standalone software PE, A7/B).
                  Eco numerator is shared across bands (does not scale with
                  phone GM scenarios).
  3. EV leg     : FY26E segment revenue (units x ASP + AI/other) x forward PS
                  0.6/1.1/1.5. The segment is loss-making, so PE is undefined
                  and the script enforces that op_ev_h1 < 0 (A8).
  4. closing    : net cash (never discounted) + investment portfolio x (1 - d),
                  d = 40%/25%/10% (A11/A12).
  Overlay (NOT in L/M/H):
  5. V_opt      : DeepSeek peer API revenue annualized x mimo_ps,
                  converted to HKD/share (A18). p_k only for table3.

Money inputs are in 亿元人民币 (1e8 CNY); per-share anchors are HKD via
fx_cny_hkd. Run after every edit of frameworks/1810.HK.md:

    python3 eval/1810.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "1810.HK.md"
FORMULA_ID = "xiaomi_sotp_phone_eco_ev_ps_cash_v3"

TOL = 0.05  # Outputs are rounded to 2 decimals
YI = 1e8  # 亿 -> unit

REQUIRED = (
    "price", "shares", "fx_cny_hkd", "tax_rate",
    "adj_np_h1", "gp_core_h1", "gp_phone_h1", "gp_ev_h1",
    "rev_core_q1", "rev_core_q2", "opex_ratio_q1", "opex_ratio_q2",
    "opex_total_h1", "sbc_h1", "fin_net_h1",
    "pe_phone_l", "pe_phone_m", "pe_phone_h",
    "gm_phone_l", "gm_phone_m", "gm_phone_h",
    "r_disc", "n_disc_phone_l", "n_disc_phone_m", "n_disc_phone_h",
    "pe_eco_l", "pe_eco_m", "pe_eco_h",
    "ev_units_fy26e", "ev_asp_cny", "ev_other_rev",
    "ps_ev_l", "ps_ev_m", "ps_ev_h",
    "cash_like", "debt", "invest_cny",
    "d_invest_l", "d_invest_m", "d_invest_h",
    "mimo_peer_rev_7m", "mimo_peer_months", "mimo_ps",
)

BANDS = ("l", "m", "h")
CELL = r"([\d.]+)(?:（[^）]*）)?"  # bare number or number（label）


# ---------------------------------------------------------------- parsing

def parse_inputs(text: str) -> tuple[dict[str, float], list[str]]:
    """Parse the §3 Inputs markdown table. 待补 -> reported as a gap."""
    section = text.split("### Inputs", 1)[1].split("### Formula", 1)[0]
    values: dict[str, float] = {}
    gaps: list[str] = []
    for line in section.splitlines():
        m = re.match(r"\|\s*([a-z][a-z0-9_]*)\s*\|\s*([^|]+)\|", line)
        if not m:
            continue
        field, raw = m.group(1), m.group(2).strip()
        if raw.startswith("待补"):
            gaps.append(field)
            continue
        num = re.match(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?", raw.replace(",", ""))
        if num:
            values[field] = float(num.group(0))
    missing = [f for f in REQUIRED if f not in values]
    if missing:
        sys.exit(f"FATAL: required inputs missing/待补 in {FRAMEWORK.name}: {missing}")
    return values, gaps


def parse_stated(text: str) -> dict:
    """Parse anchors, cut-points, per-leg table, zone boundaries and zone id."""
    out = text.split("### Outputs", 1)[1].split("## 4.", 1)[0]
    anchors = re.search(
        r"L = \*\*([\d.]+)\*\* · M = \*\*([\d.]+)\*\* · H = \*\*([\d.]+)\*\*", out)
    cuts = re.search(r"切点 A = \*\*([\d.]+)\*\* · B = \*\*([\d.]+)\*\*", out)
    zone = re.search(r"zone = \*\*`(\w+)`\*\*", out)
    if not (anchors and cuts and zone):
        sys.exit("FATAL: cannot parse Outputs (anchors / cut-points / zone line)")

    # Per-leg: | L | phone | eco | ev | closing | total |
    legs: dict[str, tuple[float, float, float, float, float]] = {}
    row_re = re.compile(
        rf"\|\s*([LMH])\s*\|\s*{CELL}\s*\|\s*{CELL}\s*\|\s*{CELL}\s*\|"
        rf"\s*{CELL}\s*\|\s*(?:\*\*)?{CELL}(?:\*\*)?\s*\|"
    )
    for line in out.splitlines():
        m = row_re.match(line)
        if m:
            legs[m.group(1)] = tuple(float(m.group(i)) for i in range(2, 7))

    # Zone table: only the price-interval column (index 2) carries boundaries.
    table = "\n".join(
        line.strip().strip("|").split("|")[2]
        for line in out.splitlines()
        if line.lstrip().startswith("| `"))
    vopt_m = re.search(
        r"V_\{?opt\}?\\?\)?\s*=\s*\*\*([\d.]+)\*\*", out)
    ptier_m = re.search(
        r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*=\s*\*\*"
        r"\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)\s*\*\*", out)
    if not vopt_m:
        sys.exit("FATAL: cannot parse V_opt from Outputs")
    if not ptier_m:
        sys.exit("FATAL: cannot parse p_L/p_M/p_H from Outputs")

    return {
        "L": float(anchors.group(1)), "M": float(anchors.group(2)),
        "H": float(anchors.group(3)),
        "A": float(cuts.group(1)), "B": float(cuts.group(2)),
        "zone": zone.group(1),
        "legs": legs,
        "bounds": {float(x) for x in re.findall(r"\d+(?:\.\d+)?", table)},
        "V_opt": float(vopt_m.group(1)),
        "p_L": float(ptier_m.group(1)),
        "p_M": float(ptier_m.group(2)),
        "p_H": float(ptier_m.group(3)),
    }


# ---------------------------------------------------------------- computation

def compute(v: dict[str, float]) -> dict:
    """Rebuild every leg from Inputs per §3 Formula (source of truth: the MD)."""
    opex_core_h1 = (v["rev_core_q1"] * v["opex_ratio_q1"]
                    + v["rev_core_q2"] * v["opex_ratio_q2"])
    opex_ev_h1 = v["opex_total_h1"] - opex_core_h1
    op_core_h1 = v["gp_core_h1"] - opex_core_h1
    op_ev_h1 = v["gp_ev_h1"] - opex_ev_h1

    core_adj_h1 = v["adj_np_h1"] - op_ev_h1
    core_np = 2.0 * (core_adj_h1 - v["sbc_h1"]
                     - v["fin_net_h1"] * (1.0 - v["tax_rate"]))

    w_phone = v["gp_phone_h1"] / v["gp_core_h1"]
    ni_phone_l = core_np * w_phone
    ni_eco = core_np * (1.0 - w_phone)

    rev_ev = v["ev_units_fy26e"] * v["ev_asp_cny"] / YI + v["ev_other_rev"]

    net_cash = v["cash_like"] - v["debt"]
    per_share = v["fx_cny_hkd"] * YI / v["shares"]

    ni_phone: dict[str, float] = {}
    disc: dict[str, float] = {}
    legs: dict[str, dict[str, float]] = {}
    for b in BANDS:
        gm_ratio = v[f"gm_phone_{b}"] / v["gm_phone_l"]
        ni_phone[b] = ni_phone_l * gm_ratio
        disc[b] = (1.0 + v["r_disc"]) ** (-v[f"n_disc_phone_{b}"])
        phone = ni_phone[b] * v[f"pe_phone_{b}"] * disc[b]
        eco = ni_eco * v[f"pe_eco_{b}"]
        ev = rev_ev * v[f"ps_ev_{b}"]
        closing = net_cash + v["invest_cny"] * (1.0 - v[f"d_invest_{b}"])
        legs[b.upper()] = {
            "phone": phone * per_share,
            "eco": eco * per_share,
            "ev": ev * per_share,
            "closing": closing * per_share,
            "total": (phone + eco + ev + closing) * per_share,
        }

    L, M, H = (legs[k]["total"] for k in ("L", "M", "H"))

    # Flat-multiple / no-discount对照: phone pe = pe_m, n=0 for all bands.
    pe_flat = v["pe_phone_m"]
    flat_legs = {}
    for b in BANDS:
        phone = ni_phone[b] * pe_flat  # no disc
        eco = ni_eco * v[f"pe_eco_{b}"]
        ev = rev_ev * v[f"ps_ev_{b}"]
        closing = net_cash + v["invest_cny"] * (1.0 - v[f"d_invest_{b}"])
        flat_legs[b.upper()] = (phone + eco + ev + closing) * per_share

    mimo_rev_ann = v["mimo_peer_rev_7m"] * 12.0 / v["mimo_peer_months"]
    v_opt = mimo_rev_ann * v["mimo_ps"] * per_share

    return {
        "opex_core_h1": opex_core_h1, "opex_ev_h1": opex_ev_h1,
        "op_core_h1": op_core_h1, "op_ev_h1": op_ev_h1,
        "core_adj_h1": core_adj_h1, "core_np": core_np,
        "w_phone": w_phone, "ni_phone_l": ni_phone_l, "ni_eco": ni_eco,
        "ni_phone": ni_phone, "disc": disc,
        "rev_ev": rev_ev, "net_cash": net_cash, "per_share": per_share,
        "legs": legs, "L": L, "M": M, "H": H,
        "A": (L + M) / 2, "B": (M + H) / 2,
        "flat_nodisc": flat_legs,
        "mimo_rev_ann": mimo_rev_ann, "V_opt": v_opt,
    }


def zone_of(price: float, c: dict) -> str:
    if price < c["L"]:
        return "deep_discount"
    if price < c["A"]:
        return "conservative"
    if price < c["B"]:
        return "neutral"
    if price <= c["H"]:
        return "optimistic"
    return "stretched"


# ---------------------------------------------------------------- main

def main() -> int:
    text = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in text:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    v, gaps = parse_inputs(text)
    stated = parse_stated(text)
    c = compute(v)

    checks: list[tuple[bool, str]] = []
    checks.append((v["pe_phone_l"] == v["pe_phone_m"] == v["pe_phone_h"],
                   f"phone PE flat ({v['pe_phone_l']}/{v['pe_phone_m']}/{v['pe_phone_h']})"))
    checks.append((v["gm_phone_l"] < v["gm_phone_m"] < v["gm_phone_h"],
                   f"phone GM ladder ({v['gm_phone_l']}/{v['gm_phone_m']}/{v['gm_phone_h']})"))
    checks.append((v["pe_eco_l"] < v["pe_eco_m"] < v["pe_eco_h"],
                   f"eco PE band ordered ({v['pe_eco_l']}/{v['pe_eco_m']}/{v['pe_eco_h']})"))
    checks.append((v["ps_ev_l"] < v["ps_ev_m"] < v["ps_ev_h"],
                   f"EV PS band ordered ({v['ps_ev_l']}/{v['ps_ev_m']}/{v['ps_ev_h']})"))
    checks.append((v["d_invest_l"] > v["d_invest_m"] > v["d_invest_h"] >= 0,
                   f"investment discount band ordered ({v['d_invest_l']}/{v['d_invest_m']}/{v['d_invest_h']})"))
    checks.append((v["n_disc_phone_l"] < v["n_disc_phone_m"] < v["n_disc_phone_h"]
                   or (v["n_disc_phone_l"] <= v["n_disc_phone_m"] <= v["n_disc_phone_h"]),
                   f"phone disc years non-decreasing ({v['n_disc_phone_l']}/{v['n_disc_phone_m']}/{v['n_disc_phone_h']})"))
    checks.append((0 < c["w_phone"] < 1,
                   f"w_phone in (0,1) ({c['w_phone']:.4f})"))
    checks.append((c["op_ev_h1"] < 0,
                   f"EV segment still loss-making (op_ev_h1 = {c['op_ev_h1']:.2f} 亿)"))
    checks.append((c["opex_ev_h1"] > 0,
                   f"EV segment opex positive after split ({c['opex_ev_h1']:.2f} 亿)"))
    checks.append((c["core_np"] > 0, f"core numerator positive ({c['core_np']:.2f} 亿)"))
    checks.append((c["L"] < c["M"] < c["H"],
                   f"L < M < H ({c['L']:.2f} < {c['M']:.2f} < {c['H']:.2f})"))
    # A2e-2c: with phone pe flat and no disc, molecules alone must still ladder.
    fn = c["flat_nodisc"]
    checks.append((fn["L"] < fn["M"] < fn["H"],
                   f"flat-nodisc phone ladder ({fn['L']:.2f} < {fn['M']:.2f} < {fn['H']:.2f})"))
    for key in ("L", "M", "H", "A", "B"):
        checks.append((abs(stated[key] - c[key]) <= TOL,
                       f"stated {key}={stated[key]} matches computed {c[key]:.4f}"))

    for band, cells in stated["legs"].items():
        got = c["legs"][band]
        for name, idx in (("phone", 0), ("eco", 1), ("ev", 2),
                          ("closing", 3), ("total", 4)):
            checks.append((abs(cells[idx] - got[name]) <= TOL,
                           f"leg table {band}.{name}: stated {cells[idx]} "
                           f"vs computed {got[name]:.4f}"))
    checks.append((set(stated["legs"]) == {"L", "M", "H"},
                   f"leg table rows {sorted(stated['legs'])} == ['H', 'L', 'M']"))

    expected_bounds = {round(c[k], 2) for k in ("L", "A", "B", "H")}
    checks.append((stated["bounds"] == expected_bounds,
                   f"zone boundaries {sorted(stated['bounds'])} == {sorted(expected_bounds)}"))

    z = zone_of(v["price"], c)
    checks.append((z == stated["zone"],
                   f"zone at price {v['price']}: computed `{z}` == stated `{stated['zone']}`"))
    checks.append((abs(stated["V_opt"] - c["V_opt"]) <= TOL,
                   f"stated V_opt={stated['V_opt']} matches computed {c['V_opt']:.4f}"))
    checks.append((stated["p_L"] == 0 and stated["p_H"] == 1,
                   f"p_L/p_H endpoints ({stated['p_L']}/{stated['p_H']})"))
    checks.append((0 <= stated["p_M"] <= 1,
                   f"p_M in [0,1] ({stated['p_M']})"))
    checks.append((v["mimo_peer_months"] > 0 and v["mimo_ps"] > 0,
                   f"mimo inputs positive (months={v['mimo_peer_months']}, ps={v['mimo_ps']})"))

    print(f"framework : {FRAMEWORK.name}   formula_id={FORMULA_ID}")
    print(f"segments  : opex core/ev = {c['opex_core_h1']:.2f} / {c['opex_ev_h1']:.2f} 亿CNY"
          f"  ->  op core/ev = {c['op_core_h1']:+.2f} / {c['op_ev_h1']:+.2f} 亿CNY (1H26)")
    print(f"core pool : core_np = {c['core_np']:.2f} 亿CNY"
          f"  w_phone = {c['w_phone']:.4f}"
          f"  -> ni_phone_L/eco = {c['ni_phone_l']:.2f} / {c['ni_eco']:.2f}")
    print(f"phone GM  : L/M/H ni = {c['ni_phone']['l']:.2f} / {c['ni_phone']['m']:.2f} / {c['ni_phone']['h']:.2f}"
          f"  disc = {c['disc']['l']:.3f} / {c['disc']['m']:.3f} / {c['disc']['h']:.3f}")
    print(f"ev leg    : rev_ev = {c['rev_ev']:.2f} 亿CNY"
          f"  ({v['ev_units_fy26e']:.0f} units x {v['ev_asp_cny']:.0f} + {v['ev_other_rev']:.1f})")
    print(f"closing   : net_cash = {c['net_cash']:.2f}  invest = {v['invest_cny']:.2f} 亿CNY")
    for b in ("L", "M", "H"):
        g = c["legs"][b]
        print(f"  {b}: phone {g['phone']:6.2f} + eco {g['eco']:6.2f}"
              f" + ev {g['ev']:5.2f} + closing {g['closing']:6.2f}"
              f"  =  {g['total']:6.2f} HKD")
    print(f"anchors   : L {c['L']:.2f} · M {c['M']:.2f} · H {c['H']:.2f}"
          f"   (A {c['A']:.2f} · B {c['B']:.2f})")
    print(f"flat-nodisc phone: L {fn['L']:.2f} · M {fn['M']:.2f} · H {fn['H']:.2f}")
    print(f"V_opt     : {c['V_opt']:.2f} HKD"
          f"  (mimo_rev_ann={c['mimo_rev_ann']:.2f}亿 × PS {v['mimo_ps']:.0f})"
          f"  p={stated['p_L']}/{stated['p_M']}/{stated['p_H']}"
          f"  V_opt/M={c['V_opt']/c['M']:.1%}")
    print(f"zone+V    : L {c['L']+stated['p_L']*c['V_opt']:.2f}"
          f" · M {c['M']+stated['p_M']*c['V_opt']:.2f}"
          f" · H {c['H']+stated['p_H']*c['V_opt']:.2f}")
    print(f"price     : {v['price']} -> zone {z}"
          f"   (vs L {v['price'] / c['L'] - 1:+.1%}, vs M {v['price'] / c['M'] - 1:+.1%})")

    if gaps:
        print(f"\ngaps (待补, not consumed): {', '.join(gaps)}")

    print("\nchecks:")
    failed = False
    for ok, label in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        failed |= not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
