#!/usr/bin/env python3
"""0189.HK (Dongyue Group) valuation eval — recompute anchors from frameworks/0189.HK.md.

frameworks/0189.HK.md is the source of truth; this script re-parses its §3 Inputs
table, recomputes L/M/H / A/B / zone and exits 1 on mismatch.

formula_id: dongyue_quota_sotp_actual_year_flat_v2

Main ruler: four-leg segment SOTP whose three scenarios are **three actually
observed operating years** (L=FY2024, M=FY2025, H=26H1 annualised, see A22).
Every leg takes the *same* year's reported segment result in a given tier, so the
inter-leg correlation structure is inherited from history rather than assumed.
The one exception is the by-product leg (A8): its "other operations" component
carries a property-development business whose FY2024/FY2025 losses were majority
one-off impairments now near exhaustion (completed properties for sale down to
RMB 6,109k; goodwill down to RMB 143,097k), so it is rebuilt as
recurring + impairment-scenario instead of the reported figure.

Each segment result is taxed, scaled by the *leg-specific* attributable ownership
ratio (refrigerant + fluoropolymer sit in Dongyue Polymers, 74.06% owned;
organosilicone is the separately A-listed Dongyue Organosilicon, 44.40% owned),
multiplied by a **flat** per-leg multiple, then attributable net cash is added.
Multiples do not vary by tier: this is a `cyclical` name whose numerators already
carry the cycle, and two legs go negative in some tier (organosilicone at M, the
by-product leg at H), which would make tiered multiples reward bigger losses.

Reporting currency is CNY, the listing currency is HKD: fx_cny_hkd is an
explicit Input and is applied once, at step 5.

Sanity checks beyond the anchor comparison:
  * L < M < H on the *total* only — individual legs are allowed to be
    non-monotonic across tiers, which is the point of the A22 construction
  * the same ownership/tax bridge must reproduce the FY2025 reported profit
    attributable to owners (RMB 1,641,812k) within BRIDGE_TOL
  * SAME-SOURCE: every tier's per-leg numerator must equal the reported figure
    for that tier's year (A22) — silently swapping in an extrapolation fails
  * PERFECT-CORRELATION GUARD: the L tier's segment total must not fall below
    FY2023's actual total (650,645). Taking each leg's own historical minimum
    would sum to 55,421 — a world that never happened (A22)

Run:  python3 eval/0189.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "0189.HK.md"
FORMULA_ID = "dongyue_quota_sotp_actual_year_flat_v2"
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

# A22 same-source anchors: reported segment results per tier-year (RMB thousand),
# straight from the FY2025 annual report / 2026 interim segment tables.
TIER_YEAR = {"l": "FY2024", "m": "FY2025", "h": "26H1 annualised"}
REPORTED = {
    "l": {"ref": 806356.0, "poly": 508088.0, "sil": 101668.0, "dcm": 372161.0},
    "m": {"ref": 2287697.0, "poly": 356642.0, "sil": -51711.0, "dcm": 358053.0},
    "h": {"ref": 2492028.0, "poly": 877146.0, "sil": 471612.0, "dcm": 119206.0},
}
SAME_SOURCE_TOL = 0.001  # upt_* is a quotient, so allow rounding at the 5th digit

# A22 perfect-correlation guard.
FY23_SEGMENT_TOTAL = 650645.0  # worst year actually observed
LEGWISE_MIN_SUM = 55421.0  # sum of each leg's own historical low — never happened

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
    "dcm_l",
    "dcm_m",
    "dcm_h",
    "oth_recur",
    "oth_imp_l",
    "oth_imp_m",
    "oth_imp_h",
    "nonseg",
    "pe_ref",
    "pe_poly",
    "pe_sil",
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

    # Multiples are FLAT by construction (A9/A10). There is deliberately no
    # ordering check here: tiered multiples would double-count the cycle for a
    # `cyclical` name and would reward bigger losses on the legs that go
    # negative. Guard the invariant that actually matters instead.
    for leg in ("ref", "poly", "sil", "oth"):
        if inp[f"pe_{leg}"] <= 0:
            errors.append(f"pe_{leg}={inp[f'pe_{leg}']} must be positive")
    if f"pe_ref_l" in inp or "pe_ref_h" in inp:
        errors.append("tiered pe_* inputs reintroduced — A10 requires flat multiples")

    # The refrigerant leg is the one that IS monotonic (quota volume is fixed,
    # so unit economics carry the tier). The other legs are allowed to invert.
    if not inp["upt_l"] < inp["upt_m"] < inp["upt_h"]:
        errors.append(
            f"upt not increasing: {inp['upt_l']}/{inp['upt_m']}/{inp['upt_h']}"
        )

    # --- A22 same-source check: each tier must be its year's reported figures --
    for x in "lmh":
        got_ref = inp["quota_t"] * inp[f"upt_{x}"] / 1000.0
        checks = {
            "ref": (got_ref, REPORTED[x]["ref"]),
            "poly": (inp[f"res_poly_{x}"], REPORTED[x]["poly"]),
            "sil": (inp[f"res_sil_{x}"], REPORTED[x]["sil"]),
            "dcm": (inp[f"dcm_{x}"], REPORTED[x]["dcm"]),
        }
        for leg, (got, want) in checks.items():
            denom = max(abs(want), 1.0)
            if abs(got - want) / denom > SAME_SOURCE_TOL:
                errors.append(
                    f"A22 same-source: {x.upper()}/{leg} = {got:,.0f} but "
                    f"{TIER_YEAR[x]} reported {want:,.0f}"
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
    def res_oth_of(x: str) -> float:
        """By-product leg (A8): dichloromethane + recurring other ops + impairment."""
        return inp[f"dcm_{x}"] + inp["oth_recur"] + inp[f"oth_imp_{x}"] + inp["nonseg"]

    def scenario(x: str) -> tuple[float, float, float, float]:
        """(refrigerant result, segment total, attributable NP, HKD/share) RMB'000."""
        res_ref = inp["quota_t"] * inp[f"upt_{x}"] / 1000.0
        res_oth = res_oth_of(x)
        np_ref, np_poly, np_sil, np_oth = attributable_np(
            res_ref,
            inp[f"res_poly_{x}"],
            inp[f"res_sil_{x}"],
            res_oth,
            inp["tax"],
            inp["own_poly"],
            inp["own_sil"],
            inp["own_oth"],
        )
        ev = (
            np_ref * inp["pe_ref"]
            + np_poly * inp["pe_poly"]
            + np_sil * inp["pe_sil"]
            + np_oth * inp["pe_oth"]
            + inp["net_cash"] * inp["cash_attrib"]
        )
        # Segment total excludes non-segment items, to compare with reported totals.
        seg_total = (
            res_ref
            + inp[f"res_poly_{x}"]
            + inp[f"res_sil_{x}"]
            + inp[f"dcm_{x}"]
            + inp["oth_recur"]
            + inp[f"oth_imp_{x}"]
        )
        per_share = ev * inp["fx_cny_hkd"] / (inp["shares"] / 1000.0)
        return res_ref, seg_total, np_ref + np_poly + np_sil + np_oth, per_share

    res_ref_l, seg_l, np_l, v_l = scenario("l")
    res_ref_m, seg_m, np_m, v_m = scenario("m")
    res_ref_h, seg_h, np_h, v_h = scenario("h")

    # --- A22 perfect-correlation guard --------------------------------------
    if seg_l < FY23_SEGMENT_TOTAL:
        errors.append(
            f"A22 guard: L-tier segment total {seg_l:,.0f} < FY2023 actual "
            f"{FY23_SEGMENT_TOTAL:,.0f} — the L tier has drifted toward the "
            f"legwise-minimum world (sum {LEGWISE_MIN_SUM:,.0f}) that never happened"
        )

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
    vo = re.search(r"V_\{opt\}\\?\)?\s*=\s*\*\*([0-9.]+)\*\*", out_sec)
    if vo is None or abs(float(vo.group(1))) > 1e-9:
        errors.append(
            f"V_opt must be stated as 0 (未来材料 is not an option leg), got "
            f"{vo.group(1) if vo else None}"
        )
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")

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
        f"tiers: L={TIER_YEAR['l']}  M={TIER_YEAR['m']}  H={TIER_YEAR['h']}  (A22 same-source OK)"
    )
    print(
        f"own poly={inp['own_poly']:.4f} sil={inp['own_sil']:.4f} oth={inp['own_oth']:.2f}"
        f"  tax={inp['tax']:.0%}  quota_t={inp['quota_t']:,.0f}"
    )
    print(
        f"FY2025 bridge={bridge:,.0f} vs reported {FY25['attributable']:,.0f} "
        f"({bridge_err:+.2%}, tol {BRIDGE_TOL:.0%})"
    )
    print(
        f"pe FLAT: ref={inp['pe_ref']:.0f} poly={inp['pe_poly']:.0f} "
        f"sil={inp['pe_sil']:.0f} oth={inp['pe_oth']:.0f}"
        "  -> L/M/H below IS the flat-multiple ladder (A2e-2c); multiple ratio = 1.00"
    )
    print(
        f"res_oth(亿CNY)={res_oth_of('l') / YI:.2f}/{res_oth_of('m') / YI:.2f}/"
        f"{res_oth_of('h') / YI:.2f}  [non-monotonic by design, A8]"
    )
    print(
        f"segment total(亿CNY)={seg_l / YI:.2f}/{seg_m / YI:.2f}/{seg_h / YI:.2f}"
        f"  guard: L >= FY2023 actual {FY23_SEGMENT_TOTAL / YI:.2f}亿 OK"
    )
    print(
        f"res_ref(亿CNY)={res_ref_l / YI:.2f}/{res_ref_m / YI:.2f}/{res_ref_h / YI:.2f}"
        f"  attribNP(亿CNY)={np_l / YI:.2f}/{np_m / YI:.2f}/{np_h / YI:.2f}"
    )
    eps_hkd = [n / (inp["shares"] / 1000.0) * inp["fx_cny_hkd"] for n in (np_l, np_m, np_h)]
    print(f"attribEPS(HKD)={eps_hkd[0]:.3f}/{eps_hkd[1]:.3f}/{eps_hkd[2]:.3f}")
    cash_ps = inp["net_cash"] * inp["cash_attrib"] * inp["fx_cny_hkd"] / (inp["shares"] / 1000.0)
    scale = inp["fx_cny_hkd"] / (inp["shares"] / 1000.0)

    def legs_ps(x: str) -> tuple[float, float, float, float, float]:
        res_ref = inp["quota_t"] * inp[f"upt_{x}"] / 1000.0
        np_ref, np_poly, np_sil, np_oth = attributable_np(
            res_ref,
            inp[f"res_poly_{x}"],
            inp[f"res_sil_{x}"],
            res_oth_of(x),
            inp["tax"],
            inp["own_poly"],
            inp["own_sil"],
            inp["own_oth"],
        )
        return (
            np_ref * inp["pe_ref"] * scale,
            np_poly * inp["pe_poly"] * scale,
            np_sil * inp["pe_sil"] * scale,
            np_oth * inp["pe_oth"] * scale,
            cash_ps,
        )

    for x in "lmh":
        ref, poly, sil, oth, cash = legs_ps(x)
        print(
            f"表1 {x.upper()}: 制冷剂={ref:.2f} 高分子={poly:.2f} 有机硅={sil:.2f}"
            f" 副产品={oth:.2f} 净现金={cash:.2f} 合计={ref + poly + sil + oth + cash:.2f}"
        )
    print(
        f"V(earnings)={v_l:.2f}/{v_m:.2f}/{v_h:.2f}  floor(pb*bvps*fx)={floor:.2f}"
        f"  attrib net cash/share={cash_ps:.2f}  V_opt=0"
    )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"ratios: L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}"
        "   [cyclical cohort median 0.63 / 1.24 / 32%]"
    )
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
