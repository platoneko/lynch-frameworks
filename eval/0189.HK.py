#!/usr/bin/env python3
"""0189.HK (Dongyue Group) valuation eval — recompute anchors from frameworks/0189.HK.md.

frameworks/0189.HK.md is the source of truth; this script re-parses its §3 Inputs
table, recomputes L/M/H / A/B / zone and exits 1 on mismatch.

formula_id: dongyue_quota_sotp_segment_pe_v1

Main ruler: four-leg segment SOTP.  Each reportable segment's operating result
(分部业绩, RMB thousand) is taxed, scaled by the *leg-specific* attributable
ownership ratio (refrigerant + fluoropolymer sit in Dongyue Polymers, 74.06%
owned; organosilicone is the separately A-listed Dongyue Organosilicon, 44.40%
owned), multiplied by a per-leg PE, then attributable net cash is added.  The
refrigerant leg is driven by MEE production quota tonnage x segment result per
quota tonne, because quota is a hard volume cap.  L is additionally floored at
pb_floor x book value per share.

Reporting currency is CNY, the listing currency is HKD: fx_cny_hkd is an
explicit Input and is applied once, at step 4.

Sanity checks beyond the anchor comparison:
  * L < M < H, pe ordering per leg, ownership ratios in (0, 1]
  * the same ownership/tax bridge must reproduce the FY2025 reported profit
    attributable to owners (RMB 1,641,812k) within BRIDGE_TOL

Run:  python3 eval/0189.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "0189.HK.md"
FORMULA_ID = "dongyue_quota_sotp_segment_pe_v1"
TOL = 0.05  # outputs are rounded to 2 decimals
YI = 1e5  # 亿, from RMB thousand

# FY2025 audited reconciliation targets (2025 annual report, RMB thousand).
FY25 = {
    "res_ref": 2287697.0,
    "res_poly": 356642.0,
    "res_sil": -51711.0,
    "res_oth": -15794.0,  # 二氯甲烷及烧碱 + 其他业务 + 非分部项目
    "tax": 0.1526,  # 393,241 / 2,576,834
    "attributable": 1641812.0,
}
BRIDGE_TOL = 0.03  # the framework claims -0.9%; fail if the bridge drifts past 3%

REQUIRED = [
    "price",
    "shares",
    "fx_cny_hkd",
    "bvps_cny",
    "tax",
    "own_poly",
    "own_sil",
    "own_oth",
    "quota_t",
    "upt_l",
    "upt_m",
    "upt_h",
    "res_poly_l",
    "res_poly_m",
    "res_poly_h",
    "res_sil_l",
    "res_sil_m",
    "res_sil_h",
    "res_oth_l",
    "res_oth_m",
    "res_oth_h",
    "pe_ref_l",
    "pe_ref_m",
    "pe_ref_h",
    "pe_poly_l",
    "pe_poly_m",
    "pe_poly_h",
    "pe_sil_l",
    "pe_sil_m",
    "pe_sil_h",
    "pe_oth",
    "net_cash",
    "cash_attrib",
    "pb_floor",
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
        if key in ("字段名",) or raw in ("取值",) or set(key) <= set("-: "):
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


def first_float(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def attributable_np(
    res_ref: float,
    res_poly: float,
    res_sil: float,
    res_oth: float,
    tax: float,
    own_poly: float,
    own_sil: float,
    own_oth: float,
) -> tuple[float, float, float, float]:
    """Per-leg after-tax profit attributable to owners of the Company (RMB'000)."""
    k = 1.0 - tax
    return (
        res_ref * own_poly * k,
        res_poly * own_poly * k,
        res_sil * own_sil * k,
        res_oth * own_oth * k,
    )


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

    # --- structural sanity on the inputs themselves -------------------------
    for name in ("own_poly", "own_sil", "own_oth", "cash_attrib"):
        if not 0.0 < inp[name] <= 1.0:
            errors.append(f"{name}={inp[name]} outside (0, 1]")
    if not 0.0 <= inp["tax"] < 0.5:
        errors.append(f"tax={inp['tax']} implausible")
    if inp["quota_t"] <= 0:
        errors.append(f"quota_t={inp['quota_t']} must be positive")
    for leg in ("ref", "poly", "sil"):
        lo, mid, hi = (inp[f"pe_{leg}_{s}"] for s in "lmh")
        if not lo < mid < hi:
            errors.append(f"pe_{leg} not increasing: {lo}/{mid}/{hi}")
    if not inp["upt_l"] < inp["upt_m"] < inp["upt_h"]:
        errors.append(
            f"upt not increasing: {inp['upt_l']}/{inp['upt_m']}/{inp['upt_h']}"
        )

    # --- FY2025 bridge: does leg-ownership reproduce reported attributable? --
    bridge_legs = attributable_np(
        FY25["res_ref"],
        FY25["res_poly"],
        FY25["res_sil"],
        FY25["res_oth"],
        FY25["tax"],
        inp["own_poly"],
        inp["own_sil"],
        inp["own_oth"],
    )
    bridge = sum(bridge_legs)
    bridge_err = bridge / FY25["attributable"] - 1.0
    if abs(bridge_err) > BRIDGE_TOL:
        errors.append(
            f"FY2025 bridge {bridge:,.0f} vs reported {FY25['attributable']:,.0f} "
            f"({bridge_err:+.2%}) exceeds {BRIDGE_TOL:.0%}"
        )

    # --- scenarios ----------------------------------------------------------
    def scenario(x: str) -> tuple[float, float, float]:
        """(refrigerant segment result RMB'000, attributable NP RMB'000, HKD/share)."""
        res_ref = inp["quota_t"] * inp[f"upt_{x}"] / 1000.0
        np_ref, np_poly, np_sil, np_oth = attributable_np(
            res_ref,
            inp[f"res_poly_{x}"],
            inp[f"res_sil_{x}"],
            inp[f"res_oth_{x}"],
            inp["tax"],
            inp["own_poly"],
            inp["own_sil"],
            inp["own_oth"],
        )
        ev = (
            np_ref * inp[f"pe_ref_{x}"]
            + np_poly * inp[f"pe_poly_{x}"]
            + np_sil * inp[f"pe_sil_{x}"]
            + np_oth * inp["pe_oth"]
            + inp["net_cash"] * inp["cash_attrib"]
        )
        per_share = ev * inp["fx_cny_hkd"] / (inp["shares"] / 1000.0)
        return res_ref, np_ref + np_poly + np_sil + np_oth, per_share

    res_ref_l, np_l, v_l = scenario("l")
    res_ref_m, np_m, v_m = scenario("m")
    res_ref_h, np_h, v_h = scenario("h")

    floor = inp["pb_floor"] * inp["bvps_cny"] * inp["fx_cny_hkd"]
    L = max(v_l, floor)  # the asset floor exists today -> not a scenario
    M = v_m
    H = v_h
    A = (L + M) / 2
    B = (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}")

    # --- compare against the stated Outputs ---------------------------------
    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    triples = re.findall(r"L = \*\*[0-9.]+\*\* · M = \*\*[0-9.]+\*\* · H = \*\*[0-9.]+\*\*", out_sec)
    if len(triples) != 1:
        errors.append(f"### Outputs must state the L/M/H triple exactly once, found {len(triples)}")

    stated = {
        "L": first_float(r"L = \*\*([0-9.]+)\*\*", out_sec),
        "M": first_float(r"M = \*\*([0-9.]+)\*\*", out_sec),
        "H": first_float(r"H = \*\*([0-9.]+)\*\*", out_sec),
        "A": first_float(r"A = \*\*([0-9.]+)\*\*", out_sec),
        "B": first_float(r"B = \*\*([0-9.]+)\*\*", out_sec),
    }
    for k, v in {"L": L, "M": M, "H": H, "A": A, "B": B}.items():
        s = stated.get(k)
        if s is None:
            errors.append(f"stated {k} not found in ### Outputs")
        elif abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")

    zm = re.search(r"zone = \*\*`([a-z_]+)`\*\*", out_sec)
    stated_zone = zm.group(1) if zm else None
    if stated_zone != zone:
        errors.append(f"zone: stated {stated_zone} vs recomputed {zone}")

    # --- report -------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(
        f"own poly={inp['own_poly']:.4f} sil={inp['own_sil']:.4f} oth={inp['own_oth']:.2f}"
        f"  tax={inp['tax']:.0%}  quota_t={inp['quota_t']:,.0f}"
    )
    print(
        f"FY2025 bridge={bridge:,.0f} vs reported {FY25['attributable']:,.0f} "
        f"({bridge_err:+.2%}, tol {BRIDGE_TOL:.0%})"
    )
    print(
        f"res_ref(亿CNY)={res_ref_l / YI:.2f}/{res_ref_m / YI:.2f}/{res_ref_h / YI:.2f}"
        f"  attribNP(亿CNY)={np_l / YI:.2f}/{np_m / YI:.2f}/{np_h / YI:.2f}"
    )
    eps_hkd = [n / (inp["shares"] / 1000.0) * inp["fx_cny_hkd"] for n in (np_l, np_m, np_h)]
    print(f"attribEPS(HKD)={eps_hkd[0]:.3f}/{eps_hkd[1]:.3f}/{eps_hkd[2]:.3f}")
    cash_ps = inp["net_cash"] * inp["cash_attrib"] * inp["fx_cny_hkd"] / (inp["shares"] / 1000.0)
    print(
        f"V(earnings)={v_l:.2f}/{v_m:.2f}/{v_h:.2f}  floor(pb*bvps*fx)={floor:.2f}"
        f"  attrib net cash/share={cash_ps:.2f}"
    )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
