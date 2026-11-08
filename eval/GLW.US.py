#!/usr/bin/env python3
"""GLW FY2027 SOTP and a separate optical revenue/profit bridge.

The framework Markdown is the source of truth. Q3 10-Q and post-earnings
estimates update the base; the direct optical bridge is a sensitivity, not
an alternative official numerator. Existing growth/return policies remain.

Carrier contracts have no demonstrated increment beyond the adopted forecasts
and receive no separate credit. New inside-the-box passive photonics is
separate from enterprise scale-out/scale-up. Its $10B year-end 2030 run-rate
is valued in 2031, less an explicitly estimated initial-capital proxy, with
credit only in H. That condition is neither a forecast nor a proven bound.

Run: python3 frameworks/eval/GLW.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from eval.lib.axes import check_capex_mount  # noqa: E402
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    annuity_factor,
    basket_r,
    check_branch,
    check_g_cap,
    check_r,
    check_transition_years,
    g_cap,
    payout_gap,
    perpetual_pe,
    recovery_two_stage_pe,
    two_stage_pe,
)
from eval.lib.inputs import parse_baskets  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "GLW.US.md"
AXIS_CAPEX = Path(__file__).resolve().parents[2] / "frameworks" / "axes" / "ai-capex.md"
AXIS_ROWS = (("y1", "y1_ai_capex_package"), ("y2", "y2_ai_capex_package"),
             ("ss_floor_ai_capex_package", "ss_floor_ai_capex_package"))  # A36
FORMULA_ID = "glw_sotp_core_segment_pe_gordon_v9"
ANCHOR_YEAR = 2027  # numerator year FY2027 = t1; anchors are start-of-FY27 values
TOL = 0.05
PE_HARD_CAP = 30.0  # user: generated OC PE and H / FY28 low EPS must be < this
MM = 1e6
TIERS = ("l", "m", "h")
LEGS = ("oc", "gi", "au")
N_STAGE = 1          # FY27 -> FY28
CONSENSUS_YEARS = 1  # FY28 point estimates (>= 2 houses) beyond the numerator year
G2_OC_PEER_RAW = 0.0635  # A25 untruncated peer median, reference only
CONTRACT_ANNUITY_BASKET = 1
LISTING_CCY = "USD"
OWN_CYCLE_IC = 0.093  # GI / AU own cycle 2020-2023, invested-capital basis, core reading (GAAP 5.0% stricter, both < r; A36)
PREV_M = 91.94  # previous committed M, comparison only

# Post-earnings estimates do not identify a separate carrier increment.
P_SIGNED = {"l": 0.0, "m": 0.0, "h": 0.0}
P_RENEW = {"l": 0.0, "m": 0.0, "h": 0.0}
# No independent leg-level revenue path: new photonics is H success only.
P_PHOT = {"l": 0.0, "m": 0.0, "h": 1.0}

ATM_GROSS_MM = 2000.0
ATM_FEE = 0.01
ATM_REF_PRICE = 165.96


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
        if key in ("字段名", "--------", "---") or raw in ("取值",):
            continue
        if raw in ("待补", "", "—"):
            continue
        try:
            out[key] = float(raw.replace(",", "").replace("&lt;", ""))
        except ValueError:
            continue
    return out


def first_float(pattern: str, md: str) -> float | None:
    m = re.search(pattern, md)
    return float(m.group(1)) if m else None


def _lin(cal: int, y1: int, y2: int, a: float, b: float) -> float:
    """a through Y1, linear to b at Y2, b after (valuation-rules ② 稳态回报三段)."""
    if cal <= y1:
        return a
    if cal >= y2:
        return b
    return a + (b - a) * (cal - y1) / (y2 - y1)


def path_value(t0: int, y1: int, y2: int, r_s: float, g1: float, n: int, g2: float, roe: float, r: float,
               recovery: bool = False, floor: bool = True, narrative: float | None = None) -> float:
    """Multiple on next-period earnings: n transition years at g1 (payout 1 - g1/ROE floored at 0
    unless floor=False, or 1 in the recovery form), then g2 with the RONIC path; t = 1 <-> year t0.
    narrative = cap -> RONIC = min(ROE, cap) for ever (叙事换代的腿, A36); else three segments: ROE
    through Y1, linear to min(ROE, r_s) at Y2, Gordon tail after."""
    if r - g2 <= 0:
        raise ValueError(f"perpetuity diverges: g2={g2} >= r={r}")
    pv, e, t = 0.0, 1.0, 1
    for _ in range(int(n)):
        p1 = 1.0 if recovery else 1.0 - g1 / roe
        pv += e * (max(0.0, p1) if floor else p1) / (1 + r) ** t
        e *= 1 + g1
        t += 1
    if narrative is not None:
        rn = min(roe, narrative)
        return pv + e * min(1.0, 1.0 - g2 / rn) / ((r - g2) * (1 + r) ** (t - 1))
    rs = min(roe, r_s)
    while True:
        cal = t0 + t - 1
        pay = min(1.0, 1.0 - g2 / _lin(cal, y1, y2, roe, rs))
        if cal > y1 and cal >= y2:
            return pv + e * pay / ((r - g2) * (1 + r) ** (t - 1))
        pv += e * pay / (1 + r) ** t
        e *= 1 + g2
        t += 1


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    required = [
        "shares_diluted", "shares_outstanding", "prefunded_warrant", "warrant_shares", "warrant_strike",
        "eps_fy27_m", "eps_fy27_h", "eps_fy27_low",
        "eps_fy28_pt_ms", "eps_fy28_pt_bernstein",
        "oc_ni_fy22", "oc_ni_fy23",
        "ni_oc_q", "ni_gi_q", "ni_au_q", "sales_so_q", "sales_ls_q",
        "g_gi", "g_au", "g_so", "g_ls", "bridge_frac_fy27", "g_so_l", "sales_so_fy28_guide",
        "unalloc_rde_q", "net_interest_q", "so_ls_ni_q",
        "equity", "eps_fy26_cons", "eps_ytd26", "div_q_left",
        "r_perp", "g2_oc", "g2_gi", "g2_au", "dps_annual", "core_eps_ann",
        "pe_own_min", "pe_own_max", "ps_so", "ps_ls",
        "corp_pretax_q", "tax_core", "nci_q", "pe_corp", "net_debt", "pension",
        "contract_liab", "pp_margin",
        "sales_oc_q", "sales_oc_q_yago", "ni_oc_q_yago", "sales_oc_q1", "ni_oc_q1",
        "sales_oc_fy24", "ni_oc_fy24", "sales_oc_fy25", "ni_oc_fy25",
        "carrier_anchor", "carrier_years", "carrier_unincluded", "contract_years", "t_opt",
        "att_years", "t_att", "meta_anchor", "meta_years",
        "phot_rev_target", "phot_cons_included", "t_phot", "phot_capex_unspent", "seg_assets_oc",
        "enterprise_growth_q", "carrier_growth_q", "enterprise_growth_single", "phot_margin_reference",
        "r_disc", "capex_l", "capex_m", "capex_h",
        "ss_return", "ss_cap_oc", "ss_mgmt_lo", "ss_mgmt_hi", "y1", "y2", "y1_ga", "y2_ga", "tau", "amort_q",
        "ss_floor_ai_capex_package",
    ]
    missing = [k for k in required if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1

    # ---- Step 0: input guards ----
    guards: list[str] = []
    guards += check_capex_mount((inp["capex_l"], inp["capex_m"], inp["capex_h"]))
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        guards.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")
    if not (0 < inp["pp_margin"] < 1):
        guards.append(f"pp_margin out of range: {inp['pp_margin']}")
    if not (inp["eps_fy27_low"] < inp["eps_fy27_m"] < inp["eps_fy27_h"]):
        guards.append("FY27 consensus low < mean < high violated")
    pts = {k[len("eps_fy28_pt_"):]: v for k, v in inp.items() if k.startswith("eps_fy28_pt_")}
    if len(pts) < 2:
        guards.append("FY28 needs >= 2 verified point estimates to open g1 (裁决表 ②)")
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        guards.append("r_perp: Inputs source cell names no 篮 N")
    guards += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    if abs(inp["r_disc"] - inp["r_perp"]) > 1e-9:
        guards.append(f"r_disc {inp['r_disc']} != r_perp {inp['r_perp']} (A30: 同篮)")
    for leg in LEGS:
        guards += check_g_cap(inp[f"g2_{leg}"], inp["r_perp"], f"g2_{leg}")
        if inp["r_perp"] - inp[f"g2_{leg}"] < 0.02:
            guards.append(f"r - g2_{leg} < 2% — at the pole")
    guards += check_transition_years(N_STAGE, CONSENSUS_YEARS, "g1 (FY27->FY28)")
    if inp["g2_au"] <= 0:
        guards.append(f"g2_au={inp['g2_au']:+.4f} <= 0 — full-payout branch on a growing leg (A5)")
    if inp["equity"] <= 0:
        guards.append("equity must be positive")
    if not (0 < inp["pe_own_min"] < inp["pe_own_max"]):
        guards.append("pe_own_min/max guardrail inverted")
    if not (0 <= inp["phot_cons_included"] <= inp["phot_rev_target"]):
        guards.append("photonics included revenue must lie within the opportunity")
    if inp["carrier_unincluded"] not in (0, 1):
        guards.append("carrier_unincluded must be 0 or 1")
    if inp["phot_capex_unspent"] < 0:
        guards.append("photonics unspent capital cannot be negative")
    if not (ANCHOR_YEAR + N_STAGE <= inp["y1"] < inp["y2"]):
        guards.append("high-return window must satisfy transition end <= Y1 < Y2 (A36)")
    # GI / AU: default window — Y1 = visible-year end (FY28), Y2 - Y1 = 4 (medium barrier), A36.
    if inp["y1_ga"] != ANCHOR_YEAR + N_STAGE or inp["y2_ga"] - inp["y1_ga"] != 4:
        guards.append(f"GI/AU window {inp['y1_ga']:g}/{inp['y2_ga']:g} != default "
                      f"{ANCHOR_YEAR + N_STAGE}/{ANCHOR_YEAR + N_STAGE + 4} (A36)")
    # GI / AU steady return = own cycle in order (A36, 2026-10-19): max(r, own 2020-2023 IC reading).
    if abs(inp["ss_return"] - max(inp["r_perp"], OWN_CYCLE_IC)) > 1e-9:
        guards.append(f"ss_return {inp['ss_return']:g} != max(r, own cycle {OWN_CYCLE_IC:g}) (A36)")
    if not (0.0 <= inp["tau"] < 3.0):
        guards.append("tau out of range (A37)")
    if not AXIS_CAPEX.is_file():
        guards.append("axes/ai-capex.md missing — y1 / y2 unchecked")
    else:
        ax = parse_inputs(AXIS_CAPEX.read_text(encoding="utf-8"))
        for mine, theirs in AXIS_ROWS:
            if theirs not in ax or abs(ax[theirs] - inp[mine]) > 1e-9:
                guards.append(f"{mine} {inp[mine]:g} != _AXIS.ai-capex {theirs} {ax.get(theirs)} (A36)")
    if guards:
        print("FAIL: " + "; ".join(guards), file=sys.stderr)
        return 1

    sh = inp["shares_diluted"] / MM
    tax = inp["tax_core"]
    r = inp["r_perp"]
    fr = inp["bridge_frac_fy27"]
    y1, y2, rs, tau = int(inp["y1"]), int(inp["y2"]), inp["ss_return"], inp["tau"]  # A36 / A37
    y1g, y2g = int(inp["y1_ga"]), int(inp["y2_ga"])  # GI / AU default window (A36)

    # ---- Step 1: leg split (existing rule) at FY27 and FY28 ----
    ni_gi = {27: inp["ni_gi_q"] * 4 * inp["g_gi"] ** fr, 28: inp["ni_gi_q"] * 4 * inp["g_gi"]}
    ni_au = {27: inp["ni_au_q"] * 4 * inp["g_au"] ** fr, 28: inp["ni_au_q"] * 4 * inp["g_au"]}
    sales_ls = inp["sales_ls_q"] * 4 * inp["g_ls"] ** fr
    s_so_m = inp["sales_so_q"] * 4 * inp["g_so"] ** fr
    sales_so = {"l": inp["sales_so_q"] * 4 * inp["g_so_l"], "m": s_so_m, "h": s_so_m}
    so_ls_ni = inp["so_ls_ni_q"] * 4
    close_core = (inp["unalloc_rde_q"] + inp["net_interest_q"]) * 4 * (1 - tax) + inp["nci_q"] * 4

    def oc_residual(eps: float, yr: int) -> float:
        return eps * sh + close_core - ni_gi[yr] - ni_au[yr] - so_ls_ni

    # L: own measured digestion year on the OC leg (A1).
    digest = inp["oc_ni_fy23"] / inp["oc_ni_fy22"]
    ni_oc = {
        "l": inp["ni_oc_q"] * 4 * digest,
        "m": oc_residual(inp["eps_fy27_m"], 27),
        "h": oc_residual(inp["eps_fy27_h"], 27),
    }
    eps = {
        "l": (ni_oc["l"] + ni_gi[27] + ni_au[27] + so_ls_ni - close_core) / sh,
        "m": inp["eps_fy27_m"],
        "h": inp["eps_fy27_h"],
    }
    if not (ni_oc["l"] < ni_oc["m"] < ni_oc["h"]):
        print(f"FAIL: OC numerator ladder not increasing: {ni_oc}", file=sys.stderr)
        return 1
    if not (sales_so["l"] <= sales_so["m"] <= sales_so["h"]):
        print(f"FAIL: Solar revenue ladder not monotone: {sales_so}", file=sys.stderr)
        return 1
    so_guide27 = inp["sales_so_q"] * 4 * (inp["sales_so_fy28_guide"] / (inp["sales_so_q"] * 4)) ** fr
    if so_guide27 <= sales_so["h"]:
        print("FAIL: Solar guide path not above H-tier Solar revenue — drop the candidate band (A29)",
              file=sys.stderr)
        return 1

    # FY28 transition (shared g1): point mean of verified houses.
    eps28 = sum(pts.values()) / len(pts)
    ni_oc28 = oc_residual(eps28, 28)
    g1 = {
        "oc": ni_oc28 / ni_oc["m"] - 1,
        "gi": ni_gi[28] / ni_gi[27] - 1,
        "au": ni_au[28] / ni_au[27] - 1,
    }

    # ---- Step 2: ROE on the FY27 opening book, rolled at the actual retention (A31) ----
    bps0 = inp["equity"] / sh
    unbooked = inp["eps_fy26_cons"] - inp["eps_ytd26"]
    bps_open = bps0 + unbooked - inp["dps_annual"] / 4 * inp["div_q_left"]  # user ruling 2026-10-18: actual retention over the rest of FY26
    ni_leg27 = {"oc": ni_oc, "gi": {k: ni_gi[27] for k in TIERS}, "au": {k: ni_au[27] for k in TIERS}}

    def g1_co(k: str, g1s: dict[str, float]) -> float:
        return sum(ni_leg27[leg][k] * g1s[leg] for leg in LEGS) / (eps[k] * sh)

    def roe_at(k: str, g1s: dict[str, float] | None = None, rolled: bool = False) -> float:
        """FY27 EPS / FY27 opening BPS.  rolled=True = the retired b1 = g/ROE issuance roll (disclosure)."""
        if not rolled:
            return eps[k] / bps_open
        x = g1_co(k, g1 if g1s is None else g1s) * unbooked / eps[k]
        if x >= 1.0:
            raise ValueError(f"opening-book roll diverges on {k}: g·N/EPS = {x:.3f}")
        return eps[k] / (bps0 / (1.0 - x))

    roe = {k: roe_at(k) for k in TIERS}
    gco = {k: g1_co(k, g1) for k in TIERS}
    b1 = {k: gco[k] / roe[k] for k in TIERS}
    cap_oc = inp["ss_cap_oc"]

    def leg_pe(leg: str, k: str, *, g2: float | None = None, g1s: dict[str, float] | None = None,
               rr: float | None = None, roe_k: float | None = None, trough: bool | None = None,
               floor: bool = True, oc_cap: float | None | bool = True) -> float:
        # L is the measured digestion year (谷底档, valuation-rules「周期票 regime / point」):
        # the step back up is utilisation, not retention, so stage 1 pays out 100% and
        # the tail carries the mid-cycle (M-tier) ROE — recovery_two_stage_pe.  The g1
        # value itself is the shared one (user ruling 2026-10-04).  OC = 叙事换代 (min(ROE, cap)
        # for ever); GI / AU = three segments (A36).  oc_cap=None -> OC back on three segments.
        g1s = g1 if g1s is None else g1s
        g2v = inp[f"g2_{leg}"] if g2 is None else g2
        rv = r if rr is None else rr
        rec = (k == "l") if trough is None else trough
        rk = (roe["m"] if rec else roe[k]) if roe_k is None else roe_k
        narr = (cap_oc if oc_cap is True else oc_cap) if leg == "oc" else None
        ya, yb = (y1, y2) if leg == "oc" else (y1g, y2g)
        # OC back on three segments (sensitivity only) lands on the _AXIS.ai-capex packaging-row
        # floor: own cycle unusable (business-model change), no same-business peer -> axis floor (A36).
        rsv = inp["ss_floor_ai_capex_package"] if leg == "oc" else rs
        return path_value(ANCHOR_YEAR, ya, yb, rsv, g1s[leg], N_STAGE, g2v, rk, rv, recovery=rec,
                          floor=floor, narrative=narr)  # A36

    pe = {leg: {k: leg_pe(leg, k) for k in TIERS} for leg in LEGS}
    for k in TIERS:
        if pe["oc"][k] >= PE_HARD_CAP - 1e-12:
            print(f"FAIL: generated OC PE {pe['oc'][k]:.2f}x ({k}) must be < {PE_HARD_CAP}", file=sys.stderr)
            return 1
    payout_co = inp["dps_annual"] / inp["core_eps_ann"]
    branch = check_branch(inp["g2_au"], roe["m"], r, payout_co, "g2_au")
    if branch:
        print("FAIL: " + "; ".join(branch), file=sys.stderr)
        return 1

    # ---- Step 3: legs, closing items, prepaid, anchors ----
    corp_cap = inp["corp_pretax_q"] * 4 * (1 - tax) * inp["pe_corp"]
    nci_cap = inp["nci_q"] * 4 * inp["pe_corp"]
    adj = -corp_cap - nci_cap - inp["net_debt"] - inp["pension"]
    pp_locked_ni = inp["contract_liab"] * inp["pp_margin"]

    def window(k: str, rd: float) -> float:
        """A37: unbooked rest-of-FY26 core EPS x (1 - b1), clipped at 0 (b1 > 1 = issuance-funded growth)."""
        return unbooked * max(0.0, 1.0 - b1[k]) * (1.0 + rd) ** (-tau / 2)

    def anchor(k: str, *, pe_k: dict[str, float] | None = None, sales_so_k: float | None = None,
               ni_oc_k: float | None = None, rd: float | None = None) -> tuple[dict[str, float], float]:
        pk = {leg: pe[leg][k] for leg in LEGS} if pe_k is None else pe_k
        rd = r if rd is None else rd
        df = (1.0 + rd) ** (-tau)  # A37: only the Gordon legs are FY27-opening values
        lg = {
            "oc": (ni_oc[k] if ni_oc_k is None else ni_oc_k) * pk["oc"] * df,
            "gi": ni_gi[27] * pk["gi"] * df,
            "au": ni_au[27] * pk["au"] * df,
            "so": (sales_so[k] if sales_so_k is None else sales_so_k) * inp["ps_so"],
            "ls": sales_ls * inp["ps_ls"],
            "pp": pp_locked_ni,
        }
        return lg, (sum(lg.values()) + adj) / sh + window(k, rd)

    legs_l, L = anchor("l")
    legs_m, M = anchor("m")
    legs_h, H = anchor("h")
    A, B = (L + M) / 2, (M + H) / 2
    _, H_cand = anchor("h", sales_so_k=so_guide27)
    cand = (L, M, H_cand)
    base = {"l": L, "m": M, "h": H}

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1
    eps28_low = min(pts.values())
    h_over_28l = H / eps28_low
    if h_over_28l >= PE_HARD_CAP - 1e-12:
        print(f"FAIL: H / FY28 low {h_over_28l:.2f} must be < {PE_HARD_CAP}", file=sys.stderr)
        return 1

    errors: list[str] = []

    # Guardrail: M blocks, L / H disclose (valuation-rules 2026-09-21).
    own_pe = {k: base[k] / inp["core_eps_ann"] for k in TIERS}
    if not (inp["pe_own_min"] <= own_pe["m"] <= inp["pe_own_max"]):
        errors.append(f"M = {own_pe['m']:.1f}x current annualised core EPS outside own band (③)")

    if not (cand[0] < cand[1] < cand[2]):
        errors.append(f"candidate band not ordered: {cand}")
    stated_cand = load_framework(FRAMEWORK).candidate
    if stated_cand is None:
        errors.append("候选带 line missing from Outputs (A29)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), stated_cand, cand):
            if abs(said - got) > TOL:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")

    # A2e-2c flat ladder: all tiers at the M-tier multiples.
    flat = {k: anchor(k, pe_k={leg: pe[leg]["m"] for leg in LEGS})[1] for k in TIERS}
    if not (flat["l"] < flat["m"] < flat["h"]):
        errors.append(f"flat-multiple ladder broken: {flat}")

    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
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
            errors.append(f"stated {k} not found")
        elif abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")

    # ---- Options (after anchors; cannot reach L/M/H) ----
    r_disc = inp["r_disc"]

    def fy28_oc_margin(d_ni: float, d_sales: float) -> tuple[float, float]:
        inc = d_ni / d_sales
        rev28 = inp["sales_oc_q"] * 4 + (ni_oc28 - inp["ni_oc_q"] * 4) / inc
        return inc, ni_oc28 / rev28

    pairs = {
        "latest qtr YoY": (inp["ni_oc_q"] - inp["ni_oc_q_yago"], inp["sales_oc_q"] - inp["sales_oc_q_yago"]),
        "FY24->FY25": (inp["ni_oc_fy25"] - inp["ni_oc_fy24"], inp["sales_oc_fy25"] - inp["sales_oc_fy24"]),
        "latest qtr QoQ": (inp["ni_oc_q"] - inp["ni_oc_q1"], inp["sales_oc_q"] - inp["sales_oc_q1"]),
    }
    margins = {lab: fy28_oc_margin(*p) for lab, p in pairs.items()}
    _, opt_margin = margins["latest qtr YoY"]
    if not (inp["pp_margin"] < opt_margin < 1):
        errors.append(f"aligned-year OC margin {opt_margin:.4f} not above the latest-quarter print (A32)")

    carrier_rate = inp["carrier_anchor"] / inp["carrier_years"]

    def lta(rate: float, n: float, t0: float, margin: float, rr: float) -> tuple[float, float]:
        signed = rate * margin * annuity_factor(0.0, rr, n) * (1.0 + rr) ** (ANCHOR_YEAR - t0) / sh
        return signed, signed / (1.0 + rr) ** n

    vz_s, vz_r = lta(carrier_rate, inp["contract_years"], inp["t_opt"], opt_margin, r_disc)
    att_s, att_r = lta(carrier_rate, inp["att_years"], inp["t_att"], opt_margin, r_disc)
    # 12y / 8y annuity identities (split is structure, not value).
    for name, (s_, r_), n in (("Verizon", (vz_s, vz_r), inp["contract_years"]), ("AT&T", (att_s, att_r), inp["att_years"])):
        whole = carrier_rate * opt_margin * annuity_factor(0.0, r_disc, 2 * n) * (1 + r_disc) ** (ANCHOR_YEAR - inp["t_opt"]) / sh
        if abs(s_ + r_ - whole) > 1e-9:
            errors.append(f"{name} segments do not sum to the {2 * n:.0f}y annuity")

    # Photonics (A34): first full revenue year at t_phot, valued back to FY27.
    phot_units = inp["phot_rev_target"] - inp["phot_cons_included"]
    phot_ni = phot_units * opt_margin
    # Success world uses the OC ruler: RONIC = min(ROE_M, cap) for ever.
    phot_pe = path_value(int(inp["t_phot"]), y1, y2, rs, 0.0, 0, inp["g2_oc"], roe["m"], r, narrative=cap_oc)
    disc_phot = (1.0 + r) ** -(inp["t_phot"] - ANCHOR_YEAR)
    capex_unspent = inp["phot_capex_unspent"]
    v_phot = (phot_ni * phot_pe - capex_unspent) * disc_phot / sh

    # All option parts are FY27-opening values: one more tau to today (A37).
    df_opt = (1.0 + r_disc) ** (-tau)
    carrier_credit = inp["carrier_unincluded"]
    v_parts = {"vz_s": vz_s * carrier_credit, "vz_r": vz_r * carrier_credit,
               "att_s": att_s * carrier_credit, "att_r": att_r * carrier_credit, "phot": v_phot}
    v_parts = {k: v * df_opt for k, v in v_parts.items()}
    vz_s, vz_r, att_s, att_r, v_phot = (v_parts[k] for k in ("vz_s", "vz_r", "att_s", "att_r", "phot"))
    v_opt = sum(v_parts.values())

    def opt_k(k: str) -> float:
        return (P_SIGNED[k] * (vz_s + att_s) + P_RENEW[k] * (vz_r + att_r) + P_PHOT[k] * v_phot)

    zone_v = {k: base[k] + opt_k(k) for k in TIERS}
    p_eff = {k: opt_k(k) / v_opt for k in TIERS}

    stated_vopt = first_float(r"\\\(V_\{opt\}\\\) = \*\*([0-9.]+)\*\*", out_sec)
    if stated_vopt is None:
        errors.append("stated V_opt not found in Outputs")
    elif abs(stated_vopt - v_opt) > TOL:
        errors.append(f"V_opt: stated {stated_vopt} vs recomputed {v_opt:.4f}")
    p_line = re.search(r"p_L/p_M/p_H\\\) = \*\*([\d.]+) / ([\d.]+) / ([\d.]+)\*\*", out_sec)
    if not p_line:
        errors.append("p_L/p_M/p_H line not found")
    else:
        for k, said in zip(TIERS, p_line.groups()):
            if abs(float(said) - p_eff[k]) > 0.005:
                errors.append(f"effective p_{k}: stated {said} vs {p_eff[k]:.4f}")

    table3 = out_sec.split("表3", 1)[-1] if "表3" in out_sec else ""
    for k in TIERS:
        row = re.search(rf"^\| {k.upper()} \| [\d.]+ \|.*\| \*\*([\d.]+)\*\* \|[^|]*\|\s*$", table3, re.MULTILINE)
        if not row:
            errors.append(f"table3 row {k.upper()} not found")
        elif abs(float(row.group(1)) - zone_v[k]) > TOL:
            errors.append(f"table3 {k.upper()}: stated {row.group(1)} vs recomputed {zone_v[k]:.4f}")
    over_strike = [k for k in TIERS if zone_v[k] > inp["warrant_strike"]]

    # ---- diagnostics ----
    print(f"formula_id={FORMULA_ID}")
    print(f"close_core={close_core:,.1f}M  FY27 EPS L/M/H = {eps['l']:.3f} (digestion) / {eps['m']:.3f} / {eps['h']:.3f}  "
          f"[consensus low {inp['eps_fy27_low']:.3f} not used]")
    print(f"OC digestion ratio FY22->FY23 = {digest:.4f} on run-rate {inp['ni_oc_q'] * 4:,.0f}")
    print("FY27 numerators $M  OC L/M/H = " + " / ".join(f"{ni_oc[k]:,.1f}" for k in TIERS)
          + f"  GI={ni_gi[27]:,.1f} AU={ni_au[27]:,.1f} LS sales={sales_ls:,.1f} "
          f"Solar L/M/H={sales_so['l']:,.1f}/{sales_so['m']:,.1f}/{sales_so['h']:,.1f}")
    print(f"FY28 point mean ({', '.join(f'{k} {v:g}' for k, v in pts.items())}) = {eps28:.4f}; "
          f"OC FY28 residual {ni_oc28:,.1f}; g1 OC/GI/AU = {g1['oc']:.4f}/{g1['gi']:.4f}/{g1['au']:.4f} (shared)")
    print(f"ROE L/M/H = {roe['l']:.4f}/{roe['m']:.4f}/{roe['h']:.4f} (FY27 EPS / opening BPS "
          + "/".join(f"{eps[k] / roe[k]:.2f}" for k in TIERS)
          + f"; BPS0 {bps0:.3f}, unbooked rest-of-FY26 {unbooked:.3f}; g1_co "
          + "/".join(f"{gco[k]:.2%}" for k in TIERS) + "; b1 " + "/".join(f"{b1[k]:.2f}" for k in TIERS) + ")")
    p1 = {leg: {k: (1.0 if k == "l" else 1 - g1[leg] / roe[k]) for k in TIERS} for leg in LEGS}
    print("stage-1 payout 1-g1/ROE (unfloored)  " + "  ".join(
        f"{leg.upper()} " + "/".join(f"{p1[leg][k]:+.2f}" for k in TIERS) for leg in LEGS)
          + "  (L = trough tier, 100% payout; negative floored at 0 — no issuance charge, user ruling 2026-10-18)")
    print("unfloored stage-1 issuance OC+GI+AU, USD/sh (not charged): " + "/".join(
              f"{sum(max(0.0, -p1[leg][k]) * ni_leg27[leg][k] for leg in LEGS) / sh:.2f}" for k in TIERS)
          + f"; FY27 opening BPS actual retention {bps_open:.3f} (= {bps0:.3f} + {unbooked:.3f} − {inp['dps_annual'] / 4 * inp['div_q_left']:.2f})"
          + f" vs retired b1 roll M/H " + "/".join(f"{eps[k] / roe_at(k, rolled=True):.2f}" for k in ("m", "h")))
    print("window b1 = g1_co/ROE M/H " + "/".join(f"{b1[k]:.2f}" for k in ("m", "h"))
          + "; window USD/sh " + "/".join(f"{window(k, r):.3f}" for k in TIERS) + "; OC steady "
          f"min(ROE, {cap_oc:.0%}) M/H " + "/".join(f"{min(roe[k], cap_oc):.2%}" for k in ("m", "h"))
          + f" (L tail on M); GI/AU steady min(ROE, {rs:.0%}) via Y1 {y1g} / Y2 {y2g} (default; OC-link axis {y1}/{y2} for the OC three-segment sens)")
    # cyclical multiple policy (construction §5): reverse or flat, pe_L >= pe_M.
    for leg in LEGS:
        if pe[leg]["l"] < pe[leg]["m"] - 1e-9:
            print(f"FAIL: cyclical multiple policy: {leg} PE_L {pe[leg]['l']:.2f} < PE_M {pe[leg]['m']:.2f}", file=sys.stderr)
            return 1
    print("generated PE  " + "  ".join(f"{leg.upper()} " + "/".join(f"{pe[leg][k]:.2f}" for k in TIERS) for leg in LEGS))
    au_mod, au_gap = payout_gap(inp["g2_au"], roe["m"], payout_co)
    print(f"check_branch g2_au ✓ sign only: modelled payout {au_mod:.0%} vs company {payout_co:.0%}, gap {au_gap:+.0%}")
    for lab, lg in (("L", legs_l), ("M", legs_m), ("H", legs_h)):
        print(f"legs $M  {lab}: " + " ".join(f"{k}={v:,.0f}" for k, v in lg.items())
              + "  | $/sh " + " ".join(f"{k}={v / sh:.2f}" for k, v in lg.items()))
    print(f"adj={adj:,.1f}M = {adj / sh:.2f}/sh; prepaid={pp_locked_ni:,.1f}M → {pp_locked_ni / sh:.2f}/sh")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"candidate (Solar guide path FY27 {so_guide27:,.1f}): L'={cand[0]:.2f} M'={cand[1]:.2f} H'={cand[2]:.2f}"
          f"  A'={(cand[0] + cand[1]) / 2:.2f} B'={(cand[1] + cand[2]) / 2:.2f}")
    print(f"decomposition: L/M {L / M:.3f} = OC numerator {ni_oc['l'] / ni_oc['m']:.3f} x OC PE {pe['oc']['l'] / pe['oc']['m']:.3f} | "
          f"H/M {H / M:.3f} = OC numerator {ni_oc['h'] / ni_oc['m']:.3f} x OC PE {pe['oc']['h'] / pe['oc']['m']:.3f} | "
          f"(H-L)/2M {(H - L) / 2 / M:.3f} | V_opt/M {v_opt / M:.3f}")
    print(f"flat-multiple ladder: {flat['l']:.2f}/{flat['m']:.2f}/{flat['h']:.2f}")
    print(f"guardrail: anchors / core_eps_ann = {own_pe['l']:.1f}/{own_pe['m']:.1f}/{own_pe['h']:.1f}x "
          f"vs [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] (M blocks; L/H disclosure); H' {H_cand / inp['core_eps_ann']:.1f}x")
    print(f"whole-co on own FY27 EPS L/M/H = {L / eps['l']:.2f}/{M / eps['m']:.2f}/{H / eps['h']:.2f}x; "
          f"H / FY28 low {eps28_low:g} = {h_over_28l:.2f}x (<30); H FY28-world EPS "
          f"{(ni_oc['h'] * (1 + g1['oc']) + ni_gi[28] + ni_au[28] + so_ls_ni - close_core) / sh:.2f}")
    print(f"correction gate: M {PREV_M} -> {M:.2f} ({M / PREV_M - 1:+.1%}); E_M/r = {eps['m'] / r:.2f} "
          f"({M / (eps['m'] / r) - 1:+.1%} vs it); neutral band [A,B) on TTM-ann {inp['core_eps_ann']:g} = "
          f"{A / inp['core_eps_ann']:.1f}-{B / inp['core_eps_ann']:.1f}x, on FY27E {inp['eps_fy27_m']:g} = "
          f"{A / inp['eps_fy27_m']:.1f}-{B / inp['eps_fy27_m']:.1f}x")

    rev_oc_m = ni_oc["m"] / inp["pp_margin"]
    print(f"capex axis implied share (OC FY27 M NI / latest-quarter margin = ${rev_oc_m / 1e3:.1f}B): M {rev_oc_m * MM / inp['capex_m']:.2%}")
    print("aligned-year OC margin (FY28 OC NI {:,.1f}): ".format(ni_oc28)
          + "  ".join(f"{lab} inc {inc:.1%} -> {mg:.2%}" for lab, (inc, mg) in margins.items()))
    print(f"V_opt={v_opt:.2f}/sh: Verizon {vz_s:.2f}+{vz_r:.2f}, AT&T {att_s:.2f}+{att_r:.2f}, photonics {v_phot:.2f}  "
          f"(carrier rate {carrier_rate:,.0f}M/y x {opt_margin:.4f}; ann6 {annuity_factor(0, r_disc, inp['contract_years']):.4f} "
          f"ann4 {annuity_factor(0, r_disc, inp['att_years']):.4f}; photonics {phot_units:,.0f} x {opt_margin:.4f} = {phot_ni:,.1f}M "
          f"x PE {phot_pe:.3f} (g2 {inp['g2_oc']:g}, ROE_M {roe['m']:.4f}) = {phot_ni * phot_pe:,.0f}M less initial capital {capex_unspent:,.0f}M @{inp['t_phot']:g} x {disc_phot:.4f})  "
          f"V_opt/M {v_opt / M:.1%}")
    print("zone+V: " + " ".join(f"{k.upper()}={zone_v[k]:.2f}" for k in TIERS)
          + f"  A'={(zone_v['l'] + zone_v['m']) / 2:.2f} B'={(zone_v['m'] + zone_v['h']) / 2:.2f}  "
          + "p_eff=" + "/".join(f"{p_eff[k]:.4f}" for k in TIERS))
    print("table3 parts M: carrier signed {:.2f} renew {:.2f} photonics {:.2f}; H: {:.2f} {:.2f} {:.2f}".format(
        P_SIGNED["m"] * (vz_s + att_s), P_RENEW["m"] * (vz_r + att_r), P_PHOT["m"] * v_phot,
        vz_s + att_s, vz_r + att_r, v_phot))
    print(f"warrant: 15M @ {inp['warrant_strike']:g} out of the money at every anchor; table3 above strike: {over_strike or 'none'}; "
          f"fully diluted check = outstanding {inp['shares_outstanding'] / MM:.2f}M + pre-funded {inp['prefunded_warrant'] / MM:g}M "
          f"vs EPS-diluted {sh:g}M")

    # ---- sensitivities ----
    def deck(**kw) -> dict[str, float]:
        return {k: anchor(k, **kw)[1] for k in TIERS}

    for g in (inp["g2_oc"] - 0.01, inp["g2_oc"] + 0.01, G2_OC_PEER_RAW):
        pk = {k: {leg: leg_pe(leg, k, g2=g if leg == "oc" else None) for leg in LEGS} for k in TIERS}
        s = {k: anchor(k, pe_k=pk[k])[1] for k in TIERS}
        tag = " (above cap, reference only)" if g > g_cap(r) + 1e-9 else ""
        print(f"sens g2_oc={g:.4f}{tag}: L/M/H = {s['l']:.2f} / {s['m']:.2f} / {s['h']:.2f}")
    for leg in ("gi", "au"):
        for g in (inp[f"g2_{leg}"] - 0.01, inp[f"g2_{leg}"] + 0.01):
            pk = {k: {lg: leg_pe(lg, k, g2=g if lg == leg else None) for lg in LEGS} for k in TIERS}
            s = {k: anchor(k, pe_k=pk[k])[1] for k in TIERS}
            print(f"sens g2_{leg}={g:+.4f}: L/M/H = {s['l']:.2f} / {s['m']:.2f} / {s['h']:.2f}")

    def with_g1(g1_oc: float) -> dict[str, float]:
        g1s = dict(g1, oc=g1_oc)
        return {k: anchor(k, pe_k={leg: leg_pe(leg, k, g1s=g1s) for leg in LEGS})[1] for k in TIERS}

    def with_pe(**kw) -> dict[str, float]:
        return {k: anchor(k, pe_k={leg: leg_pe(leg, k, **kw) for leg in LEGS})[1] for k in TIERS}

    # A36 steady-return readings for the OC leg.
    for lab, cap in ((f"OC back on three segments (axis floor {inp['ss_floor_ai_capex_package']:.0%}, Y1/Y2)", None),
                     (f"OC steady at management ROIC target, low {inp['ss_mgmt_lo']:.0%}", inp["ss_mgmt_lo"]),
                     (f"OC steady at management ROIC target, high {inp['ss_mgmt_hi']:.0%}", inp["ss_mgmt_hi"])):
        s = with_pe(oc_cap=cap)
        print(f"sens {lab}: L/M/H = {s['l']:.2f} / {s['m']:.2f} / {s['h']:.2f}")
    s = with_pe(floor=False)
    print(f"sens stage-1 payout not floored (issuance charged): L/M/H = {s['l']:.2f} / {s['m']:.2f} / {s['h']:.2f}")
    rr_ = {k: roe_at(k, rolled=True) for k in ("m", "h")}
    rr_["l"] = rr_["m"]
    s = {k: anchor(k, pe_k={leg: leg_pe(leg, k, roe_k=rr_[k]) for leg in LEGS})[1] for k in TIERS}
    print(f"sens opening book on the retired b1 roll (ROE M/H {rr_['m']:.4f}/{rr_['h']:.4f}): "
          f"L/M/H = {s['l']:.2f} / {s['m']:.2f} / {s['h']:.2f}")
    amort_ps = inp["amort_q"] * 4 * (1 - tax) * inp["pe_corp"] / sh
    print(f"sens amortisation capitalised again (retired): each tier −{amort_ps:.2f}")
    y1gs, y2gs = y1g, y2g
    y1g, y2g = y1, y2
    s = with_pe()
    print(f"sens GI/AU on the OC-link axis window Y1 {y1g} / Y2 {y2g} (retired 2026-10-18): "
          f"L/M/H = {s['l']:.2f} / {s['m']:.2f} / {s['h']:.2f}")
    y1g, y2g = y1gs, y2gs

    for lab, val in (("Morgan Stanley only", inp["eps_fy28_pt_ms"]),
                     ("Bernstein only", inp["eps_fy28_pt_bernstein"]),
                     ("OC g1 = 0", None)):
        g = 0.0 if val is None else oc_residual(val, 28) / ni_oc["m"] - 1
        s = with_g1(g)
        print(f"sens g1 {lab}: g1_oc {g:.4f} -> L/M/H = {s['l']:.2f} / {s['m']:.2f} / {s['h']:.2f}")

    for lab, mg in (("company OM 20% x (1-21%) stress", 0.20 * 0.79),
                    ("latest-quarter OC print", inp["ni_oc_q"] / inp["sales_oc_q"]),
                    ("prior reference margin", inp["phot_margin_reference"])):
        vp = (phot_units * mg * phot_pe - capex_unspent) * disc_phot / sh * df_opt
        print(f"sens photonics margin {lab} {mg:.4f}: photonics {vp:.2f}, V_opt {v_opt - v_phot + vp:.2f}")
    cap_int = inp["seg_assets_oc"] / (inp["sales_oc_q"] * 4)
    cap_need = phot_units * cap_int
    vp_cap = (phot_ni * phot_pe - cap_need) * disc_phot / sh * df_opt
    if abs(capex_unspent - cap_need) > 0.01:
        errors.append("photonics initial capital does not match the disclosed asset-density proxy")
    vp_gross = phot_ni * phot_pe * disc_phot / sh * df_opt
    print(f"sens photonics initial capital proxy {cap_int:.3f}: ${cap_need:,.0f}M; "
          f"net success {vp_cap:.2f}, gross without initial capital {vp_gross:.2f}")
    vp_late = v_phot / (1 + r) ** 2
    print(f"sens photonics two years late ({inp['t_phot'] + 2:g}): {vp_late:.2f}")
    meta_rate = inp["meta_anchor"] / inp["meta_years"]
    vm_s, vm_r = lta(meta_rate, inp["contract_years"], inp["t_opt"], opt_margin, r_disc)
    print(f"excluded carrier gross audit: Verizon on old Meta anchor {meta_rate:,.0f}M/y: {(vm_s + vm_r) * df_opt:.2f} (vs {vz_s + vz_r:.2f})")
    r_c = basket_r(CONTRACT_ANNUITY_BASKET)
    c_s, c_r = lta(carrier_rate, inp["contract_years"], inp["t_opt"], opt_margin, r_c)
    print(f"excluded carrier gross audit: Verizon r_disc -> 篮 {CONTRACT_ANNUITY_BASKET} {r_c:.1%}: {(c_s + c_r) * (1 + r_c) ** (-tau):.2f}")
    for lab, (_, mg) in margins.items():
        a_, b_ = lta(carrier_rate, inp["contract_years"], inp["t_opt"], mg, r_disc)
        c_, d_ = lta(carrier_rate, inp["att_years"], inp["t_att"], mg, r_disc)
        vp = (phot_units * mg * phot_pe - capex_unspent) * disc_phot / sh
        print(f"sens opt margin {lab} {mg:.4f}: V_opt "
              f"{((a_ + b_ + c_ + d_) * carrier_credit + vp) * df_opt:.2f}")

    atm_shares = ATM_GROSS_MM / ATM_REF_PRICE
    atm_net = ATM_GROSS_MM * (1 - ATM_FEE)
    pf = {k: (v * sh + atm_net) / (sh + atm_shares) for k, v in base.items()}
    print(f"ATM pro-forma: L/M/H = {pf['l']:.2f} / {pf['m']:.2f} / {pf['h']:.2f}")
    nci_oc = (inp["nci_q"] * 4 * (pe["oc"]["m"] - inp["pe_corp"])) / sh
    print(f"sens A8 NCI at OC M multiple {pe['oc']['m']:.2f}x: each tier −{nci_oc:.2f}")

    # Independent optical revenue sensitivities never feed official numerators.
    ent_prev = (inp["sales_oc_q"] - inp["sales_oc_q_yago"] * (1 + inp["carrier_growth_q"])) / (
        inp["enterprise_growth_q"] - inp["carrier_growth_q"])
    ent_q = ent_prev * (1 + inp["enterprise_growth_q"])
    carrier_q = inp["sales_oc_q"] - ent_q
    inc_margin = pairs["latest qtr YoY"][0] / pairs["latest qtr YoY"][1]
    other_ps = M - legs_m["oc"] / sh - window("m", r)
    bridge_section = out_sec.split("表4 · 光通信收入桥", 1)[-1]
    for label, ent_growth, margin in (
            ("企业网络 +30%", 0.30, inc_margin),
            ("企业网络 +40%", 0.40, inc_margin),
            ("企业网络 +51%", inp["enterprise_growth_single"], inc_margin),
            ("企业网络 +51%·利润率持平", inp["enterprise_growth_single"],
             inp["ni_oc_q"] / inp["sales_oc_q"])):
        revenues = {yr: 4 * (ent_q * (1 + ent_growth) ** (yr - 2026)
                    + carrier_q * (1 + inp["carrier_growth_q"]) ** (yr - 2026)) for yr in (2027, 2028)}
        profits = {yr: inp["ni_oc_q"] * 4 + (rev - inp["sales_oc_q"] * 4) * margin
                   for yr, rev in revenues.items()}
        eps_b = (profits[2027] + ni_gi[27] + ni_au[27] + so_ls_ni - close_core) / sh
        roe_b = eps_b / bps_open
        pe_b = path_value(ANCHOR_YEAR, y1, y2, rs, profits[2028] / profits[2027] - 1,
                          N_STAGE, inp["g2_oc"], roe_b, r, narrative=cap_oc)
        optical_ps = profits[2027] * pe_b * (1 + r) ** (-tau) / sh
        total_ps = optical_ps + other_ps
        print(f"AI bridge {label}: OC NI27/28 {profits[2027]:.2f}/{profits[2028]:.2f}M; "
              f"optical {optical_ps:.2f} + other {other_ps:.2f} = {total_ps:.2f}")
        row = next((ln for ln in bridge_section.splitlines() if ln.startswith(f"| {label} |")), "")
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        if len(cells) != 4:
            errors.append(f"optical bridge row missing: {label}")
        elif any(abs(float(said) - got) > TOL for said, got in zip(cells[1:], (optical_ps, other_ps, total_ps))):
            errors.append(f"optical bridge row mismatch: {label}")

    def band_at(dr: float) -> tuple[float, float, float]:
        return tuple(anchor(k, pe_k={leg: leg_pe(leg, k, rr=r + dr) for leg in LEGS}, rd=r + dr)[1] for k in TIERS)

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_at)
    if any(abs(x - y) > TOL for x, y in zip(band_at(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1
    write_rf_readings("GLW.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
