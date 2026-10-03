#!/usr/bin/env python3
"""INTC.US valuation eval — base L/M/H with Foundry at 0, V_opt = Foundry 2030 target world.

frameworks/INTC.US.md is the source of truth for inputs; this script recomputes
the base L/M/H (CPU leg on Gordon multiples + closing items, Foundry = 0), A/B
and V_opt, and exits 1 on mismatch with stated Outputs.  The doc carries no
current price (AGENTS.md「现价 — 禁写契约」): which zone a quote falls in is
derived live by the daily digest and the app, so nothing here reads a price.

formula_id (CPU):     intc_cpu_product_gordon_v3
formula_id (Foundry): intc_foundry_target_option_v2  (ceiling only; not in the base)

CPU leg (A2e-1 / AGENTS.md 永续增长口径; 2026-10-03 data priority + leg economics):
  numerators  L = FY2025 full-year Intel Products operating income (realised
              digestion year; the cyclical L exception in valuation-rules
              「数据优先级与同业同尺」).  M / H = FY2027 company revenue consensus
              (yfinance mean / high, >=2 houses with a range, the farthest such
              year) x product share of revenue x product operating margin, the
              last two inferred from public segment data (A5c): two quarters
              (Q1'26 / Q2'26) both print the same margin and share, so the
              inference holds "both constant at H1'26".  Realised H1/Q2 run-rates
              are now snapshots only, never numerators.
  multiples   perpetual_pe(g2_cpu, ROE_x, r_perp) with ROE_x = NI_x / company
              equity (no leg equity is disclosed, so company ROE is used and
              said so).  r_perp comes from the basket the CPU leg is assigned to
              (valuation-rules「§r 篮子」, A19): 篮 4 龙头制造; the Inputs source
              cell names the basket and `check_r` demands the value match it.
              The Foundry leg sits in 篮 7 but has no r row -- it is an option,
              never in L/M/H; its V_opt is discounted at the base basket r
              (construction §7c-1), 15% only as a printed sensitivity (A19).
              One g2 shared across tiers (turnaround class), reverse-solved from
              the well-conditioned semis cluster (A15) and capped at g_cap(r);
              the multiple only moves with ROE, mechanically.  No two-stage transition:
              FY2027 is the farthest year with >=2 ranged houses and is the
              numerator itself; FY2028 has no >=2-house reading (A17 ②), so
              check_transition_years is not applicable here.
  cross-check HSBC 2027E core 4.25 (single house, A5b) must sit inside [M, H]
              of the inferred product EPS; the old 候选带 is retired (A18).
  guardrail   every generated multiple must sit inside the ticker's own realised
              trailing-PE band (pe_own_min / pe_own_max).
  closure     corporate unallocated cost is capitalised at the M-tier generated
              multiple (A10b), so it moves with the same g2/ROE as the leg.

Foundry stays an option, closed by public data (valuation-rules「未建模期权」
2026-10-03): count = the company's named 2030 external-foundry revenue target
plus today's measured internal foundry revenue (snapshot), unit economics =
the company's named 30% Foundry operating-margin target, valued on Intel's own
ruler (basket r, company-ROE 口径, foundry-cluster g2) in 2030 and discounted
to the FY2027 numerator year at r.  No peer multiple (the old SMIC-level PB is
gone).  表3 = base_k + p_k × V_opt with P_K an eval constant, never an Input
(A2e-7a); p_M = the pre-split success weight 0.25 (A7).

Run:  python3 frameworks/eval/INTC.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
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
from eval.lib.zones import cut_points  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "INTC.US.md"
FORMULA_IDS = (
    "intc_cpu_product_gordon_v3",
    "intc_foundry_target_option_v2",
)
TOL = 0.05
MIN_R_MINUS_G = 0.02  # AGENTS.md: below this the multiple sits at the pole
# _AXIS.rates segment: a US listing reads the USD r_f (valuation-rules「按上市货币取段」).
LISTING_CCY = "USD"

# 表3 per-tier option credit (A7): p_M = pre-split success weight.  Never Inputs.
P_K = (0.0, 0.25, 1.0)
# The foundry g2 is the foundry-cluster reverse-solve that GFS A5 also uses and
# that GFS.US stores as its `g2_rest_src` (GFS A5 is the cluster's source):
# same cluster, same number.  INTC's foundry is an advanced logic leg.
PEER = REPO_ROOT / "frameworks" / "GFS.US.md"

# Closing items that are already $/share; corporate unallocated is capitalised
# from its annual after-tax cost at the M-tier multiple instead (A10b).
ADJ_PS = ("net_cash_ps", "nci_ps", "mbly_stake_ps", "altera_stake_ps", "tax_asset_ps")

QTRS = ("q1", "q2")
REQUIRED = [
    "shares_diluted", "equity", "tax_rate", "oi_products_l",
    "rev_fy27_low", "rev_fy27_m", "rev_fy27_h",
    *(f"{k}_{q}" for k in ("prod_rev", "prod_oi", "cons_rev") for q in QTRS),
    "prod_rev_fy25", "cons_rev_fy25",
    "r_perp", "g2_cpu", "pe_own_min", "pe_own_max", "eps_fy27_hsbc",
    "opt_rev_ext", "foundry_rev_h1", "foundry_ext_h1", "opt_opm", "g2_foundry", "t_opt", "t_num",
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
    # ---- Step 0: leg economics by public-data inference (A5c) ----
    # Two disclosed quarters, two unknowns held constant: product margin and
    # product share of consolidated revenue.  Both must agree within 1pp.
    q_margin = {q: inp[f"prod_oi_{q}"] / inp[f"prod_rev_{q}"] for q in QTRS}
    q_share = {q: inp[f"prod_rev_{q}"] / inp[f"cons_rev_{q}"] for q in QTRS}
    for lab, d in (("margin", q_margin), ("share", q_share)):
        if max(d.values()) - min(d.values()) > 0.01:
            errors.append(f"product {lab} not constant across {QTRS}: {d} — inference assumption fails (A5c)")
    margin = sum(inp[f"prod_oi_{q}"] for q in QTRS) / sum(inp[f"prod_rev_{q}"] for q in QTRS)
    share = sum(inp[f"prod_rev_{q}"] for q in QTRS) / sum(inp[f"cons_rev_{q}"] for q in QTRS)
    margin_fy25 = inp["oi_products_l"] / inp["prod_rev_fy25"]

    def oi_at(rev: float, m_: float = margin, s_: float = share) -> float:
        return rev * s_ * m_ / MM  # $M

    # ---- Step 1: CPU leg — numerator, tier ROE, generated multiple ----
    # L: realised digestion year (cyclical L exception); M/H: FY2027 consensus.
    oi = {"L": inp["oi_products_l"], "M": oi_at(inp["rev_fy27_m"]), "H": oi_at(inp["rev_fy27_h"])}
    errors += ladder("oi_products", oi["L"], oi["M"], oi["H"])
    ni = {t: oi[t] * MM * keep for t in TIERS}
    eps = {t: ni[t] / sh for t in TIERS}
    roe = {t: ni[t] / eq for t in TIERS}
    def tier_pe(r_: float) -> dict[str, float]:
        return {t: perpetual_pe(g2, roe[t], r_) for t in TIERS}

    pe = tier_pe(r)
    cpu = {t: eps[t] * pe[t] for t in TIERS}
    for t in TIERS:
        if not (inp["pe_own_min"] <= pe[t] <= inp["pe_own_max"]):
            errors.append(
                f"{t} generated PE {pe[t]:.2f}x outside own realised band "
                f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] — 回对话，不拧 g"
            )

    # ---- Step 2: closing items (A10); corporate unallocated at the M multiple (A10b) ----
    def closure_at(pe_: dict[str, float]) -> float:
        return sum(inp[k] for k in ADJ_PS) + inp["corp_other_eps"] * pe_["M"]

    corp_ps = inp["corp_other_eps"] * pe["M"]
    adj = closure_at(pe)
    base = {t: cpu[t] + adj for t in TIERS}
    L, M, H = (base[t] for t in TIERS)
    A, B = cut_points(L, M, H)

    # ---- Step 3: A2e-2c flat ladder + A2e-5 decomposition ----
    flat_errs, flat_eps = flat_multiple_ladder((eps["L"], eps["M"], eps["H"]), pe["M"])
    errors += flat_errs
    flat = tuple(v + adj for v in flat_eps)
    dec = decompose((L, M, H), (pe["L"], pe["M"], pe["H"]))

    # ---- Step 3b: single-house cross-check (A5b / A18) — not a band ----
    eps_c = inp["eps_fy27_hsbc"]
    if not (eps["M"] <= eps_c <= eps["H"]):
        errors.append(f"HSBC core 2027E {eps_c} outside inferred product EPS [M {eps['M']:.2f}, H {eps['H']:.2f}] — recheck A5c")
    if load_framework(FRAMEWORK).candidate is not None:
        errors.append("候选带 line still in Outputs — retired 2026-10-03 (A18)")

    # ---- Step 4: Foundry option (A6/A11) and 表3 (probabilities only here) ----
    # Count: named 2030 external target + measured internal revenue (H1'26 x2).
    g2f = inp["g2_foundry"]
    errors += check_g_cap(g2f, r, "g2_foundry")
    if r - g2f < MIN_R_MINUS_G:
        errors.append(f"r - g2_foundry = {r - g2f:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    rev_int = (inp["foundry_rev_h1"] - inp["foundry_ext_h1"]) * 2 * MM
    opt_rev = inp["opt_rev_ext"] + rev_int
    ni_opt = opt_rev * inp["opt_opm"] * keep
    eps_opt = ni_opt / sh
    roe_post = (ni["H"] + ni_opt) / eq  # company-ROE 口径 in the realised world (A15)
    pe_f = perpetual_pe(g2f, roe_post, r)
    years = inp["t_opt"] - inp["t_num"]
    df = (1 + r) ** -years
    v_opt = eps_opt * pe_f * df
    p_k = P_K
    adj_band = [base[t] + p_k[i] * v_opt for i, t in enumerate(TIERS)]
    a2, b2 = cut_points(*adj_band)
    meta = load_framework(FRAMEWORK)
    if meta.v_opt is None or abs(meta.v_opt - v_opt) > TOL:
        errors.append(f"V_opt: stated {meta.v_opt} vs recomputed {v_opt:.4f}")
    if meta.p_tiers is None or any(abs(a - b) > 1e-9 for a, b in zip(meta.p_tiers, p_k)):
        errors.append(f"p_L/p_M/p_H: stated {meta.p_tiers} vs eval {p_k}")
    if PEER.is_file():
        peer = parse_inputs(PEER.read_text(encoding="utf-8"))
        if abs(peer.get("g2_rest_src", float("nan")) - g2f) > 1e-9:
            errors.append(f"g2_foundry {g2f:g} != foundry-cluster reading g2_rest_src {peer.get('g2_rest_src')} (A6)")
    else:
        errors.append("frameworks/GFS.US.md missing — foundry-cluster g2 unchecked")

    # ---- Report ----
    print(f"formula_id: {FORMULA_IDS[0]} + {FORMULA_IDS[1]}")
    print(f"g2_cpu={g2:.4f} r={r:g} (篮 {baskets.get('r_perp')}) equity={eq / 1e9:.1f}B shares={sh / 1e9:.2f}B (company ROE, no leg equity disclosed)")
    print(f"leg inference (A5c): margin " + " / ".join(f"{q} {q_margin[q]:.4f}" for q in QTRS)
          + f" -> H1 {margin:.4f} (FY25 {margin_fy25:.4f}); share " + " / ".join(f"{q} {q_share[q]:.4f}" for q in QTRS)
          + f" -> H1 {share:.4f} (FY25 {inp['prod_rev_fy25'] / inp['cons_rev_fy25']:.4f})")
    print(f"snapshot (not numerators): H1'26 annualised OI {(inp['prod_oi_q1'] + inp['prod_oi_q2']) * 2:,.0f}M, "
          f"Q2'26 annualised {inp['prod_oi_q2'] * 4:,.0f}M; FY27 consensus low -> OI {oi_at(inp['rev_fy27_low']):,.0f}M (L stays FY2025)")
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
    print(f"foundry option: ({inp['opt_rev_ext'] / 1e9:.1f}B ext target + {rev_int / 1e9:.2f}B internal) x OPM {inp['opt_opm']:.0%}"
          f" x (1-t) / shares = {eps_opt:.4f}/sh; ROE_post {roe_post:.3f} -> PE {pe_f:.2f}x (g2 {g2f:.2%}, r {r:g})"
          f" -> {eps_opt * pe_f:.2f} @{inp['t_opt']:.0f} x df {df:.4f} ({years:.0f}y) = V_opt {v_opt:.2f}")
    print(f"表3  V_opt={v_opt:.2f}  p_k={p_k[0]:.2f}/{p_k[1]:.2f}/{p_k[2]:.2f}  "
          + "  ".join(f"{t}:{base[t]:.2f}+{p_k[i]:.2f}xV={adj_band[i]:.2f}" for i, t in enumerate(TIERS))
          + f"  A'={a2:.2f} B'={b2:.2f}")
    print(f"cross-check HSBC 2027E core {eps_c:g} in [M {eps['M']:.2f}, H {eps['H']:.2f}]")

    def band_with(m_: float = margin, s_: float = share, g_: float = g2) -> tuple[float, float, float]:
        oi_ = {"L": inp["oi_products_l"], "M": oi_at(inp["rev_fy27_m"], m_, s_), "H": oi_at(inp["rev_fy27_h"], m_, s_)}
        e_ = {t: oi_[t] * MM * keep / sh for t in TIERS}
        p_ = {t: perpetual_pe(g_, e_[t] * sh / eq, r) for t in TIERS}
        a_ = sum(inp[k] for k in ADJ_PS) + inp["corp_other_eps"] * p_["M"]
        return tuple(e_[t] * p_[t] + a_ for t in TIERS)  # type: ignore[return-value]

    for g in (g2 - 0.01, g2 + 0.01):
        print(f"sensitivity g2={g:.2%}: L/M/H " + "/".join(f"{v:.2f}" for v in band_with(g_=g)))
    print(f"sensitivity margin FY25 {margin_fy25:.4f}: L/M/H " + "/".join(f"{v:.2f}" for v in band_with(m_=margin_fy25)))
    print(f"sensitivity df at 15% (篮 7 leg r, not adopted): V_opt {eps_opt * pe_f * 1.15 ** -years:.2f}")

    # ---- Checks ----
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, tol=TOL)
    errors += ladder("base", L, M, H)
    errors += check_no_p_leak(L, adj_band[0])
    if not p_k[0] <= p_k[1] <= p_k[2]:
        errors += [f"p_k must be non-decreasing, got {p_k}"]
    if v_opt <= 0:
        errors += [f"V_opt must be > 0 (valuation-rules: no zero for want of sell-side counts), got {v_opt:.2f}"]
    if not years > 0:
        errors += [f"t_opt {inp['t_opt']} must be after t_num {inp['t_num']}"]
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors += [f"p-class fields must not appear in Inputs (A2e-7a): {leaked}"]

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_perp 1:1 in every tier multiple and so in the corp-unallocated closure
    # capitalised at the M multiple (A10b); OI, ROE, g2 and the $/share closing
    # items stay put, and the Foundry option is outside the base.  Disclosure only.
    def band_at(dr: float) -> tuple[float, float, float]:
        pe_ = tier_pe(r + dr)
        adj_ = closure_at(pe_)
        return tuple(eps[t] * pe_[t] + adj_ for t in TIERS)  # type: ignore[return-value]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_at)
    # Only a clean run feeds the daily digest.
    if not errors:
        write_rf_readings("INTC.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
