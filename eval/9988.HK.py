#!/usr/bin/env python3
"""9988.HK (Alibaba) valuation eval — recompute anchors from frameworks/9988.HK.md.

frameworks/9988.HK.md is the source of truth for inputs; this script is the
enforcement layer that keeps its number chain honest:

    parse §3 Inputs table -> recompute the four legs, L/M/H, A/B, zone
                          -> diff against the numbers printed in §3 Outputs
                          -> exit 1 on any mismatch or invariant violation

formula_id: 9988_sotp_ecom_pe_cloud_ps_nav_v2

Main ruler: SOTP — e-commerce leg (Alibaba E-commerce Group adjusted EBITA,
annualized and taxed, x PE 7/11/14) + cloud leg (FY2027E segment revenue
x PS 4/6/8) - loss leg (non-ALA residual only, capitalized at 3.0/1.5/0
years) + NAV x (1-d) + net cash. AI Labs burn is NOT capitalized as negative
equity; upside is V_opt = ALA revenue annualized x ala_ps (A19).
Both operating legs are unlevered/EV-basis; interest/net cash only in closing.

Ticket-specific sanity checks (mirror of framework §3 Formula step 1 and §2):
  1. segment identity: AEG + cloud + rest == group adjusted EBITA
  2. multiple/discount bands are ordered and inside their A4/A5/A7/A9 ranges
  3. L < M < H, and the stated anchors / cut-points / zone-table boundaries
     match recomputation within 0.05
  4. the zone implied by price matches the zone printed in Outputs

Run after every edit of frameworks/9988.HK.md:  python3 eval/9988.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "9988.HK.md"
FORMULA_ID = "9988_sotp_ecom_pe_cloud_ps_nav_v2"
TOL = 0.05  # Outputs are rounded to 2 decimals
YI = 1e8  # 亿, for human-readable reporting

# Mirror of framework §2 bands (update together with the MD).
PE_ECOM_BAND = (5.0, 16.0)  # A4: sell-side spread is 5x (Nomura) .. 14x (JPM)
PS_CLOUD_BAND = (2.0, 10.0)  # A5: Barclays 4x FY28 .. Nomura 7x FY28 (~9.5x FY27)
D_NAV_BAND = (0.10, 0.60)  # A9: Nomura implies ~41%
LOSS_YEARS_BAND = (0.0, 5.0)  # A7

REQUIRED = (
    "price", "shares", "fx_cny_hkd", "tax_rate",
    "ebita_aeg_q_cny", "ebita_cloud_q_cny", "ebita_rest_q_cny", "ebita_group_q_cny",
    "ebita_ala_q_cny", "rev_ala_q_cny", "ala_ps",
    "pe_ecom_l", "pe_ecom_m", "pe_ecom_h",
    "rev_cloud_fy27e_cny", "ps_cloud_l", "ps_cloud_m", "ps_cloud_h",
    "loss_years_l", "loss_years_m", "loss_years_h",
    "nav_cny", "d_l", "d_m", "d_h",
    "net_cash_cny", "placement_hkd",
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
    """Parse anchors, cut-points, 表1 legs, zone-table boundaries and zone id.

    The 交叉校验 table that follows carries narrative figures, so the Outputs
    slice stops at it rather than at the next `##`.
    """
    out = md.split("### Outputs", 1)[1].split("### 交叉校验", 1)[0]
    anchors = re.search(
        r"L = \*\*([\d.]+)\*\* · M = \*\*([\d.]+)\*\* · H = \*\*([\d.]+)\*\*", out)
    cuts = re.search(r"切点 A = \*\*([\d.]+)\*\* · B = \*\*([\d.]+)\*\*", out)
    zone = re.search(r"zone = \*\*`(\w+)`\*\*", out)
    if not (anchors and cuts and zone):
        sys.exit("FATAL: cannot parse §3 Outputs (anchors / cut-points / zone line)")
    # 表1: 档 | 电商 | 云 | 亏损腿 | NAV+现金 | 合计
    legs: dict[str, list[float]] = {}
    row_re = re.compile(
        rf"\|\s*([LMH])\s*\|\s*{CELL}\s*\|\s*{CELL}\s*\|\s*{CELL}\s*\|"
        rf"\s*{CELL}\s*\|\s*(?:\*\*)?{CELL}(?:\*\*)?\s*\|"
    )
    for line in out.splitlines():
        m = row_re.match(line)
        if m:
            legs[m.group(1)] = [
                float(m.group(i).replace("−", "-")) for i in range(2, 7)
            ]
    # Only the price-interval column (index 2) carries boundary numbers; the
    # scenario column holds narrative figures that must not enter the check.
    table = "\n".join(
        line.strip().strip("|").split("|")[2]
        for line in out.splitlines()
        if line.lstrip().startswith("|") and "`" in line)
    vopt_m = re.search(
        r"V_\{?opt\}?\\?\)?\s*=\s*\*\*([\d.]+)\*\*", out)
    ptier_m = re.search(
        r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*=\s*\*\*"
        r"\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)\s*\*\*", out)
    if not vopt_m or not ptier_m:
        sys.exit("FATAL: cannot parse V_opt / p_tiers from Outputs")
    return {
        "L": float(anchors.group(1)),
        "M": float(anchors.group(2)),
        "H": float(anchors.group(3)),
        "A": float(cuts.group(1)),
        "B": float(cuts.group(2)),
        "zone": zone.group(1),
        "legs": legs,
        "table_nums": {float(x) for x in re.findall(r"\d+(?:\.\d+)?", table)},
        "V_opt": float(vopt_m.group(1)),
        "p_L": float(ptier_m.group(1)),
        "p_M": float(ptier_m.group(2)),
        "p_H": float(ptier_m.group(3)),
    }


# ---------------------------------------------------------------- computation

def compute(v: dict[str, float]) -> dict:
    """Recompute the chain per framework §3 Formula (source of truth: the MD)."""
    fx = v["fx_cny_hkd"]
    base_ecom = v["ebita_aeg_q_cny"] * 4 * (1 - v["tax_rate"]) * fx
    base_cloud = v["rev_cloud_fy27e_cny"] * fx
    # Non-ALA residual only — ALA burn stays out of the bottom card (A19).
    non_ala = v["ebita_rest_q_cny"] - v["ebita_ala_q_cny"]
    burn = -non_ala * 4 * fx  # positive: annual cash burn, HKD
    nav = v["nav_cny"] * fx
    cash = v["net_cash_cny"] * fx + v["placement_hkd"]
    v_opt = v["rev_ala_q_cny"] * 4 * v["ala_ps"] * fx / v["shares"]

    legs: dict[str, dict[str, float]] = {}
    anchors: dict[str, float] = {}
    for k in SCENARIOS:
        parts = {
            "ecom": base_ecom * v[f"pe_ecom_{k}"],
            "cloud": base_cloud * v[f"ps_cloud_{k}"],
            "loss": -burn * v[f"loss_years_{k}"],
            "nav": nav * (1 - v[f"d_{k}"]),
            "cash": cash,
        }
        legs[k] = {name: x / v["shares"] for name, x in parts.items()}
        anchors[k.upper()] = sum(parts.values()) / v["shares"]

    L, M, H = anchors["L"], anchors["M"], anchors["H"]
    return {
        "base_ecom": base_ecom, "base_cloud": base_cloud, "burn": burn,
        "nav": nav, "cash": cash, "legs": legs, "V_opt": v_opt,
        "non_ala_q": non_ala,
        "L": L, "M": M, "H": H, "A": (L + M) / 2, "B": (M + H) / 2,
    }


def zone_of(price: float, c: dict) -> str:
    # AGENTS.md five-tier rule: midpoints of L/M/H slice the band.
    if price < c["L"]:
        return "deep_discount"
    if price < c["A"]:
        return "conservative"
    if price < c["B"]:
        return "neutral"
    if price <= c["H"]:
        return "optimistic"
    return "stretched"


def implied(v: dict, c: dict, leg: str) -> float:
    """Solve the multiple the market pays for one leg, others held at L."""
    target = v["price"] * v["shares"]
    others = c["nav"] * (1 - v["d_l"]) + c["cash"] - c["burn"] * v["loss_years_l"]
    if leg == "cloud":
        return (target - others - c["base_ecom"] * v["pe_ecom_l"]) / c["base_cloud"]
    return (target - others - c["base_cloud"] * v["ps_cloud_l"]) / c["base_ecom"]


# ---------------------------------------------------------------- main

def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    v, gaps = parse_inputs(md)
    stated = parse_stated(md)
    c = compute(v)

    checks: list[tuple[bool, str]] = []

    # 1. segment identity — the loss leg is defined as the residual, so this
    #    must close exactly (see §3 Formula step 1 / A7).
    seg_sum = v["ebita_aeg_q_cny"] + v["ebita_cloud_q_cny"] + v["ebita_rest_q_cny"]
    checks.append((abs(seg_sum - v["ebita_group_q_cny"]) < 1e6,
                   f"segment identity AEG+cloud+rest = group "
                   f"({seg_sum / YI:.2f} vs {v['ebita_group_q_cny'] / YI:.2f} 亿 CNY)"))
    # ALA is a component of rest (same sign, |ala| <= |rest|)
    checks.append((v["ebita_ala_q_cny"] < 0 and v["ebita_rest_q_cny"] < 0
                   and abs(v["ebita_ala_q_cny"]) <= abs(v["ebita_rest_q_cny"]) + 1e6,
                   f"ALA inside rest (ala={v['ebita_ala_q_cny']/YI:.2f}, "
                   f"rest={v['ebita_rest_q_cny']/YI:.2f} 亿)"))
    checks.append((v["rev_ala_q_cny"] > 0 and v["ala_ps"] > 0,
                   f"ALA V_opt inputs positive (rev={v['rev_ala_q_cny']/YI:.2f}, ps={v['ala_ps']})"))

    # 2. bands and ordering
    for name, band, keys, ascending in (
        ("pe_ecom", PE_ECOM_BAND, "pe_ecom", True),
        ("ps_cloud", PS_CLOUD_BAND, "ps_cloud", True),
        ("loss_years", LOSS_YEARS_BAND, "loss_years", False),
        ("d_nav", D_NAV_BAND, "d", False),
    ):
        vals = [v[f"{keys}_{k}"] for k in SCENARIOS]
        lo, hi = band
        checks.append((all(lo <= x <= hi for x in vals),
                       f"{name} {vals} inside band [{lo}, {hi}]"))
        ordered = vals[0] < vals[1] < vals[2] if ascending else vals[0] > vals[1] > vals[2]
        checks.append((ordered, f"{name} ordered {'L<M<H' if ascending else 'L>M>H'}: {vals}"))
    checks.append((0 < v["tax_rate"] < 0.5, f"tax_rate {v['tax_rate']} in (0, 0.5)"))

    # 3. anchors
    checks.append((c["L"] < c["M"] < c["H"],
                   f"L < M < H ({c['L']:.2f} < {c['M']:.2f} < {c['H']:.2f})"))
    for key in ("L", "M", "H", "A", "B"):
        checks.append((abs(stated[key] - c[key]) <= TOL,
                       f"stated {key}={stated[key]} matches computed {c[key]:.4f}"))
    expected = {round(c[k], 2) for k in ("L", "A", "B", "H")}
    checks.append((stated["table_nums"] == expected,
                   f"zone table boundaries {sorted(stated['table_nums'])} == {sorted(expected)}"))

    checks.append((set(stated["legs"]) == {"L", "M", "H"},
                   f"leg table rows {sorted(stated['legs'])} == ['H', 'L', 'M']"))
    for tag in SCENARIOS:
        row = stated["legs"].get(tag.upper())
        if row is None:
            continue
        got = c["legs"][tag]
        want = [got["ecom"], got["cloud"], got["loss"],
                got["nav"] + got["cash"], sum(got.values())]
        names = ("电商", "云", "亏损腿", "NAV+现金", "合计")
        for name, stated_v, exp in zip(names, row, want):
            checks.append((abs(stated_v - exp) <= TOL,
                           f"leg table {tag.upper()}/{name}: stated {stated_v} "
                           f"vs computed {exp:.4f}"))

    # 4. zone
    z = zone_of(v["price"], c)
    checks.append((z == stated["zone"],
                   f"zone at price {v['price']}: computed `{z}` == stated `{stated['zone']}`"))
    checks.append((abs(stated["V_opt"] - c["V_opt"]) <= TOL,
                   f"stated V_opt={stated['V_opt']} matches computed {c['V_opt']:.4f}"))
    checks.append((stated["p_L"] == 0 and stated["p_H"] == 1,
                   f"p_L/p_H endpoints ({stated['p_L']}/{stated['p_H']})"))
    checks.append((0 <= stated["p_M"] <= 1,
                   f"p_M in [0,1] ({stated['p_M']})"))

    print(f"framework : {FRAMEWORK.name}   formula_id={FORMULA_ID}")
    print(f"segments  : AEG {v['ebita_aeg_q_cny'] / YI:.2f} + cloud "
          f"{v['ebita_cloud_q_cny'] / YI:.2f} + rest {v['ebita_rest_q_cny'] / YI:.2f} "
          f"= {v['ebita_group_q_cny'] / YI:.2f} 亿 CNY/季")
    print(f"  of which ALA {v['ebita_ala_q_cny']/YI:.2f} · non-ALA burn base "
          f"{c['non_ala_q']/YI:.2f} 亿/季")
    print(f"leg bases : ecom {c['base_ecom'] / YI:.1f} · cloud {c['base_cloud'] / YI:.1f} · "
          f"burn/yr {c['burn'] / YI:.1f} · nav {c['nav'] / YI:.1f} · cash {c['cash'] / YI:.1f} 亿 HKD")
    for k in SCENARIOS:
        legs = c["legs"][k]
        print(f"  {k.upper()} per share: " + " ".join(f"{n}={x:+.2f}" for n, x in legs.items())
              + f"  ->  {sum(legs.values()):.2f}")
    print(f"anchors   : L {c['L']:.2f} · M {c['M']:.2f} · H {c['H']:.2f} "
          f"(A {c['A']:.2f} · B {c['B']:.2f})")
    print(f"V_opt     : {c['V_opt']:.2f} HKD  (ALA rev×4×PS {v['ala_ps']:.0f})"
          f"  p={stated['p_L']}/{stated['p_M']}/{stated['p_H']}"
          f"  V_opt/M={c['V_opt']/c['M']:.1%}")
    print(f"zone+V    : L {c['L']+stated['p_L']*c['V_opt']:.2f}"
          f" · M {c['M']+stated['p_M']*c['V_opt']:.2f}"
          f" · H {c['H']+stated['p_H']*c['V_opt']:.2f}")
    print(f"price     : {v['price']} -> zone `{z}`")

    if "eps_fy28e_hkd" in v:
        e = v["eps_fy28e_hkd"]
        print("implied FY28E PE: " + " ".join(
            f"{n} {x / e:.2f}x" for n, x in
            (("price", v["price"]), ("L", c["L"]), ("M", c["M"]), ("H", c["H"]))))

    print(f"market solves for (others at L): ps_cloud={implied(v, c, 'cloud'):.3f} · "
          f"pe_ecom={implied(v, c, 'ecom'):.3f}")

    print("sensitivity (ps_cloud_l, others at L):")
    for ps in (2.5, 3.0, 3.5, v["ps_cloud_l"]):
        alt = compute(dict(v, ps_cloud_l=ps))
        print(f"  ps_cloud_l={ps:.1f}: L={alt['L']:.2f}, zone@{v['price']}="
              f"{zone_of(v['price'], alt)}")

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
