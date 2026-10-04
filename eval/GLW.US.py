#!/usr/bin/env python3
"""GLW.US (Corning) valuation eval — recompute anchors from frameworks/GLW.US.md.

frameworks/GLW.US.md is the source of truth; this script re-derives
L/M/H / A/B from the §3 Inputs table and exits 1 on mismatch.  The doc carries no
current price (AGENTS.md「现价 — 禁写契约」): which zone a quote falls in is
derived live by the daily digest and the app, so nothing here reads a price.

formula_id: glw_sotp_core_segment_pe_gordon_v8

v8 (user ruling 2026-10-04; valuation-rules 裁决表 ② / 数据优先级 / 周期票中枢
「适用范围」/ 未建模期权):

Numerator year = FY2027, the farthest consensus year with >= 2 houses AND a
range (yfinance, 18 houses, 3.853 / 4.354 / 4.990).  M = mean, H = high.
Corning is a demand-cycle manufacturer (prices negotiated, cycle in volume),
so the mid-cycle rule does not apply; L is the stock's own MEASURED digestion
year instead of the consensus low: the OC leg falls from its latest run-rate
(Q2'26 x 4) by the FY2022 -> FY2023 OC segment NI ratio (661 -> 478, the
carrier / hyperscale inventory digestion), every other leg as in M.
FY2028 has only point estimates (each house one number, no range); the ones
whose original could be checked (Barclays 5.17, Wolfe 5.75, BofA 6.50, Citi
220 / 32x) are averaged into a one-year transition g1 (n = 1), shared by all
three tiers.  The self-built leg bridge is retired as a numerator.

Legs keep the existing split: GI / Automotive / Solar revenue / LS revenue
follow the bridge factors (FY28 factors over two years from the Q2'26
run-rate; FY27 takes the geometric half-way point g^0.5), Solar / LS run-rate
losses stay flat, and OC is the RESIDUAL of company EPS (eps x shares +
close_core - GI - AU - Solar/LS losses).  Leg g1 (shared across tiers) = OC
FY28 residual (point mean) over OC FY27 residual (M) - 1; GI / AU g1 = the
bridge's second-year step.

Multiples: OC / GI / AU = two_stage_pe(g1_leg, 1, g2_leg, ROE_k, r), r = basket 4
10%.  ROE_k = FY27 EPS / FY27 OPENING BPS: the Q2'26 book rolled over the
unbooked 2H26 (FY26 consensus - 1H26 actual) at b1 = g1_co / ROE, g1_co the
NI-weighted g1 of the three Gordon legs (valuation-rules ③ 步 2, b1 = the same b
as stage 1).  g1 above ROE makes stage-1 payout negative and b1 > 1: the
model charges the growth as equity issuance (valuation-rules「两段式过渡」:
not floored, MUST be reported) — printed below.  Solar / LS stay on P/S of the
FY27 revenue.  FY27 = current FY + 1: no discounting; anchors are start-of-FY27
values.

Guardrail: only the M tier blocks against the own realised band (valuation-rules
「永续增长口径」: L / H positions are disclosure only, 2026-09-21).

Options (never touch the base hand, p hard-coded here, A2e-7a):
  * Verizon 2027-2032 LTA: annual rate re-anchored on the carrier unit (AT&T
    > $3B / 4 years ≈ $750M/yr) instead of Meta; signed 6y annuity + k=1 renewal.
  * AT&T > $3B multi-year (2026-09-29): announced after every sell-side point,
    same construction on its own disclosed rate, term 4y (2027-2030) + renewal.
  * Photonics MAP $10B by 2030 (company target; GlassBridge / glass substrate
    folded in): count = 10,000 - consensus-included 0; unit economic = the
    aligned-year OC net margin (A32 inference, held to 2030 on the company's
    "OM at or above 20%, EPS faster than sales"); valued on this ticker's OC
    ruler perpetual_pe(g2_oc, ROE_M, r) at 2030 and discounted to FY27;
    no named photonics capacity budget -> unspent capital deducted = 0
    (capital-intensity sensitivity printed).
Warrants: NVIDIA's 3M pre-funded warrant is already counted as outstanding in
EPS shares; the 15M $180 traditional warrant is out of the money at every
anchor (holder's choice) — any table-3 value above the strike is flagged.

Run:  python3 frameworks/eval/GLW.US.py
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
FORMULA_ID = "glw_sotp_core_segment_pe_gordon_v8"
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
PREV_M = 98.21  # v7 M, for the correction reconciliation (纠正对账门)

# Option tier realisation (A23a/A23b/A33/A34). Never in Inputs (A2e-7a).
P_SIGNED = {"l": 0.0, "m": 0.50, "h": 1.0}   # carrier LTAs: incremental vs substitution
P_RENEW = {"l": 0.0, "m": 0.25, "h": 1.0}    # carrier LTAs: renewed after build-out
# Photonics: M = company high-confidence / internal discount on the 2030 increment
# (0.5) x the solar precedent (profit two years late) at the basket r: 0.5/1.1^2.
P_PHOT = {"l": 0.0, "m": 0.41, "h": 1.0}

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


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    required = [
        "shares_diluted", "shares_outstanding", "prefunded_warrant", "warrant_shares", "warrant_strike",
        "eps_fy27_m", "eps_fy27_h", "eps_fy27_low",
        "eps_fy28_pt_barclays", "eps_fy28_pt_wolfe", "eps_fy28_pt_bofa", "eps_fy28_pt_citi",
        "oc_ni_fy22", "oc_ni_fy23",
        "ni_oc_q", "ni_gi_q", "ni_au_q", "sales_so_q", "sales_ls_q",
        "g_gi", "g_au", "g_so", "g_ls", "bridge_frac_fy27", "g_so_l", "sales_so_fy28_guide",
        "unalloc_rde_q", "net_interest_q", "so_ls_ni_q",
        "equity", "eps_fy26_cons", "eps_1h26",
        "r_perp", "g2_oc", "g2_gi", "g2_au", "dps_annual", "core_eps_ann",
        "pe_own_min", "pe_own_max", "ps_so", "ps_ls",
        "corp_pretax_q", "tax_core", "nci_q", "pe_corp", "net_debt", "pension",
        "contract_liab", "pp_margin",
        "sales_oc_q", "sales_oc_q_yago", "ni_oc_q_yago", "sales_oc_q1", "ni_oc_q1",
        "sales_oc_fy24", "ni_oc_fy24", "sales_oc_fy25", "ni_oc_fy25",
        "carrier_anchor", "carrier_years", "contract_years", "t_opt",
        "att_years", "t_att", "meta_anchor", "meta_years",
        "phot_rev_target", "phot_cons_included", "t_phot", "phot_capex_named", "seg_assets_oc",
        "r_disc", "capex_l", "capex_m", "capex_h",
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
    if inp["phot_cons_included"] != 0:
        guards.append("phot_cons_included must stay 0 unless a consensus year covers photonics (A34)")
    if guards:
        print("FAIL: " + "; ".join(guards), file=sys.stderr)
        return 1

    sh = inp["shares_diluted"] / MM
    tax = inp["tax_core"]
    r = inp["r_perp"]
    fr = inp["bridge_frac_fy27"]

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

    # ---- Step 2: ROE on the FY27 opening book, rolled at b1 = g1_co / ROE ----
    bps0 = inp["equity"] / sh
    unbooked = inp["eps_fy26_cons"] - inp["eps_1h26"]
    ni_leg27 = {"oc": ni_oc, "gi": {k: ni_gi[27] for k in TIERS}, "au": {k: ni_au[27] for k in TIERS}}

    def g1_co(k: str, g1s: dict[str, float]) -> float:
        return sum(ni_leg27[leg][k] * g1s[leg] for leg in LEGS) / (eps[k] * sh)

    def roe_at(k: str, g1s: dict[str, float]) -> float:
        x = g1_co(k, g1s) * unbooked / eps[k]
        if x >= 1.0:
            raise ValueError(f"opening-book roll diverges on {k}: g·N/EPS = {x:.3f}")
        return eps[k] / (bps0 / (1.0 - x))

    roe = {k: roe_at(k, g1) for k in TIERS}
    gco = {k: g1_co(k, g1) for k in TIERS}
    b1 = {k: gco[k] / roe[k] for k in TIERS}

    def leg_pe(leg: str, k: str, *, g2: float | None = None, g1s: dict[str, float] | None = None,
               rr: float | None = None, roe_k: float | None = None, trough: bool | None = None) -> float:
        # L is the measured digestion year (谷底档, valuation-rules「周期票 regime / point」):
        # the step back up is utilisation, not retention, so stage 1 pays out 100% and
        # the tail carries the mid-cycle (M-tier) ROE — recovery_two_stage_pe.  The g1
        # value itself is the shared one (user ruling 2026-10-04).
        g1s = g1 if g1s is None else g1s
        g2v = inp[f"g2_{leg}"] if g2 is None else g2
        rv = r if rr is None else rr
        if (k == "l") if trough is None else trough:
            return recovery_two_stage_pe(g1s[leg], N_STAGE, g2v, roe["m"] if roe_k is None else roe_k, rv)
        return two_stage_pe(g1s[leg], N_STAGE, g2v, roe[k] if roe_k is None else roe_k, rv)

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

    def anchor(k: str, *, pe_k: dict[str, float] | None = None, sales_so_k: float | None = None,
               ni_oc_k: float | None = None) -> tuple[dict[str, float], float]:
        pk = {leg: pe[leg][k] for leg in LEGS} if pe_k is None else pe_k
        lg = {
            "oc": (ni_oc[k] if ni_oc_k is None else ni_oc_k) * pk["oc"],
            "gi": ni_gi[27] * pk["gi"],
            "au": ni_au[27] * pk["au"],
            "so": (sales_so[k] if sales_so_k is None else sales_so_k) * inp["ps_so"],
            "ls": sales_ls * inp["ps_ls"],
            "pp": pp_locked_ni,
        }
        return lg, (sum(lg.values()) + adj) / sh

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
        "Q2'25->Q2'26": (inp["ni_oc_q"] - inp["ni_oc_q_yago"], inp["sales_oc_q"] - inp["sales_oc_q_yago"]),
        "FY24->FY25": (inp["ni_oc_fy25"] - inp["ni_oc_fy24"], inp["sales_oc_fy25"] - inp["sales_oc_fy24"]),
        "Q1->Q2'26": (inp["ni_oc_q"] - inp["ni_oc_q1"], inp["sales_oc_q"] - inp["sales_oc_q1"]),
    }
    margins = {lab: fy28_oc_margin(*p) for lab, p in pairs.items()}
    _, opt_margin = margins["Q2'25->Q2'26"]
    if not (inp["pp_margin"] < opt_margin < 1):
        errors.append(f"aligned-year OC margin {opt_margin:.4f} not above the Q2'26 print (A32)")

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

    # Photonics (A34): count x aligned margin -> 2030 NI x OC ruler at ROE_M, back to FY27.
    phot_units = inp["phot_rev_target"] - inp["phot_cons_included"]
    phot_ni = phot_units * opt_margin
    phot_pe = perpetual_pe(inp["g2_oc"], roe["m"], r)
    disc_phot = (1.0 + r) ** -(inp["t_phot"] - ANCHOR_YEAR)
    capex_unspent = inp["phot_capex_named"]
    v_phot = (phot_ni * phot_pe - capex_unspent) * disc_phot / sh

    v_parts = {"vz_s": vz_s, "vz_r": vz_r, "att_s": att_s, "att_r": att_r, "phot": v_phot}
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
          + f"; BPS0 {bps0:.3f}, unbooked 2H26 {unbooked:.3f}; g1_co "
          + "/".join(f"{gco[k]:.2%}" for k in TIERS) + "; b1 " + "/".join(f"{b1[k]:.2f}" for k in TIERS) + ")")
    p1 = {leg: {k: (1.0 if k == "l" else 1 - g1[leg] / roe[k]) for k in TIERS} for leg in LEGS}
    print("stage-1 payout 1-g1/ROE  " + "  ".join(
        f"{leg.upper()} " + "/".join(f"{p1[leg][k]:+.2f}" for k in TIERS) for leg in LEGS)
          + "  (L = trough tier, 100% payout; negative = growth funded by issuance, 发股融资的增长)")
    print("modelled issuance in 2H26 roll (b1-1)xN, USD/sh M/H: " + "/".join(f"{max(0.0, b1[k] - 1) * unbooked:.2f}" for k in ("m", "h"))
          + "; stage-1 issuance OC+GI+AU, USD/sh: " + "/".join(
              f"{sum(max(0.0, -p1[leg][k]) * ni_leg27[leg][k] for leg in LEGS) / sh:.2f}" for k in TIERS))
    print("B bucket (actual retention − b1)×N, M/H: " + "/".join(f"{(1 - payout_co - b1[k]) * unbooked:+.2f}" for k in ("m", "h")))
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
    print(f"candidate (Solar guide path FY27 {so_guide27:,.1f}): L'={cand[0]:.2f} M'={cand[1]:.2f} H'={cand[2]:.2f}")
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
    print(f"capex axis implied share (OC FY27 M NI / Q2 margin = ${rev_oc_m / 1e3:.1f}B): M {rev_oc_m * MM / inp['capex_m']:.2%}")
    print("aligned-year OC margin (FY28 OC NI {:,.1f}): ".format(ni_oc28)
          + "  ".join(f"{lab} inc {inc:.1%} -> {mg:.2%}" for lab, (inc, mg) in margins.items()))
    print(f"V_opt={v_opt:.2f}/sh: Verizon {vz_s:.2f}+{vz_r:.2f}, AT&T {att_s:.2f}+{att_r:.2f}, photonics {v_phot:.2f}  "
          f"(carrier rate {carrier_rate:,.0f}M/y x {opt_margin:.4f}; ann6 {annuity_factor(0, r_disc, inp['contract_years']):.4f} "
          f"ann4 {annuity_factor(0, r_disc, inp['att_years']):.4f}; photonics {phot_units:,.0f} x {opt_margin:.4f} = {phot_ni:,.1f}M "
          f"x PE {phot_pe:.3f} (g2 {inp['g2_oc']:g}, ROE_M {roe['m']:.4f}) = {phot_ni * phot_pe:,.0f}M @2030 x {disc_phot:.4f})  "
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
        rk = {k: roe_at(k, g1s) for k in TIERS}
        rk["l"] = rk["m"]  # trough tail runs on the mid-cycle ROE
        return {k: anchor(k, pe_k={leg: leg_pe(leg, k, g1s=g1s, roe_k=rk[k]) for leg in LEGS})[1] for k in TIERS}

    for lab, val in (("Barclays+Citi only (Wisburg-checked)", (inp["eps_fy28_pt_barclays"] + inp["eps_fy28_pt_citi"]) / 2),
                     ("+UBS 6.70 (superseded)", (sum(pts.values()) + 6.70) / (len(pts) + 1)),
                     ("OC g1 = 0", None)):
        g = 0.0 if val is None else oc_residual(val, 28) / ni_oc["m"] - 1
        s = with_g1(g)
        print(f"sens g1 {lab}: g1_oc {g:.4f} -> L/M/H = {s['l']:.2f} / {s['m']:.2f} / {s['h']:.2f}")
    # L on the consensus low instead of the digestion year.
    ni_oc_low = oc_residual(inp["eps_fy27_low"], 27)
    eps_save = eps["l"]
    eps["l"] = inp["eps_fy27_low"]
    roe_low = roe_at("l", g1)
    eps["l"] = eps_save
    pe_low = {leg: leg_pe(leg, "l", roe_k=roe_low, trough=False) for leg in LEGS}
    _, L_low = anchor("l", pe_k=pe_low, ni_oc_k=ni_oc_low)
    print(f"sens L on consensus low {inp['eps_fy27_low']:.3f}: OC {ni_oc_low:,.0f}, ROE {roe_low:.4f}, L = {L_low:.2f}")

    for lab, mg in (("company OM 20% x (1-21%)", 0.20 * 0.79), ("Q2'26 OC print", inp["pp_margin"])):
        vp = (phot_units * mg * phot_pe - capex_unspent) * disc_phot / sh
        print(f"sens photonics margin {lab} {mg:.4f}: photonics {vp:.2f}, V_opt {v_opt - v_phot + vp:.2f}")
    cap_int = inp["seg_assets_oc"] / (inp["sales_oc_q"] * 4)
    cap_need = phot_units * cap_int
    vp_cap = (phot_ni * phot_pe - cap_need) * disc_phot / sh
    print(f"sens photonics capital at OC asset intensity {cap_int:.3f} -> ${cap_need:,.0f}M deducted at 2030: photonics {vp_cap:.2f}")
    vp_late = v_phot / (1 + r) ** 2
    print(f"sens photonics two years late (2032): {vp_late:.2f}")
    meta_rate = inp["meta_anchor"] / inp["meta_years"]
    vm_s, vm_r = lta(meta_rate, inp["contract_years"], inp["t_opt"], opt_margin, r_disc)
    print(f"sens Verizon on old Meta anchor {meta_rate:,.0f}M/y: {vm_s + vm_r:.2f} (vs {vz_s + vz_r:.2f})")
    r_c = basket_r(CONTRACT_ANNUITY_BASKET)
    c_s, c_r = lta(carrier_rate, inp["contract_years"], inp["t_opt"], opt_margin, r_c)
    print(f"sens Verizon r_disc -> 篮 {CONTRACT_ANNUITY_BASKET} {r_c:.1%}: {c_s + c_r:.2f}")
    for lab, (_, mg) in margins.items():
        a_, b_ = lta(carrier_rate, inp["contract_years"], inp["t_opt"], mg, r_disc)
        c_, d_ = lta(carrier_rate, inp["att_years"], inp["t_att"], mg, r_disc)
        vp = phot_units * mg * phot_pe * disc_phot / sh
        print(f"sens opt margin {lab} {mg:.4f}: V_opt {a_ + b_ + c_ + d_ + vp:.2f}")

    atm_shares = ATM_GROSS_MM / ATM_REF_PRICE
    atm_net = ATM_GROSS_MM * (1 - ATM_FEE)
    pf = {k: (v * sh + atm_net) / (sh + atm_shares) for k, v in base.items()}
    print(f"ATM pro-forma: L/M/H = {pf['l']:.2f} / {pf['m']:.2f} / {pf['h']:.2f}")
    nci_oc = (inp["nci_q"] * 4 * (pe["oc"]["m"] - inp["pe_corp"])) / sh
    print(f"sens A8 NCI at OC M multiple {pe['oc']['m']:.2f}x: each tier −{nci_oc:.2f}")

    def band_at(dr: float) -> tuple[float, float, float]:
        return tuple(anchor(k, pe_k={leg: leg_pe(leg, k, rr=r + dr) for leg in LEGS})[1] for k in TIERS)

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
