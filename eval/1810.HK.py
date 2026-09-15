#!/usr/bin/env python3
"""1810.HK (Xiaomi) valuation eval — recompute anchors from frameworks/1810.HK.md.

frameworks/1810.HK.md is the human-facing source of truth for inputs; this
script is the enforcement layer that keeps its number chain honest:

    parse §3 Inputs table -> rebuild the four SOTP legs from components
                          -> diff against the numbers printed in §3 Outputs
                          -> exit 1 on any mismatch or invariant violation

formula_id: xiaomi_sotp_phone_eco_ev_ps_cash_v3_gordon_v2

gordon_v2 (valuation-rules「构造规则冲突的裁决顺序」②): the operating numerator is
the furthest fiscal year with a >=2-house RANGE -- FY2027E (calendar FY, FY+1,
no discounting), yfinance 19-house low/mean/high adjusted EPS in CNY x issued
shares, less run-rate SBC (A6, the consensus adds it back) and after-tax net
financial income (A5, cash sits in the closing item).  That whole-company
numerator still carries the EV / MiMo segment's FY27E result (no >=2-house
segment split exists, A4'), so the deck is conservative by that amount; the EV
leg's PS value is the growth beyond FY27.  The numerator is split phone / eco by
the 1H26 gross-profit weight (A16).  FY2028E is single-house (Morgan Stanley),
so there is no g1 in the deck and `check_transition_years` does not apply; the
candidate band reruns the same formula with both Gordon legs on
two_stage_pe(g1_fy28_ms, n_fy28_cand) (A22).

Main ruler (four legs, summed — no hand-written total is ever consumed):
  1. phone leg  : ni_phone_k x perpetual_pe(g2_phone=0, ROE, r).  g2 = 0 pins
                  the multiple at 1/r, flat across tiers whatever the ROE (A7).
  2. eco leg    : ni_eco_k x perpetual_pe(g2_eco, ROE_eco_k, r); ROE on operating
                  net assets, not book equity (A15).
  3. EV leg     : FY26E segment revenue x realised peer PS cluster p25/p50/p75 (A9).
  4. closing    : net cash (never discounted) + investment portfolio x (1 - d).
  Overlay (NOT in L/M/H):
  5. V_opt      : DeepSeek peer API revenue annualized x mimo_ps (A18).

The 1H26 segment recompute (A3) is kept for reconciliation, the leg weights and
the A4' add-back upper bound; the run-rate worlds are pressure coordinates only.

Guardrail: every tier's whole-ticker multiple (anchor / GAAP-TTM EPS) must sit
inside the realised 5-year band [pe_own_min, pe_own_max] (A21, weak band).

Money inputs are in 亿元人民币; per-share anchors are HKD via fx_cny_hkd.
Run after every edit of frameworks/1810.HK.md:   python3 eval/1810.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import check_g_cap, check_r, implied_g, perpetual_pe, two_stage_pe  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "1810.HK.md"
FORMULA_ID = "xiaomi_sotp_phone_eco_ev_ps_cash_v3_gordon_v2"

TOL = 0.05  # Outputs are rounded to 2 decimals
YI = 1e8  # 亿 -> unit

REQUIRED = (
    "price", "shares", "fx_cny_hkd", "tax_rate",
    "eps27_l_cny", "eps27_m_cny", "eps27_h_cny",
    "adj_np_h1", "gp_core_h1", "gp_phone_h1", "gp_ev_h1",
    "rev_core_q1", "rev_core_q2", "opex_ratio_q1", "opex_ratio_q2",
    "opex_total_h1", "sbc_h1", "fin_net_h1",
    "r_perp", "g2_phone", "g2_eco", "g1_fy28_ms", "n_fy28_cand", "equity_cny",
    "ev_units_fy26e", "ev_asp_cny", "ev_other_rev",
    "ps_ev_l", "ps_ev_m", "ps_ev_h",
    "cash_like", "debt", "invest_cny",
    "d_invest_l", "d_invest_m", "d_invest_h",
    "pe_own_min", "pe_own_max", "eps_ttm_gaap",
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
    """Parse anchors, cut-points, per-leg table, zone boundaries, zone id, V_opt, candidate."""
    out = text.split("### Outputs", 1)[1].split("### 交叉校验", 1)[0]
    anchors = re.search(
        r"L = \*\*([\d.]+)\*\* · M = \*\*([\d.]+)\*\* · H = \*\*([\d.]+)\*\*", out)
    cuts = re.search(r"切点 A = \*\*([\d.]+)\*\* · B = \*\*([\d.]+)\*\*", out)
    zone = re.search(r"zone = \*\*`(\w+)`\*\*", out)
    if not (anchors and cuts and zone):
        sys.exit("FATAL: cannot parse Outputs (anchors / cut-points / zone line)")

    legs: dict[str, tuple[float, float, float, float, float]] = {}
    row_re = re.compile(
        rf"\|\s*([LMH])\s*\|\s*{CELL}\s*\|\s*{CELL}\s*\|\s*{CELL}\s*\|"
        rf"\s*{CELL}\s*\|\s*(?:\*\*)?{CELL}(?:\*\*)?\s*\|"
    )
    for line in out.splitlines():
        m = row_re.match(line)
        if m:
            legs[m.group(1)] = tuple(float(m.group(i)) for i in range(2, 7))

    table = "\n".join(
        line.strip().strip("|").split("|")[2]
        for line in out.splitlines()
        if line.lstrip().startswith("| `"))
    vopt_m = re.search(r"V_\{?opt\}?\\?\)?\s*=\s*\*\*([\d.]+)\*\*", out)
    ptier_m = re.search(
        r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*=\s*\*\*"
        r"\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)\s*\*\*", out)
    cand = re.findall(
        r"候选带（[^）]+）[^\n]*?L′ = \*\*([\d.]+)\*\*[^\n]*?M′ = \*\*([\d.]+)\*\*[^\n]*?H′ = \*\*([\d.]+)\*\*",
        out)
    if not vopt_m or not ptier_m:
        sys.exit("FATAL: cannot parse V_opt / p_L/p_M/p_H from Outputs")
    if len(cand) != 1:
        sys.exit(f"FATAL: expected exactly one 候选带 line, found {len(cand)}")

    return {
        "L": float(anchors.group(1)), "M": float(anchors.group(2)), "H": float(anchors.group(3)),
        "A": float(cuts.group(1)), "B": float(cuts.group(2)),
        "zone": zone.group(1), "legs": legs,
        "bounds": {float(x) for x in re.findall(r"\d+(?:\.\d+)?", table)},
        "V_opt": float(vopt_m.group(1)),
        "p_L": float(ptier_m.group(1)), "p_M": float(ptier_m.group(2)), "p_H": float(ptier_m.group(3)),
        "cand": tuple(float(x) for x in cand[0]),
    }


# ---------------------------------------------------------------- computation

def compute(v: dict[str, float], candidate: bool = False, flat_at_m: bool = False) -> dict:
    """Rebuild every leg from Inputs per §3 Formula (source of truth: the MD)."""
    r = v["r_perp"]
    # Step 1: 1H26 segment recompute (reconciliation, weights, A4' bound)
    opex_core_h1 = v["rev_core_q1"] * v["opex_ratio_q1"] + v["rev_core_q2"] * v["opex_ratio_q2"]
    opex_ev_h1 = v["opex_total_h1"] - opex_core_h1
    op_core_h1 = v["gp_core_h1"] - opex_core_h1
    op_ev_h1 = v["gp_ev_h1"] - opex_ev_h1
    strip_h1 = v["sbc_h1"] + v["fin_net_h1"] * (1.0 - v["tax_rate"])
    core_np_rr = 2.0 * (v["adj_np_h1"] - op_ev_h1 - strip_h1)  # run-rate core, EV loss added back
    np_rr = 2.0 * (v["adj_np_h1"] - strip_h1)  # run-rate whole company

    # Step 2: consensus numerator, split by gross-profit weight
    w_phone = v["gp_phone_h1"] / v["gp_core_h1"]
    ni = {b: v[f"eps27_{b}_cny"] * v["shares"] / YI - 2.0 * strip_h1 for b in BANDS}

    # Step 3: operating net assets and Gordon multiples
    net_cash = v["cash_like"] - v["debt"]
    equity_op = v["equity_cny"] - net_cash - v["invest_cny"]
    eq_phone = equity_op * w_phone
    eq_eco = equity_op * (1.0 - w_phone)

    rev_ev = v["ev_units_fy26e"] * v["ev_asp_cny"] / YI + v["ev_other_rev"]
    per_share = v["fx_cny_hkd"] * YI / v["shares"]

    def multiples(b: str) -> tuple[float, float, float]:
        roe_ph = ni[b] * w_phone / eq_phone
        roe_ec = ni[b] * (1.0 - w_phone) / eq_eco
        if candidate:
            n = int(v["n_fy28_cand"])
            pe_ph = two_stage_pe(v["g1_fy28_ms"], n, v["g2_phone"], roe_ph, r)
            pe_ec = two_stage_pe(v["g1_fy28_ms"], n, v["g2_eco"], roe_ec, r)
        else:
            pe_ph = perpetual_pe(v["g2_phone"], roe_ph, r)
            pe_ec = perpetual_pe(v["g2_eco"], roe_ec, r)
        return pe_ph, pe_ec, roe_ec

    pe_m = multiples("m")
    tiers: dict[str, dict[str, float]] = {}
    for b in BANDS:
        pe_ph, pe_ec, roe_ec = multiples(b)
        if flat_at_m:
            pe_ph, pe_ec = pe_m[0], pe_m[1]
            ps, d = v["ps_ev_m"], v["d_invest_m"]
        else:
            ps, d = v[f"ps_ev_{b}"], v[f"d_invest_{b}"]
        ni_phone = ni[b] * w_phone
        ni_eco = ni[b] * (1.0 - w_phone)
        phone = ni_phone * pe_ph
        eco = ni_eco * pe_ec
        ev = rev_ev * ps
        closing = net_cash + v["invest_cny"] * (1.0 - d)
        tiers[b] = {
            "ni": ni[b], "ni_phone": ni_phone, "ni_eco": ni_eco,
            "pe_phone": pe_ph, "pe_eco": pe_ec, "roe_eco": roe_ec,
            "blend": w_phone * pe_ph + (1.0 - w_phone) * pe_ec,
            "phone": phone * per_share, "eco": eco * per_share, "ev": ev * per_share,
            "closing": closing * per_share,
            "total": (phone + eco + ev + closing) * per_share,
        }

    L, M, H = (tiers[b]["total"] for b in BANDS)
    mimo_rev_ann = v["mimo_peer_rev_7m"] * 12.0 / v["mimo_peer_months"]
    v_opt = mimo_rev_ann * v["mimo_ps"] * per_share

    return {
        "opex_core_h1": opex_core_h1, "opex_ev_h1": opex_ev_h1,
        "op_core_h1": op_core_h1, "op_ev_h1": op_ev_h1,
        "core_np_rr": core_np_rr, "np_rr": np_rr, "strip_h1": strip_h1,
        "w_phone": w_phone, "equity_op": equity_op, "eq_eco": eq_eco,
        "rev_ev": rev_ev, "net_cash": net_cash, "per_share": per_share,
        "tiers": tiers, "L": L, "M": M, "H": H, "A": (L + M) / 2, "B": (M + H) / 2,
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
    cand = compute(v, candidate=True)
    fc = compute(v, flat_at_m=True)
    T = c["tiers"]

    checks: list[tuple[bool, str]] = []
    for msg in (check_r(v["r_perp"], "r_perp")
                + check_g_cap(v["g2_phone"], "g2_phone") + check_g_cap(v["g2_eco"], "g2_eco")):
        checks.append((False, msg))
    checks.append((True, f"r_perp={v['r_perp']} g2_phone={v['g2_phone']} g2_eco={v['g2_eco']} ≤ cap; "
                         f"no transition stage in the deck (FY2028E single house -> candidate only)"))
    checks.append((v["eps27_l_cny"] < v["eps27_m_cny"] < v["eps27_h_cny"],
                   f"numerator ladder FY27E {v['eps27_l_cny']} < {v['eps27_m_cny']} < {v['eps27_h_cny']} CNY"))
    checks.append((all(T[b]["ni"] > 0 for b in BANDS),
                   f"operating numerators positive after SBC / net-financial strip ({T['l']['ni']:.2f} 亿 at L)"))
    checks.append((abs(T["l"]["pe_phone"] - T["m"]["pe_phone"]) < 1e-9
                   and abs(T["m"]["pe_phone"] - T["h"]["pe_phone"]) < 1e-9,
                   f"phone multiple flat across tiers ({T['m']['pe_phone']:.2f}x, g2=0 ⇒ 1/r)"))
    checks.append((v["ps_ev_l"] < v["ps_ev_m"] < v["ps_ev_h"],
                   f"EV PS band ordered ({v['ps_ev_l']}/{v['ps_ev_m']}/{v['ps_ev_h']})"))
    checks.append((v["d_invest_l"] > v["d_invest_m"] > v["d_invest_h"] >= 0,
                   f"investment discount band ordered ({v['d_invest_l']}/{v['d_invest_m']}/{v['d_invest_h']})"))
    checks.append((0 < c["w_phone"] < 1, f"w_phone in (0,1) ({c['w_phone']:.4f})"))
    checks.append((c["op_ev_h1"] < 0, f"EV segment still loss-making (op_ev_h1 = {c['op_ev_h1']:.2f} 亿; A4' bound)"))
    checks.append((c["equity_op"] > 0, f"operating net assets positive ({c['equity_op']:.2f} 亿, A15)"))
    checks.append((c["L"] < c["M"] < c["H"], f"L < M < H ({c['L']:.2f} < {c['M']:.2f} < {c['H']:.2f})"))
    checks.append((fc["L"] < fc["M"] < fc["H"],
                   f"flat ladder (eco pe / PS / d at M) still L<M<H ({fc['L']:.2f} < {fc['M']:.2f} < {fc['H']:.2f})"))
    for k in ("L", "M", "H"):
        own = c[k] / v["eps_ttm_gaap"]
        checks.append((v["pe_own_min"] - 1e-9 <= own <= v["pe_own_max"] + 1e-9,
                       f"guardrail {k}: {own:.2f}x GAAP-TTM EPS inside own band [{v['pe_own_min']}, {v['pe_own_max']}]"))
    for key in ("L", "M", "H", "A", "B"):
        checks.append((abs(stated[key] - c[key]) <= TOL,
                       f"stated {key}={stated[key]} matches computed {c[key]:.4f}"))

    for band, cells in stated["legs"].items():
        got = T[band.lower()]
        for name, idx in (("phone", 0), ("eco", 1), ("ev", 2), ("closing", 3), ("total", 4)):
            checks.append((abs(cells[idx] - got[name]) <= TOL,
                           f"leg table {band}.{name}: stated {cells[idx]} vs computed {got[name]:.4f}"))
    checks.append((set(stated["legs"]) == {"L", "M", "H"}, f"leg table rows {sorted(stated['legs'])}"))

    expected_bounds = {round(c[k], 2) for k in ("L", "A", "B", "H")}
    checks.append((stated["bounds"] == expected_bounds,
                   f"zone boundaries {sorted(stated['bounds'])} == {sorted(expected_bounds)}"))

    z = zone_of(v["price"], c)
    checks.append((z == stated["zone"], f"zone at price {v['price']}: computed `{z}` == stated `{stated['zone']}`"))
    checks.append((abs(stated["V_opt"] - c["V_opt"]) <= TOL,
                   f"stated V_opt={stated['V_opt']} matches computed {c['V_opt']:.4f}"))
    checks.append((stated["p_L"] == 0 and stated["p_H"] == 1, f"p_L/p_H endpoints ({stated['p_L']}/{stated['p_H']})"))
    checks.append((0 <= stated["p_M"] <= 1, f"p_M in [0,1] ({stated['p_M']})"))
    checks.append((cand["L"] < cand["M"] < cand["H"], "candidate band L′<M′<H′"))
    for i, k in enumerate(("L", "M", "H")):
        checks.append((abs(stated["cand"][i] - cand[k]) <= TOL,
                       f"候选带 {k}′ stated {stated['cand'][i]} vs computed {cand[k]:.4f}"))
    leaked = [k for k in v if k == "p" or k.startswith("p_")]
    checks.append((not leaked, f"no p-class fields in Inputs (A2e-7a) {leaked}"))

    print(f"framework : {FRAMEWORK.name}   formula_id={FORMULA_ID}")
    print(f"segments  : opex core/ev = {c['opex_core_h1']:.2f} / {c['opex_ev_h1']:.2f} 亿CNY"
          f"  ->  op core/ev = {c['op_core_h1']:+.2f} / {c['op_ev_h1']:+.2f} 亿CNY (1H26)")
    print(f"run-rate  : core (EV loss added back) {c['core_np_rr']:.2f} · whole company {c['np_rr']:.2f} 亿CNY"
          f"  (pressure coordinates, not tiers)")
    print(f"numerator : FY2027E consensus (19 houses, CNY) {v['eps27_l_cny']} / {v['eps27_m_cny']} / {v['eps27_h_cny']}"
          f" x shares - 2x(SBC {v['sbc_h1']:.2f} + fin {v['fin_net_h1']:.2f}x(1-t)) -> "
          + " / ".join(f"{T[b]['ni']:.2f}" for b in BANDS) + " 亿CNY")
    print(f"weights   : w_phone {c['w_phone']:.4f}; equity_op {c['equity_op']:.2f} 亿CNY (eq_eco {c['eq_eco']:.2f})")
    for b in BANDS:
        t = T[b]
        print(f"  {b.upper()}: phone ni {t['ni_phone']:.2f} x {t['pe_phone']:.2f}"
              f" | eco ni {t['ni_eco']:.2f} roe {t['roe_eco']:.2f} x {t['pe_eco']:.3f}"
              f" | ev {t['ev']:.2f} | closing {t['closing']:.2f}  =  {t['total']:.2f} HKD")
    print(f"anchors   : L {c['L']:.2f} · M {c['M']:.2f} · H {c['H']:.2f}   (A {c['A']:.2f} · B {c['B']:.2f})")
    print(f"candidate : g1 {v['g1_fy28_ms']:.4f} x {int(v['n_fy28_cand'])}y on both Gordon legs -> "
          f"{cand['L']:.2f} / {cand['M']:.2f} / {cand['H']:.2f}")
    # A2e-3: a two-stage leg reports its multiple on the post-transition-year
    # numerator; the FY27E reading carries (1+g1) and is a cross line only
    post = (1.0 + v["g1_fy28_ms"]) ** int(v["n_fy28_cand"])
    for leg in ("pe_phone", "pe_eco"):
        print(f"  {leg} on FY27E numerator: " + " / ".join(f"{cand['tiers'][b][leg]:.3f}" for b in BANDS)
              + "  | on FY28E (post-transition) numerator: "
              + " / ".join(f"{cand['tiers'][b][leg] / post:.3f}" for b in BANDS))
    print(f"flat @M   : {fc['L']:.2f} / {fc['M']:.2f} / {fc['H']:.2f}  width {(fc['H'] - fc['L']) / (2 * fc['M']):.1%}")
    print(f"decompose : L/M {c['L'] / c['M']:.3f} = num {T['l']['ni'] / T['m']['ni']:.3f} x blend-pe "
          f"{T['l']['blend'] / T['m']['blend']:.3f}; ev ps {v['ps_ev_l'] / v['ps_ev_m']:.2f}; invest "
          f"{(1 - v['d_invest_l']) / (1 - v['d_invest_m']):.2f} | H/M {c['H'] / c['M']:.3f} = num "
          f"{T['h']['ni'] / T['m']['ni']:.3f} x blend-pe {T['h']['blend'] / T['m']['blend']:.3f}; ev ps "
          f"{v['ps_ev_h'] / v['ps_ev_m']:.2f}; invest {(1 - v['d_invest_h']) / (1 - v['d_invest_m']):.2f}")
    print(f"guardrail : anchors / GAAP-TTM EPS {v['eps_ttm_gaap']} = "
          + " / ".join(f"{c[k] / v['eps_ttm_gaap']:.2f}x" for k in ("L", "M", "H"))
          + f"  band [{v['pe_own_min']}, {v['pe_own_max']}]")
    print(f"V_opt     : {c['V_opt']:.2f} HKD  (mimo_rev_ann={c['mimo_rev_ann']:.2f}亿 × PS {v['mimo_ps']:.0f})"
          f"  p={stated['p_L']}/{stated['p_M']}/{stated['p_H']}  V_opt/M={c['V_opt'] / c['M']:.1%}")
    print(f"zone+V    : L {c['L'] + stated['p_L'] * c['V_opt']:.2f} · M {c['M'] + stated['p_M'] * c['V_opt']:.2f}"
          f" · H {c['H'] + stated['p_H'] * c['V_opt']:.2f}")
    print(f"price     : {v['price']} -> zone {z}   (vs L {v['price'] / c['L'] - 1:+.1%}, vs M {v['price'] / c['M'] - 1:+.1%})")
    # market-implied core multiple with the M-tier EV leg and closing held
    m = T["m"]
    core_mkt = (v["price"] - m["ev"] - m["closing"]) / (m["ni"] * c["per_share"])
    g_mkt, ok = implied_g(core_mkt, m["roe_eco"], v["r_perp"])
    print(f"market solves for (EV leg / closing at M): core PE {core_mkt:.2f}x on FY27E ops -> blended g {g_mkt:+.2%}"
          f"{'' if ok else ' (ill-conditioned)'}")
    # pressure coordinates (deep_discount): whole-company run-rate at the L-tier multiples / at 1/r
    lt = T["l"]
    ev_l = c["rev_ev"] * v["ps_ev_l"]
    cl_l = c["net_cash"] + v["invest_cny"] * (1.0 - v["d_invest_l"])
    print(f"pressure  : whole-company run-rate {c['np_rr']:.1f} 亿 @L blend {c['np_rr'] * lt['blend'] * c['per_share'] + (ev_l + cl_l) * c['per_share']:.2f}"
          f" · x 1/r {c['np_rr'] / v['r_perp'] * c['per_share'] + (ev_l + cl_l) * c['per_share']:.2f}"
          f" · run-rate core (EV loss added back) @L {c['core_np_rr'] * lt['blend'] * c['per_share'] + (ev_l + cl_l) * c['per_share']:.2f}")
    print("sensitivity:")
    for g in (v["g2_eco"] - 0.01, v["g2_eco"] + 0.01, -0.0098):
        alt = compute(dict(v, g2_eco=g))
        print(f"  g2_eco={g:+.4f}: {alt['L']:.2f} / {alt['M']:.2f} / {alt['H']:.2f}")
    addback = -2.0 * c["op_ev_h1"] / (v["shares"] / YI)  # CNY/share equivalent of the run-rate EV loss
    alt = compute({**v, **{f"eps27_{b}_cny": v[f"eps27_{b}_cny"] + addback for b in BANDS}})
    print(f"  A4' upper bound (add back 1H26 annualized EV loss {-2 * c['op_ev_h1']:.1f} 亿): "
          f"{alt['L']:.2f} / {alt['M']:.2f} / {alt['H']:.2f}")
    alt = compute(dict(v, eps27_m_cny=v["eps27_m_cny"] + 0.1))
    print(f"  eps27_m +0.1 CNY: M {alt['M']:.2f} ({alt['M'] - c['M']:+.2f})")

    if gaps:
        print(f"\ngaps (待补, not consumed): {', '.join(gaps)}")

    print("\nchecks:")
    failed = False
    for ok, label in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        failed |= not ok
    if failed:
        print("FAIL: framework Outputs disagree with recomputation", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
