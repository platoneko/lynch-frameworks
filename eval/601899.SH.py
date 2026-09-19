#!/usr/bin/env python3
"""601899.SH (Zijin Mining) valuation eval — recompute anchors from frameworks/601899.SH.md.

frameworks/601899.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: zijin_fed_li_dual_axis_gp_pe_v4_gordon_v2

Two orthogonal axes:
  * Fed rate path → gold / copper USD ladder (_AXIS.fed-path-gold-copper)
  * Lithium supply regime → battery-grade Li2CO3 CNY (_AXIS.lithium-carbonate)

Base deck: every leg, lithium included, uses current consolidated sales (no
discount).  The 2028 lithium plan (30 万 t × δ², δ at the lithium leg's basket
r) is a single-source company guide and therefore lives in the candidate band
only (AGENTS.md「共识升级候选带」).

Multiples are Gordon-generated per leg and summed (valuation-rules「永续增长口径」
+「§r 篮子」): parent NI is split across three legs by gross-profit share, each
leg carries its own basket r and g2 (flat across tiers, A2e-5 cyclical default)
and the company-wide ROE_x = parent_x / equity (legs share one balance sheet,
A11).  Gold/copper/silver: 篮 4 r 10%, g2 2.5% (commodity-leg tier default:
inflation + ~0 real price drift; the peer cross-section 2.76% is only a
cross-check).  Lithium and the residual block: 篮 6 r 13%, g 0 → 1/r.  The
axis 永续 g2 rows are referenced verbatim (`axis_g2_*`) and not adopted.  The
tier-to-tier spread of the gold/copper leg multiple is the ROE term only.

L tier (valuation-rules「谷底档」): the axis L world (gold 3,942 / copper 9,431
/ Li2CO3 103k) is a regime, not the company's realised trough, so it is priced
as a low steady state.  The recovery form `recovery_two_stage_pe` on the
company's own measured path (FY2016 18.40 亿 → FY2018 40.94 亿, n = 2) is
printed as a coordinate: it overshoots M with the measured CAGR and collapses
into M with the model's L→M magnitude, so it is not the anchor.  The own-year
PE band is only a guardrail.  The PB floor is disclosure only (A9): L is the
scenario value, never max(scenario, floor).

M regression: gold+copper+silver+non-li residual reproduce the 1H2026
annualised bridge; lithium is 8.8 万 t × axis-M realization, so group M parent
differs from 1H2026×2 only by the axis-M vs H1 ASP gap on that volume.

Run:  python3 eval/601899.SH.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import AXIS_AU_CU, AXIS_LI2CO3, check_au_cu_mount, check_li2co3_mount  # noqa: E402
from lib.gordon import check_g_cap, check_r, perpetual_pe, recovery_two_stage_pe  # noqa: E402
from lib.inputs import check_against_stated, parse_baskets, parse_inputs  # noqa: E402
from lib.tiers import report as tier_report  # noqa: E402
from lib.zones import zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "601899.SH.md"
PEER = Path(__file__).resolve().parent.parent / "frameworks" / "603993.SH.md"
FORMULA_ID = "zijin_fed_li_dual_axis_gp_pe_v4_gordon_v2"
MIN_R_MINUS_G = 0.02
# A25: the company's own realised trough→recovery path (Longbridge annual parent NI,
# FY2016 18.40 亿 → FY2018 40.94 亿, the last copper/gold cycle trough).
RECOVERY_MEASURED = {"FY2016→FY2018": (18.40, 40.94, 2)}
TOL = 0.05
DELTA_TOL = 0.0005  # implied-r δ stated to 0.01pp
YI = 1e8
OZ_TO_G = 31.1035

# Legs: (r field, g field, basket label) — r values come from Inputs, baskets
# from the Inputs source cells (parse_baskets); check_r ties the two together.
LEGS = {
    "metal": ("r_perp", "g2_aucu"),
    "li": ("r_li", "g2_li"),
    "rest": ("r_rest", "g2_rest"),
}
ALT_METAL_BASKET_R = 0.11  # 备选篮 5 (country premium), disclosure only

SHARED_LADDER = {
    "lme_cu_l": "p_cu_l",
    "lme_cu_m": "p_cu_m",
    "lme_cu_h": "p_cu_h",
    "lme_au_l": "lme_au_l",
    "lme_au_m": "lme_au_m",
    "lme_au_h": "lme_au_h",
}

# 1H2026×2 for the non-lithium bridge check (see M guard below).
H1_2026_X2 = {
    "gp": (194_178_458_630 - 120_881_455_727) * 2,
    "pretax": 63_489_448_069 * 2,
    "net_income": (63_489_448_069 - 13_676_755_053) * 2,
    "parent": 39_169_807_243 * 2,
}
IDENTITY_TOL = 0.01

M_PRICE_REF = {"p_au": ("price_au_m", 1006.5), "p_cu": ("price_cu_m", 84466.0)}
M_PRICE_TOL = 0.005

# 1H2026 lithium: revenue from product table; GP from business-map 3.4% share.
LI_REV_H1 = (28.80 + 10.98) * 1e8
LI_GP_H1 = 732.97e8 * 0.034
LI_VOL_H1 = 4.4e4
LI_ASP_H1 = LI_REV_H1 / LI_VOL_H1
LI_COST_H1 = (LI_REV_H1 - LI_GP_H1) / LI_VOL_H1

REQUIRED = [
    "price", "shares", "bps",
    "fx_usd_cny", "realization_au", "realization_cu",
    "lme_au_l", "lme_au_m", "lme_au_h", "vol_au_g", "cost_au",
    "lme_cu_l", "lme_cu_m", "lme_cu_h", "vol_cu_t", "cost_cu",
    "vol_ag_g", "price_ag_m", "cost_ag",
    "li2co3_l", "li2co3_m", "li2co3_h", "realization_li",
    "vol_li_t", "cost_li", "r_disc_li", "n_disc_li",
    "vol_li_plan", "n_disc_li_plan",
    "gp_rest", "rev_other_mine", "levy_rate", "opex_fixed", "inv_income",
    "tax_rate", "nci_share",
    "equity", "r_perp", "r_li", "r_rest",
    "axis_g2_aucu", "axis_g2_li", "g2_aucu", "g2_li", "g2_rest", "g2",
    "pe_own_min", "pe_own_max", "pb_floor",
]

# Axis「永续 g2（YYYY-MM-DD）」row: the shared perpetual g every mount reads.
_AXIS_G2_ROW = re.compile(r"^\|\s*\*\*永续 g2（[0-9-]+）\*\*\s*\|\s*\*\*([0-9.]+)%", re.MULTILINE)


def axis_g2(path: Path) -> float:
    m = _AXIS_G2_ROW.search(path.read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f"{path.name}: no 永续 g2 row")
    return float(m.group(1)) / 100.0


def first_float(pattern: str, md: str) -> float | None:
    m = re.search(pattern, md)
    return float(m.group(1)) if m else None


def prices(inp: dict[str, float], tag: str) -> tuple[float, float, float, float]:
    p_au = inp[f"lme_au_{tag}"] / OZ_TO_G * inp["fx_usd_cny"] * inp["realization_au"]
    p_cu = inp[f"lme_cu_{tag}"] * inp["fx_usd_cny"] * inp["realization_cu"]
    p_ag = inp["price_ag_m"] * inp[f"lme_au_{tag}"] / inp["lme_au_m"]
    p_li = inp[f"li2co3_{tag}"] * inp["realization_li"]
    return p_au, p_cu, p_ag, p_li


def scenario(inp: dict[str, float], tag: str) -> dict[str, float]:
    p_au, p_cu, p_ag, p_li = prices(inp, tag)
    disc = (1.0 + inp["r_disc_li"]) ** (-inp["n_disc_li"])

    gp_au = inp["vol_au_g"] * (p_au - inp["cost_au"])
    gp_cu = inp["vol_cu_t"] * (p_cu - inp["cost_cu"])
    gp_ag = inp["vol_ag_g"] * (p_ag - inp["cost_ag"])
    gp_li = inp["vol_li_t"] * (p_li - inp["cost_li"]) * disc
    rev_li = inp["vol_li_t"] * p_li * disc

    gp = gp_au + gp_cu + gp_ag + inp["gp_rest"] + gp_li
    mine_rev = (
        inp["vol_au_g"] * p_au
        + inp["vol_cu_t"] * p_cu
        + inp["rev_other_mine"]
        + rev_li
    )
    levy = mine_rev * inp["levy_rate"]
    pretax = gp - levy - inp["opex_fixed"] + inp["inv_income"]
    net = pretax * (1.0 - inp["tax_rate"])
    parent = net * (1.0 - inp["nci_share"])
    return {
        "p_au": p_au, "p_cu": p_cu, "p_ag": p_ag, "p_li": p_li,
        "gp_au": gp_au, "gp_cu": gp_cu, "gp_ag": gp_ag, "gp_li": gp_li,
        "gp": gp, "levy": levy, "pretax": pretax, "net_income": net,
        "parent": parent, "eps": parent / inp["shares"], "disc": disc,
        # Leg gross-profit shares: how parent NI is split across baskets (A11).
        "w_metal": (gp_au + gp_cu + gp_ag) / gp,
        "w_li": gp_li / gp,
        "w_rest": inp["gp_rest"] / gp,
    }


def leg_multiples(s: dict[str, float], inp: dict[str, float], r_shift: float = 0.0) -> dict[str, float]:
    """Per-leg Gordon PE at the tier's company ROE; r_shift is the implied-r δ probe."""
    roe = s["parent"] / inp["equity"]
    return {
        leg: perpetual_pe(inp[g_key], roe, inp[r_key] + r_shift)
        for leg, (r_key, g_key) in LEGS.items()
    }


def anchor(s: dict[str, float], pe: dict[str, float]) -> float:
    """Sum-of-legs anchor: EPS × Σ leg share × leg PE (Formula step 9)."""
    return s["eps"] * (s["w_metal"] * pe["metal"] + s["w_li"] * pe["li"] + s["w_rest"] * pe["rest"])


def lithium_parent_standalone(asp: float, vol: float, inp: dict[str, float]) -> float:
    """Marginal parent from a lithium volume×ASP block (levy on li rev only)."""
    gp = (asp - inp["cost_li"]) * vol
    rev = asp * vol
    pbt = gp - inp["levy_rate"] * rev
    return pbt * (1.0 - inp["tax_rate"]) * (1.0 - inp["nci_share"])


def implied_delta(S: dict[str, dict[str, float]], inp: dict[str, float]) -> float:
    """δ added to every leg's basket r so that the M anchor equals the price."""
    lo, hi = -0.08, 0.15
    for _ in range(100):
        mid = (lo + hi) / 2
        if anchor(S["m"], leg_multiples(S["m"], inp, mid)) > inp["price"]:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


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
    baskets = parse_baskets(md)

    errors: list[str] = []
    for metal, keys in (
        ("gold", ("lme_au_l", "lme_au_m", "lme_au_h")),
        ("copper", ("lme_cu_l", "lme_cu_m", "lme_cu_h")),
        ("li2co3", ("li2co3_l", "li2co3_m", "li2co3_h")),
    ):
        lo, mid, hi = (inp[k] for k in keys)
        if not (lo < mid < hi):
            errors.append(f"{metal} ladder violated: {lo}/{mid}/{hi}")
    if inp["r_disc_li"] <= 0 or inp["n_disc_li"] < 0 or inp["n_disc_li_plan"] < 0:
        errors.append("lithium discount inputs invalid")
    if inp["n_disc_li"] != 0:
        errors.append("base deck lithium is current volume and must not be discounted (A12)")
    if abs(inp["r_disc_li"] - inp["r_li"]) > 1e-9:
        errors.append(f"r_disc_li={inp['r_disc_li']} must equal the lithium leg basket r r_li={inp['r_li']} (A12)")
    # Gordon inputs (valuation-rules「§r 篮子」): every leg's r is its named
    # basket's value, every g sits under that leg's cap, r − g off the pole, and
    # the axis rows referenced verbatim (they are not adopted, A21).
    for leg, (r_key, g_key) in LEGS.items():
        if r_key not in baskets:
            errors.append(f"{r_key}: no 篮 N in its Inputs source cell (A26)")
        errors += check_r(inp[r_key], r_key, baskets.get(r_key))
        errors += check_g_cap(inp[g_key], inp[r_key], g_key)
        if inp[r_key] - inp[g_key] < MIN_R_MINUS_G:
            errors.append(f"{leg}: r − g = {inp[r_key] - inp[g_key]:.4f} < {MIN_R_MINUS_G} (pole)")
    errors += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    errors += check_g_cap(inp["axis_g2_aucu"], inp["r_perp"], "axis_g2_aucu")
    errors += check_g_cap(inp["axis_g2_li"], inp["r_li"], "axis_g2_li")
    for k, path in (("axis_g2_aucu", AXIS_AU_CU), ("axis_g2_li", AXIS_LI2CO3)):
        want = axis_g2(path)
        if abs(inp[k] - want) > 1e-9:
            errors.append(f"{k}={inp[k]} vs {path.name} 永续 g2 {want}")
    for k in inp:
        if k.startswith("p_"):
            errors.append(f"probability-style input {k} in Inputs")
    if abs(inp["cost_li"] - LI_COST_H1) / LI_COST_H1 > 0.01:
        errors.append(f"cost_li {inp['cost_li']:.2f} vs H1-implied {LI_COST_H1:.2f}")
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    errors += check_au_cu_mount(
        (inp["lme_au_l"], inp["lme_au_m"], inp["lme_au_h"]),
        (inp["lme_cu_l"], inp["lme_cu_m"], inp["lme_cu_h"]),
    )
    errors += check_li2co3_mount(
        (inp["li2co3_l"], inp["li2co3_m"], inp["li2co3_h"]),
    )
    peer = parse_inputs(PEER.read_text(encoding="utf-8"))
    for ours, theirs in SHARED_LADDER.items():
        if theirs not in peer:
            errors.append(f"peer 603993.SH missing {theirs}")
        elif abs(inp[ours] - peer[theirs]) > 1e-6:
            errors.append(
                f"shared ladder drift: {ours}={inp[ours]} vs 603993.{theirs}={peer[theirs]}"
            )
    if errors:
        print("FAIL (shared ladder):", "; ".join(errors), file=sys.stderr)
        return 1

    S = {t: scenario(inp, t) for t in ("l", "m", "h")}

    if inp["price_ag_m"] <= inp["cost_ag"]:
        errors.append("silver unit cost exceeds M price")
    if S["l"]["p_au"] <= inp["cost_au"] or S["l"]["p_cu"] <= inp["cost_cu"]:
        errors.append("unit cost exceeds L-scenario Au/Cu price")
    if S["l"]["p_li"] <= inp["cost_li"]:
        errors.append("unit cost exceeds L-scenario lithium price")

    for key, (label, ref) in M_PRICE_REF.items():
        got = S["m"][key]
        if abs(got / ref - 1.0) > M_PRICE_TOL:
            errors.append(f"{label} derived {got:.2f} vs filing-implied {ref}")

    # Lithium realization was calibrated as H1 ASP / old axis M (150,000); the
    # axis M now sits on the 2027 consensus deck, so p_li_m = H1 ASP × M/150k
    # rather than the H1 ASP itself.  The M regression below still pins M.
    li_m_ref = LI_ASP_H1 * inp["li2co3_m"] / 150_000
    if abs(S["m"]["p_li"] / li_m_ref - 1.0) > M_PRICE_TOL:
        errors.append(
            f"price_li_m derived {S['m']['p_li']:.2f} vs H1 ASP × M/150k {li_m_ref:.2f}"
        )

    # M regression: non-li 1H26×2 + lithium re-priced at axis M on H1 volume.
    li_old = lithium_parent_standalone(LI_ASP_H1, LI_VOL_H1 * 2, inp)
    li_new = lithium_parent_standalone(S["m"]["p_li"], inp["vol_li_t"], inp) * S["m"]["disc"]
    expected_m_parent = H1_2026_X2["parent"] - li_old + li_new
    got_m = S["m"]["parent"]
    if abs(got_m / expected_m_parent - 1.0) > IDENTITY_TOL:
        errors.append(
            f"M-scenario parent {got_m / YI:.1f}亿 vs expected "
            f"{expected_m_parent / YI:.1f}亿 (H1×2 − old li + PV li) "
            f"({got_m / expected_m_parent - 1:+.2%})"
        )
    if errors:
        print("FAIL (M guard):", "; ".join(errors), file=sys.stderr)
        return 1

    # --- Gordon multiples, per leg ---------------------------------------------
    # `g2` is only the blended reference (metal g × M-tier metal share); it does
    # not enter the formula but must still reconcile with the weights.
    sm = S["m"]
    g2_blend = sm["w_metal"] * inp["g2_aucu"] + sm["w_li"] * inp["g2_li"] + sm["w_rest"] * inp["g2_rest"]
    if abs(inp["g2"] - g2_blend) > 1e-4:
        errors.append(f"g2={inp['g2']} vs blended reference {g2_blend:.5f}")

    PE = {t: leg_multiples(S[t], inp) for t in ("l", "m", "h")}
    ROE = {t: S[t]["parent"] / inp["equity"] for t in ("l", "m", "h")}
    L, M, H = (anchor(S[t], PE[t]) for t in ("l", "m", "h"))
    eq_pe = {t: anchor(S[t], PE[t]) / S[t]["eps"] for t in ("l", "m", "h")}
    # Guardrail (裁决顺序 ③): the growth leg's multiple and the blended
    # equivalent multiple both inside the own-year band; a tier outside is
    # BLOCKED, never fixed by twisting g or r (A23).
    for tag in ("l", "m", "h"):
        for label, pe in ((f"metal PE_{tag.upper()}", PE[tag]["metal"]), (f"equivalent PE_{tag.upper()}", eq_pe[tag])):
            if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
                errors.append(
                    f"guardrail: {label}={pe:.2f} outside own band [{inp['pe_own_min']}, {inp['pe_own_max']}] — BLOCKED, do not twist g"
                )

    # A9: the PB floor is disclosed, never max()-ed into L.
    floor = inp["pb_floor"] * inp["bps"]
    A = (L + M) / 2
    B = (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1

    # A2e-2c flat-multiple ladder: every tier at the metal-leg PE_M must still order.
    pe_m_metal = PE["m"]["metal"]
    flat = [S[t]["eps"] * pe_m_metal for t in ("l", "m", "h")]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken at metal PE_M={pe_m_metal:.2f}: {flat}")

    # Candidate band (A2e-7h): same formula, only the single-source 2028 plan
    # volume and its discount swapped in; leg baskets, g and ROE rule untouched.
    cand_inp = dict(inp, vol_li_t=inp["vol_li_plan"], n_disc_li=inp["n_disc_li_plan"])
    C = {t: scenario(cand_inp, t) for t in ("l", "m", "h")}
    Lc, Mc, Hc = (anchor(C[t], leg_multiples(C[t], inp)) for t in ("l", "m", "h"))
    if not (Lc < Mc < Hc):
        errors.append(f"candidate band not ordered: {Lc:.2f}/{Mc:.2f}/{Hc:.2f}")

    delta = implied_delta(S, inp)
    alt_inp = dict(inp, r_perp=ALT_METAL_BASKET_R)
    alt = [anchor(S[t], leg_multiples(S[t], alt_inp)) for t in ("l", "m", "h")]

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)
    out_sec = md.split("### Outputs", 1)[-1]
    for label, want, rx, tol in (
        ("floor", floor, r"`floor` = \*\*([0-9.]+)\*\*", TOL),
        ("L′", Lc, r"L′ = \*\*([0-9.]+)\*\*", TOL),
        ("M′", Mc, r"M′ = \*\*([0-9.]+)\*\*", TOL),
        ("H′", Hc, r"H′ = \*\*([0-9.]+)\*\*", TOL),
        ("δ", delta * 100, r"δ = \*\*([+-]?[0-9.]+)%\*\*", DELTA_TOL * 100),
    ):
        got = first_float(rx, out_sec)
        if got is None or abs(got - want) > tol:
            errors.append(f"{label}: stated {got} vs recomputed {want:.4f}")

    print(f"formula_id={FORMULA_ID}")
    print(
        "shared Au/Cu OK vs _AXIS.fed-path-gold-copper (+ peer 603993.SH); "
        "Li2CO3 OK vs _AXIS.lithium-carbonate: "
        + "/".join(f"{inp[k]:g}" for k in ("li2co3_l", "li2co3_m", "li2co3_h"))
        + " 元/t"
    )
    print(
        f"{'档':<3}{'金元/克':>9}{'铜元/吨':>10}{'锂元/吨':>10}"
        f"{'金腿':>8}{'铜腿':>8}{'银腿':>7}{'锂腿':>8}"
        f"{'毛利':>9}{'归母':>9}{'EPS':>8}"
    )
    for t in ("l", "m", "h"):
        s = S[t]
        print(
            f"{t.upper():<3}{s['p_au']:9.1f}{s['p_cu']:10.0f}{s['p_li']:10.0f}"
            f"{s['gp_au'] / YI:8.1f}{s['gp_cu'] / YI:8.1f}{s['gp_ag'] / YI:7.1f}"
            f"{s['gp_li'] / YI:8.1f}{s['gp'] / YI:9.1f}{s['parent'] / YI:9.1f}{s['eps']:8.4f}"
        )
    print(
        f"M guard OK: parent {S['m']['parent'] / YI:.1f}亿 = "
        f"H1×2 {H1_2026_X2['parent'] / YI:.1f} − old-li {li_old / YI:.1f} "
        f"+ PV-li {li_new / YI:.1f}"
    )
    print(
        "baskets: "
        + ", ".join(f"{r_key} 篮 {baskets[r_key]} r={inp[r_key]:g} g={inp[g_key]:g}" for r_key, g_key in LEGS.values())
        + f"; axis rows {inp['axis_g2_aucu']:g} / {inp['axis_g2_li']:g} referenced, not adopted; "
        f"blended reference g2 {g2_blend:.4f}"
    )
    for t in ("l", "m", "h"):
        s, pe = S[t], PE[t]
        print(
            f"  {t.upper()}: ROE {ROE[t]:.3f} | metal w {s['w_metal']:.3f} × {pe['metal']:.2f}x"
            f" + li w {s['w_li']:.3f} × {pe['li']:.2f}x + rest w {s['w_rest']:.3f} × {pe['rest']:.2f}x"
            f" -> equivalent PE {eq_pe[t]:.2f}x (own band [{inp['pe_own_min']}, {inp['pe_own_max']}])"
        )
    for dg in (-0.01, 0.01):
        shifted = dict(inp, g2_aucu=inp["g2_aucu"] + dg)
        band = [anchor(S[t], leg_multiples(S[t], shifted)) for t in ("l", "m", "h")]
        print(f"  metal g2 {dg:+.0%} -> L/M/H {band[0]:.2f}/{band[1]:.2f}/{band[2]:.2f} zone {zone_of(inp['price'], *band)}")
    # A25 谷底档 coordinates on the metal leg's r/g: (i) the measured trough→recovery
    # CAGR applied to the L numerator; (ii) the measured n with the model's own
    # L→M magnitude.  Both are printed, neither is the anchor (see docstring).
    r_metal, g_metal = inp["r_perp"], inp["g2_aucu"]
    for label, (np0, np1, n) in RECOVERY_MEASURED.items():
        g1_meas = (np1 / np0) ** (1.0 / n) - 1.0
        pe_i = recovery_two_stage_pe(g1_meas, n, g_metal, ROE["m"], r_metal)
        g1_lm = (S["m"]["eps"] / S["l"]["eps"]) ** (1.0 / n) - 1.0
        pe_ii = recovery_two_stage_pe(g1_lm, n, g_metal, ROE["m"], r_metal)
        print(
            f"谷底档坐标（A25）{label} n={n}: (i) measured CAGR {g1_meas:.1%} -> {pe_i:.1f}x -> {S['l']['eps'] * pe_i:.2f} "
            f"(vs M {M:.2f}: {'overshoot' if S['l']['eps'] * pe_i > M else 'below M'}); "
            f"(ii) L→M magnitude g1 {g1_lm:.1%} -> {pe_ii:.2f}x -> {S['l']['eps'] * pe_ii:.2f} (L/M {S['l']['eps'] * pe_ii / M:.3f}, collapsed)"
        )
    print(f"谷底 x 1/r = {S['l']['eps'] / r_metal:.2f}  (deep_discount pressure coordinate, metal-leg r)")
    print(f"floor={floor:.2f} (PB {inp['pb_floor']:g} × BPS; disclosure only, not max()-ed; L is the scenario value)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat-multiple ladder @ metal PE_M {pe_m_metal:.2f}: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    for line in tier_report((L, M, H), (eq_pe["l"], eq_pe["m"], eq_pe["h"]), (S["l"]["eps"], S["m"]["eps"], S["h"]["eps"])):
        print(line)
    print(
        f"L/M {L / M:.3f} = num {S['l']['eps'] / S['m']['eps']:.3f} x pe {eq_pe['l'] / eq_pe['m']:.3f} | "
        f"H/M {H / M:.3f} = num {S['h']['eps'] / S['m']['eps']:.3f} x pe {eq_pe['h'] / eq_pe['m']:.3f} | "
        f"width {(H - L) / (2 * M):.3f}"
    )
    print(
        f"candidate (2028 规划量·公司指引, {inp['vol_li_plan']:g} t × δ {(1 + inp['r_disc_li']) ** (-inp['n_disc_li_plan']):.4f}): "
        f"L′={Lc:.2f} M′={Mc:.2f} H′={Hc:.2f}"
    )
    print(
        f"implied r: δ={delta:+.2%} on every leg (metal {inp['r_perp'] + delta:.1%} / li·rest {inp['r_li'] + delta:.1%}) "
        f"makes M = price; alt 篮 5 metal r {ALT_METAL_BASKET_R:g} -> {alt[0]:.2f}/{alt[1]:.2f}/{alt[2]:.2f} "
        f"zone {zone_of(inp['price'], *alt)} (disclosure only)"
    )
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
