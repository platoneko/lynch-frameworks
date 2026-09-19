#!/usr/bin/env python3
"""INTC.US valuation eval — base L/M/H with Foundry at 0, V_opt = success mid.

frameworks/INTC.US.md is the source of truth for inputs; this script recomputes
the base L/M/H (CPU leg on Gordon multiples + closing items, Foundry = 0), A/B,
zone and V_opt, and exits 1 on mismatch with stated Outputs.

formula_id (CPU):     intc_cpu_product_gordon_v2
formula_id (Foundry): intc_foundry_pb_option_v1  (ceiling only; not in the base)

CPU leg (A2e-1 / AGENTS.md 永续增长口径):
  numerators  three realised Intel Products operating-income points on the same
              internal-foundry-model 口径: L = FY2025 full year (10-K FY2025
              Note 3 — the A2e-1 "消化年": product revenue frozen at $48-49B for
              FY2023-25, and the last realised full year; a perpetuity's numerator
              is a steady level, so the FY2023 trough is a deep_discount coordinate,
              not an anchor), M = H1'26 annualised, H = Q2'26 annualised (10-Q).
              The tier ladder therefore lives in the numerator; no tier borrows a PE.
  multiples   perpetual_pe(g2_cpu, ROE_x, r_perp) with ROE_x = NI_x / company
              equity (no leg equity is disclosed, so company ROE is used and
              said so).  r_perp comes from the basket the CPU leg is assigned to
              (valuation-rules「§r 篮子」, A19): 篮 4 龙头制造; the Inputs source
              cell names the basket and `check_r` demands the value match it.
              The Foundry leg sits in 篮 7 but has no r row -- it is a PB option,
              never in L/M/H (its 15% is not applied to foundry_discount; A19).
              One g2 shared across tiers (turnaround class), reverse-solved from
              the well-conditioned semis cluster (A15) and capped at g_cap(r);
              the multiple only moves with ROE, mechanically.  No two-stage transition: the
              FY27 product leg has no consensus year (A17 ②), so
              check_transition_years is not applicable here.
  candidate   the only FY27 product-leg number is single-house (HSBC core 4.25),
              so it feeds a 候选带 line (7h): H′ swaps that numerator in, L′/M′
              copy the base; never a zone input (A18).
  guardrail   every generated multiple must sit inside the ticker's own realised
              trailing-PE band (pe_own_min / pe_own_max).
  closure     corporate unallocated cost is capitalised at the M-tier generated
              multiple (A10b), so it moves with the same g2/ROE as the leg.

Foundry stays an option: V_opt = pb_success_mid × bvps_foundry_2027e ×
foundry_discount; 表3 = base_k + p_k × V_opt with P_K an eval constant, never
an Input (A2e-7a).  p_M is the value-ratio E[P_f]/V_opt from the pre-split
0.20/0.55/0.25 weighting (A7).

Run:  python3 eval/INTC.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    check_g_cap,
    check_r,
    implied_g,
    perpetual_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_baskets,
    parse_inputs,
    report,
)
from eval.lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from eval.lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "INTC.US.md"
FORMULA_IDS = (
    "intc_cpu_product_gordon_v2",
    "intc_foundry_pb_option_v1",
)
TOL = 0.05
MIN_R_MINUS_G = 0.02  # AGENTS.md: below this the multiple sits at the pole

# Mirror of framework §2 A6 PB bands (update together with the MD).
PB_BANDS = {"fail": (0.3, 0.8), "base": (1.2, 2.2), "success": (2.5, 3.5)}

# Pre-split fail/base/success weights. 表3 only — never Inputs, never the base.
OLD_P = {"fail": 0.20, "base": 0.55, "success": 0.25}

# Closing items that are already $/share; corporate unallocated is capitalised
# from its annual after-tax cost at the M-tier multiple instead (A10b).
ADJ_PS = ("net_cash_ps", "nci_ps", "mbly_stake_ps", "altera_stake_ps", "tax_asset_ps")

REQUIRED = [
    "price", "shares_diluted", "equity", "tax_rate",
    "oi_products_l", "oi_products_m", "oi_products_h",
    "r_perp", "g2_cpu", "pe_own_min", "pe_own_max", "eps_fy27_hsbc",
    "bvps_foundry_2027e", "pb_fail_mid", "pb_base_mid", "pb_success_mid", "foundry_discount",
    "corp_other_eps", *ADJ_PS,
]
TIERS = ("L", "M", "H")
MM = 1e6  # oi_products_* are in $M


def check_no_p_leak(base_l: float, row_l: float) -> list[str]:
    if abs(row_l - base_l) > 1e-9:
        return [f"p leaked into the base: 表3 L row {row_l:.4f} != base L {base_l:.4f}"]
    return []


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    for fid in FORMULA_IDS:
        if fid not in md:
            print(f"FAIL: formula_id {fid} missing from framework", file=sys.stderr)
            return 1

    inp = parse_inputs(md)
    baskets = parse_baskets(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r, g2 = inp["r_perp"], inp["g2_cpu"]
    sh, eq, keep = inp["shares_diluted"], inp["equity"], 1.0 - inp["tax_rate"]

    # ---- Guards on the growth 口径 (AGENTS.md 永续增长口径) ----
    # The r row must name its basket and carry that basket's value (A19).
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(g2, r, "g2_cpu")
    if r - g2 < MIN_R_MINUS_G:
        errors.append(f"r - g2_cpu = {r - g2:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    # A2e-2a/2c: three realised points on one 口径, strictly increasing.
    errors += ladder("oi_products", inp["oi_products_l"], inp["oi_products_m"], inp["oi_products_h"])

    # ---- Step 1: CPU leg — numerator, tier ROE, generated multiple ----
    oi = {"L": inp["oi_products_l"], "M": inp["oi_products_m"], "H": inp["oi_products_h"]}
    ni = {t: oi[t] * MM * keep for t in TIERS}
    eps = {t: ni[t] / sh for t in TIERS}
    roe = {t: ni[t] / eq for t in TIERS}
    pe = {t: perpetual_pe(g2, roe[t], r) for t in TIERS}
    cpu = {t: eps[t] * pe[t] for t in TIERS}
    for t in TIERS:
        if not (inp["pe_own_min"] <= pe[t] <= inp["pe_own_max"]):
            errors.append(
                f"{t} generated PE {pe[t]:.2f}x outside own realised band "
                f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] — 回对话，不拧 g"
            )

    # ---- Step 2: closing items (A10); corporate unallocated at the M multiple (A10b) ----
    corp_ps = inp["corp_other_eps"] * pe["M"]
    adj = sum(inp[k] for k in ADJ_PS) + corp_ps
    base = {t: cpu[t] + adj for t in TIERS}
    L, M, H = (base[t] for t in TIERS)
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    # ---- Step 3: A2e-2c flat ladder + A2e-5 decomposition ----
    flat_errs, flat_eps = flat_multiple_ladder((eps["L"], eps["M"], eps["H"]), pe["M"])
    errors += flat_errs
    flat = tuple(v + adj for v in flat_eps)
    dec = decompose((L, M, H), (pe["L"], pe["M"], pe["H"]))

    # ---- Step 3b: 候选带 (A18, 7h) — single-house FY27 product EPS swapped into H only ----
    eps_c = inp["eps_fy27_hsbc"]
    pe_c = perpetual_pe(g2, eps_c * sh / eq, r)
    if not (inp["pe_own_min"] <= pe_c <= inp["pe_own_max"]):
        errors.append(f"候选带 H′ multiple {pe_c:.2f}x outside own realised band")
    cand = (L, M, eps_c * pe_c + adj)
    stated_cand = load_framework(FRAMEWORK).candidate
    if stated_cand is None:
        errors.append("候选带 line missing from Outputs (A18)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), stated_cand, cand):
            if abs(said - got) > TOL:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")

    # ---- Step 4: Foundry option ceiling and 表3 (probabilities only here) ----
    mids = {
        k: inp[f"pb_{k}_mid"] * inp["bvps_foundry_2027e"] * inp["foundry_discount"]
        for k in PB_BANDS
    }
    v_opt = mids["success"]
    epf = sum(OLD_P[k] * mids[k] for k in PB_BANDS)
    p_m = epf / v_opt
    p_k = (0.0, p_m, 1.0)
    adj_band = [base[t] + p_k[i] * v_opt for i, t in enumerate(TIERS)]
    a2, b2 = cut_points(*adj_band)
    zone_v = zone_of(inp["price"], *adj_band)

    # ---- Report ----
    print(f"formula_id: {FORMULA_IDS[0]} + {FORMULA_IDS[1]}")
    print(f"g2_cpu={g2:.4f} r={r:g} (篮 {baskets.get('r_perp')}) equity={eq / 1e9:.1f}B shares={sh / 1e9:.2f}B (company ROE, no leg equity disclosed)")
    for t in TIERS:
        print(
            f"{t}: OI {oi[t]:,.0f}M -> eps {eps[t]:.4f} ROE {roe[t]:.3f} payout {1 - g2 / roe[t]:.3f}"
            f" -> PE {pe[t]:.2f}x -> CPU {cpu[t]:.2f}/sh"
        )
    print(f"closure {adj:+.2f} = " + " ".join(f"{k}={inp[k]:+.2f}" for k in ADJ_PS)
          + f" corp_other={corp_ps:+.2f} ({inp['corp_other_eps']:+.3f}/yr x M-PE {pe['M']:.2f})")
    print(f"base L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}")
    # decompose() folds the closure item into its numerator ratio; split it out
    # so the cross-ticker reading uses the pure eps ratio (A2e-5).
    num_lm, num_hm = eps["L"] / eps["M"], eps["H"] / eps["M"]
    print(f"L/M {dec['lm']:.3f} = eps {num_lm:.3f} x pe {dec['pe_lm']:.3f} x closure {dec['lm'] / (num_lm * dec['pe_lm']):.3f} | "
          f"H/M {dec['hm']:.3f} = eps {num_hm:.3f} x pe {dec['pe_hm']:.3f} x closure {dec['hm'] / (num_hm * dec['pe_hm']):.3f} | "
          f"width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.1%}")
    print(f"flat-multiple ladder @ M {pe['M']:.2f}x (incl. closure): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"guardrail: generated {pe['L']:.2f}/{pe['M']:.2f}/{pe['H']:.2f}x vs own band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]")
    # AGENTS.md 裁决顺序 ③: the band is evidence too — what g the market paid at each tier's ROE.
    g_lo, _ = implied_g(inp["pe_own_min"], roe["M"], r)
    g_hi, _ = implied_g(inp["pe_own_max"], roe["M"], r)
    print(f"guardrail ⇔ g at M-tier ROE {roe['M']:.3f}: [{g_lo:+.2%}, {g_hi:+.2%}]; g2_cpu {g2:.2%} inside -> no band-edge reverse-solve")
    print(f"foundry mids df={inp['foundry_discount']:g} = "
          + " / ".join(f"{k} {mids[k]:.1f}" for k in PB_BANDS)
          + f"  ->  V_opt={v_opt:.2f}  E[P_f]={epf:.1f}")
    print(f"表2  price {inp['price']} -> zone = {zone}")
    print(f"表3  V_opt={v_opt:.2f}  p_k={p_k[0]:.2f}/{p_k[1]:.3f}/{p_k[2]:.2f}  "
          + "  ".join(f"{t}:{base[t]:.2f}+{p_k[i]:.3f}xV={adj_band[i]:.2f}" for i, t in enumerate(TIERS))
          + f"  A'={a2:.2f} B'={b2:.2f} zone+V={zone_v}")
    if inp["price"] > H:
        print(f"     市价隐含 p = {(inp['price'] - H) / v_opt:.2f}; P/(H+V) = {inp['price'] / adj_band[2] - 1:+.1%}")
    print(f"候选带（FY27·汇丰单家 {eps_c:g}，ROE {eps_c * sh / eq:.3f} -> {pe_c:.2f}x；不进底牌/zone）: "
          f"L′/M′/H′={cand[0]:.2f}/{cand[1]:.2f}/{cand[2]:.2f}  候选 zone={zone_of(inp['price'], *cand)}  "
          f"H′+V={cand[2] + v_opt:.2f} -> P/(H′+V) = {inp['price'] / (cand[2] + v_opt) - 1:+.1%}")
    for g in (g2 - 0.01, g2 + 0.01):
        pm = perpetual_pe(g, roe["M"], r)
        print(f"sensitivity g2={g:.2%}: M-PE {pm:.2f}x -> M {eps['M'] * pm + sum(inp[k] for k in ADJ_PS) + inp['corp_other_eps'] * pm:.2f}")

    # ---- Checks ----
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, tol=TOL)
    errors += ladder("base", L, M, H)
    errors += check_no_p_leak(L, adj_band[0])
    if not p_k[0] <= p_k[1] <= p_k[2]:
        errors += [f"p_k must be non-decreasing, got {p_k}"]
    if v_opt < 0:
        errors += [f"V_opt must be >= 0, got {v_opt:.2f}"]
    if abs(sum(OLD_P.values()) - 1.0) > 1e-9:
        errors += [f"OLD_P must sum to 1, got {sum(OLD_P.values())}"]
    df = inp["foundry_discount"]
    if not (0 < df <= 1):
        errors += [f"foundry_discount {df} not in (0, 1]"]
    for k, (lo, hi) in PB_BANDS.items():
        pb = inp[f"pb_{k}_mid"]
        if not (lo <= pb <= hi):
            errors += [f"pb_{k}_mid {pb} outside A6 band [{lo}, {hi}]"]
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors += [f"p-class fields must not appear in Inputs (A2e-7a): {leaked}"]
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
