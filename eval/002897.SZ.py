#!/usr/bin/env python3
"""002897.SZ valuation eval — base deck from measured legs, Ascend ramp as V_opt.

formula_id: yihua_base_sotp_gordon_v2 (base deck) / yihua_ascend_option_v1 (option)

Base deck is an asymmetric SOTP of the business that already exists.  Both legs
take their three tiers from the company's own filings (A14): connectors =
H1'26 annualised / FY2025 / FY2024 peak (group net profit minus the solar
sub-group's consolidated P&L disclosed in the goodwill-impairment appraisal);
solar = H1'26 annualised / three-year median / FY2025 recurring.  Multiples are
Gordon-generated (`perpetual_pe`, g2 = 6% cross-basket peer reverse-solve
capped, r = the basket r read from Inputs — 篮 6 周期商品 / 小盘 13%, A17, the
whole company in one basket; tier ROE = NI / book equity of the leg); no
transition stage, because no consensus enters the base deck (A10 — the dialogue
ruled that domestic sell-side consensus belongs in the option, not the deck).
At 13% the connector tiers (ROE 9.6–13.8%) sit in the peak / degenerate
regions, so the multiples stay at or below 1/r — a result, not a fault.

The Ascend / super-node high-speed-connector ramp has no measured profit yet
(revenue +37%, profit flat), so it is priced as V_opt on a realised unit: 华丰科技
FY2025 net profit (A15, k = 1), at the same Gordon ruler.  p_M is derived from
an observable — Yihua's realised comms-connector revenue increment over the
华丰 unit's revenue increment — and lives only in table 3 (A2e-7a).  Consensus
enters only as reading B / B' (EPS-gap option) for the k ≈ 1 cross-check and
the A2f premium table; it never touches the anchors or the zone.

The two ③ guardrails ((H+V)/TTM vs own band, option multiple vs peer cluster)
are out of band at the basket r and are DISCLOSED, not asserted: the peer
cluster prices 篮 4 names (cross-basket, §13 rule 7) and the own band never
priced "13% + no ramp".  Ruling on the basket is a §13 research step, not this
script.  No floor enters L; book value per share is printed as disclosure.

Run:  python3 eval/002897.SZ.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import (  # noqa: E402
    check_g_cap,
    check_r,
    perpetual_pe,
    two_stage_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_baskets,
    parse_inputs,
    report,
)
from eval.lib.tiers import decompose  # noqa: E402
from eval.lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "002897.SZ.md"
FORMULA_ID_BASE = "yihua_base_sotp_gordon_v2"
FORMULA_ID_OPT = "yihua_ascend_option_v1"
TOL = 0.05
DERIVED_TOL = 5e-4
MIN_R_MINUS_G = 0.02
G2_STEPS = (0.03, 0.0)  # base-deck zone must survive the g2 evidence range (A13)
K_CROSS_BAND = (0.9, 1.3)  # reading B / V_opt: consensus should price ≈ one 华丰 unit (A15)
P_H = 1.0  # H world: the ramp reproduces the realised unit in full

REQUIRED = [
    "price",
    "shares",
    "equity_total",
    "equity_solar",
    "ni_conn_l",
    "ni_conn_m",
    "ni_conn_h",
    "ni_solar_l",
    "ni_solar_m",
    "ni_solar_h",
    "g2",
    "g2_solar",
    "r_perp",
    "unit_hf",
    "rev_comm_run_rate",
    "rev_comm_fy24",
    "hf_unit_rev",
    "cons_fy27_m",
    "cons_fy27_h",
    "cons_fy28_m",
    "pe_own_lo",
    "pe_own_hi",
    "pe_peer_lo",
    "pe_peer_hi",
    "ttm_eps",
    "equity_conn",
    "roe_conn_l",
    "roe_conn_m",
    "roe_conn_h",
]
TIERS = ("L", "M", "H")


def stated_v_opt(md: str) -> float | None:
    m = re.search(r"V_\{opt\}\\\)\s*=\s*\*\*([0-9.]+)\*\*", md)
    return float(m.group(1)) if m else None


def stated_p_tiers(md: str) -> tuple[float, float, float] | None:
    m = re.search(r"p_L/p_M/p_H\\\)\s*=\s*\*\*([0-9.]+)\s*/\s*([0-9.]+)\s*/\s*([0-9.]+)\*\*", md)
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    errs: list[str] = []
    # valuation-rules「§r 篮子」: r_perp must name its basket and carry that basket's value (A17).
    if "r_perp" not in baskets:
        errs.append("r_perp: Inputs source cell names no 篮 N (A17)")
    errs += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    for key in ("g2", "g2_solar"):
        errs += check_g_cap(inp[key], inp["r_perp"], key)
        gap = inp["r_perp"] - inp[key]
        if gap <= 0:
            errs.append(f"perpetuity diverges: {key} >= r")
        elif gap < MIN_R_MINUS_G:
            errs.append(f"r - {key} = {gap:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    # A2e-2c: both legs must differ in the numerator, tier by tier.
    errs += ladder("connector numerator", inp["ni_conn_l"], inp["ni_conn_m"], inp["ni_conn_h"])
    errs += ladder("solar numerator", inp["ni_solar_l"], inp["ni_solar_m"], inp["ni_solar_h"])
    # A2e-7a: probabilities stay out of Inputs.
    p_fields = [k for k in inp if k.startswith("p_")]
    if p_fields:
        errs.append(f"Inputs carry probability fields {p_fields} — p_k belongs in table 3 only")
    return errs


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    for fid in (FORMULA_ID_BASE, FORMULA_ID_OPT):
        if fid not in md:
            print(f"FAIL: formula_id {fid} missing from framework", file=sys.stderr)
            return 1

    inp = parse_inputs(md)
    baskets = parse_baskets(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    errors = sanity_checks(inp, baskets)

    r = inp["r_perp"]
    sh = inp["shares"]
    conn = {"L": inp["ni_conn_l"], "M": inp["ni_conn_m"], "H": inp["ni_conn_h"]}
    solar = {"L": inp["ni_solar_l"], "M": inp["ni_solar_m"], "H": inp["ni_solar_h"]}

    # ---- Step 1: derived inputs recomputed from their sources ----
    eq_conn = inp["equity_total"] - inp["equity_solar"]
    if abs(eq_conn - inp["equity_conn"]) > 1e5:
        errors.append(f"equity_conn: stated {inp['equity_conn']:.4e} vs recomputed {eq_conn:.4e}")
    roe_conn = {t: conn[t] / eq_conn for t in TIERS}
    for t, key in zip(TIERS, ("roe_conn_l", "roe_conn_m", "roe_conn_h")):
        if abs(roe_conn[t] - inp[key]) > DERIVED_TOL:
            errors.append(f"{key}: stated {inp[key]:.4f} vs recomputed {roe_conn[t]:.4f}")

    # ---- Step 2: base deck — measured legs × Gordon, no transition (A10 / A14) ----
    def deck(g2: float, r_: float = r) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
        pe_a = {t: perpetual_pe(g2, roe_conn[t], r_) for t in TIERS}
        pe_b = {t: perpetual_pe(inp["g2_solar"], solar[t] / inp["equity_solar"], r_) for t in TIERS}
        px = {t: (conn[t] * pe_a[t] + solar[t] * pe_b[t]) / sh for t in TIERS}
        return px, pe_a, pe_b

    px, pe_a, pe_b = deck(inp["g2"])
    L, M, H = (px[t] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)

    # A2e-2c flat ladder on the connector leg (all tiers at PE_M), solar as is.
    flat = tuple((conn[t] * pe_a["M"] + solar[t] * pe_b[t]) / sh for t in TIERS)
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")
    dec = decompose((L, M, H), (pe_a["L"], pe_a["M"], pe_a["H"]))

    # g2 leverage (A13): the base-deck zone must not move inside the evidence range.
    g2_rows = []
    for g2_ in G2_STEPS:
        px_, _, _ = deck(g2_)
        z_ = zone_of(inp["price"], px_["L"], px_["M"], px_["H"])
        g2_rows.append((g2_, px_, z_))
        if z_ != zone:
            errors.append(f"zone moves within g2 evidence range: {zone} at {inp['g2']:.0%} vs {z_} at {g2_:.0%} — BLOCKED")

    # ---- Step 3: option, reading A = realised 华丰 unit, k = 1 (A15) ----
    roe_opt = (conn["M"] + inp["unit_hf"]) / eq_conn
    pe_opt = perpetual_pe(inp["g2"], roe_opt, r)
    v_opt = inp["unit_hf"] * pe_opt / sh
    if v_opt < 0:
        errors.append(f"V_opt must be >= 0, got {v_opt:.2f}")
    said_v = stated_v_opt(md)
    if said_v is None or abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")

    p_m = (inp["rev_comm_run_rate"] - inp["rev_comm_fy24"]) / inp["hf_unit_rev"]
    p_k = (0.0, p_m, P_H)
    said_p = stated_p_tiers(md)
    if said_p is None or any(abs(a - b) > 0.01 for a, b in zip(said_p, p_k)):
        errors.append(f"p_L/p_M/p_H: stated {said_p} vs recomputed {tuple(round(x, 3) for x in p_k)}")
    adj = tuple(px[t] + p * v_opt for t, p in zip(TIERS, p_k))
    if abs(adj[0] - L) > 1e-9:
        errors.append("table 3 L row must equal base L (p_L = 0, check_no_p_leak)")
    zone_adj = zone_of(inp["price"], *adj)
    a_adj, b_adj = cut_points(*adj)

    # ---- Step 4: guardrails (A12) — ③ out-of-band is disclosed, not asserted (A17 / §13 rule 7) ----
    hv_ttm = adj[2] / inp["ttm_eps"]
    warns: list[str] = []
    if not (inp["pe_own_lo"] <= hv_ttm <= inp["pe_own_hi"]):
        warns.append(f"③ (H+V)/TTM {hv_ttm:.1f}x outside own band [{inp['pe_own_lo']}, {inp['pe_own_hi']}] — disclosed, basket review pending (§13)")
    if not (inp["pe_peer_lo"] <= pe_opt <= inp["pe_peer_hi"]):
        warns.append(f"③ option multiple {pe_opt:.2f}x outside peer cluster [{inp['pe_peer_lo']}, {inp['pe_peer_hi']}] — cross-basket cluster (篮 4), disclosed only")
    base_ttm = {t: px[t] / inp["ttm_eps"] for t in TIERS}  # reported only: ROE≈r keeps the deck below the band
    book_ps = inp["equity_total"] / sh  # PB 1.0 coordinate: disclosure only, never max()-ed into L

    # ---- Step 5: reading B / B' — consensus EPS gap as option (cross-check only, A10 / A15) ----
    gap = inp["cons_fy27_m"] - inp["ni_solar_m"] - conn["M"]
    roe_b = (inp["cons_fy27_m"] - inp["ni_solar_m"]) / eq_conn
    v_b = gap * perpetual_pe(inp["g2"], roe_b, r) / sh
    g1 = inp["cons_fy28_m"] / inp["cons_fy27_m"] - 1.0
    v_b2 = gap * two_stage_pe(g1, 1, inp["g2"], roe_b, r) / sh
    k_cross = v_b / v_opt
    k_warn = not (K_CROSS_BAND[0] <= k_cross <= K_CROSS_BAND[1])

    # ---- Report ----
    print(f"formula_id={FORMULA_ID_BASE} + {FORMULA_ID_OPT}")
    print(f"baskets={baskets} r={r:g} g2={inp['g2']:.0%} g2_solar={inp['g2_solar']:.0%}  equity_conn={eq_conn:.4e}")
    for t in TIERS:
        print(
            f"{t}: conn {conn[t] / 1e8:.2f}亿 x {pe_a[t]:.2f}x (ROE {roe_conn[t]:.1%}) + "
            f"solar {solar[t] / 1e8:.2f}亿 x {pe_b[t]:.2f}x = {px[t]:.2f}"
        )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  price={inp['price']:.2f} zone={zone}")
    print(f"flat-multiple ladder @ PE_A_M {pe_a['M']:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(
        f"L/M {dec['lm']:.3f} = num {dec['num_lm']:.3f} x pe {dec['pe_lm']:.3f} | "
        f"H/M {dec['hm']:.3f} = num {dec['num_hm']:.3f} x pe {dec['pe_hm']:.3f} | "
        f"width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.1%}"
    )
    for g2_, px_, z_ in g2_rows:
        print(f"g2 {g2_:.0%} -> {px_['L']:.2f}/{px_['M']:.2f}/{px_['H']:.2f} zone={z_}")
    print(
        f"V_opt (A, 华丰 unit k=1) = {inp['unit_hf'] / 1e8:.2f}亿 x {pe_opt:.2f}x (ROE {roe_opt:.1%}) = {v_opt:.2f}  "
        f"p_k = {p_k[0]:.2f}/{p_k[1]:.3f}/{p_k[2]:.2f}"
    )
    print(f"表3: {adj[0]:.2f}/{adj[1]:.2f}/{adj[2]:.2f}  A'={a_adj:.2f} B'={b_adj:.2f}  zone+V={zone_adj}")
    print(
        f"市价隐含 p = {(inp['price'] - H) / v_opt:.2f}; P/(H+V) = {inp['price'] / adj[2] - 1:+.1%}; "
        f"(H+V)/TTM {hv_ttm:.1f}x vs own band [{inp['pe_own_lo']}, {inp['pe_own_hi']}]; "
        f"option PE {pe_opt:.2f}x vs peer cluster [{inp['pe_peer_lo']}, {inp['pe_peer_hi']}]"
    )
    print(f"base deck / TTM (reported, below own band by construction): {base_ttm['M']:.1f}x / {base_ttm['H']:.1f}x")
    print(f"floor: none in formula; PB 1.0 = {book_ps:.2f} (disclosure only, not max()-ed; L stays {L:.2f})")
    for w in warns:
        print(f"WARN[A12]: {w}")
    print(
        f"reading B: gap {gap / 1e8:.2f}亿 = {gap / inp['unit_hf']:.2f} units -> V_B {v_b:.2f} "
        f"(B'/g1 {g1:.1%}: {v_b2:.2f}); B/A = {k_cross:.2f}"
    )
    if k_warn:
        print(f"WARN[A15]: reading B / V_opt = {k_cross:.2f} outside {K_CROSS_BAND} — consensus no longer prices ≈ one unit")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
