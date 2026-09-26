#!/usr/bin/env python3
"""0189.HK (Dongyue Group) valuation eval — recompute anchors from frameworks/0189.HK.md.

frameworks/0189.HK.md is the source of truth; this script re-parses its §3 Inputs
table, recomputes L/M/H / A/B / zone and exits 1 on mismatch.

formula_id: dongyue_quota_sotp_actual_year_flat_v2

Main ruler: four-leg segment SOTP.  The refrigerant leg's three tiers are
**named price scenarios** (L = R32 45,000 / M = 2025 average 53,600 / H = Q3
contract 64,500 held flat, A4) mapped to a unit segment result per quota tonne
through a bridge `k * sum_i w_i (P_i - c_i)` (w_i = 2026 MEE quota by product,
c_i = cash cost implied by the 2026-04 per-tonne gross margins, k calibrated on
FY2025 + 26H1).  The other three legs take **three actually observed operating
years** (L=FY2024, M=FY2025, H=26H1 annualised, A22), every leg the *same* year
in a given tier so the inter-leg correlation structure is inherited from
history rather than assumed.  The by-product leg (A8) is rebuilt as
recurring + impairment-scenario because its reported FY2024/FY2025 losses were
majority one-off property impairments now near exhaustion.

Each segment result is taxed, scaled by the *leg-specific* attributable ownership
ratio (refrigerant + fluoropolymer sit in Dongyue Polymers, 74.06% owned;
organosilicone is the separately A-listed Dongyue Organosilicon, 44.40% owned),
multiplied by a **flat** per-leg Gordon multiple generated at the basket r
(all four legs sit in basket 6 周期商品, r 13%, A24), then attributable net cash
is added at face value.  Multiples do not vary by tier: this is a `cyclical`
name whose numerators already carry the cycle, and two legs go negative in
some tier (organosilicone at M, the by-product leg at H), which would make
tiered multiples reward bigger losses.

Reporting currency is CNY, the listing currency is HKD: fx_cny_hkd is an
explicit Input and is applied once, at step 5.

The PB floor is disclosed only, never max()-ed into L (A16).  The candidate
band (consensus-2027E price deck, A4) swaps only the refrigerant prices into
H' and is recomputed against the Outputs 候选带 line; V_opt (PTFE-AI, 1.86)
stays out of the deck.

Sanity checks beyond the anchor comparison:
  * r_perp must be the basket the Inputs row names (parse_baskets + check_r);
    every g2 must sit under g_cap(r); every pe_* must equal the Gordon multiple
    its named g2 / ROE / r generate
  * BRIDGE REPRODUCTION (A4): bridge_k on the FY2025 / 26H1 actual average
    prices must reproduce the reported unit result within BRIDGE_REPRO_TOL,
    bridge_k must equal the mean of those two calibration ratios, and every
    upt_x must equal the bridge at that tier's px_* (FY2024 is a regime break
    and is printed as the deep_discount pressure coordinate, not asserted)
  * SAME-SOURCE (A22) on the three actual-year legs: fluoropolymer,
    organosilicone and dichloromethane must equal the reported figure for that
    tier's year — silently swapping in an extrapolation fails
  * the same ownership/tax bridge must reproduce the FY2025 reported profit
    attributable to owners (RMB 1,641,812k) within OWNERSHIP_BRIDGE_TOL
  * PERFECT-CORRELATION GUARD: the L tier's segment total must not fall below
    FY2023's actual total (650,645); each leg's own historical minimum would
    sum to 55,421 — a world that never happened (A22)
  * L < M < H on the *total* only — individual legs may be non-monotonic

Run:  python3 eval/0189.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import check_g_cap, check_r, perpetual_pe  # noqa: E402
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    outputs_section,
    parse_baskets,
    parse_inputs,
)
from eval.lib.zones import zone_of  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "0189.HK.md"
FORMULA_ID = "dongyue_quota_sotp_actual_year_flat_v2"
LISTING_CCY = "HKD"
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
OWNERSHIP_BRIDGE_TOL = 0.03  # the framework claims -0.9%; fail if the bridge drifts past 3%

# A22 same-source anchors for the three actual-year legs (RMB thousand),
# straight from the FY2025 annual report / 2026 interim segment tables.
TIER_YEAR = {"l": "FY2024", "m": "FY2025", "h": "26H1 annualised"}
REPORTED = {
    "l": {"poly": 508088.0, "sil": 101668.0, "dcm": 372161.0},
    "m": {"poly": 356642.0, "sil": -51711.0, "dcm": 358053.0},
    "h": {"poly": 877146.0, "sil": 471612.0, "dcm": 119206.0},
}
SAME_SOURCE_TOL = 0.001

# A4 price bridge.  Products in bridge order; 其他 HFC (152a etc.) has no price
# series and rides R125's price and cash cost.
PRODUCTS = ("r32", "r125", "r134a", "hfc_oth", "r22")
PRICE_KEY = {"r32": "r32", "r125": "r125", "r134a": "r134a", "hfc_oth": "r125", "r22": "r22"}
# Calibration points (annual average prices 元/吨 R32 / R125 / R134a / R22, and
# the reported unit segment result per quota tonne).  FY2024 is quota year 1
# with a different cost base — a regime break the bridge is documented NOT to
# reproduce (+64%), so it is printed, not asserted.
BRIDGE_CALIB = {
    "FY2025": ((53600, 45000, 49500, 27000), 17656.06),
    "26H1": ((63500, 55000, 60000, 20000), 19233.03),
}
BRIDGE_REGIME_BREAK = {"FY2024": ((33000, 36800, 33000, 31000), 6223.28)}
BRIDGE_REPRO_TOL = 0.20  # valuation-rules.md: ≥2 years within ±20%
BRIDGE_K_TOL = 0.001  # bridge_k is stated to 4 decimals
UPT_TOL = 1.0  # upt_* are stated to the 元/吨

# A22 perfect-correlation guard.
FY23_SEGMENT_TOTAL = 650645.0  # worst year actually observed
LEGWISE_MIN_SUM = 55421.0  # sum of each leg's own historical low — never happened

# Own post-quota PE band (A10), for the ③ 出带 disclosure only.
OWN_PE_BAND_MIN = 10.71

REQUIRED = [
    "price", "shares", "fx_cny_hkd", "bvps_cny", "tax",
    "own_poly", "own_sil", "own_oth",
    "quota_t", "q_r32", "q_r125", "q_r134a", "q_hfc_oth", "q_r22",
    "upt_l", "upt_m", "upt_h",
    "px_r32_l", "px_r32_m", "px_r32_h", "px_r125_l", "px_r125_m", "px_r125_h",
    "px_r134a_l", "px_r134a_m", "px_r134a_h", "px_r22_l", "px_r22_m", "px_r22_h",
    "px_r32_c", "px_r125_c", "px_r134a_c", "px_r22_c",
    "c_r32", "c_r125", "c_r134a", "c_r22", "bridge_k",
    "res_poly_l", "res_poly_m", "res_poly_h",
    "res_sil_l", "res_sil_m", "res_sil_h",
    "dcm_l", "dcm_m", "dcm_h",
    "oth_recur", "oth_imp_l", "oth_imp_m", "oth_imp_h", "nonseg",
    "r_perp", "np_poly_fy25", "equity_poly_avg", "equity_sil_avg",
    "g2_ref", "g2_poly", "g2_sil", "g2_oth",
    "pe_ref", "pe_poly", "pe_sil", "pe_oth",
    "net_cash", "cash_attrib", "pb_floor",
]


def first_float(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def attributable_np(
    res_ref: float, res_poly: float, res_sil: float, res_oth: float,
    tax: float, own_poly: float, own_sil: float, own_oth: float,
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
    errors = check_missing(inp, REQUIRED)
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    # --- structural sanity on the inputs themselves -------------------------
    for name in ("own_poly", "own_sil", "own_oth", "cash_attrib"):
        if not 0.0 < inp[name] <= 1.0:
            errors.append(f"{name}={inp[name]} outside (0, 1]")
    if not 0.0 <= inp["tax"] < 0.5:
        errors.append(f"tax={inp['tax']} implausible")
    if inp["quota_t"] <= 0:
        errors.append(f"quota_t={inp['quota_t']} must be positive")
    quota = {p: inp[f"q_{p}"] for p in PRODUCTS}
    if abs(sum(quota.values()) - inp["quota_t"]) > 0.5:
        errors.append(f"q_* sum {sum(quota.values()):,.0f} != quota_t {inp['quota_t']:,.0f}")

    # Multiples are FLAT by construction (A9/A10). There is deliberately no
    # ordering check here: tiered multiples would double-count the cycle for a
    # `cyclical` name and would reward bigger losses on the legs that go
    # negative. Guard the invariant that actually matters instead.
    for leg in ("ref", "poly", "sil", "oth"):
        if inp[f"pe_{leg}"] <= 0:
            errors.append(f"pe_{leg}={inp[f'pe_{leg}']} must be positive")
    if "pe_ref_l" in inp or "pe_ref_h" in inp:
        errors.append("tiered pe_* inputs reintroduced — A10 requires flat multiples")

    # --- A24 / A10: basket r, and flat multiples Gordon-generated per leg ----
    # ROE per leg comes from the note-36 subsidiary accounts (Dongyue Polymers
    # carries refrigerants + fluoropolymers; Dongyue Organosilicon the silicone
    # leg); the by-product leg has no entity, and with g2 < 0 the payout cap
    # binds so its ROE is irrelevant.
    r = inp["r_perp"]
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    for leg in ("ref", "poly", "sil", "oth"):
        errors += check_g_cap(inp[f"g2_{leg}"], r, f"g2_{leg}")
    roe_poly = inp["np_poly_fy25"] / inp["equity_poly_avg"]
    roe_sil = inp["res_sil_h"] * (1.0 - inp["tax"]) / inp["equity_sil_avg"]

    def gordon(r_: float) -> dict[str, float]:
        return {
            "ref": perpetual_pe(inp["g2_ref"], roe_poly, r_),
            "poly": perpetual_pe(inp["g2_poly"], roe_poly, r_),
            "sil": perpetual_pe(inp["g2_sil"], roe_sil, r_),
            "oth": perpetual_pe(inp["g2_oth"], 0.139, r_),  # ROE drops out at g2 < 0
        }

    gen = gordon(r)
    for leg, val in gen.items():
        if abs(val - inp[f"pe_{leg}"]) > TOL:
            errors.append(
                f"pe_{leg}={inp[f'pe_{leg}']} is not the Gordon multiple {val:.3f} generated by "
                f"g2_{leg}={inp[f'g2_{leg}']} at r={r} — the multiple has come loose from its named g"
            )

    # --- A4 price bridge: unit segment result per quota tonne -----------------
    def bridge_unit(px: dict[str, float], k: float) -> float:
        """k × Σ w_i (P_i − c_i), weights = product quota / total quota."""
        margin = sum(quota[p] * (px[PRICE_KEY[p]] - inp[f"c_{PRICE_KEY[p]}"]) for p in PRODUCTS)
        return k * margin / inp["quota_t"]

    def px_of(r32: float, r125: float, r134a: float, r22: float) -> dict[str, float]:
        return {"r32": r32, "r125": r125, "r134a": r134a, "r22": r22}

    def tier_px(x: str) -> dict[str, float]:
        return px_of(*(inp[f"px_{p}_{x}"] for p in ("r32", "r125", "r134a", "r22")))

    calib_ratio = {y: unit / bridge_unit(px_of(*px), 1.0) for y, (px, unit) in BRIDGE_CALIB.items()}
    k_mean = sum(calib_ratio.values()) / len(calib_ratio)
    if abs(k_mean - inp["bridge_k"]) > BRIDGE_K_TOL:
        errors.append(f"bridge_k={inp['bridge_k']} is not the mean of the calibration ratios {k_mean:.4f}")
    for y, (px, unit) in BRIDGE_CALIB.items():
        est = bridge_unit(px_of(*px), inp["bridge_k"])
        if abs(est / unit - 1.0) > BRIDGE_REPRO_TOL:
            errors.append(f"bridge does not reproduce {y}: {est:,.0f} vs reported {unit:,.0f} ({est / unit - 1:+.1%})")
    for x in "lmh":
        est = bridge_unit(tier_px(x), inp["bridge_k"])
        if abs(est - inp[f"upt_{x}"]) > UPT_TOL:
            errors.append(f"upt_{x}={inp[f'upt_{x}']:,.0f} but bridge @ px_*_{x} gives {est:,.1f}")

    # The refrigerant leg is the one that IS monotonic (quota volume is fixed,
    # so the price scenario carries the tier). The other legs are allowed to invert.
    if not inp["upt_l"] < inp["upt_m"] < inp["upt_h"]:
        errors.append(f"upt not increasing: {inp['upt_l']}/{inp['upt_m']}/{inp['upt_h']}")

    # --- A22 same-source check on the three actual-year legs -------------------
    for x in "lmh":
        checks = {
            "poly": (inp[f"res_poly_{x}"], REPORTED[x]["poly"]),
            "sil": (inp[f"res_sil_{x}"], REPORTED[x]["sil"]),
            "dcm": (inp[f"dcm_{x}"], REPORTED[x]["dcm"]),
        }
        for leg, (got, want) in checks.items():
            if abs(got - want) / max(abs(want), 1.0) > SAME_SOURCE_TOL:
                errors.append(
                    f"A22 same-source: {x.upper()}/{leg} = {got:,.0f} but "
                    f"{TIER_YEAR[x]} reported {want:,.0f}"
                )

    # --- FY2025 bridge: does leg-ownership reproduce reported attributable? --
    bridge = sum(attributable_np(
        FY25["res_ref"], FY25["res_poly"], FY25["res_sil"], FY25["res_oth"],
        FY25["tax"], inp["own_poly"], inp["own_sil"], inp["own_oth"],
    ))
    bridge_err = bridge / FY25["attributable"] - 1.0
    if abs(bridge_err) > OWNERSHIP_BRIDGE_TOL:
        errors.append(
            f"FY2025 bridge {bridge:,.0f} vs reported {FY25['attributable']:,.0f} "
            f"({bridge_err:+.2%}) exceeds {OWNERSHIP_BRIDGE_TOL:.0%}"
        )

    # --- scenarios ----------------------------------------------------------
    scale = inp["fx_cny_hkd"] / (inp["shares"] / 1000.0)  # RMB'000 -> HKD/share
    cash_ps = inp["net_cash"] * inp["cash_attrib"] * scale

    def res_oth_of(x: str) -> float:
        """By-product leg (A8): dichloromethane + recurring other ops + impairment."""
        return inp[f"dcm_{x}"] + inp["oth_recur"] + inp[f"oth_imp_{x}"] + inp["nonseg"]

    def scenario(x: str, upt: float, pe: dict[str, float]) -> dict[str, float]:
        """Tier x with refrigerant unit result `upt` and multiples `pe`."""
        res_ref = inp["quota_t"] * upt / 1000.0
        res_oth = res_oth_of(x)
        np_legs = attributable_np(
            res_ref, inp[f"res_poly_{x}"], inp[f"res_sil_{x}"], res_oth,
            inp["tax"], inp["own_poly"], inp["own_sil"], inp["own_oth"],
        )
        ps = {leg: n * pe[leg] * scale for leg, n in zip(("ref", "poly", "sil", "oth"), np_legs)}
        # Segment total excludes non-segment items, to compare with reported totals.
        seg_total = res_ref + inp[f"res_poly_{x}"] + inp[f"res_sil_{x}"] + inp[f"dcm_{x}"] \
            + inp["oth_recur"] + inp[f"oth_imp_{x}"]
        return {
            "res_ref": res_ref, "seg_total": seg_total, "np": sum(np_legs),
            **ps, "cash": cash_ps, "value": sum(ps.values()) + cash_ps,
        }

    tiers = {x: scenario(x, inp[f"upt_{x}"], gen) for x in "lmh"}
    L, M, H = (tiers[x]["value"] for x in "lmh")
    A, B = (L + M) / 2, (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}")

    # --- A22 perfect-correlation guard --------------------------------------
    if tiers["l"]["seg_total"] < FY23_SEGMENT_TOTAL:
        errors.append(
            f"A22 guard: L-tier segment total {tiers['l']['seg_total']:,.0f} < FY2023 actual "
            f"{FY23_SEGMENT_TOTAL:,.0f} — the L tier has drifted toward the "
            f"legwise-minimum world (sum {LEGWISE_MIN_SUM:,.0f}) that never happened"
        )

    # --- floor: disclosed only (A16) ------------------------------------------
    floor = inp["pb_floor"] * inp["bvps_cny"] * inp["fx_cny_hkd"]

    # --- candidate band (A4): consensus-2027E prices into the refrigerant leg of H only
    px_c = px_of(*(inp[f"px_{p}_c"] for p in ("r32", "r125", "r134a", "r22")))
    upt_c = bridge_unit(px_c, inp["bridge_k"])
    cand = scenario("h", upt_c, gen)
    cand_band = (L, M, cand["value"])
    if not cand_band[0] < cand_band[1] < cand_band[2]:
        errors.append(f"candidate band not ordered: {cand_band}")
    meta = load_framework(FRAMEWORK)
    if meta.candidate is None:
        errors.append("候选带 line missing from Outputs (A4)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), meta.candidate, cand_band):
            if abs(said - got) > TOL:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")

    # --- compare against the stated Outputs ---------------------------------
    out_sec = outputs_section(md)
    triples = re.findall(r"L = \*\*[0-9.]+\*\* · M = \*\*[0-9.]+\*\* · H = \*\*[0-9.]+\*\*", out_sec)
    if len(triples) != 1:
        errors.append(f"### Outputs must state the L/M/H triple exactly once, found {len(triples)}")
    if meta.v_opt is None:
        errors.append("V_opt must be stated in Outputs (PTFE-AI option, §1)")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)

    # --- report -------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"basket: r_perp={r} 篮 {baskets.get('r_perp')} (all four legs) | ROE_poly {roe_poly:.4f} (note 36) ROE_sil {roe_sil:.4f} | "
          + " ".join(f"{leg}: g2 {inp[f'g2_{leg}']:+.4f} -> {gen[leg]:.2f}x (stated {inp[f'pe_{leg}']:g})" for leg in gen))
    alt_poly = perpetual_pe(0.0376, roe_poly, r)
    print(f"  sens g2_poly=0.0376 (A-share cross-section median, cross-market): poly {alt_poly:.2f}x")
    print(f"tiers: refrigerant = price scenarios (A4); other legs L={TIER_YEAR['l']} M={TIER_YEAR['m']} H={TIER_YEAR['h']} (A22 same-source OK)")
    print(f"bridge: k={inp['bridge_k']} = mean(" + ", ".join(f"{y} {v:.4f}" for y, v in calib_ratio.items()) + ")")
    for y, (px, unit) in {**BRIDGE_CALIB, **BRIDGE_REGIME_BREAK}.items():
        est = bridge_unit(px_of(*px), inp["bridge_k"])
        tag = "regime break, not asserted" if y in BRIDGE_REGIME_BREAK else f"within ±{BRIDGE_REPRO_TOL:.0%}"
        print(f"  reproduce {y}: {est:,.0f} vs reported {unit:,.0f} ({est / unit - 1:+.1%}, {tag})")
    for x in "lmh":
        px = tier_px(x)
        print(f"  {x.upper()}: R32 {px['r32']:,.0f} / R125 {px['r125']:,.0f} / R134a {px['r134a']:,.0f} / R22 {px['r22']:,.0f}"
              f" -> upt {bridge_unit(px, inp['bridge_k']):,.0f} 元/吨 (stated {inp[f'upt_{x}']:,.0f})")
    print(f"own poly={inp['own_poly']:.4f} sil={inp['own_sil']:.4f} oth={inp['own_oth']:.2f}"
          f"  tax={inp['tax']:.0%}  quota_t={inp['quota_t']:,.0f}")
    print(f"FY2025 ownership bridge={bridge:,.0f} vs reported {FY25['attributable']:,.0f} "
          f"({bridge_err:+.2%}, tol {OWNERSHIP_BRIDGE_TOL:.0%})")
    print(f"pe FLAT: ref={inp['pe_ref']:.2f} poly={inp['pe_poly']:.2f} sil={inp['pe_sil']:.2f} oth={inp['pe_oth']:.2f}"
          "  -> L/M/H below IS the flat-multiple ladder (A2e-2c); multiple ratio = 1.00")
    print(f"res_oth(亿CNY)={res_oth_of('l') / YI:.2f}/{res_oth_of('m') / YI:.2f}/{res_oth_of('h') / YI:.2f}"
          "  [non-monotonic by design, A8]")
    print("segment total(亿CNY)=" + "/".join(f"{tiers[x]['seg_total'] / YI:.2f}" for x in "lmh")
          + f"  guard: L >= FY2023 actual {FY23_SEGMENT_TOTAL / YI:.2f}亿 OK")
    print("res_ref(亿CNY)=" + "/".join(f"{tiers[x]['res_ref'] / YI:.2f}" for x in "lmh")
          + "  attribNP(亿CNY)=" + "/".join(f"{tiers[x]['np'] / YI:.2f}" for x in "lmh"))
    eps = {x: tiers[x]["np"] * scale for x in "lmh"}
    print("attribEPS(HKD)=" + "/".join(f"{eps[x]:.3f}" for x in "lmh"))
    for x in "lmh":
        t = tiers[x]
        print(f"表1 {x.upper()}: 制冷剂={t['ref']:.2f} 高分子={t['poly']:.2f} 有机硅={t['sil']:.2f}"
              f" 副产品={t['oth']:.2f} 净现金={t['cash']:.2f} 合计={t['value']:.2f}")
    print(f"V(earnings)={L:.2f}/{M:.2f}/{H:.2f}  attrib net cash/share={cash_ps:.2f}")
    print(f"floor={floor:.2f} (PB {inp['pb_floor']:g} × bvps × fx, disclosed only, A16)  scenario_L={L:.2f}"
          f"  floor vs band: {zone_of(floor, L, M, H)}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"ratios: L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}"
          "   [cyclical cohort L/M median 0.71, repo H/M median 1.25]")
    print(f"price={inp['price']} zone={zone}")
    # Disclosure rows (Outputs): implied r, ③ 出带, sensitivity, candidate, option.
    print(f"implied r(P): E_M/P = {eps['m'] / inp['price']:.1%} incl cash, "
          f"{eps['m'] / (inp['price'] - cash_ps):.1%} ex cash  (basket r {r:.1%})")
    print("implied PE incl cash: " + "/".join(f"{tiers[x]['value'] / eps[x]:.2f}x" for x in "lmh")
          + "  ex cash: " + "/".join(f"{(tiers[x]['value'] - cash_ps) / eps[x]:.2f}x" for x in "lmh")
          + f"  vs own post-quota band min {OWN_PE_BAND_MIN} -> "
          + ("③ 出带 (M/H below band min, disclosed)" if M / eps["m"] < OWN_PE_BAND_MIN else "in band"))
    for label, r_alt in (("r +50bp", r + 0.005), ("r -50bp", r - 0.005), ("篮 7 15%", 0.15), ("篮 4 10%", 0.10)):
        pe_alt = gordon(r_alt)
        band = [scenario(x, inp[f"upt_{x}"], pe_alt)["value"] for x in "lmh"]
        print(f"  sens {label}: {band[0]:.2f}/{band[1]:.2f}/{band[2]:.2f} -> {zone_of(inp['price'], *band)}")
    print(f"candidate (A4, consensus-2027E prices R32 {px_c['r32']:,.0f} -> H' only): "
          f"upt {upt_c:,.0f} 元/吨, L'/M'/H' = {cand_band[0]:.2f}/{cand_band[1]:.2f}/{cand_band[2]:.2f}")
    fy24_px, fy24_unit = BRIDGE_REGIME_BREAK["FY2024"]
    print(f"deep_discount pressure coordinate (FY2024 actual unit {fy24_unit:,.0f}, other legs FY2024): "
          f"{scenario('l', fy24_unit, gen)['value']:.2f}")
    if meta.v_opt is not None:
        print(f"V_opt={meta.v_opt:.2f} (not in deck) p_tiers={meta.p_tiers}  zone+V: M+p·V={M + (meta.p_tiers[1] if meta.p_tiers else 0) * meta.v_opt:.2f}"
              f" H+V={H + meta.v_opt:.2f}")
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # the one basket r all four legs share 1:1; price scenarios, g2, ROE, ownership
    # and fx stay put.  Disclosure only — the anchors above are the 中枢 column.
    def band_rf(dr: float) -> tuple[float, float, float]:
        pe_rf = gordon(r + dr)
        return tuple(scenario(x, inp[f"upt_{x}"], pe_rf)["value"] for x in "lmh")

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf, inp["price"])
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    # Only a clean run feeds the daily digest.
    write_rf_readings("0189.HK", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
