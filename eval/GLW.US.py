#!/usr/bin/env python3
"""GLW.US (Corning) valuation eval — recompute anchors from frameworks/GLW.US.md.

frameworks/GLW.US.md is the source of truth; this script re-derives
L/M/H / A/B / zone from the §3 Inputs table and exits 1 on mismatch.

formula_id: glw_sotp_core_segment_pe_gordon_v6

Main ruler (base hand, zero probability): FY2028 segment SOTP whose tier ladder
lives in the numerator. M-tier leg numerators come from the leg bridge
(ni_*_q×4×g_*). L and H take the two ends of the sell-side FY28E EPS range
(Barclays 5.17 / Citi ≈6.88, n=2, same source) and back the OC numerator out as
a RESIDUAL: eps_k × shares + close_core − GI − AU − Solar/LS run-rate losses,
where close_core (unallocated RD&E + net interest, after tax, + NCI) is the
core-EPS-to-segment-NI gap. GI, Automotive and LS numerators are flat across
tiers; Solar revenue is frozen at the Q2 run-rate in L (A2e-1 "收入冻结").

Multiples are GENERATED, not borrowed (AGENTS.md 永续增长口径, A2e-5b): each PE
leg is `perpetual_pe(g2_leg, ROE_k, r_perp)` with tier ROE = eps_fy28_k × shares
/ equity (no leg equity exists, so the company ROE stands in for every leg).
The perpetual g is flat across tiers — `cyclical` primary, A2e-5 — so the only
tier-to-tier movement in a multiple is the ROE term: OC g2 6.0% (peer
cross-section median 6.35% truncated at g_cap(r)) gives 20.8/21.2/21.9x, GI g2 0
gives 10x, Automotive g2 +1.23% (auto-supplier retention-branch median, n=2:
GNTX / BWA; APTV / LEA sit below 1/r on ROE >> r and are unreachable at r=10%,
so BLOCKED and excluded — valuation-rules「反解分支」单调区) gives 11.0/11.1/11.1x.
The auto leg has no payout of its own, so `check_branch` runs on the company
payout (dps_annual / core_eps_ann ≈ 36%) and, with ROE >> r, reduces to the
sign test; `payout_gap` is printed as a disclosure only. Solar / LS stay on P/S
(loss-making). The v4 flat 22/11/10 band is retired; the own realised core-PE
series (A16, 19.7–91.1x on the trailing-quarter annualised core EPS) is now the
guardrail, not a source.

r is not a per-ticker dial: every `r*` Inputs row names its basket (`篮 N`) and
the value must equal gordon.BASKET_R for that basket. Here OC / GI / AU and the
option-leg r_disc all sit in basket 4 龙头制造 (10%, A30); `check_r(r, where,
basket)` enforces the match and `check_g_cap(g, r, where)` caps every g2 at
g_cap(r) = min(6%, r - 4%).

Constraint: generated OC PE < 30 and H / eps_fy28_l < 30 (the user's FY28<30
rule read against the strictest denominator). Prepaid locked profit enters in
full (cash already received); closing items are capitalised as before.

Candidate band (A2e-7h, A29): management's Solar 2028 revenue target ($3.0B,
company guidance, above the M/H bridge value 2,628) replaces only the H-tier
Solar revenue -> H'. Same formula, same g2 / r / P/S; L' and M' copy the base
deck. Never a zone input. There is no transition stage anywhere (FY29 has no
consensus), so `check_transition_years` does not apply.

Sensitivities printed for the A2f record: g2_oc ±1pp (the +1pp side crosses
g_cap(r) and is reference only) and the untruncated peer median 6.35%; g2_gi ±1pp
because GI's g2 = 0 has no peer anchor; g2_au ±1pp; and the OC perpetual g that
would put each tier on the guardrail edges (band-as-evidence, 裁决顺序 ③).

Option leg (A23a/A23b), which never touches the base hand: the Verizon 2027-2032
LTA discloses volume (80M+ miles) but no price per fibre-km, so its numerator is
not computable — 7c-1 allows a fuzzy count, never a fuzzy unit economic. Its
ceiling anchor bypasses the price layer and takes Corning's own largest
disclosed OC LTA in dollar terms (Meta, up to $6B through 2030) as an ANNUAL
RATE, capitalised as a zero-growth annuity over contract_years at r_disc (the
deal has a fixed term; Gordon would assume T=∞). Renewal past 2032 is an option,
not an annuity: k=1 more identical cycle discounted by contract_years, with its
own p_k. Everything past 2038 is worth zero here. The two segments sum to the
12-year annuity by construction; the guard below asserts it. Tier realisation
p_k is hard-coded on purpose: p-class fields must never appear in §3 Inputs
(A2e-7a).

Run:  python3 eval/GLW.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# eval/lib/frameworks.py imports `eval.lib.inputs`, so the repo root (not
# eval/) must be importable.
REPO_ROOT = Path(__file__).resolve().parents[1]
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
    g_cap,
    payout_gap,
    perpetual_pe,
)
from eval.lib.inputs import parse_baskets  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "GLW.US.md"
FORMULA_ID = "glw_sotp_core_segment_pe_gordon_v6"
TOL = 0.05
PE_OC_HARD_CAP = 30.0  # strict: generated OC PE and H/eps_fy28_l must be < this
MM = 1e6
TIERS = ("l", "m", "h")
# A25: the untruncated AI-interconnect peer median behind g2_oc; printed as a
# reference sensitivity only, never used as an anchor (it sits above g_cap).
G2_OC_PEER_RAW = 0.0635
# A23a upgrade path: if the Verizon deal ever discloses its rate, r_disc moves
# to the fixed-contract annuity basket. Printed as a sensitivity only.
CONTRACT_ANNUITY_BASKET = 1

# Tier realisation of the two Verizon LTA option segments (A23a / A23b). Lives
# here rather than in §3 Inputs because A2e-7a forbids p-class fields from
# reaching the anchors. The signed segment carries "incremental vs substitution";
# the renewal segment carries "renewed vs not" and sits lower at M because the
# announcement ties this deal to a 40-50M passings build-out, after which demand
# degrades to maintenance and upgrade.
P_SIGNED = {"l": 0.0, "m": 0.50, "h": 1.0}
P_RENEW = {"l": 0.0, "m": 0.25, "h": 1.0}

# ATM programme constants (A24). Deliberately NOT in Inputs: nothing has been
# sold, so the base hand must not pre-fill dilution. They only feed the
# pro-forma sensitivity line — full execution at the 424B5 illustration price.
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
        "price",
        "shares_diluted",
        "eps_fy28_l",
        "eps_fy28_h",
        "ni_oc_q",
        "ni_gi_q",
        "ni_au_q",
        "sales_so_q",
        "sales_ls_q",
        "g_oc",
        "g_gi",
        "g_au",
        "g_so",
        "g_ls",
        "g_so_l",
        "sales_so_fy28_guide",
        "unalloc_rde_q",
        "net_interest_q",
        "so_ls_ni_q",
        "equity",
        "r_perp",
        "g2_oc",
        "g2_gi",
        "g2_au",
        "dps_annual",
        "core_eps_ann",
        "pe_own_min",
        "pe_own_max",
        "ps_so",
        "ps_ls",
        "corp_pretax_q",
        "tax_core",
        "nci_q",
        "pe_corp",
        "net_debt",
        "pension",
        "contract_liab",
        "pp_margin",
        "lta_anchor",
        "lta_years",
        "contract_years",
        "r_disc",
        "capex_l",
        "capex_m",
        "capex_h",
    ]
    missing = [k for k in required if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1

    # ---- Step 0: input guards ----
    guards: list[str] = []
    # Demand-side mount on the AI-capex axis: rungs must be the axis's own.
    guards += check_capex_mount((inp["capex_l"], inp["capex_m"], inp["capex_h"]))
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        guards.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")
    if not (0 < inp["pp_margin"] < 1):
        guards.append(f"pp_margin out of range: {inp['pp_margin']}")
    if not (inp["eps_fy28_l"] < inp["eps_fy28_h"]):
        guards.append("eps_fy28_l must be < eps_fy28_h")
    # Gordon 口径: every r row names its basket and carries that basket's value
    # (valuation-rules「§r 篮子」), every perpetual g is at or below g_cap(r), and
    # the perpetuity converges.
    baskets = parse_baskets(md)
    for where in ("r_perp", "r_disc"):
        if where not in baskets:
            guards.append(f"{where}: Inputs source cell names no 篮 N (valuation-rules「§r 篮子」)")
        guards += check_r(inp[where], where, baskets.get(where))
    for leg in ("oc", "gi", "au"):
        guards += check_g_cap(inp[f"g2_{leg}"], inp["r_perp"], f"g2_{leg}")
        if inp["r_perp"] - inp[f"g2_{leg}"] < 0.02:
            guards.append(f"r - g2_{leg} < 2% — at the pole (AGENTS.md)")
    # A5: g2_au is the retention-branch peer median and the leg's own direction
    # is up (Q2'26 segment NI +4% YoY, bridge g_au 1.20), so a g2 <= 0 source is
    # the wrong branch whatever the payout says.
    if inp["g2_au"] <= 0:
        guards.append(f"g2_au={inp['g2_au']:+.4f} <= 0 — full-payout branch on a growing leg (A5)")
    if inp["equity"] <= 0:
        guards.append("equity must be positive")
    if not (0 < inp["pe_own_min"] < inp["pe_own_max"]):
        guards.append("pe_own_min/max guardrail inverted")
    if guards:
        print("FAIL: " + "; ".join(guards), file=sys.stderr)
        return 1

    sh = inp["shares_diluted"] / MM  # work in $M and M shares
    tax = inp["tax_core"]
    r = inp["r_perp"]

    # ---- Step 1: M-tier leg numerators from the bridge (A1) ----
    ni_gi = inp["ni_gi_q"] * 4 * inp["g_gi"]
    ni_au = inp["ni_au_q"] * 4 * inp["g_au"]
    ni_oc_m = inp["ni_oc_q"] * 4 * inp["g_oc"]
    sales_ls = inp["sales_ls_q"] * 4 * inp["g_ls"]
    sales_so = {
        "l": inp["sales_so_q"] * 4 * inp["g_so_l"],
        "m": inp["sales_so_q"] * 4 * inp["g_so"],
        "h": inp["sales_so_q"] * 4 * inp["g_so"],
    }
    so_ls_ni = inp["so_ls_ni_q"] * 4
    # Core-EPS-to-segment-NI gap: unallocated RD&E and net interest after tax,
    # plus NCI. Amortisation is already excluded from core.
    close_core = (inp["unalloc_rde_q"] + inp["net_interest_q"]) * 4 * (1 - tax) + inp["nci_q"] * 4
    eps_m = (ni_oc_m + ni_gi + ni_au + so_ls_ni - close_core) / sh

    # ---- Step 2: L / H OC numerator = residual of the sell-side EPS ends ----
    eps = {"l": inp["eps_fy28_l"], "m": eps_m, "h": inp["eps_fy28_h"]}
    ni_oc = {
        k: eps[k] * sh + close_core - ni_gi - ni_au - so_ls_ni for k in ("l", "h")
    }
    ni_oc["m"] = ni_oc_m
    if not (ni_oc["l"] < ni_oc["m"] < ni_oc["h"]):
        print(f"FAIL: OC numerator ladder not increasing: {ni_oc}", file=sys.stderr)
        return 1
    if not (sales_so["l"] <= sales_so["m"] <= sales_so["h"]):
        print(f"FAIL: Solar revenue ladder not monotone: {sales_so}", file=sys.stderr)
        return 1
    # A29: the guidance is a candidate input only while it sits above what the
    # base deck already carries; inside the bridge it is not a missing input.
    if inp["sales_so_fy28_guide"] <= sales_so["h"]:
        print(
            f"FAIL: sales_so_fy28_guide {inp['sales_so_fy28_guide']:,.0f} <= H-tier Solar revenue "
            f"{sales_so['h']:,.0f} — not a missing input, drop the candidate band (A29)",
            file=sys.stderr,
        )
        return 1

    # ---- Step 3: multiples generated by Gordon (A2 / A25-A27) ----
    # Tier ROE from one equity field; g2 is flat across tiers, so the multiple
    # moves only through the retention term. Company ROE stands in for every
    # leg (no segment equity is disclosed).
    roe = {k: eps[k] * sh / inp["equity"] for k in TIERS}
    pe = {
        leg: {k: perpetual_pe(inp[f"g2_{leg}"], roe[k], r) for k in TIERS}
        for leg in ("oc", "gi", "au")
    }
    for k in TIERS:
        if pe["oc"][k] >= PE_OC_HARD_CAP - 1e-12:
            print(f"FAIL: generated OC PE {pe['oc'][k]:.2f}x ({k}) must be < {PE_OC_HARD_CAP}",
                  file=sys.stderr)
            return 1
    # valuation-rules「反解分支」(A5): the auto leg has no observable payout, so
    # the company payout stands in. With ROE_M >> r (单调区) check_branch is the
    # sign test only; the magnitude gap is a disclosure (printed below), not a
    # red line — on a ~40% book any g2 <= G_CAP models >= 85% payout.
    payout_co = inp["dps_annual"] / inp["core_eps_ann"]
    branch = check_branch(inp["g2_au"], roe["m"], r, payout_co, "g2_au")
    if branch:
        print("FAIL: " + "; ".join(branch), file=sys.stderr)
        return 1

    # ---- Step 4-5: legs, closing items, prepaid, anchors ----
    corp_cap = inp["corp_pretax_q"] * 4 * (1 - tax) * inp["pe_corp"]
    nci_cap = inp["nci_q"] * 4 * inp["pe_corp"]
    adj = -corp_cap - nci_cap - inp["net_debt"] - inp["pension"]
    # Cash already received: full locked NI in every tier (A22, A2e-7a / 7c-4).
    pp_locked_ni = inp["contract_liab"] * inp["pp_margin"]

    def legs(
        k: str,
        pe_oc_k: float | None = None,
        *,
        pe_gi_k: float | None = None,
        pe_au_k: float | None = None,
        sales_so_k: float | None = None,
    ) -> dict[str, float]:
        return {
            "oc": ni_oc[k] * (pe["oc"][k] if pe_oc_k is None else pe_oc_k),
            "gi": ni_gi * (pe["gi"][k] if pe_gi_k is None else pe_gi_k),
            "au": ni_au * (pe["au"][k] if pe_au_k is None else pe_au_k),
            "so": (sales_so[k] if sales_so_k is None else sales_so_k) * inp["ps_so"],
            "ls": sales_ls * inp["ps_ls"],
            "pp": pp_locked_ni,
        }

    def anchor(k: str, pe_oc_k: float | None = None, **kw: float) -> tuple[dict[str, float], float]:
        lg = legs(k, pe_oc_k, **kw)
        return lg, (sum(lg.values()) + adj) / sh

    legs_l, L = anchor("l")
    legs_m, M = anchor("m")
    legs_h, H = anchor("h")
    A = (L + M) / 2
    B = (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    # Candidate band (A29): only the H-tier Solar revenue moves to the guidance.
    _, H_cand = anchor("h", sales_so_k=inp["sales_so_fy28_guide"])
    cand = (L, M, H_cand)

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1
    h_over_eps_l = H / inp["eps_fy28_l"]
    if h_over_eps_l >= PE_OC_HARD_CAP - 1e-12:
        print(f"FAIL: H/eps_fy28_l={h_over_eps_l:.2f} must be < {PE_OC_HARD_CAP}",
              file=sys.stderr)
        return 1

    errors: list[str] = []

    # Guardrail (A6 / A27): every tier, read on the same numerator as the own
    # realised series (trailing-quarter annualised core EPS), must sit inside
    # the band the stock has actually printed. Outside is red, never a dial.
    base = {"l": L, "m": M, "h": H}
    own_pe = {k: base[k] / inp["core_eps_ann"] for k in TIERS}
    own_pe_cand = H_cand / inp["core_eps_ann"]
    for label, mult in (*((k.upper(), own_pe[k]) for k in TIERS), ("H' (candidate)", own_pe_cand)):
        if not (inp["pe_own_min"] <= mult <= inp["pe_own_max"]):
            errors.append(
                f"{label} = {mult:.1f}x current annualised core EPS, outside own realised band "
                f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] (A27)"
            )

    # Candidate band line (A2e-7h): the digest reads it through frameworks.py;
    # recompute and compare ±TOL, and it must still be a ladder.
    if not (cand[0] < cand[1] < cand[2]):
        errors.append(f"candidate band not ordered: {cand}")
    stated_cand = load_framework(FRAMEWORK).candidate
    if stated_cand is None:
        errors.append("候选带 line missing from Outputs (A29)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), stated_cand, cand):
            if abs(said - got) > TOL:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")

    # A2e-2c flat ladder: every tier at the M-tier OC multiple must still be a
    # ladder — with flat g the ladder is the OC numerator ladder plus Solar.
    flat = {k: anchor(k, pe["oc"]["m"])[1] for k in TIERS}
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
    recomputed = {"L": L, "M": M, "H": H, "A": A, "B": B}
    for k, v in recomputed.items():
        s = stated.get(k)
        if s is None:
            errors.append(f"stated {k} not found")
        elif abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")

    zm = re.search(r"zone = \*\*`([a-z_]+)`\*\*", out_sec)
    stated_zone = zm.group(1) if zm else None
    if stated_zone != zone:
        errors.append(f"zone: stated {stated_zone} vs recomputed {zone}")

    # Option leg (A23a/A23b). Deliberately computed after zone: it must not be
    # able to reach L/M/H, the cut points, the zone verdict, or the four
    # cross-ticker ratios (A2e-7a).
    r_disc, n_yrs = inp["r_disc"], inp["contract_years"]
    lta_rate = inp["lta_anchor"] / inp["lta_years"]
    ann_n = annuity_factor(0.0, r_disc, n_yrs)
    v_signed = lta_rate * inp["pp_margin"] * ann_n / sh
    v_renew = v_signed / (1.0 + r_disc) ** n_yrs
    v_opt = v_signed + v_renew

    # The two segments are one 2n-year annuity split at year n. If a later edit
    # touches one side alone they stop summing, and this catches it.
    v_two_cycle = lta_rate * inp["pp_margin"] * annuity_factor(0.0, r_disc, 2 * n_yrs) / sh
    if abs(v_opt - v_two_cycle) > 1e-9:
        errors.append(
            f"V_opt segments sum to {v_opt:.6f} but the "
            f"{2 * n_yrs:.0f}y annuity is {v_two_cycle:.6f}"
        )

    zone_v = {k: base[k] + P_SIGNED[k] * v_signed + P_RENEW[k] * v_renew for k in "lmh"}

    stated_vopt = first_float(r"\\\(V_\{opt\}\\\) = \*\*([0-9.]+)\*\*", out_sec)
    if stated_vopt is None:
        errors.append("stated V_opt not found in Outputs")
    elif abs(stated_vopt - v_opt) > TOL:
        errors.append(f"V_opt: stated {stated_vopt} vs recomputed {v_opt:.4f}")

    table3 = out_sec.split("表3", 1)[-1] if "表3" in out_sec else ""
    for k, label in (("l", "L"), ("m", "M"), ("h", "H")):
        row = re.search(
            rf"^\| {label} \| [\d.]+ \| \*\*([\d.]+)\*\* \| [\d.]+ "
            rf"\| \*\*([\d.]+)\*\* \| [\d.]+ \| \*\*([\d.]+)\*\*",
            table3,
            re.MULTILINE,
        )
        if not row:
            errors.append(f"table3 row {label} not found")
            continue
        for stated_p, hard, name in (
            (row.group(1), P_SIGNED[k], "p_signed"),
            (row.group(2), P_RENEW[k], "p_renew"),
        ):
            if abs(float(stated_p) - hard) > 1e-9:
                errors.append(f"table3 {label}: {name} stated {stated_p} vs hard-coded {hard}")
        if abs(float(row.group(3)) - zone_v[k]) > TOL:
            errors.append(f"table3 {label}: stated {row.group(3)} vs recomputed {zone_v[k]:.4f}")

    # ---- diagnostics ----
    print(f"formula_id={FORMULA_ID}")
    print(
        f"close_core={close_core:,.1f}M  eps_fy28 L/M/H = {eps['l']:.2f} / {eps['m']:.2f} (bridge-implied) / {eps['h']:.2f}"
    )
    print(
        "FY28 numerators $M  OC L/M/H = "
        f"{ni_oc['l']:,.0f} / {ni_oc['m']:,.0f} / {ni_oc['h']:,.0f} (residual / bridge / residual)  "
        f"GI={ni_gi:,.0f} AU={ni_au:,.0f} LS={sales_ls:,.0f} Solar L/M/H={sales_so['l']:,.0f}/{sales_so['m']:,.0f}/{sales_so['h']:,.0f}"
    )
    print(
        f"tier ROE L/M/H = {roe['l']:.3f}/{roe['m']:.3f}/{roe['h']:.3f} (eps x shares / equity {inp['equity']:,.0f}M)  "
        f"r={r:g} (篮 {baskets['r_perp']}; r_disc 篮 {baskets['r_disc']})  g_cap={g_cap(r):.3f}  "
        f"g2 oc/gi/au = {inp['g2_oc']:.4f}/{inp['g2_gi']:.4f}/{inp['g2_au']:.4f}"
    )
    print(
        "generated PE  OC L/M/H = "
        f"{pe['oc']['l']:.2f}/{pe['oc']['m']:.2f}/{pe['oc']['h']:.2f}x  "
        f"GI {pe['gi']['l']:.2f}/{pe['gi']['m']:.2f}/{pe['gi']['h']:.2f}x  "
        f"AU {pe['au']['l']:.2f}/{pe['au']['m']:.2f}/{pe['au']['h']:.2f}x"
    )
    au_modelled, au_gap = payout_gap(inp["g2_au"], roe["m"], payout_co)
    print(
        f"check_branch g2_au ✓ sign only (单调区: ROE_M {roe['m']:.1%} ≫ r): modelled payout "
        f"{au_modelled:.0%} vs company {payout_co:.0%} (DPS {inp['dps_annual']:g} / core EPS "
        f"{inp['core_eps_ann']:g}), gap {au_gap:+.0%} = book vs marginal ROE, not the branch (A5)"
    )
    for lab, lg in (("L", legs_l), ("M", legs_m), ("H", legs_h)):
        print(f"legs $M  {lab}: " + " ".join(f"{k}={v:,.0f}" for k, v in lg.items()))
    print(
        f"adj={adj:,.1f}M = {adj / sh:.2f}/sh; prepaid={pp_locked_ni:,.1f}M → {pp_locked_ni / sh:.2f}/sh (all tiers)"
    )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"candidate (A29, Solar guide {inp['sales_so_fy28_guide']:,.0f} -> H' only): "
        f"L'={cand[0]:.2f} M'={cand[1]:.2f} H'={cand[2]:.2f}  [H'/core_eps_ann {own_pe_cand:.1f}x]"
    )
    print(
        f"tier decomposition (A2e-5): L/M {L / M:.3f} = OC numerator {ni_oc['l'] / ni_oc['m']:.3f} x OC multiple "
        f"{pe['oc']['l'] / pe['oc']['m']:.3f} | H/M {H / M:.3f} = OC numerator {ni_oc['h'] / ni_oc['m']:.3f} x OC multiple "
        f"{pe['oc']['h'] / pe['oc']['m']:.3f} | (H-L)/2M {(H - L) / 2 / M:.3f} | V_opt/M {v_opt / M:.3f}"
    )
    print(
        f"flat-multiple ladder (A2e-2c, all tiers at OC M-tier {pe['oc']['m']:.2f}x): "
        f"{flat['l']:.2f}/{flat['m']:.2f}/{flat['h']:.2f}"
    )
    print(
        f"guardrail (A27): anchors / core_eps_ann {inp['core_eps_ann']:g} = "
        f"{own_pe['l']:.1f}/{own_pe['m']:.1f}/{own_pe['h']:.1f}x (H' {own_pe_cand:.1f}x) vs own band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]"
    )

    # Band as evidence (裁决顺序 ③): the OC perpetual g that would put each tier
    # exactly on a guardrail edge, solved numerically (the anchor is a sum of
    # legs, so the closed-form implied_g does not apply). A g at the upper edge
    # sits within 2pp of the pole and is a market reading, not a candidate.
    def g_oc_for_multiple(k: str, target: float) -> float:
        want = target * inp["core_eps_ann"]
        lo, hi = -0.5, r - 1e-6
        for _ in range(200):
            mid = (lo + hi) / 2
            if anchor(k, perpetual_pe(mid, roe[k], r))[1] < want:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    edges = {
        k: (g_oc_for_multiple(k, inp["pe_own_min"]), g_oc_for_multiple(k, inp["pe_own_max"]))
        for k in TIERS
    }
    print(
        "band-edge implied g_oc (whole-co anchor / core_eps_ann on [min, max]): "
        + "  ".join(
            f"{k.upper()} [{lo:+.2%}, {hi:+.2%}{' pole' if r - hi < 0.02 else ''}]"
            for k, (lo, hi) in edges.items()
        )
        + f"  — g2_oc {inp['g2_oc']:.2%} inside every tier: "
        f"{all(lo <= inp['g2_oc'] <= hi for lo, hi in edges.values())}"
    )
    print(
        f"whole-co FY28 PE on own-tier EPS L/M/H = {L / eps['l']:.2f}/{M / eps['m']:.2f}/{H / eps['h']:.2f}x; "
        f"H/eps_fy28_l = {h_over_eps_l:.2f}x (cap <{PE_OC_HARD_CAP:g}); H/eps_fy28_h = {H / eps['h']:.2f}x"
    )

    # Wide-scope share of the capex axis: OC segment NI grossed up by the OC net
    # margin (carrier + enterprise; the enterprise-only narrow scope is 待补).
    rev_oc_m = ni_oc["m"] / inp["pp_margin"]
    print(
        f"capex axis implied share (wide, OC FY28 NI/margin = ${rev_oc_m / 1e3:.1f}B):"
        f" M {rev_oc_m * MM / inp['capex_m']:.2%}"
    )

    others_m = sum(v for k, v in legs_m.items() if k != "oc")
    implied_pe_oc = (inp["price"] * sh - adj - others_m) / ni_oc["m"]
    print(
        f"price={inp['price']} zone={zone}  "
        f"price/eps_fy28_l={inp['price'] / eps['l']:.2f}x  price/eps_fy28_h={inp['price'] / eps['h']:.2f}x  "
        f"implied pe_oc FY28 (others+pp at M)={implied_pe_oc:.1f}x  P/H={inp['price'] / H - 1:+.1%}  "
        f"P/(H+V_opt)={inp['price'] / (H + v_opt) - 1:+.1%}  P/(H'+V_opt)={inp['price'] / (H_cand + v_opt) - 1:+.1%}"
    )
    print(
        f"V_opt={v_opt:.2f}/sh = signed {v_signed:.2f} + renew {v_renew:.2f}  "
        f"(rate {lta_rate:,.0f}M/y x {inp['pp_margin']:.4f} x "
        f"ann(g=0, r={r_disc:.0%}, n={n_yrs:.0f})={ann_n:.3f}; "
        f"renew = signed/(1+r)^{n_yrs:.0f})  V_opt/M={v_opt / M * 100:.1f}%"
    )
    print(
        "zone+V (table3, NOT used for any verdict): "
        + " ".join(
            f"{lab}={zone_v[k]:.2f}(p_sig={P_SIGNED[k]:g},p_ren={P_RENEW[k]:g})"
            for k, lab in (("l", "L"), ("m", "M"), ("h", "H"))
        )
    )
    if inp["price"] > H:
        print(
            f"market-implied multiple = (price - H)/V_opt = "
            f"{(inp['price'] - H) / v_opt:.2f} Verizon-sized six-year deals"
        )
    # Implied r(P), disclosure only (A30): single-stage Gordon approximation on
    # the OC leg's g2 and the M anchor; a multi-leg SOTP makes it approximate.
    implied_r = inp["g2_oc"] + (r - inp["g2_oc"]) * M / inp["price"]
    print(
        f"implied r(P) ≈ g2_oc + (r - g2_oc) x M/P = {implied_r:.2%} "
        f"vs 篮 {baskets['r_perp']} {r:.1%} ({implied_r - r:+.1%}) — disclosure only"
    )

    # Sensitivities the A2f record quotes. g2_oc: ±1pp and the untruncated peer
    # median (both above-cap values are reference only). g2_gi: ±1pp because
    # its g2 has no peer anchor. g2_au: ±1pp.
    for g in (inp["g2_oc"] - 0.01, inp["g2_oc"] + 0.01, G2_OC_PEER_RAW):
        pe_g = {k: perpetual_pe(g, roe[k], r) for k in TIERS}
        s = {k: anchor(k, pe_g[k])[1] for k in TIERS}
        tag = " (above cap, reference only)" if g > g_cap(r) + 1e-9 else ""
        print(
            f"sensitivity g2_oc={g:.4f}{tag}: OC PE {pe_g['l']:.2f}/{pe_g['m']:.2f}/{pe_g['h']:.2f}x -> "
            f"L/M/H = {s['l']:.2f} / {s['m']:.2f} / {s['h']:.2f}  H+V_opt {s['h'] + v_opt:.2f}"
        )
    for leg, key in (("gi", "pe_gi_k"), ("au", "pe_au_k")):
        for g in (inp[f"g2_{leg}"] - 0.01, inp[f"g2_{leg}"] + 0.01):
            s = {k: anchor(k, **{key: perpetual_pe(g, roe[k], r)})[1] for k in TIERS}
            print(
                f"sensitivity g2_{leg}={g:+.4f}{' (no peer anchor)' if leg == 'gi' else ''}: "
                f"L/M/H = {s['l']:.2f} / {s['m']:.2f} / {s['h']:.2f}"
            )

    # A23a upgrade path: r_disc in the fixed-contract annuity basket. The
    # annuity form is what keeps this small; a perpetuity would swing ~43%.
    r_c = basket_r(CONTRACT_ANNUITY_BASKET)
    vs_c = lta_rate * inp["pp_margin"] * annuity_factor(0.0, r_c, n_yrs) / sh
    vo_c = vs_c * (1 + 1 / (1.0 + r_c) ** n_yrs)
    print(
        f"sensitivity r_disc -> 篮 {CONTRACT_ANNUITY_BASKET} {r_c:.1%}: signed {vs_c:.2f} "
        f"({vs_c / v_signed - 1:+.1%}), V_opt {vo_c:.2f} ({vo_c / v_opt - 1:+.1%}), "
        f"table3 H {H + vo_c:.2f}, market-implied multiple {(inp['price'] - H) / vo_c:.2f}"
    )

    # ATM full-execution pro-forma (A24): new shares at the illustration price,
    # net proceeds reduce net debt. Accretive iff the issue price exceeds the anchor.
    atm_shares = ATM_GROSS_MM / ATM_REF_PRICE
    atm_net = ATM_GROSS_MM * (1 - ATM_FEE)
    pf = {k: (v * sh + atm_net) / (sh + atm_shares) for k, v in base.items()}
    print(
        f"ATM pro-forma (A24, full $2.0B at {ATM_REF_PRICE}, +{atm_shares:.2f}M sh, net {atm_net:,.0f}M): "
        f"L/M/H = {pf['l']:.2f} / {pf['m']:.2f} / {pf['h']:.2f}"
    )

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
