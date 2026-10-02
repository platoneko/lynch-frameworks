#!/usr/bin/env python3
"""300308.SZ (中际旭创 / Zhongji Innolight) valuation eval — recompute anchors
from frameworks/300308.SZ.md.

frameworks/300308.SZ.md is the source of truth; this script re-derives
L/M/H / A/B and the NPO option from the §3 Inputs table and exits 1 on
mismatch.  The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so
nothing here reads a quote.

formula_id: zjxc_pluggable_fy27_two_stage_gordon_npo_opt_v1

Main ruler: the pluggable-module business only (NPO is carved out into V_opt).
Numerator year FY2027 — the furthest year with a >=2-house consensus range
(yfinance +1y, 4 houses) — restated from the A-share count the consensus is
struck on to the post-H-share total count.  L = FY27 digestion year (FY26
revenue consensus x (1 - rev_cut_l) x FY25 realised net margin), no transition.
M / H = FY27 consensus mean / high, then ONE transition year: FY28 growth =
mean of the two houses that state FY28 (UBS EPS, Citi NI) with the NPO share
(UBS 10%, applied to both — A11) stripped out, then perpetual g2.  g2 is a
user-set 2% (below the named macro 4%: a declared rule deviation, A16).

ROE is E_{n+1}/B_n: FY27 EPS over the FY27 opening book = 2026-06-30 equity +
H-share net proceeds - interim dividend + the unbooked H2 FY26 consensus
profit retained at the growth-required b = g/ROE (g1 for M/H, g2 for L);
solved as a fixed point.  Anchors carry the retention haircut k (x (1 - k)).

Option (A13): NPO FY28 net profit = UBS FY28 revenue x NPO share x FY25
realised net margin, capitalised at the M-tier ROE with g_npo and discounted
one year (FY28 is t = 2).  p_L / p_M / p_H are constants here, never Inputs.

Run:  python3 frameworks/eval/300308.SZ.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import (  # noqa: E402
    check_capex_mount,
    check_optical_narrow_attach,
    check_optical_oe_mount,
    optical_attachment,
)
from eval.lib.gordon import (  # noqa: E402
    check_branch,
    check_g_cap,
    check_r,
    check_transition_years,
    g_cap,
    implied_g,
    payout,
    perpetual_pe,
    two_stage_pe,
)
from eval.lib.inputs import parse_baskets  # noqa: E402
from eval.lib.tiers import decompose, flat_multiple_ladder  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "300308.SZ.md"
FORMULA_ID = "zjxc_pluggable_fy27_two_stage_gordon_npo_opt_v1"
TOL = 0.05
MIN_R_MINUS_G = 0.02
N_STAGE = 1  # FY28 is the only year beyond the numerator with >=2 stated houses
CONSENSUS_YEARS_BEYOND = 1
MACRO_G = 0.04  # valuation-rules「6% 的含义」: named long-run nominal growth
P_TIERS = (0.3, 0.6, 1.0)  # A13: 无概率锚·拍值; p_H default 1.0
TIERS = ("L", "M", "H")


def parse_inputs(md: str) -> dict[str, float]:
    """§3 Inputs: | field | value | meaning | as-of |."""
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
        if len(cells) < 2 or cells[0] in ("字段名", "--------", "---"):
            continue
        try:
            out[cells[0]] = float(cells[1].replace(",", ""))
        except ValueError:
            continue
    return out


def first_float(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


REQUIRED = [
    "eps_fy26_cons", "rev_fy26_cons", "nm_fy25", "rev_cut_l",
    "eps_fy27_l", "eps_fy27_m", "eps_fy27_h", "shares_a", "shares_total",
    "ubs_eps27", "ubs_eps28", "citi_ni27", "citi_ni28", "npo_share_28", "ubs_rev28",
    "equity_h1", "h_shares", "h_price_hkd", "hkdcny", "h_fee", "dps_interim",
    "shares_div", "ni_h2_cons", "r_perp", "g2", "g_npo", "k_l", "k_m", "k_h",
    "payout_obs", "pe_own_min", "pe_own_max", "rev_fy27_cons", "usdcny",
    "npo_units_27", "npo_units_28", "oe_l", "oe_m", "oe_h",
    "capex_l", "capex_m", "capex_h",
]


def check_inputs(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    e: list[str] = []
    if "r_perp" not in baskets:
        e.append("r_perp: Inputs source cell names no 篮 N (A15)")
    e += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    for key in ("g2", "g_npo"):
        e += check_g_cap(inp[key], inp["r_perp"], key)
        if inp["r_perp"] - inp[key] < MIN_R_MINUS_G:
            e.append(f"r - {key} < {MIN_R_MINUS_G:.0%}: at the pole")
    if inp["g2"] <= 0:
        e.append("g2 <= 0 barred: FY27 -> FY28 consensus rises (同世界门, A16)")
    e += check_transition_years(N_STAGE, CONSENSUS_YEARS_BEYOND, "g1")
    if not (inp["eps_fy27_l"] < inp["eps_fy27_m"] < inp["eps_fy27_h"]):
        e.append("FY27 consensus range must be ordered low < mean < high (one record, two ends)")
    if not (0 < inp["rev_cut_l"] < 1 and 0 < inp["nm_fy25"] < 1 and 0 < inp["npo_share_28"] < 1):
        e.append("rev_cut_l / nm_fy25 / npo_share_28 must be fractions")
    if not (0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] < 1):
        e.append("k must satisfy 0 <= k_L <= k_M <= k_H < 1 (cyclical, 留存去向审计)")
    if inp["shares_a"] >= inp["shares_total"]:
        e.append("shares_a must be below shares_total (H-share dilution)")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        e.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")
    return e


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
    errors = check_inputs(inp, baskets)
    errors += check_optical_oe_mount((inp["oe_l"], inp["oe_m"], inp["oe_h"]))
    errors += check_capex_mount((inp["capex_l"], inp["capex_m"], inp["capex_h"]))
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    r, g2 = inp["r_perp"], inp["g2"]
    sh = inp["shares_total"]  # 百万股; money inputs are 百万 CNY
    adj = inp["shares_a"] / sh

    # ---- Step 1: numerators (FY27, per total share) ----
    eps = {
        "L": inp["rev_fy26_cons"] * (1 - inp["rev_cut_l"]) * inp["nm_fy25"] / sh,
        "M": inp["eps_fy27_m"] * adj,
        "H": inp["eps_fy27_h"] * adj,
    }
    # ---- Step 2: FY28 transition, NPO stripped (A4 / A11) ----
    g_total = (inp["ubs_eps28"] / inp["ubs_eps27"] + inp["citi_ni28"] / inp["citi_ni27"]) / 2
    g1 = g_total * (1 - inp["npo_share_28"]) - 1
    stage = {"L": False, "M": True, "H": True}

    # ---- Step 3: FY27 opening book, fixed point on b = g/ROE (A21) ----
    h_net = inp["h_shares"] * inp["h_price_hkd"] * inp["hkdcny"] * (1 - inp["h_fee"])
    eq0 = inp["equity_h1"] + h_net - inp["dps_interim"] * inp["shares_div"]

    def tier(e: float, with_g1: bool, g: float = g2) -> tuple[float, float, float]:
        """(BPS_open, ROE, multiple) for one FY27 numerator."""
        grow = g1 if with_g1 else g
        bps = (eq0 + inp["ni_h2_cons"]) / sh
        for _ in range(200):
            roe = e / bps
            nxt = (eq0 + inp["ni_h2_cons"] * min(1.0, grow / roe)) / sh
            if abs(nxt - bps) < 1e-10:
                break
            bps = nxt
        roe = e / bps
        pe = two_stage_pe(g1, N_STAGE, g, roe, r) if with_g1 else perpetual_pe(g, roe, r)
        return bps, roe, pe

    bps, roe, pe = {}, {}, {}
    for t in TIERS:
        bps[t], roe[t], pe[t] = tier(eps[t], stage[t])
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}
    pre = {t: eps[t] * pe[t] for t in TIERS}
    L, M, H = (pre[t] * (1 - k[t]) for t in TIERS)
    A, B = (L + M) / 2, (M + H) / 2
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}")
    for t in TIERS:
        if roe[t] - r < 0.03:
            errors.append(f"{t}: ROE {roe[t]:.3f} not in the monotone domain at r {r:g}")
        errors += check_branch(g2, roe[t], r, inp["payout_obs"], f"g2@{t}")
    for t in ("M", "H"):
        if not (0 < g1 / roe[t] < 1):
            errors.append(f"{t}: stage-1 b1 = g1/ROE {g1 / roe[t]:.3f} outside (0,1)")

    # ③ guardrail: M multiple inside own realised current-FY forward-PE band (A17).
    if not (inp["pe_own_min"] <= pe["M"] <= inp["pe_own_max"]):
        errors.append(f"M multiple {pe['M']:.2f}x outside own band [{inp['pe_own_min']}, {inp['pe_own_max']}] — ③ 出带")

    # ---- Step 5: NPO option (A13) ----
    npo_ni = inp["ubs_rev28"] * inp["npo_share_28"] * inp["nm_fy25"]
    eps_npo = npo_ni / sh
    pe_npo = perpetual_pe(inp["g_npo"], roe["M"], r)
    v_opt = eps_npo * pe_npo / (1 + r)
    plus_v = tuple(x + p * v_opt for x, p in zip((L, M, H), P_TIERS))

    # ---- A2e-2c flat ladder + decomposition ----
    flat_errs, flat = flat_multiple_ladder((eps["L"], eps["M"], eps["H"]), pe["M"])
    errors += flat_errs
    dec = decompose((L, M, H), (pe["L"] * (1 - k["L"]), pe["M"] * (1 - k["M"]), pe["H"] * (1 - k["H"])))

    # ---- Axes (A18) ----
    npo_asp_cny = inp["ubs_rev28"] * inp["npo_share_28"] / inp["npo_units_28"]  # 百万 CNY / unit
    narrow = {
        # Axis tiers are one year (2028): L = delayed a year (2027 volume), M = H = UBS 2028.
        "L": inp["npo_units_27"] * npo_asp_cny * 1e6 / inp["usdcny"],
        "M": inp["ubs_rev28"] * inp["npo_share_28"] * 1e6 / inp["usdcny"],
        "H": inp["ubs_rev28"] * inp["npo_share_28"] * 1e6 / inp["usdcny"],
    }
    errors += check_optical_narrow_attach(narrow)
    oe = {"L": inp["oe_l"], "M": inp["oe_m"], "H": inp["oe_h"]}

    # ---- Reconcile stated Outputs ----
    out_sec = md.split("### Outputs", 1)[-1]
    stated = {
        "L": first_float(r"L = \*\*([0-9.]+)\*\*", out_sec),
        "M": first_float(r"M = \*\*([0-9.]+)\*\*", out_sec),
        "H": first_float(r"H = \*\*([0-9.]+)\*\*", out_sec),
        "A": first_float(r"A = \*\*([0-9.]+)\*\*", out_sec),
        "B": first_float(r"B = \*\*([0-9.]+)\*\*", out_sec),
        "V": first_float(r"V_\{opt\}\\\) = \*\*([0-9.]+)\*\*", out_sec),
    }
    for key, got in {"L": L, "M": M, "H": H, "A": A, "B": B, "V": v_opt}.items():
        said = stated.get(key)
        if said is None:
            errors.append(f"stated {key} not found in Outputs")
        elif abs(said - got) > TOL:
            errors.append(f"{key}: stated {said} vs recomputed {got:.4f}")
    p_line = re.search(r"p_L/p_M/p_H\\\) = \*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*", out_sec)
    if p_line is None or tuple(float(x) for x in p_line.groups()) != P_TIERS:
        errors.append(f"Outputs p_L/p_M/p_H must state {P_TIERS}")

    # ---- Report ----
    print(f"formula_id={FORMULA_ID}")
    print(f"share basis: consensus EPS on A shares {inp['shares_a']:.3f}M -> total {sh:.3f}M (x{adj:.4f})")
    print(f"FY28: UBS {inp['ubs_eps28'] / inp['ubs_eps27'] - 1:+.1%}, Citi {inp['citi_ni28'] / inp['citi_ni27'] - 1:+.1%}"
          f" -> mean {g_total - 1:+.1%}, NPO {inp['npo_share_28']:.0%} stripped -> g1 {g1:+.2%} (M/H, n={N_STAGE})")
    print(f"g2 {g2:.2%} (user-set; named macro {MACRO_G:.0%}, cap {g_cap(r):.0%}) r {r:g} (篮 {baskets['r_perp']})")
    print(f"FY27 opening equity: H1 {inp['equity_h1']:.0f} + H-share net {h_net:.0f} - interim div "
          f"{inp['dps_interim'] * inp['shares_div']:.0f} + retained share of H2 NI {inp['ni_h2_cons']:.0f} (百万 CNY)")
    for t in TIERS:
        print(f"{t}: EPS {eps[t]:.4f} BPS_open {bps[t]:.2f} ROE {roe[t]:.3f} PE {pe[t]:.2f}"
              f" -> {pre[t]:.2f} x (1-k {k[t]:.2f}) = {pre[t] * (1 - k[t]):.2f}"
              f"  [perpetual payout {payout(g2, roe[t]):.3f}{f', stage-1 b1 {g1 / roe[t]:.3f}' if stage[t] else ''}]")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"NPO option: NI {npo_ni:.0f} 百万 -> EPS {eps_npo:.4f} x PE {pe_npo:.2f} (g {inp['g_npo']:.0%}, ROE_M {roe['M']:.3f})"
          f" / {1 + r:g} = V_opt {v_opt:.2f}; p {P_TIERS} -> +V {plus_v[0]:.2f}/{plus_v[1]:.2f}/{plus_v[2]:.2f}"
          f" A' {(plus_v[0] + plus_v[1]) / 2:.2f} B' {(plus_v[1] + plus_v[2]) / 2:.2f}")
    print(f"guardrail: M {pe['M']:.2f}x (after k {pe['M'] * (1 - k['M']):.2f}x) vs own band "
          f"[{inp['pe_own_min']}, {inp['pe_own_max']}]; L {pe['L']:.2f}x H {pe['H']:.2f}x")
    for t in TIERS:
        g_lo, _ = implied_g(inp["pe_own_min"], roe[t], r)
        g_hi, _ = implied_g(inp["pe_own_max"], roe[t], r)
        print(f"  band-edge implied g @ ROE_{t} {roe[t]:.3f}: [{g_lo:+.2%}, {g_hi:+.2%}]")
    print(f"flat ladder @ M {pe['M']:.2f}x x (1-k_M): "
          + "/".join(f"{e_ * pe['M'] * (1 - k['M']):.2f}" for e_ in (eps['L'], eps['M'], eps['H'])))
    print(f"L/M {dec['lm']:.3f} = num {dec['num_lm']:.3f} x pe {dec['pe_lm']:.3f} | H/M {dec['hm']:.3f}"
          f" = num {dec['num_hm']:.3f} x pe {dec['pe_hm']:.3f} | width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}")
    ret = 1 - inp["payout_obs"]
    print("视同派出、实际留存 (k 前 / k 后, 元/股/年, FY27 分子): "
          + " ".join(f"{t} {(ret - (g1 if stage[t] else g2) / roe[t]) * eps[t]:.2f}" for t in TIERS)
          + f"  [actual retention {ret:.0%}]")
    for g in (g2 - 0.01, g2 + 0.01, MACRO_G):
        vals = [eps[t] * tier(eps[t], stage[t], g)[2] * (1 - k[t]) for t in TIERS]
        print(f"  sens g2={g:.2%}: {vals[0]:.2f}/{vals[1]:.2f}/{vals[2]:.2f}")
    for lab, gt in (("derived 4-house mean", (84.96 / 60.69 + 1670 / 970 + 79 / 59.89 + 82.4 / 59.67) / 4),):
        g1_alt = gt * (1 - inp["npo_share_28"]) - 1
        vals = []
        for t in TIERS:
            e_ = eps[t]
            if stage[t]:
                b_, r_, _ = tier(e_, True)
                vals.append(e_ * two_stage_pe(g1_alt, N_STAGE, g2, r_, r) * (1 - k[t]))
            else:
                vals.append(pre[t] * (1 - k[t]))
        print(f"  sens g1 from {lab} ({g1_alt:+.1%}): {vals[0]:.2f}/{vals[1]:.2f}/{vals[2]:.2f}")
    for cut in (0.20, 0.40):
        e_ = inp["rev_fy26_cons"] * (1 - cut) * inp["nm_fy25"] / sh
        print(f"  sens rev_cut_l={cut:.0%}: L {e_ * tier(e_, False)[2]:.2f}")
    print(f"  k = 0 reference: {pre['L']:.2f}/{pre['M']:.2f}/{pre['H']:.2f}")
    print("optical narrow (NPO, USD): " + " ".join(
        f"{t} ${narrow[t] / 1e9:.3f}B attach {optical_attachment(narrow[t], t):.1%} (OE share {n_ / oe[t]:.1%})"
        for t, n_ in (("L", inp["npo_units_27"]), ("M", inp["npo_units_28"]), ("H", inp["npo_units_28"]))))
    rev_usd = inp["rev_fy27_cons"] * 1e6 / inp["usdcny"]
    print(f"capex axis implied share (wide, FY27 revenue ${rev_usd / 1e9:.1f}B): M {rev_usd / inp['capex_m']:.2%}")
    print("r_f readings: CNY segment of _AXIS.rates 待建 — not printed")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
