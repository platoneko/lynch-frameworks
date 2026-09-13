#!/usr/bin/env python3
"""0700.HK — Tencent SOTP v4: dom / intl / ads / FBS PE + NAV (1-d) + net cash.

formula_id = 0700_sotp_dom_intl_ads_fbs_nav_v4

Truth source: frameworks/0700.HK.md §3.
v4: pe_L sector-calibrated (NetEase/Alibaba forward parity + quality premium);
    no spot reverse-fit.

Four operating legs share one FY26E group Non-IFRS EPS, split by revenue
weight and each given its own PE; the investment book enters as NAV x (1 - d)
and net cash at book.  All three scenarios use the same numerator — only the
multiples and the NAV discount move.

Beyond the anchor comparison this script also re-derives the per-leg
contribution table and the five-zone boundary table, so a hand-edited cell in
either one fails the run rather than sitting there unnoticed.

Run:  python3 eval/0700.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "0700.HK.md"
FORMULA_ID = "0700_sotp_dom_intl_ads_fbs_nav_v4"
TOL = 0.05  # anchors stated to 1 decimal
LEG_TOL = 0.1  # per-leg table is rounded to 1 decimal

LEGS = ("dom", "intl", "ads", "fbs")

REQUIRED = [
    "price", "shares", "fx", "eps_fy26e_cny",
    "w_dom", "w_intl", "w_ads", "w_fbs",
    "pe_dom_l", "pe_dom_m", "pe_dom_h",
    "pe_intl_l", "pe_intl_m", "pe_intl_h",
    "pe_ads_l", "pe_ads_m", "pe_ads_h",
    "pe_fbs_l", "pe_fbs_m", "pe_fbs_h",
    "nav_hkd", "d_l", "d_m", "d_h", "net_cash_cny",
]


def parse_inputs(md: str) -> dict[str, float]:
    """Parse §3 Inputs table: | field | value | meaning | as-of |."""
    out: dict[str, float] = {}
    in_inputs = False
    for line in md.splitlines():
        if line.startswith("### Inputs"):
            in_inputs = True
            continue
        if in_inputs and line.startswith("### "):
            break
        if not in_inputs or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        key, raw = cells[0], cells[1]
        if key == "字段名" or raw == "取值" or set(key) <= set("- :"):
            continue
        if raw in ("待补", "", "—"):
            continue
        try:
            out[key] = float(raw.replace(",", ""))
        except ValueError:
            continue
    return out


def zone_of(price: float, L: float, M: float, H: float) -> str:
    A = (L + M) / 2
    B = (M + H) / 2
    if price < L:
        return "deep_discount"
    if price < A:
        return "conservative"
    if price < B:
        return "neutral"
    if price <= H:
        return "optimistic"
    return "stretched"


def scenario(inp: dict[str, float], tag: str) -> dict[str, float]:
    """One scenario -> per-leg HKD/share contributions and the anchor."""
    eps_hkd = inp["eps_fy26e_cny"] * inp["fx"]  # group EPS restated in HKD
    legs = {leg: eps_hkd * inp[f"w_{leg}"] * inp[f"pe_{leg}_{tag}"] for leg in LEGS}
    ops = sum(legs.values())
    nav = inp["nav_hkd"] * (1.0 - inp[f"d_{tag}"]) / inp["shares"]
    cash = inp["net_cash_cny"] * inp["fx"] / inp["shares"]
    out = dict(legs)
    out.update(ops=ops, nav=nav, cash=cash, anchor=ops + nav + cash)
    return out


def stated_leg_table(md: str) -> dict[str, list[float]]:
    """Rows of the 分腿贡献 table: 档 | 国内 | 国际 | 广告 | FBS | 经营合计 | NAV | 净现金 | 合计."""
    out: dict[str, list[float]] = {}
    for line in md.splitlines():
        if not line.startswith("| L ") and not line.startswith("| M ") and not line.startswith("| H "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 9:
            continue
        nums: list[float] = []
        for c in cells[1:9]:
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)", c.replace("**", ""))
            if not m:
                break
            nums.append(float(m.group(1)))
        if len(nums) == 8:
            out[cells[0]] = nums
    return out


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    missing = [k for k in REQUIRED if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1

    errors: list[str] = []

    # --- ladder sanity ------------------------------------------------------
    w_sum = sum(inp[f"w_{leg}"] for leg in LEGS)
    if abs(w_sum - 1.0) > 1e-3:
        errors.append(f"leg weights sum to {w_sum:.4f}, not 1")
    for leg in LEGS:
        lo, mid, hi = (inp[f"pe_{leg}_{t}"] for t in ("l", "m", "h"))
        if not (lo < mid < hi):
            errors.append(f"pe_{leg} band violated: {lo}/{mid}/{hi}")
    # A wider NAV discount is the harsher scenario, so d must fall L -> H.
    if not (inp["d_l"] > inp["d_m"] > inp["d_h"]):
        errors.append(f"NAV discount must fall L>M>H: {inp['d_l']}/{inp['d_m']}/{inp['d_h']}")
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    S = {t: scenario(inp, t) for t in ("l", "m", "h")}
    L, M, H = (S[t]["anchor"] for t in ("l", "m", "h"))
    A = (L + M) / 2
    B = (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1

    # --- stated anchors and cut points --------------------------------------
    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    for key, val in (("L", L), ("M", M), ("H", H)):
        m = re.search(rf"{key} = \*\*([0-9.]+)\*\*", out_sec)
        if not m:
            errors.append(f"stated {key} not found")
        elif abs(float(m.group(1)) - val) > TOL:
            errors.append(f"{key}: stated {m.group(1)} vs recomputed {val:.4f}")
    for key, val in (("A", A), ("B", B)):
        m = re.search(rf"{key} = \**([0-9.]+)", out_sec)
        if not m:
            errors.append(f"stated cut point {key} not found")
        elif abs(float(m.group(1)) - val) > TOL:
            errors.append(f"{key}: stated {m.group(1)} vs recomputed {val:.4f}")

    # --- per-leg contribution table -----------------------------------------
    stated_legs = stated_leg_table(out_sec)
    for tag in ("L", "M", "H"):
        row = stated_legs.get(tag)
        s = S[tag.lower()]
        if row is None:
            errors.append(f"leg table row {tag} not found")
            continue
        want = [s["dom"], s["intl"], s["ads"], s["fbs"], s["ops"], s["nav"], s["cash"], s["anchor"]]
        names = ("国内", "国际", "广告", "FBS", "经营合计", "NAV", "净现金", "合计")
        for name, got, exp in zip(names, row, want):
            if abs(got - exp) > LEG_TOL:
                errors.append(f"leg table {tag}/{name}: stated {got} vs recomputed {exp:.2f}")

    # --- five-zone boundary table -------------------------------------------
    # Only the price-interval column (index 2) carries boundaries; 场景 must
    # not leak narrative figures into the check.
    zone_nums = set()
    for line in out_sec.splitlines():
        if line.startswith("| `") and "|" in line:
            cells = line.strip().strip("|").split("|")
            if len(cells) >= 3:
                zone_nums.update(
                    float(x) for x in re.findall(r"([0-9]+\.[0-9]+)", cells[2])
                )
    for name, val in (("L", L), ("A", A), ("B", B), ("H", H)):
        if not any(abs(val - z) <= TOL for z in zone_nums):
            errors.append(f"zone table missing boundary {name}={val:.1f}")

    # --- report -------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"{'档':<3}{'国内':>9}{'国际':>9}{'广告':>9}{'FBS':>9}{'经营合计':>11}{'NAV':>9}{'净现金':>9}{'合计':>10}")
    for tag in ("l", "m", "h"):
        s = S[tag]
        print(
            f"{tag.upper():<3}{s['dom']:9.1f}{s['intl']:9.1f}{s['ads']:9.1f}{s['fbs']:9.1f}"
            f"{s['ops']:11.1f}{s['nav']:9.1f}{s['cash']:9.1f}{s['anchor']:10.1f}"
        )
    eps_hkd = inp["eps_fy26e_cny"] * inp["fx"]
    for tag in ("l", "m", "h"):
        blended = S[tag]["ops"] / eps_hkd
        print(f"  {tag.upper()} blended operating pe = {blended:.2f}x")
    print(f"L={L:.1f} M={M:.1f} H={H:.1f} A={A:.1f} B={B:.1f}")
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
