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
tiers (lithium peer cross-section, tier 1), r = 10%, tier ROE = NI_x / equity.
The tier-to-tier spread of the multiple is therefore purely the ROE term.  The
L tier is floor-bound: the trough-tier recovery form (`recovery_two_stage_pe`
with the ticker's own measured n = 1 / 2 — FY2021 → FY2022, FY2020 → FY2022)
lands at or above M (A10), so it is printed as a coordinate and not used as
the anchor; the axis L world is a low steady state, not the realised trough.
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
from lib.tiers import flat_multiple_ladder, report as tier_report  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "ALB.US.md"
FORMULA_ID = "alb_li2co3_grid_interp_spec_gordon_v2"
TOL = 0.05
MIN_R_MINUS_G = 0.02
# A10: the ticker's own measured trough→recovery years — FY2021 123.7M (lowest positive year)
# → FY2022 2,689.8M is n = 1; from the pre-shock FY2020 375.8M it is n = 2.  Both are printed.
RECOVERY_YEARS = (1, 2)

REQUIRED = [
    "price", "shares_diluted", "bps", "equity",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "vat", "fx_usd_cny",
    "grid_p1", "grid_p2", "grid_p3",
    "grid_es1", "grid_es2", "grid_es3",
    "spec_ebitda", "da", "interest", "tax_rate", "nci",
    "r_perp", "g2", "axis_g2_li",
    "pe_own_min", "pe_own_max", "pb_floor",
]


def parse_inputs(md: str) -> dict[str, float]:
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
        if key in ("字段名", "--------", "---") or raw == "取值":
            continue
        if "待补" in raw:
            continue
        try:
            out[key] = float(raw.replace(",", ""))
        except ValueError:
            continue
    return out


def zone_of(price: float, L: float, M: float, H: float) -> str:
    A, B = (L + M) / 2, (M + H) / 2
    if price < L:
        return "deep_discount"
    if price < A:
        return "conservative"
    if price < B:
        return "neutral"
    if price <= H:
        return "optimistic"
    return "stretched"


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
    p = inp[f"li2co3_{tag}"] / inp["vat"] / inp["fx_usd_cny"] / 1000.0
    es = es_ebitda(p, inp)
    ebitda = es + inp["spec_ebitda"]
    ebt = ebitda - inp["da"] - inp["interest"]
    ni = ebt * (1.0 - inp["tax_rate"]) - inp["nci"]
    eps = ni * 1000.0 / inp["shares_diluted"]
    roe = ni / inp["equity"]
    pe = perpetual_pe(inp["g2"], roe, inp["r_perp"])
    per_share = 1000.0 / inp["shares_diluted"]
    # Per-leg USD/share at the tier multiple: EBITDA × (1−t) × PE; the closing item
    # carries D&A, interest (after tax) and NCI at the same multiple.
    leg_es = es * (1.0 - inp["tax_rate"]) * per_share * pe
    leg_spec = inp["spec_ebitda"] * (1.0 - inp["tax_rate"]) * per_share * pe
    closing = -((inp["da"] + inp["interest"]) * (1.0 - inp["tax_rate"]) + inp["nci"]) * per_share * pe
    return {"p": p, "es": es, "ebitda": ebitda, "ebt": ebt, "ni": ni, "eps": eps, "roe": roe, "pe": pe,
            "leg_es": leg_es, "leg_spec": leg_spec, "closing": closing}


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
    # Gordon discipline: r on a tier, one g2 ≤ cap, r − g ≥ 2%, axis row referenced verbatim.
    errors += check_r(inp["r_perp"], "r_perp")
    errors += check_g_cap(inp["g2"], "g2")
    errors += check_g_cap(inp["axis_g2_li"], "axis_g2_li")
    if inp["r_perp"] - inp["g2"] < MIN_R_MINUS_G:
        errors.append(f"r − g2 = {inp['r_perp'] - inp['g2']:.4f} < {MIN_R_MINUS_G} (pole)")
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

    S = {t: scenario(inp, t) for t in ("l", "m", "h")}
    for t in ("l", "m", "h"):
        if not (inp["grid_p1"] <= S[t]["p"] <= inp["grid_p3"]):
            errors.append(f"{t.upper()} $/kg {S[t]['p']:.2f} outside company grid")
        if not (0.0 < payout(inp["g2"], S[t]["roe"]) <= 1.0):
            errors.append(f"{t.upper()} payout out of (0,1]")
        # Guardrail (裁决顺序 ③): generated multiple inside the own realised band.
        if not (inp["pe_own_min"] - 1e-9 <= S[t]["pe"] <= inp["pe_own_max"] + 1e-9):
            errors.append(f"{t.upper()} PE {S[t]['pe']:.2f} outside own band [{inp['pe_own_min']}, {inp['pe_own_max']}] — BLOCKED, do not twist g")
    floor = inp["pb_floor"] * inp["bps"]
    scenario_L = S["l"]["eps"] * S["l"]["pe"]
    L = max(scenario_L, floor)
    M = S["m"]["eps"] * S["m"]["pe"]
    H = S["h"]["eps"] * S["h"]["pe"]
    A, B = (L + M) / 2, (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1
    eps3 = (S["l"]["eps"], S["m"]["eps"], S["h"]["eps"])
    ladder_errors, flat = flat_multiple_ladder(eps3, S["m"]["pe"])
    errors += ladder_errors

    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    for k, v in {"L": L, "M": M, "H": H, "A": A, "B": B}.items():
        s = first_float(rf"{k} = \*\*([0-9.]+)\*\*", out_sec)
        if s is None:
            errors.append(f"stated {k} not found")
        elif abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")
    for label, v in (("scenario_L", scenario_L), ("floor", floor)):
        s = first_float(rf"`{label}` = \*\*([0-9.]+)\*\*", out_sec)
        if s is None or abs(s - v) > TOL:
            errors.append(f"{label}: stated {s} vs recomputed {v:.4f}")

    zm = re.search(r"zone = \*\*`([a-z_]+)`\*\*", out_sec)
    stated_zone = zm.group(1) if zm else None
    if stated_zone != zone:
        errors.append(f"zone: stated {stated_zone} vs recomputed {zone}")

    print(f"formula_id={FORMULA_ID}")
    print(
        "li2co3 OK: "
        + "/".join(f"{inp[k]:g}" for k in ("li2co3_l", "li2co3_m", "li2co3_h"))
        + f"  | axis 永续 g2 {inp['axis_g2_li']:g} referenced, g2 adopted {inp['g2']:g} (tier 1 peer cross-section, A7)"
    )
    print(f"{'档':<3}{'$/kg':>7}{'ES EBITDA':>11}{'EBITDA':>8}{'EBT':>7}{'NI':>7}{'EPS':>7}{'ROE':>7}{'PE':>7}{'ES腿':>8}{'Spec腿':>8}{'闭合项':>8}{'锚点':>8}")
    for t in ("l", "m", "h"):
        s_ = S[t]
        print(
            f"{t.upper():<3}{s_['p']:7.2f}{s_['es']:11.3f}{s_['ebitda']:8.3f}"
            f"{s_['ebt']:7.3f}{s_['ni']:7.3f}{s_['eps']:7.2f}{s_['roe']:7.1%}{s_['pe']:7.2f}"
            f"{s_['leg_es']:8.2f}{s_['leg_spec']:8.2f}{s_['closing']:8.2f}{s_['eps']*s_['pe']:8.2f}"
        )
    winner = "floor" if floor > scenario_L else "scenario_L"
    print(f"floor={floor:.2f}  scenario_L={scenario_L:.2f}  winner={winner}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    pes = (S["l"]["pe"], S["m"]["pe"], S["h"]["pe"])
    for line in tier_report((scenario_L, M, H), pes, eps3):
        print(line)
    print(f"flat ladder with floor-bound L: {max(flat[0], floor):.2f}/{flat[1]:.2f}/{flat[2]:.2f}  (L tier: {winner})")
    print(
        f"L/M={L/M:.2f} H/M={H/M:.2f} (H-L)/2M={(H-L)/2/M:.2%} "
        f"| numerator L/M={S['l']['eps']/S['m']['eps']:.2f} H/M={S['h']['eps']/S['m']['eps']:.2f} "
        f"| multiple ratio L/M={pes[0]/pes[1]:.2f} H/M={pes[2]/pes[1]:.2f} (ROE term only, g flat)"
    )
    # A10: trough-tier recovery form with the ticker's own measured n and the model's L→M magnitude;
    # landing at M it prices the L world at ~M, so it is a coordinate, not the anchor.
    for n in RECOVERY_YEARS:
        g1 = (S["m"]["eps"] / S["l"]["eps"]) ** (1.0 / n) - 1.0
        pe_rec = recovery_two_stage_pe(g1, n, inp["g2"], S["m"]["roe"], inp["r_perp"])
        print(
            f"谷底档坐标（A10）: recovery_two_stage_pe(g1={g1:.2%}, n={n}, g2={inp['g2']:g}, ROE_M {S['m']['roe']:.1%}) "
            f"= {pe_rec:.2f}x -> {S['l']['eps'] * pe_rec:.2f} (vs M {M:.2f}; {'>= M, collapsed' if S['l']['eps'] * pe_rec >= M else 'below M'})"
        )
    print(f"谷底 x 1/r = {S['l']['eps'] / inp['r_perp']:.2f}  (deep_discount pressure coordinate)")
    g_lo, ok_lo = implied_g(inp["pe_own_min"], S["m"]["roe"], inp["r_perp"])
    g_hi, ok_hi = implied_g(inp["pe_own_max"], S["m"]["roe"], inp["r_perp"])
    print(
        f"guardrail [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] band-edge g at ROE_M: "
        f"{g_lo:+.2%} ({'ok' if ok_lo else 'ill-conditioned'}) / {g_hi:+.2%} ({'ok' if ok_hi else 'ill-conditioned'}) — ROE_M≈r, reported only (A12)"
    )
    for g in (inp["g2"] - 0.01, inp["g2"] + 0.01):
        pm = perpetual_pe(g, S["m"]["roe"], inp["r_perp"])
        ph = perpetual_pe(g, S["h"]["roe"], inp["r_perp"])
        print(f"  g2 {g:.4f}: M {S['m']['eps'] * pm:.2f}  H {S['h']['eps'] * ph:.2f}")
    print(f"price={inp['price']} zone={zone}  P/H={inp['price']/H:.3f}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
