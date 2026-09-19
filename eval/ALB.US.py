#!/usr/bin/env python3
"""ALB.US (Albemarle) valuation eval.

frameworks/ALB.US.md is the source of truth.
formula_id: alb_li2co3_grid_interp_spec_gordon_v2

The Energy Storage leg is not modelled bottom-up: Albemarle publishes a
FY2026E "outlook considerations" grid (adj. EBITDA at ~$10 / ~$20 / ~$30 per kg
LCE) that already carries its contract book (~40% of salts on LTAs), the
Windfield equity income and CORFO royalties.  The eval maps the shared Li2CO3
axis (CNY/t incl. VAT) onto $/kg and interpolates that grid piecewise-linearly.

Multiples are generated, not sampled (valuation-rules「永续增长口径」): one g2 for all
tiers (lithium peer cross-section, tier 1), r per leg from its basket (ES leg
篮 6 13%, Specialties leg 篮 4 10%; A13), tier ROE = NI_x / equity shared by both
legs.  The closing item (D&A, interest after tax, NCI) is split across the legs
by EBITDA weight and each leg is capitalised at its own multiple; L/M/H is the
sum.  The tier-to-tier spread of the multiple is therefore purely the ROE term.
The PB floor is disclosed, never max()-ed into L: an asset number that does not
move with r would sit above M once the ES leg discounts at 13% (A8).  The
trough-tier recovery form (`recovery_two_stage_pe` with the ticker's own
measured n = 1 / 2 — FY2021 → FY2022, FY2020 → FY2022) lands at M (A10), so it
is printed as a coordinate and not used as the anchor.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import AXIS_LI2CO3, check_li2co3_mount, load_axis_g2  # noqa: E402
from lib.gordon import (  # noqa: E402
    check_g_cap, check_r, implied_g, payout, perpetual_pe, recovery_two_stage_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, outputs_section, parse_baskets, parse_inputs,
)
from lib.tiers import flat_multiple_ladder, report as tier_report  # noqa: E402
from lib.zones import zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "ALB.US.md"
FORMULA_ID = "alb_li2co3_grid_interp_spec_gordon_v2"
TOL = 0.05
MIN_R_MINUS_G = 0.02
# A10: the ticker's own measured trough→recovery years — FY2021 123.7M (lowest positive year)
# → FY2022 2,689.8M is n = 1; from the pre-shock FY2020 375.8M it is n = 2.  Both are printed.
RECOVERY_YEARS = (1, 2)
# Inputs r field → leg label; each must name its basket in the source cell.
LEG_R = {"r_perp": "ES", "r_spec": "Spec"}

REQUIRED = [
    "price", "shares_diluted", "bps", "equity",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "vat", "fx_usd_cny",
    "grid_p1", "grid_p2", "grid_p3",
    "grid_es1", "grid_es2", "grid_es3",
    "spec_ebitda", "da", "interest", "tax_rate", "nci",
    "r_perp", "r_spec", "g2", "axis_g2_li",
    "pe_own_min", "pe_own_max", "pb_floor",
]


def first_float(pattern: str, md: str) -> float | None:
    m = re.search(pattern, md)
    return float(m.group(1)) if m else None


def es_ebitda(p_usd_kg: float, inp: dict[str, float]) -> float:
    """Piecewise-linear read of the company grid; no extrapolation beyond $30."""
    p1, p2, p3 = inp["grid_p1"], inp["grid_p2"], inp["grid_p3"]
    e1, e2, e3 = inp["grid_es1"], inp["grid_es2"], inp["grid_es3"]
    if p_usd_kg <= p2:
        return e1 + (p_usd_kg - p1) * (e2 - e1) / (p2 - p1)
    return e2 + (p_usd_kg - p2) * (e3 - e2) / (p3 - p2)


def scenario(inp: dict[str, float], tag: str) -> dict[str, float]:
    """One tier: numerator bridge, then per-leg EPS with the closing item split by EBITDA weight."""
    p = inp[f"li2co3_{tag}"] / inp["vat"] / inp["fx_usd_cny"] / 1000.0
    es = es_ebitda(p, inp)
    spec = inp["spec_ebitda"]
    keep = 1.0 - inp["tax_rate"]
    ebitda = es + spec
    ebt = ebitda - inp["da"] - inp["interest"]
    ni = ebt * keep - inp["nci"]
    per_share = 1000.0 / inp["shares_diluted"]
    eps = ni * per_share
    roe = ni / inp["equity"]
    closing = -((inp["da"] + inp["interest"]) * keep + inp["nci"])
    w = es / ebitda
    eps_es = (es * keep + closing * w) * per_share
    eps_spec = (spec * keep + closing * (1.0 - w)) * per_share
    return {"p": p, "es": es, "ebitda": ebitda, "ebt": ebt, "ni": ni, "eps": eps, "roe": roe,
            "eps_es": eps_es, "eps_spec": eps_spec}


def leg_value(s: dict[str, float], g2: float, r_es: float, r_spec: float) -> tuple[float, float, float, float]:
    """(ES leg, Spec leg, PE_es, PE_spec) at this tier's ROE."""
    pe_es = perpetual_pe(g2, s["roe"], r_es)
    pe_spec = perpetual_pe(g2, s["roe"], r_spec)
    return s["eps_es"] * pe_es, s["eps_spec"] * pe_spec, pe_es, pe_spec


def band(S: dict[str, dict[str, float]], g2: float, r_es: float, r_spec: float) -> tuple[float, float, float]:
    return tuple(sum(leg_value(S[t], g2, r_es, r_spec)[:2]) for t in ("l", "m", "h"))  # type: ignore[return-value]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    missing = [k for k in REQUIRED if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1
    leaked = [k for k in inp if k.startswith("p_")]
    if leaked:
        print(f"FAIL: probability fields in Inputs {leaked} (A2e-7a)", file=sys.stderr)
        return 1

    errors: list[str] = []
    if not (inp["li2co3_l"] < inp["li2co3_m"] < inp["li2co3_h"]):
        errors.append("li2co3 ladder violated")
    # Gordon discipline: each leg's r is its named basket's value, one g2 ≤ cap(r) on
    # both legs, r − g ≥ 2%, axis row referenced verbatim.
    baskets = parse_baskets(md)
    for field in LEG_R:
        if field not in baskets:
            errors.append(f"{field}: no 篮 N in Inputs source cell (A13)")
        errors += check_r(inp[field], field, baskets.get(field))
        errors += check_g_cap(inp["g2"], inp[field], f"g2@{field}")
        errors += check_g_cap(inp["axis_g2_li"], inp[field], f"axis_g2_li@{field}")
        if inp[field] - inp["g2"] < MIN_R_MINUS_G:
            errors.append(f"{field} − g2 = {inp[field] - inp['g2']:.4f} < {MIN_R_MINUS_G} (pole)")
    want_axis = load_axis_g2(AXIS_LI2CO3)
    if abs(inp["axis_g2_li"] - want_axis) > 1e-9:
        errors.append(f"axis_g2_li={inp['axis_g2_li']} vs _AXIS.lithium-carbonate 永续 g2 {want_axis}")
    if not (inp["grid_p1"] < inp["grid_p2"] < inp["grid_p3"]
            and inp["grid_es1"] < inp["grid_es2"] < inp["grid_es3"]):
        errors.append("company grid must be monotonic")
    errors += check_li2co3_mount(
        (inp["li2co3_l"], inp["li2co3_m"], inp["li2co3_h"])
    )
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    g2, r_es, r_spec = inp["g2"], inp["r_perp"], inp["r_spec"]
    S = {t: scenario(inp, t) for t in ("l", "m", "h")}
    legs = {t: leg_value(S[t], g2, r_es, r_spec) for t in ("l", "m", "h")}
    for t in ("l", "m", "h"):
        if not (inp["grid_p1"] <= S[t]["p"] <= inp["grid_p3"]):
            errors.append(f"{t.upper()} $/kg {S[t]['p']:.2f} outside company grid")
        if not (0.0 < payout(g2, S[t]["roe"]) <= 1.0):
            errors.append(f"{t.upper()} payout out of (0,1]")
        # Guardrail (裁决顺序 ③): both legs' generated multiples inside the own realised band.
        for leg, pe in (("ES", legs[t][2]), ("Spec", legs[t][3])):
            if not (inp["pe_own_min"] - 1e-9 <= pe <= inp["pe_own_max"] + 1e-9):
                errors.append(f"{t.upper()} {leg} PE {pe:.2f} outside own band [{inp['pe_own_min']}, {inp['pe_own_max']}] — BLOCKED, do not twist g")
    floor = inp["pb_floor"] * inp["bps"]
    L, M, H = band(S, g2, r_es, r_spec)
    scenario_L = L  # the floor is disclosed only (A8): L is the scenario value
    A, B = (L + M) / 2, (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1
    eps3 = (S["l"]["eps"], S["m"]["eps"], S["h"]["eps"])
    ladder_errors, flat = flat_multiple_ladder(eps3, M / S["m"]["eps"])
    errors += ladder_errors

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)
    out_sec = outputs_section(md)
    for label, v in (("scenario_L", scenario_L), ("floor", floor)):
        s = first_float(rf"`{label}` = \*\*([0-9.]+)\*\*", out_sec)
        if s is None or abs(s - v) > TOL:
            errors.append(f"{label}: stated {s} vs recomputed {v:.4f}")

    print(f"formula_id={FORMULA_ID}")
    print(
        "li2co3 OK: "
        + "/".join(f"{inp[k]:g}" for k in ("li2co3_l", "li2co3_m", "li2co3_h"))
        + f"  | axis 永续 g2 {inp['axis_g2_li']:g} referenced, g2 adopted {g2:g} (tier 1 peer cross-section, A7)"
    )
    print("baskets: " + ", ".join(f"{k} 篮 {baskets[k]} r={inp[k]:g}" for k in LEG_R))
    print(f"{'档':<3}{'$/kg':>7}{'ES EBITDA':>11}{'EBITDA':>8}{'EBT':>7}{'NI':>7}{'EPS':>7}{'ROE':>7}{'PE_ES':>7}{'PE_Sp':>7}{'ES腿':>8}{'Spec腿':>8}{'锚点':>8}")
    for t in ("l", "m", "h"):
        s_ = S[t]
        v_es, v_sp, pe_es, pe_sp = legs[t]
        print(
            f"{t.upper():<3}{s_['p']:7.2f}{s_['es']:11.3f}{s_['ebitda']:8.3f}"
            f"{s_['ebt']:7.3f}{s_['ni']:7.3f}{s_['eps']:7.2f}{s_['roe']:7.1%}{pe_es:7.2f}{pe_sp:7.2f}"
            f"{v_es:8.2f}{v_sp:8.2f}{v_es + v_sp:8.2f}"
        )
    print(f"floor={floor:.2f} (PB {inp['pb_floor']:g} × bps, disclosed only, A8)  scenario_L={scenario_L:.2f}  "
          f"floor vs band: {zone_of(floor, L, M, H)}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    blended = tuple(v / e for v, e in zip((L, M, H), eps3))
    for line in tier_report((L, M, H), blended, eps3):
        print(line)
    print(f"flat ladder (blended M multiple {blended[1]:.2f}x): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(
        f"L/M={L/M:.2f} H/M={H/M:.2f} (H-L)/2M={(H-L)/2/M:.2%} "
        f"| numerator L/M={S['l']['eps']/S['m']['eps']:.2f} H/M={S['h']['eps']/S['m']['eps']:.2f} "
        f"| blended multiple ratio L/M={blended[0]/blended[1]:.2f} H/M={blended[2]/blended[1]:.2f} (ROE term only, g flat)"
    )
    # A10: trough-tier recovery form per leg with the ticker's own measured n and the model's
    # L→M magnitude; landing at M it prices the L world at ~M, so it is a coordinate, not the anchor.
    for n in RECOVERY_YEARS:
        g1 = (S["m"]["eps"] / S["l"]["eps"]) ** (1.0 / n) - 1.0
        pe_es = recovery_two_stage_pe(g1, n, g2, S["m"]["roe"], r_es)
        pe_sp = recovery_two_stage_pe(g1, n, g2, S["m"]["roe"], r_spec)
        v = S["l"]["eps_es"] * pe_es + S["l"]["eps_spec"] * pe_sp
        print(
            f"谷底档坐标（A10）: recovery_two_stage_pe(g1={g1:.2%}, n={n}, g2={g2:g}, ROE_M {S['m']['roe']:.1%}) "
            f"ES {pe_es:.2f}x / Spec {pe_sp:.2f}x -> {v:.2f} (vs M {M:.2f}; {'>= M, collapsed' if v >= M else 'below M'})"
        )
    print(f"谷底 x 1/r (per leg) = {S['l']['eps_es'] / r_es + S['l']['eps_spec'] / r_spec:.2f}  (deep_discount pressure coordinate)")
    g_lo, ok_lo = implied_g(inp["pe_own_min"], S["m"]["roe"], r_es)
    g_hi, ok_hi = implied_g(inp["pe_own_max"], S["m"]["roe"], r_es)
    print(
        f"guardrail [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] band-edge g at ROE_M, r_ES: "
        f"{g_lo:+.2%} ({'ok' if ok_lo else 'ill-conditioned'}) / {g_hi:+.2%} ({'ok' if ok_hi else 'ill-conditioned'}) — reported only (A12)"
    )
    for g in (g2 - 0.01, g2 + 0.01, 0.0):
        l_, m_, h_ = band(S, g, r_es, r_spec)
        print(f"  g2 {g:.4f}: {l_:.2f} / {m_:.2f} / {h_:.2f}  zone={zone_of(inp['price'], l_, m_, h_)}")
    l_, m_, h_ = band(S, g2, r_es, r_es)
    print(f"  both legs at r_ES {r_es:g} (first-leg approximation): {l_:.2f} / {m_:.2f} / {h_:.2f}")
    print(f"price={inp['price']} zone={zone}  P/H={inp['price']/H:.3f}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
