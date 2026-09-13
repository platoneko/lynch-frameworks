#!/usr/bin/env python3
"""GLW.US (Corning) valuation eval — recompute anchors from frameworks/GLW.US.md.

frameworks/GLW.US.md is the source of truth; this script re-derives
L/M/H / A/B / zone from the §3 Inputs table and exits 1 on mismatch.

formula_id: glw_sotp_core_segment_pe_v4

Main ruler (base hand, zero probability): FY2028 segment SOTP whose tier ladder
lives ENTIRELY in the numerator. M-tier leg numerators come from the leg bridge
(ni_*_q×4×g_*). L and H take the two ends of the sell-side FY28E EPS range
(Barclays 5.17 / Citi ≈6.88, n=2, same source) and back the OC numerator out as
a RESIDUAL: eps_k × shares + close_core − GI − AU − Solar/LS run-rate losses,
where close_core (unallocated RD&E + net interest, after tax, + NCI) is the
core-EPS-to-segment-NI gap. GI, Automotive and LS numerators are flat across
tiers; Solar revenue is frozen at the Q2 run-rate in L (A2e-1 "收入冻结").

Multiples are FLAT across tiers (A2e-5 default for a `cyclical` primary): OC 22,
GI 11, AU 10, Solar P/S 1.0, LS P/S 0.8. The v3 bands (14/22/29 etc.) carried
the whole ladder in the multiple with a numerator ratio of 1.00 — an A2e-1
violation — and are retired. The A2e-2c flat-multiple ladder check is now
implemented: with flat multiples the ladder IS the numerator ladder, so the
script asserts OC_L < OC_M < OC_H and prints numerator / multiple ratios.

Constraint: pe_oc < 30 and H / eps_fy28_l < 30 (the user's FY28<30 rule read
against the strictest denominator). Prepaid locked profit enters in full (cash
already received); closing items are capitalised as before.

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.gordon import annuity_factor, check_r  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "GLW.US.md"
FORMULA_ID = "glw_sotp_core_segment_pe_v4"
TOL = 0.05
PE_OC_HARD_CAP = 30.0  # strict: pe_oc and H/eps_fy28_l must be < this
MM = 1e6

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
        "unalloc_rde_q",
        "net_interest_q",
        "so_ls_ni_q",
        "pe_oc",
        "pe_gi",
        "pe_au",
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
    ]
    missing = [k for k in required if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1

    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        print(f"FAIL: p-class fields must not appear in Inputs (A2e-7a): {leaked}",
              file=sys.stderr)
        return 1
    if not (0 < inp["pp_margin"] < 1):
        print(f"FAIL: pp_margin out of range: {inp['pp_margin']}", file=sys.stderr)
        return 1
    if inp["pe_oc"] >= PE_OC_HARD_CAP - 1e-12:
        print(f"FAIL: pe_oc={inp['pe_oc']} must be < {PE_OC_HARD_CAP}", file=sys.stderr)
        return 1
    if not (inp["eps_fy28_l"] < inp["eps_fy28_h"]):
        print("FAIL: eps_fy28_l must be < eps_fy28_h", file=sys.stderr)
        return 1

    sh = inp["shares_diluted"] / MM  # work in $M and M shares
    tax = inp["tax_core"]

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

    # ---- Step 3-5: flat multiples, closing items, prepaid, anchors ----
    corp_cap = inp["corp_pretax_q"] * 4 * (1 - tax) * inp["pe_corp"]
    nci_cap = inp["nci_q"] * 4 * inp["pe_corp"]
    adj = -corp_cap - nci_cap - inp["net_debt"] - inp["pension"]
    # Cash already received: full locked NI in every tier (A22, A2e-7a / 7c-4).
    pp_locked_ni = inp["contract_liab"] * inp["pp_margin"]

    def legs(k: str) -> dict[str, float]:
        return {
            "oc": ni_oc[k] * inp["pe_oc"],
            "gi": ni_gi * inp["pe_gi"],
            "au": ni_au * inp["pe_au"],
            "so": sales_so[k] * inp["ps_so"],
            "ls": sales_ls * inp["ps_ls"],
            "pp": pp_locked_ni,
        }

    def anchor(k: str) -> tuple[dict[str, float], float]:
        lg = legs(k)
        return lg, (sum(lg.values()) + adj) / sh

    legs_l, L = anchor("l")
    legs_m, M = anchor("m")
    legs_h, H = anchor("h")
    A = (L + M) / 2
    B = (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1
    h_over_eps_l = H / inp["eps_fy28_l"]
    if h_over_eps_l >= PE_OC_HARD_CAP - 1e-12:
        print(f"FAIL: H/eps_fy28_l={h_over_eps_l:.2f} must be < {PE_OC_HARD_CAP}",
              file=sys.stderr)
        return 1

    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    stated = {
        "L": first_float(r"L = \*\*([0-9.]+)\*\*", out_sec),
        "M": first_float(r"M = \*\*([0-9.]+)\*\*", out_sec),
        "H": first_float(r"H = \*\*([0-9.]+)\*\*", out_sec),
        "A": first_float(r"A = \*\*([0-9.]+)\*\*", out_sec),
        "B": first_float(r"B = \*\*([0-9.]+)\*\*", out_sec),
    }
    recomputed = {"L": L, "M": M, "H": H, "A": A, "B": B}
    errors: list[str] = []
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
    errors += check_r(r_disc, "r_disc")
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

    base = {"l": L, "m": M, "h": H}
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
    for lab, lg in (("L", legs_l), ("M", legs_m), ("H", legs_h)):
        print(f"legs $M  {lab}: " + " ".join(f"{k}={v:,.0f}" for k, v in lg.items()))
    print(
        f"adj={adj:,.1f}M = {adj / sh:.2f}/sh; prepaid={pp_locked_ni:,.1f}M → {pp_locked_ni / sh:.2f}/sh (all tiers)"
    )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"tier decomposition (A2e-5): L/M {L / M:.3f} = OC numerator {ni_oc['l'] / ni_oc['m']:.3f} x multiple 1.000 | "
        f"H/M {H / M:.3f} = OC numerator {ni_oc['h'] / ni_oc['m']:.3f} x multiple 1.000 | (H-L)/2M {(H - L) / 2 / M:.3f}"
    )
    print(
        "flat-multiple ladder (A2e-2c): multiples are literally flat, so the ladder IS the OC numerator ladder: "
        f"{ni_oc['l']:,.0f} < {ni_oc['m']:,.0f} < {ni_oc['h']:,.0f}"
    )
    print(
        f"whole-co FY28 PE on own-tier EPS L/M/H = {L / eps['l']:.2f}/{M / eps['m']:.2f}/{H / eps['h']:.2f}x; "
        f"H/eps_fy28_l = {h_over_eps_l:.2f}x (cap <{PE_OC_HARD_CAP:g}); H/eps_fy28_h = {H / eps['h']:.2f}x"
    )

    others_m = sum(v for k, v in legs_m.items() if k != "oc")
    implied_pe_oc = (inp["price"] * sh - adj - others_m) / ni_oc["m"]
    print(
        f"price={inp['price']} zone={zone}  "
        f"price/eps_fy28_l={inp['price'] / eps['l']:.2f}x  price/eps_fy28_h={inp['price'] / eps['h']:.2f}x  "
        f"implied pe_oc FY28 (others+pp at M)={implied_pe_oc:.1f}x"
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
