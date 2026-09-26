#!/usr/bin/env python3
"""9988.HK (Alibaba) valuation eval — recompute anchors from frameworks/9988.HK.md.

frameworks/9988.HK.md is the source of truth for inputs; this script is the
enforcement layer that keeps its number chain honest:

    parse §3 Inputs table -> strip run-rate non-operating income from the FY2028E
                             consensus three points, generate the two operating
                             multiples with Gordon, recompute the legs, L/M/H,
                             A/B, zone, the candidate band and V_opt
                          -> diff against the numbers printed in §3 Outputs
                          -> exit 1 on any mismatch or invariant violation

formula_id: 9988_sotp_ecom_pe_cloud_ps_nav_v2_gordon_v2

gordon_v2 (valuation-rules「构造规则冲突的裁决顺序」②): the numerator is the
furthest fiscal year >= 2 houses can see — FY2028E (March-2028 year-end,
FY+1, so no discounting), yfinance 17-house low/mean/high in CNY per share —
net of the June-2026-quarter run-rate non-operating income that non-GAAP NI
retains (interest, equity-method, other; A9b) because those assets are counted
once in the NAV / net-cash closure.  The taxed numerator is split by run-rate
adjusted-EBITA weight into the e-commerce leg (perpetual_pe, g2_ecom peer
reverse-solve) and the cloud leg (perpetual_pe, g2_cloud peer cross-section
capped at g_cap(r)).  ROE_k = FY28E EPS tier / BPS at the OPENING of FY2028
(= end-FY2027, E_{n+1}/B_n): the June-2026 book rolled over the FY2027E
earnings not yet booked (consensus minus the June quarter) at the
growth-required retention b1 = g/ROE, g = the EBITA-weighted company g2 (no
g1 window in the deck; the candidate band rolls at its own company g with
the cloud leg on g1) -- closed form BPS = BPS0 / (1 - g N / EPS)
(valuation-rules 裁决表 ② as of 62c72a2, 2026-09-21; A21).  Company ROE: no
leg equity is disclosed (A4).  r is the basket rate: the Inputs `r_perp` row names 篮 4
龙头制造 (A20, both operating legs) and `check_r` requires r to equal that
basket's value.  There is no transition stage in the deck — FY2029E cloud
growth is single-house, so `check_transition_years` does not apply; the
candidate band reruns the same formula with the cloud leg on
two_stage_pe(g1_cloud_cand, n_cloud_cand) (A6').  The loss leg of gordon_v1 is
gone: consensus FY28E EPS already carries every segment's loss path (A7).
AI Labs upside stays outside the deck as V_opt = ALA revenue x ala_ps (A19).

Checks beyond the anchor comparison:
  1. A9b closure: non-operating pre-tax equals the announcement's bridge value
  2. r basket (Inputs 篮 N == r), g2 caps at g_cap(r), r - g2 >= 2%, numerator ladder
  3. own realised PE band guardrail (weak band; band-edge g printed as evidence)
  4. flat-multiple ladder (both multiples and d at M) still L < M < H
  5. candidate band matches the one Outputs line and is ordered
  6. no p_* fields in Inputs; V_opt / p tiers as stated

Run after every edit of frameworks/9988.HK.md:  python3 eval/9988.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import (  # noqa: E402
    check_g_cap, check_r, implied_g, perpetual_pe, two_stage_pe,
)
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.inputs import parse_baskets  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "9988.HK.md"
FORMULA_ID = "9988_sotp_ecom_pe_cloud_ps_nav_v2_gordon_v2"
TOL = 0.05  # Outputs are rounded to 2 decimals
YI = 1e8  # 亿, for human-readable reporting
MIN_R_MINUS_G = 0.02  # valuation-rules: below this the multiple sits at the pole
# _AXIS.rates segment: HKD rides the USD r_f via the peg (valuation-rules「按上市货币取段」).
LISTING_CCY = "HKD"
NONOP_PRETAX_BRIDGE_CNY = 3.378e9  # A9b: adj EBITA 27,329 + 3,378 - 9,992 tax = 20,715 non-GAAP NI

D_NAV_BAND = (0.10, 0.60)  # A9

REQUIRED = (
    "price", "shares", "fx_cny_hkd",
    "eps28_l_cny", "eps28_m_cny", "eps28_h_cny",
    "nonop_pretax_q_cny", "eq_method_q_cny", "tax_rate",
    "ebita_aeg_q_cny", "ebita_cloud_q_cny",
    "rev_ala_q_cny", "ala_ps",
    "r_perp", "bps_hkd", "g2_ecom", "g2_cloud", "g1_cloud_cand", "n_cloud_cand",
    "pe_own_min", "pe_own_max", "eps_ttm_gaap",
    "nav_cny", "d_l", "d_m", "d_h",
    "net_cash_cny", "placement_hkd",
    "eps27_m_cny", "eps_1q27_cny", "payout_3y",
)

SCENARIOS = ("l", "m", "h")


# ---------------------------------------------------------------- parsing

def parse_inputs(md: str) -> tuple[dict[str, float], list[str]]:
    """Parse the §3 Inputs table: | field | value | meaning | as-of |."""
    section = md.split("### Inputs", 1)[1].split("### Formula", 1)[0]
    inputs: dict[str, float] = {}
    gaps: list[str] = []
    for line in section.splitlines():
        m = re.match(r"\|\s*([a-z][a-z0-9_]*)\s*\|\s*([^|]*)\|", line)
        if not m:
            continue
        field, raw = m.group(1), m.group(2).strip()
        if raw.startswith("待补") or raw in ("", "—"):
            gaps.append(field)
            continue
        num = re.match(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", raw.replace(",", ""))
        if num:
            inputs[field] = float(num.group(0))
    missing = [f for f in REQUIRED if f not in inputs]
    if missing:
        sys.exit(f"FATAL: required inputs missing/待补 in {FRAMEWORK.name}: {missing}")
    return inputs, gaps


CELL = r"([−-]?[0-9]+(?:\.[0-9]+)?)(?:（[^）]*）)?"


def parse_stated(md: str) -> dict:
    """Parse anchors, cut-points, 表1 legs, zone-table boundaries, zone id, V_opt, candidate."""
    out = md.split("### Outputs", 1)[1].split("### 交叉校验", 1)[0]
    anchors = re.search(
        r"L = \*\*([\d.]+)\*\* · M = \*\*([\d.]+)\*\* · H = \*\*([\d.]+)\*\*", out)
    cuts = re.search(r"切点 A = \*\*([\d.]+)\*\* · B = \*\*([\d.]+)\*\*", out)
    zone = re.search(r"zone = \*\*`(\w+)`\*\*", out)
    if not (anchors and cuts and zone):
        sys.exit("FATAL: cannot parse §3 Outputs (anchors / cut-points / zone line)")
    legs: dict[str, list[float]] = {}
    row_re = re.compile(
        rf"\|\s*([LMH])\s*\|\s*{CELL}\s*\|\s*{CELL}\s*\|\s*{CELL}\s*\|"
        rf"\s*{CELL}\s*\|\s*(?:\*\*)?{CELL}(?:\*\*)?\s*\|"
    )
    for line in out.splitlines():
        m = row_re.match(line)
        if m:
            legs[m.group(1)] = [float(m.group(i).replace("−", "-")) for i in range(2, 7)]
    table = "\n".join(
        line.strip().strip("|").split("|")[2]
        for line in out.splitlines()
        if line.lstrip().startswith("|") and "`" in line)
    vopt_m = re.search(r"V_\{?opt\}?\\?\)?\s*=\s*\*\*([\d.]+)\*\*", out)
    ptier_m = re.search(
        r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*=\s*\*\*"
        r"\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)\s*\*\*", out)
    cand = re.findall(
        r"候选带（[^）]+）[^\n]*?L′ = \*\*([\d.]+)\*\*[^\n]*?M′ = \*\*([\d.]+)\*\*[^\n]*?H′ = \*\*([\d.]+)\*\*",
        out)
    if not vopt_m or not ptier_m:
        sys.exit("FATAL: cannot parse V_opt / p_tiers from Outputs")
    if len(cand) != 1:
        sys.exit(f"FATAL: expected exactly one 候选带 line, found {len(cand)}")
    return {
        "L": float(anchors.group(1)), "M": float(anchors.group(2)), "H": float(anchors.group(3)),
        "A": float(cuts.group(1)), "B": float(cuts.group(2)),
        "zone": zone.group(1), "legs": legs,
        "table_nums": {float(x) for x in re.findall(r"\d+(?:\.\d+)?", table)},
        "V_opt": float(vopt_m.group(1)),
        "p_L": float(ptier_m.group(1)), "p_M": float(ptier_m.group(2)), "p_H": float(ptier_m.group(3)),
        "cand": tuple(float(x) for x in cand[0]),
    }


# ---------------------------------------------------------------- computation

def compute(v: dict[str, float], candidate: bool = False, flat_at_m: bool = False) -> dict:
    """Recompute the chain per framework §3 Formula (source of truth: the MD)."""
    fx = v["fx_cny_hkd"]
    r = v["r_perp"]
    # A9b: run-rate non-operating income retained in non-GAAP NI, taxed except the equity-method share
    nonop_q = (v["nonop_pretax_q_cny"] - v["eq_method_q_cny"]) * (1 - v["tax_rate"]) + v["eq_method_q_cny"]
    nonop_ps = nonop_q * 4 / v["shares"]
    w_ecom = v["ebita_aeg_q_cny"] / (v["ebita_aeg_q_cny"] + v["ebita_cloud_q_cny"])
    w_cloud = 1.0 - w_ecom
    nav_ps = v["nav_cny"] * fx / v["shares"]
    cash_ps = (v["net_cash_cny"] * fx + v["placement_hkd"]) / v["shares"]
    v_opt = v["rev_ala_q_cny"] * 4 * v["ala_ps"] * fx / v["shares"]

    e_full = {k: v[f"eps28_{k}_cny"] * fx for k in SCENARIOS}
    e_ops = {k: (v[f"eps28_{k}_cny"] - nonop_ps) * fx for k in SCENARIOS}
    # ROE = E_{n+1} / B_n: FY28E EPS over the book at the OPENING of FY2028
    # (= end-FY2027), not the June-2026 book and not the FY2028 year-end book
    # (valuation-rules 裁决表 ② as of 62c72a2, 2026-09-21; A21).  The June-2026
    # book (end of 1Q FY27) is rolled over the FY2027E earnings not yet booked
    # (consensus minus the June quarter) at the GROWTH-REQUIRED retention
    # b1 = g/ROE, g = the company-level g the multiples charge next: the
    # EBITA-weighted blend of the two legs' g2 in the deck (no g1 window), or
    # of g2_ecom and g1_cloud_cand in the candidate band.  ROE and BPS depend
    # on each other; closed form BPS = BPS0 / (1 - g N / EPS).  FY2028's own
    # retention is NOT rolled (that would be the year-end error).  Actual
    # retention beyond b1 is the B bucket: disclosure only, not in BPS.
    g_cloud_roll = v["g1_cloud_cand"] if candidate else v["g2_cloud"]
    g_roll = w_ecom * v["g2_ecom"] + w_cloud * g_cloud_roll
    unbooked = (v["eps27_m_cny"] - v["eps_1q27_cny"]) * fx  # HKD/share, 2Q–4Q FY27 only
    bps_open = {k: v["bps_hkd"] / (1.0 - g_roll * unbooked / e_full[k]) for k in SCENARIOS}
    roe = {k: e_full[k] / bps_open[k] for k in SCENARIOS}
    b1 = {k: g_roll / roe[k] for k in SCENARIOS}
    excess_cash = {k: ((1.0 - v["payout_3y"]) - b1[k]) * unbooked for k in SCENARIOS}  # B bucket, disclosure only
    pe_ecom = {k: perpetual_pe(v["g2_ecom"], roe[k], r) for k in SCENARIOS}
    if candidate:
        pe_cloud = {k: two_stage_pe(v["g1_cloud_cand"], int(v["n_cloud_cand"]), v["g2_cloud"], roe[k], r)
                    for k in SCENARIOS}
    else:
        pe_cloud = {k: perpetual_pe(v["g2_cloud"], roe[k], r) for k in SCENARIOS}

    legs: dict[str, dict[str, float]] = {}
    anchors: dict[str, float] = {}
    for k in SCENARIOS:
        pe_e = pe_ecom["m"] if flat_at_m else pe_ecom[k]
        pe_c = pe_cloud["m"] if flat_at_m else pe_cloud[k]
        d = v["d_m"] if flat_at_m else v[f"d_{k}"]
        legs[k] = {
            "ecom": e_ops[k] * w_ecom * pe_e,
            "cloud": e_ops[k] * w_cloud * pe_c,
            "nav": nav_ps * (1 - d),
            "cash": cash_ps,
        }
        anchors[k.upper()] = sum(legs[k].values())

    L, M, H = anchors["L"], anchors["M"], anchors["H"]
    return {
        "nonop_ps": nonop_ps, "w_ecom": w_ecom, "w_cloud": w_cloud,
        "nav_ps": nav_ps, "cash_ps": cash_ps, "legs": legs, "V_opt": v_opt,
        "e_full": e_full, "e_ops": e_ops, "roe": roe, "pe_ecom": pe_ecom, "pe_cloud": pe_cloud,
        "g_roll": g_roll, "unbooked": unbooked, "bps_open": bps_open, "b1": b1, "excess_cash": excess_cash,
        "blend": {k: w_ecom * pe_ecom[k] + w_cloud * pe_cloud[k] for k in SCENARIOS},
        "L": L, "M": M, "H": H, "A": (L + M) / 2, "B": (M + H) / 2,
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


def implied_ops_pe(v: dict, c: dict, tier: str) -> float:
    """Operating-leg multiple the market pays with NAV / cash held at the tier's closure values."""
    return (v["price"] - c["legs"][tier]["nav"] - c["legs"][tier]["cash"]) / c["e_ops"][tier]


# ---------------------------------------------------------------- main

def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    v, gaps = parse_inputs(md)
    stated = parse_stated(md)
    c = compute(v)
    cand = compute(v, candidate=True)
    fc = compute(v, flat_at_m=True)

    checks: list[tuple[bool, str]] = []

    # 1. A9b closure and numerator ladder
    checks.append((abs(v["nonop_pretax_q_cny"] - NONOP_PRETAX_BRIDGE_CNY) < 1e6,
                   f"A9b non-operating pre-tax {v['nonop_pretax_q_cny'] / YI:.2f} 亿 = announcement bridge "
                   f"{NONOP_PRETAX_BRIDGE_CNY / YI:.2f} 亿 CNY/季"))
    checks.append((0 < v["eq_method_q_cny"] < v["nonop_pretax_q_cny"], "equity-method share inside non-operating"))
    checks.append((v["eps28_l_cny"] < v["eps28_m_cny"] < v["eps28_h_cny"],
                   f"numerator ladder FY28E {v['eps28_l_cny']} < {v['eps28_m_cny']} < {v['eps28_h_cny']} CNY"))
    checks.append((all(c["e_ops"][k] > 0 for k in SCENARIOS), "operating numerators positive after non-op strip"))
    checks.append((v["ebita_cloud_q_cny"] > 0 and v["ebita_aeg_q_cny"] > 0, "leg weights from positive run-rate EBITA"))

    # 2. growth-口径 discipline (valuation-rules「永续增长口径」「§r 篮子」):
    # the r_perp row must name its basket (A20) and r must be that basket's value.
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        checks.append((False, "r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)"))
    for msg in (check_r(v["r_perp"], "r_perp", baskets.get("r_perp"))
                + check_g_cap(v["g2_ecom"], v["r_perp"], "g2_ecom")
                + check_g_cap(v["g2_cloud"], v["r_perp"], "g2_cloud")):
        checks.append((False, msg))
    for name in ("g2_ecom", "g2_cloud"):
        checks.append((v["r_perp"] - v[name] >= MIN_R_MINUS_G - 1e-9,
                       f"r - {name} = {v['r_perp'] - v[name]:.2%} >= {MIN_R_MINUS_G:.0%}"))
    checks.append((True, f"r={v['r_perp']} (篮 {baskets.get('r_perp')}) g2_ecom={v['g2_ecom']} g2_cloud={v['g2_cloud']} "
                         f"no transition stage in the deck (FY2029E single house -> candidate only)"))
    for k in SCENARIOS:
        checks.append((c["pe_ecom"][k] > 0 and c["pe_cloud"][k] > 0,
                       f"ROE_{k}={c['roe'][k]:.4f} -> pe_ecom {c['pe_ecom'][k]:.2f} / pe_cloud {c['pe_cloud'][k]:.2f} "
                       f"(payout {1 - v['g2_ecom'] / c['roe'][k]:.2f} / {1 - v['g2_cloud'] / c['roe'][k]:.2f}) positive"))
        # b1 in (0,1): the deck has no negative stage-1 payout, so b1 >= 1 would be an unpriced equity raise
        checks.append((0.0 < c["b1"][k] < 1.0 and 0.0 < cand["b1"][k] < 1.0,
                       f"ROE basis {k}: roll converges, b1 = g/ROE = {c['b1'][k]:.3f} (candidate {cand['b1'][k]:.3f}) in (0,1)"))
    checks.append((0 < v["eps_1q27_cny"] < v["eps27_m_cny"], "1Q FY27 booked EPS inside FY2027E consensus"))

    # 3. bands and ordering
    d_vals = [v[f"d_{k}"] for k in SCENARIOS]
    lo, hi = D_NAV_BAND
    checks.append((all(lo <= x <= hi for x in d_vals), f"d_nav {d_vals} inside band [{lo}, {hi}]"))
    checks.append((d_vals[0] > d_vals[1] > d_vals[2], f"d_nav ordered L>M>H: {d_vals}"))
    checks.append((0 < v["tax_rate"] < 0.5, f"tax_rate {v['tax_rate']} in (0, 0.5)"))

    # 4. anchors, guardrail (裁决顺序 ③)
    checks.append((c["L"] < c["M"] < c["H"], f"L < M < H ({c['L']:.2f} < {c['M']:.2f} < {c['H']:.2f})"))
    for key in ("L", "M", "H", "A", "B"):
        checks.append((abs(stated[key] - c[key]) <= TOL,
                       f"stated {key}={stated[key]} matches computed {c[key]:.4f}"))
    expected = {round(c[k], 2) for k in ("L", "A", "B", "H")}
    checks.append((stated["table_nums"] == expected,
                   f"zone table boundaries {sorted(stated['table_nums'])} == {sorted(expected)}"))
    for k in ("L", "M", "H"):
        own = c[k] / v["eps_ttm_gaap"]
        checks.append((v["pe_own_min"] - 1e-9 <= own <= v["pe_own_max"] + 1e-9,
                       f"guardrail {k}: {own:.2f}x GAAP-TTM EPS inside own band [{v['pe_own_min']}, {v['pe_own_max']}]"))

    checks.append((set(stated["legs"]) == {"L", "M", "H"}, f"leg table rows {sorted(stated['legs'])}"))
    for tag in SCENARIOS:
        row = stated["legs"].get(tag.upper())
        if row is None:
            continue
        got = c["legs"][tag]
        want = [got["ecom"], got["cloud"], got["nav"], got["cash"], sum(got.values())]
        for name, stated_v, exp in zip(("电商", "云", "NAV", "净现金", "合计"), row, want):
            checks.append((abs(stated_v - exp) <= TOL,
                           f"leg table {tag.upper()}/{name}: stated {stated_v} vs computed {exp:.4f}"))

    # 5. zone, V_opt, candidate band, flat ladder, p-leak
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
    checks.append((fc["L"] < fc["M"] < fc["H"],
                   f"flat-multiple ladder (both multiples/d at M) still L<M<H "
                   f"({fc['L']:.2f} < {fc['M']:.2f} < {fc['H']:.2f})"))
    leaked = [k for k in v if k == "p" or k.startswith("p_")]
    checks.append((not leaked, f"no p-class fields in Inputs (A2e-7a) {leaked}"))

    print(f"framework : {FRAMEWORK.name}   formula_id={FORMULA_ID}")
    print(f"numerator : FY2028E consensus (17 houses, CNY) {v['eps28_l_cny']:.2f} / {v['eps28_m_cny']:.2f} / "
          f"{v['eps28_h_cny']:.2f}  minus run-rate non-op {c['nonop_ps']:.4f} CNY/share  "
          f"-> ops HKD {c['e_ops']['l']:.3f} / {c['e_ops']['m']:.3f} / {c['e_ops']['h']:.3f}")
    print(f"weights   : ecom {c['w_ecom']:.4f} · cloud {c['w_cloud']:.4f} (run-rate adj EBITA)   "
          f"nav/share {c['nav_ps']:.2f} · cash/share {c['cash_ps']:.2f} HKD")
    for k in SCENARIOS:
        legs = c["legs"][k]
        print(f"  {k.upper()} roe {c['roe'][k]:.4f} pe_ecom {c['pe_ecom'][k]:.3f} pe_cloud {c['pe_cloud'][k]:.3f} "
              f"blend {c['blend'][k]:.3f}: " + " ".join(f"{n}={x:+.2f}" for n, x in legs.items())
              + f"  ->  {sum(legs.values()):.2f}")
    print(f"ROE basis : BPS_open FY28 = {c['bps_open']['l']:.2f}/{c['bps_open']['m']:.2f}/{c['bps_open']['h']:.2f} HKD "
          f"(2026-06 book {v['bps_hkd']:.2f} rolled over unbooked 2Q–4Q FY27 {c['unbooked']:.2f} HKD at "
          f"b1 = g/ROE = {c['b1']['l']:.3f}/{c['b1']['m']:.3f}/{c['b1']['h']:.3f}, g_roll {c['g_roll']:.2%} = "
          f"EBITA-weighted g2); old basis (2026-06 book) would read ROE "
          + "/".join(f"{c['e_full'][k] / v['bps_hkd']:.2%}" for k in SCENARIOS))
    print(f"B bucket  : (actual retention {1 - v['payout_3y']:.0%} − b1) × unbooked = "
          f"{c['excess_cash']['l']:.2f}/{c['excess_cash']['m']:.2f}/{c['excess_cash']['h']:.2f} HKD/share "
          f"modelled-as-distributed, actually retained (disclosure only; not a leg, not in BPS)")
    print(f"anchors   : L {c['L']:.2f} · M {c['M']:.2f} · H {c['H']:.2f} (A {c['A']:.2f} · B {c['B']:.2f})")
    print(f"candidate : cloud two_stage g1={v['g1_cloud_cand']} n={int(v['n_cloud_cand'])} -> "
          f"{cand['L']:.2f} / {cand['M']:.2f} / {cand['H']:.2f}  (book rolled at company g {cand['g_roll']:.2%}: "
          f"ROE {cand['roe']['l']:.2%}/{cand['roe']['m']:.2%}/{cand['roe']['h']:.2%}, "
          f"b1 {cand['b1']['l']:.3f}/{cand['b1']['m']:.3f}/{cand['b1']['h']:.3f})")
    # A2e-3: a two-stage leg reports its multiple on the post-transition-year
    # numerator; the FY28E reading carries (1+g1) and is a cross line only
    post = (1.0 + v["g1_cloud_cand"]) ** int(v["n_cloud_cand"])
    print("  cloud PE on FY28E numerator: " + " / ".join(f"{cand['pe_cloud'][k]:.3f}" for k in SCENARIOS)
          + "  | on FY29E (post-transition) numerator: "
          + " / ".join(f"{cand['pe_cloud'][k] / post:.3f}" for k in SCENARIOS))
    print(f"flat      : multiples/d at M -> {fc['L']:.2f} / {fc['M']:.2f} / {fc['H']:.2f}"
          f"  width {(fc['H'] - fc['L']) / (2 * fc['M']):.1%}")
    print(f"decompose : L/M {c['L'] / c['M']:.3f} = num {c['e_ops']['l'] / c['e_ops']['m']:.3f} x blend-pe "
          f"{c['blend']['l'] / c['blend']['m']:.3f} (ecom {c['pe_ecom']['l'] / c['pe_ecom']['m']:.3f} / "
          f"cloud {c['pe_cloud']['l'] / c['pe_cloud']['m']:.3f}) (+NAV d) | H/M {c['H'] / c['M']:.3f} = num "
          f"{c['e_ops']['h'] / c['e_ops']['m']:.3f} x blend-pe {c['blend']['h'] / c['blend']['m']:.3f} "
          f"(ecom {c['pe_ecom']['h'] / c['pe_ecom']['m']:.3f} / cloud {c['pe_cloud']['h'] / c['pe_cloud']['m']:.3f})")
    print(f"guardrail : anchors / GAAP-TTM EPS {v['eps_ttm_gaap']} = "
          + " / ".join(f"{c[k] / v['eps_ttm_gaap']:.2f}x" for k in ("L", "M", "H"))
          + f"  band [{v['pe_own_min']}, {v['pe_own_max']}]")
    # 裁决顺序 ③「带即证据」: g the band edges pay at the M-tier ROE (weak band, reported not enforced)
    for edge in (v["pe_own_min"], v["pe_own_max"]):
        pe_edge = (edge * v["eps_ttm_gaap"] - c["legs"]["m"]["nav"] - c["legs"]["m"]["cash"]) / c["e_ops"]["m"]
        g_edge, ok = implied_g(pe_edge, c["roe"]["m"], v["r_perp"])
        print(f"  band edge {edge}x -> ops PE {pe_edge:.2f} -> g {g_edge:+.2%}{'' if ok else ' (ill-conditioned)'}")
    print(f"V_opt     : {c['V_opt']:.2f} HKD (ALA rev×4×PS {v['ala_ps']:.0f})  p={stated['p_L']}/{stated['p_M']}/{stated['p_H']}"
          f"  V_opt/M={c['V_opt'] / c['M']:.1%}")
    print(f"zone+V    : L {c['L'] + stated['p_L'] * c['V_opt']:.2f} · M {c['M'] + stated['p_M'] * c['V_opt']:.2f}"
          f" · H {c['H'] + stated['p_H'] * c['V_opt']:.2f}")
    print(f"price     : {v['price']} -> zone `{z}`")
    if "eps27_m_cny" in v:
        e27 = v["eps27_m_cny"] * v["fx_cny_hkd"]
        print("implied PE: on FY28E mean " + " ".join(f"{n} {x / c['e_full']['m']:.2f}x" for n, x in
              (("price", v["price"]), ("L", c["L"]), ("M", c["M"]), ("H", c["H"])))
              + " | on FY27E mean " + " ".join(f"{n} {x / e27:.2f}x" for n, x in
              (("price", v["price"]), ("L", c["L"]), ("M", c["M"]), ("H", c["H"]))))
    for tier in ("m", "l"):
        pe_mkt = implied_ops_pe(v, c, tier)
        g_mkt, ok = implied_g(pe_mkt, c["roe"][tier], v["r_perp"])
        print(f"market solves for (closure at {tier.upper()}): ops PE {pe_mkt:.2f}x -> blended g {g_mkt:+.2%}"
              f"{'' if ok else ' (ill-conditioned: ROE near r)'}")
    if "eps_rr_cny" in v:
        e_rr = (v["eps_rr_cny"] - c["nonop_ps"]) * v["fx_cny_hkd"]
        print(f"pressure  : run-rate non-GAAP EPS {v['eps_rr_cny']} CNY -> ops {e_rr:.2f} HKD; "
              f"@L blend {e_rr * c['blend']['l'] + c['legs']['l']['nav'] + c['legs']['l']['cash']:.1f} · "
              f"@M blend {e_rr * c['blend']['m'] + c['legs']['m']['nav'] + c['legs']['m']['cash']:.1f} · "
              f"x 1/r {e_rr / v['r_perp'] + c['legs']['l']['nav'] + c['legs']['l']['cash']:.1f}")
    print("sensitivity:")
    for g in (v["g2_ecom"] - 0.01, v["g2_ecom"] + 0.01):
        alt = compute(dict(v, g2_ecom=g))
        print(f"  g2_ecom={g:.4f}: {alt['L']:.2f} / {alt['M']:.2f} / {alt['H']:.2f}")
    alt = compute(dict(v, g2_cloud=v["g2_cloud"] - 0.01))
    print(f"  g2_cloud={v['g2_cloud'] - 0.01:.2f}: {alt['L']:.2f} / {alt['M']:.2f} / {alt['H']:.2f}")
    alt = compute(dict(v, ebita_cloud_q_cny=v["ebita_aeg_q_cny"] / 3))  # w_cloud = 25%
    print(f"  w_cloud=25%: {alt['L']:.2f} / {alt['M']:.2f} / {alt['H']:.2f}")
    alt = compute(dict(v, nonop_pretax_q_cny=0.0, eq_method_q_cny=0.0))
    print(f"  no non-op strip: {alt['L']:.2f} / {alt['M']:.2f} / {alt['H']:.2f}")
    alt = compute(dict(v, bps_hkd=v["bps_hkd"] - c["nav_ps"] - v["net_cash_cny"] * v["fx_cny_hkd"] / v["shares"]))
    print(f"  ops BPS (ex NAV, ex net cash): {alt['L']:.2f} / {alt['M']:.2f} / {alt['H']:.2f}")
    alt = compute(dict(v, eps28_m_cny=v["eps28_m_cny"] + 1.0))
    print(f"  eps28_m +1 CNY: M {alt['M']:.2f} ({alt['M'] - c['M']:+.2f})")
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): r_perp is
    # the only r in the anchors (both Gordon legs); the NAV discount d and net
    # cash carry no r.  g2, ROE basis, numerators and d stay put.
    # Disclosure only — the anchors above are the 中枢 column.
    def band_rf(dr: float) -> tuple[float, float, float]:
        alt_rf = compute(dict(v, r_perp=v["r_perp"] + dr))
        return alt_rf["L"], alt_rf["M"], alt_rf["H"]

    rf = rf_block(LISTING_CCY, {"r_perp": v["r_perp"]}, band_rf, v["price"])
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (c["L"], c["M"], c["H"]))):
        checks.append((False, "r_f readings: the dr = 0 column does not reproduce L/M/H"))
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
    # Only a clean run writes, so a FAIL never feeds the daily digest.
    write_rf_readings("9988.HK", rf.seg, (c["L"], c["M"], c["H"]), rf.consensus, rf.pressure)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
