#!/usr/bin/env python3
"""NOK.US (Nokia) valuation eval — recompute anchors from frameworks/NOK.US.md.

frameworks/NOK.US.md stays the human-facing source of truth for inputs; this
script is the enforcement layer that keeps its number chain honest:

    parse §3 Inputs table -> rebuild every SOTP leg -> L/M/H, A/B, zone
                          -> diff against the numbers printed in §3 Outputs
                          -> exit 1 on any mismatch or invariant violation

formula_id: nok_sotp_ni2028_ts_annuity_ran_v1

Main ruler (SOTP, modelled in EUR, reported in USD per ADR):
  * Network Infrastructure — the only leg carrying the L/M/H scenario, and it
    carries it in the NUMERATOR (2028E EBIT delivery), not in the multiple,
    because the downside risk is "the 2028 profit never arrives".  Fixed
    22x EV/EBIT, discounted by disc_ni back from FY2028.
  * Technology Standards (patent licensing annuity) — run-rate sales x margin,
    current-year basis, NOT discounted, multiple band 9/12/16x.
  * MI-core (Radio Networks + Core Software) — current-year EBIT derived from
    the group guidance identity, NOT discounted, multiple band 5/7/10x.
  * Corporate unallocated capitalised at 10x (negative -> deduction).
  * Closing items summed from components (net cash, pension credited at 0,
    one year of restructuring cash outflow).  No hand-written total.
  * EUR per share -> USD per ADR via fx_eur_usd x adr_ratio.

Hard checks mirror framework §3 校验步骤:
  1. segment EBIT identity holds AND group value sits inside FY2026 guidance
  2. multiple/scenario ordering, 0 < disc_ni <= 1
  3. L < M < H and stated anchors / cut-points / zone-table bounds match (±0.05)
  4. zone implied by price matches the zone printed in Outputs

Run after every edit of frameworks/NOK.US.md:  python3 eval/NOK.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "NOK.US.md"
FORMULA_ID = "nok_sotp_ni2028_ts_annuity_ran_v1"

TOL = 0.05  # stated anchors are rounded to 2 decimals
EBIT_TOL = 5e6  # segment identity slack, EUR (inputs are quoted to 0.005bn)

# Closing items (A8): adj is always the sum of these — the MD carries no
# hand-written total that could drift.
CLOSING_COMPONENTS = ("net_cash_eur", "pension_net_eur", "restructuring_eur")

SCENARIOS = ("l", "m", "h")

REQUIRED = (
    "price", "fx_eur_usd", "adr_ratio", "shares",
    "ebit_group_fy26", "guide_ebit_low", "guide_ebit_high",
    "ebit_ni_fy26", "ts_sales_rr", "ts_margin",
    "ebit_mi_core_fy26", "ebit_pb_fy26", "ebit_corp_fy26",
    "ebit_ni_2028_l", "ebit_ni_2028_m", "ebit_ni_2028_h",
    "ev_ebit_ni", "disc_ni",
    "ev_ebit_ts_l", "ev_ebit_ts_m", "ev_ebit_ts_h",
    "ev_ebit_mi_l", "ev_ebit_mi_m", "ev_ebit_mi_h",
    "ev_ebit_corp",
) + CLOSING_COMPONENTS


# ---------------------------------------------------------------- parsing

def parse_inputs(text: str) -> tuple[dict, list[str]]:
    """Parse the §3 Inputs markdown table. 待补 -> None (reported as gap)."""
    section = text.split("### Inputs", 1)[1].split("### Formula", 1)[0]
    inputs: dict[str, float | None] = {}
    gaps: list[str] = []
    for line in section.splitlines():
        m = re.match(r"\|\s*([a-z][a-z0-9_]*)\s*\|\s*([^|]+)\|", line)
        if not m:
            continue
        field, raw = m.group(1), m.group(2).strip()
        if raw.startswith("待补"):
            inputs[field] = None
            gaps.append(field)
            continue
        num = re.match(r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?", raw)
        if num:
            inputs[field] = float(num.group(0))
    missing = [f for f in REQUIRED if inputs.get(f) is None]
    if missing:
        sys.exit(f"FATAL: required inputs missing/待补 in {FRAMEWORK}: {missing}")
    return inputs, gaps


def parse_stated(text: str) -> dict:
    """Parse anchors, cut-points, zone-table bounds and zone id from §3 Outputs."""
    out = text.split("### Outputs", 1)[1].split("## 4.", 1)[0]
    anchors = re.search(
        r"L = \*\*([\d.]+)\*\* · M = \*\*([\d.]+)\*\* · H = \*\*([\d.]+)\*\*", out)
    cuts = re.search(r"A = \*\*([\d.]+)\*\* · B = \*\*([\d.]+)\*\*", out)
    zone = re.search(r"zone = \*\*`(\w+)`\*\*", out)
    if not (anchors and cuts and zone):
        sys.exit("FATAL: cannot parse Outputs section (anchors/cuts/zone line)")
    # Only the price-interval column (index 2) carries boundary numbers; the
    # scenario column holds narrative figures that must not enter table_nums.
    table = "\n".join(
        l.strip().strip("|").split("|")[2]
        for l in out.splitlines() if l.lstrip().startswith("|") and "`" in l)
    return {
        "L": float(anchors.group(1)), "M": float(anchors.group(2)),
        "H": float(anchors.group(3)),
        "A": float(cuts.group(1)), "B": float(cuts.group(2)),
        "zone": zone.group(1),
        "table_nums": {float(x) for x in re.findall(r"\d+(?:\.\d+)?", table)},
    }


# ---------------------------------------------------------------- computation

def compute(v: dict) -> dict:
    """Recompute the full chain per framework §3 Formula (source of truth: MD)."""
    ebit_ts = v["ts_sales_rr"] * v["ts_margin"]

    legs_sum = (v["ebit_ni_fy26"] + ebit_ts + v["ebit_mi_core_fy26"]
                + v["ebit_pb_fy26"] + v["ebit_corp_fy26"])

    ev_corp = v["ebit_corp_fy26"] * v["ev_ebit_corp"]
    adj = sum(v[k] for k in CLOSING_COMPONENTS)
    unit = v["fx_eur_usd"] * v["adr_ratio"] / v["shares"]  # EUR total -> USD/ADR

    ev_ni, ev_ts, ev_mi, anchors = {}, {}, {}, {}
    for k in SCENARIOS:
        # NI: scenario lives in the numerator (delivery), multiple is fixed.
        ev_ni[k] = v[f"ebit_ni_2028_{k}"] * v["ev_ebit_ni"] * v["disc_ni"]
        ev_ts[k] = ebit_ts * v[f"ev_ebit_ts_{k}"]
        ev_mi[k] = v["ebit_mi_core_fy26"] * v[f"ev_ebit_mi_{k}"]
        ev = ev_ni[k] + ev_ts[k] + ev_mi[k] + ev_corp
        anchors[k.upper()] = (ev + adj) * unit

    L, M, H = anchors["L"], anchors["M"], anchors["H"]
    return {
        "ebit_ts": ebit_ts, "legs_sum": legs_sum,
        "ev_ni": ev_ni, "ev_ts": ev_ts, "ev_mi": ev_mi, "ev_corp": ev_corp,
        "adj": adj, "unit": unit,
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


def implied_ni_2028(target: float, v: dict, c: dict) -> float:
    """Solve NI 2028E EBIT from a target ADR price, holding TS/MI at M multiples.

    This is the framework's single most informative read-out: how much of the
    AI order book the market is underwriting.  Because the other legs stay at
    their M multiples, H itself implies >100% delivery.
    """
    ev_target = target / c["unit"] - c["adj"]
    rest = c["ev_ts"]["m"] + c["ev_mi"]["m"] + c["ev_corp"]
    return (ev_target - rest) / (v["ev_ebit_ni"] * v["disc_ni"])


def delivery_pct(ebit_ni: float, v: dict) -> float:
    span = v["ebit_ni_2028_h"] - v["ebit_ni_2028_m"]
    return (ebit_ni - v["ebit_ni_2028_m"]) / span


# ---------------------------------------------------------------- main

def main() -> None:
    text = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in text:
        sys.exit(f"FATAL: formula_id {FORMULA_ID} missing from {FRAMEWORK.name}")

    v, gaps = parse_inputs(text)
    stated = parse_stated(text)
    c = compute(v)
    bn = 1e9

    checks: list[tuple[bool, str]] = []

    # 1. segment identity + guidance envelope (framework §3 校验步骤 1)
    drift = c["legs_sum"] - v["ebit_group_fy26"]
    checks.append((abs(drift) <= EBIT_TOL,
                   f"segment EBIT identity: legs {c['legs_sum'] / bn:.4f}bn "
                   f"== group {v['ebit_group_fy26'] / bn:.4f}bn (drift {drift / 1e6:+.1f}M)"))
    checks.append((v["guide_ebit_low"] <= v["ebit_group_fy26"] <= v["guide_ebit_high"],
                   f"group EBIT {v['ebit_group_fy26'] / bn:.2f}bn inside FY26 guidance "
                   f"[{v['guide_ebit_low'] / bn:.1f}, {v['guide_ebit_high'] / bn:.1f}]bn"))

    # 2. ordering / policy invariants
    checks.append((v["ebit_ni_2028_l"] < v["ebit_ni_2028_m"] < v["ebit_ni_2028_h"],
                   "NI 2028E EBIT scenarios ordered l < m < h"))
    for leg in ("ts", "mi"):
        lo, mid, hi = (v[f"ev_ebit_{leg}_{k}"] for k in SCENARIOS)
        checks.append((lo < mid < hi,
                       f"ev_ebit_{leg} band ordered {lo} < {mid} < {hi}"))
    checks.append((0 < v["disc_ni"] <= 1, f"disc_ni {v['disc_ni']} in (0, 1]"))
    checks.append((v["ts_margin"] > 0 and v["ebit_mi_core_fy26"] > 0,
                   "ts_margin > 0 and MI-core residual EBIT > 0 "
                   f"({v['ebit_mi_core_fy26'] / bn:.3f}bn)"))
    checks.append((v["ebit_corp_fy26"] < 0,
                   f"corporate unallocated is a cost ({v['ebit_corp_fy26'] / bn:+.2f}bn)"))

    # 3. anchors vs Outputs
    checks.append((c["L"] < c["M"] < c["H"],
                   f"L < M < H ({c['L']:.2f} < {c['M']:.2f} < {c['H']:.2f})"))
    for key in ("L", "M", "H", "A", "B"):
        checks.append((abs(stated[key] - c[key]) <= TOL,
                       f"stated {key}={stated[key]} matches computed {c[key]:.4f}"))
    expected_bounds = {round(c[k], 2) for k in ("L", "A", "B", "H")}
    checks.append((stated["table_nums"] == expected_bounds,
                   f"zone table bounds {sorted(stated['table_nums'])} "
                   f"== {sorted(expected_bounds)}"))

    # 4. zone
    z = zone_of(v["price"], c)
    checks.append((z == stated["zone"],
                   f"zone at price {v['price']}: computed `{z}` == stated `{stated['zone']}`"))

    # ------------------------------------------------------------ report
    print(f"framework : {FRAMEWORK.name}   formula_id={FORMULA_ID}")
    print(f"segments  : NI(FY26E) {v['ebit_ni_fy26'] / bn:.3f} + TS {c['ebit_ts'] / bn:.3f} "
          f"+ MI-core {v['ebit_mi_core_fy26'] / bn:.3f} + PB {v['ebit_pb_fy26'] / bn:.3f} "
          f"+ corp {v['ebit_corp_fy26'] / bn:+.3f} = {c['legs_sum'] / bn:.3f}bn EUR")
    print(f"NI leg    : 2028E EBIT {v['ebit_ni_2028_l'] / bn:.2f}/{v['ebit_ni_2028_m'] / bn:.2f}/"
          f"{v['ebit_ni_2028_h'] / bn:.2f}bn x {v['ev_ebit_ni']:g}x x df {v['disc_ni']:g}"
          f"  ->  EV " + " / ".join(f"{c['ev_ni'][k] / bn:.2f}" for k in SCENARIOS) + "bn")
    print("TS leg    : EV " + " / ".join(f"{c['ev_ts'][k] / bn:.2f}" for k in SCENARIOS)
          + "bn   MI-core leg: EV "
          + " / ".join(f"{c['ev_mi'][k] / bn:.2f}" for k in SCENARIOS)
          + f"bn   corp: {c['ev_corp'] / bn:+.2f}bn")
    print(f"closing   : {c['adj'] / bn:+.3f}bn = "
          + " ".join(f"{k}={v[k] / bn:+.3f}" for k in CLOSING_COMPONENTS))
    for k in SCENARIOS:
        ev = c["ev_ni"][k] + c["ev_ts"][k] + c["ev_mi"][k] + c["ev_corp"]
        print(f"  {k.upper()}: EV {ev / bn:6.2f}bn  equity {(ev + c['adj']) / bn:6.2f}bn"
              f"  EUR/sh {(ev + c['adj']) / v['shares']:6.3f}"
              f"  USD/ADR {c[k.upper()]:6.2f}"
              f"  | implied group EV/EBIT(FY26E) {ev / v['ebit_group_fy26']:5.2f}x")
    print(f"anchors   : L {c['L']:.2f} · M {c['M']:.2f} · H {c['H']:.2f}"
          f"  (A {c['A']:.2f} · B {c['B']:.2f})")

    print("\nimplied NI 2028E EBIT (TS/MI held at M multiples):")
    for label, px in (("price", v["price"]), ("A", c["A"]), ("B", c["B"]),
                      ("sell-side TP mean 14.96", 14.96), ("52w high 16.85", 16.85)):
        e = implied_ni_2028(px, v, c)
        print(f"  {label:<24} ${px:6.2f} -> {e / bn:5.2f}bn EUR "
              f"(delivery {delivery_pct(e, v):+7.1%})")

    print("\nsensitivity:")
    for m in (0.60, v["ts_margin"], 0.78):
        c2 = compute(dict(v, ts_margin=m,
                          ebit_mi_core_fy26=v["ebit_group_fy26"] - v["ebit_ni_fy26"]
                          - v["ts_sales_rr"] * m - v["ebit_pb_fy26"] - v["ebit_corp_fy26"]))
        print(f"  ts_margin {m:.2f} (MI-core absorbs): "
              f"L {c2['L']:.2f} M {c2['M']:.2f} H {c2['H']:.2f}")
    for fx in (1.14, v["fx_eur_usd"]):
        c2 = compute(dict(v, fx_eur_usd=fx))
        print(f"  fx_eur_usd {fx:.4f}: L {c2['L']:.2f} M {c2['M']:.2f} H {c2['H']:.2f}"
              f"  zone@{v['price']} = {zone_of(v['price'], c2)}")
    c2 = compute(dict(v, shares=5.8019e9))
    print(f"  diluted shares 5.8019e9: L {c2['L']:.2f} M {c2['M']:.2f} H {c2['H']:.2f}")
    c2 = compute(dict(v, ev_ebit_ni=30))
    print(f"  ev_ebit_ni 30x (BofA): L {c2['L']:.2f} M {c2['M']:.2f} H {c2['H']:.2f}"
          f"  zone@{v['price']} = {zone_of(v['price'], c2)}")

    if gaps:
        print(f"\ngaps (待补, not consumed yet): {', '.join(gaps)}")

    print("\nchecks:")
    failed = False
    for ok, label in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        failed |= not ok
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
