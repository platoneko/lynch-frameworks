#!/usr/bin/env python3
"""BA.US (Boeing) valuation eval — recompute anchors from frameworks/BA.US.md.

frameworks/BA.US.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries no
current price (AGENTS.md「现价 — 禁写契约」): which zone a quote falls in is
derived live by the daily digest and the app, so nothing here reads a price.

formula_id: ba_unlevered_fy27_recovery_gordon_v1

The leverage gate fires (FY2025 net debt / EBITDA 4.4, interest / EBIT 65%), so
the ruler is unlevered: FY2027E core EPS consensus three points (21 analysts)
are bridged to NOPAT by adding back the mandatory-convertible dividend and the
after-tax net interest; EV = NOPAT × Gordon multiple on ROIC; equity = EV −
net debt − after-tax pension / retiree-health deficit; per share on the
post-conversion share count (the 2027-10 mandatory convertible converts at a
rate set by the price, so each tier solves its own count).

M / H carry one transition year (FY2027 → FY2028 consensus EBIT growth, n = 1)
in the recovery form: the jump is rate ramp on lines already built, so stage 1
pays out in full and only the tail carries the retention term, at the FY2028
ROIC.  L carries no transition — the world where the recovery stalls at the
FY2027 consensus low.  Basket 4 r 10%, g2 = peer-cluster median capped at 6%.

Run:  python3 frameworks/eval/BA.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import (  # noqa: E402
    check_branch, check_g_cap, check_r, check_transition_years, g_cap, perpetual_pe,
    recovery_two_stage_pe, two_stage_pe,
)
from lib.inputs import check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report  # noqa: E402
from lib.zones import cut_points  # noqa: E402

# rf_report imports eval.lib.* absolutely, so the repo root must be importable too.
sys.path.append(str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "BA.US.md"
FORMULA_ID = "ba_unlevered_fy27_recovery_gordon_v1"
LISTING_CCY = "USD"
REQUIRED = [
    "shares_basic", "mcp_units", "mcp_rate_min", "mcp_rate_max",
    "eps27_low", "eps27_mean", "eps27_high", "pref_div", "int_exp", "int_inc", "tax_rate",
    "ebit27_ms", "ebit28_ms", "n_stage", "equity", "debt", "cash", "pension_def", "opeb_def",
    "r_perp", "g2", "peer_g_median", "peer_g_defense", "payout_observed",
    "net_debt_ebitda_fy25", "interest_ebit_fy25", "ebitda28_ms", "fcf28_ms", "k_l", "k_m", "k_h",
]


def mcp_shares(price: float, inp: dict[str, float]) -> float:
    """Common shares the mandatory convertible delivers at a given price (millions)."""
    # Between the two thresholds each $1,000 preferred delivers $1,000 of stock.
    rate = min(max(1000.0 / price, inp["mcp_rate_min"]), inp["mcp_rate_max"])
    return inp["mcp_units"] * rate


def per_share(equity_value: float, inp: dict[str, float]) -> tuple[float, float]:
    """Fixed point: the conversion rate depends on the per-share value it produces."""
    value = equity_value / inp["shares_basic"]
    for _ in range(50):
        shares = inp["shares_basic"] + mcp_shares(value, inp)
        value = equity_value / shares
    return value, shares


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8") if FRAMEWORK.exists() else ""
    if md and FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r, g2, t = inp["r_perp"], inp["g2"], inp["tax_rate"]
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N in the Inputs source cell")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(g2, r, "g2")
    if abs(g2 - min(inp["peer_g_median"], g_cap(r))) > 1e-9:
        errors.append(f"g2 {g2} != min(peer median {inp['peer_g_median']}, cap {g_cap(r)})")
    n = int(inp["n_stage"])
    errors += check_transition_years(n, 1, "n_stage (FY2028 point consensus only)")
    errors += ladder("eps27", inp["eps27_low"], inp["eps27_mean"], inp["eps27_high"])

    # Step 1 — unlevered numerator (NOPAT, $M): core NI + MCP dividend + after-tax net interest.
    addback = inp["pref_div"] + (inp["int_exp"] - inp["int_inc"]) * (1 - t)
    nopat = {k: inp[f"eps27_{k}"] * inp["shares_basic"] + addback for k in ("low", "mean", "high")}
    g1 = inp["ebit28_ms"] / inp["ebit27_ms"] - 1

    # Step 2 — invested capital and ROIC (leverage gate: retention runs on ROIC, not ROE).
    net_debt = inp["debt"] - inp["cash"]
    ic = inp["equity"] + net_debt
    roic27 = {k: v / ic for k, v in nopat.items()}
    roic28 = {k: v * (1 + g1) / ic for k, v in nopat.items()}

    # Step 3 — multiples on FY2027 NOPAT.
    pe_l = perpetual_pe(g2, roic27["low"], r)
    pe_m = recovery_two_stage_pe(g1, n, g2, roic28["mean"], r)
    pe_h = recovery_two_stage_pe(g1, n, g2, roic28["high"], r)
    for tier, roic in (("M", roic28["mean"]), ("H", roic28["high"])):
        errors += check_branch(g2, roic, r, inp["payout_observed"], f"{tier} tail")

    # Step 4 — EV → equity → per share; × (1 − k) for cash the model treats as paid out
    # while the company retains it (A bucket: debt paydown, so k = 0 by source ②).
    claims = net_debt + (inp["pension_def"] + inp["opeb_def"]) * (1 - t)
    ev = {"L": nopat["low"] * pe_l, "M": nopat["mean"] * pe_m, "H": nopat["high"] * pe_h}
    ks = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}
    anchors, shares = {}, {}
    for k, v in ev.items():
        value, shares[k] = per_share(v - claims, inp)
        anchors[k] = value * (1 - ks[k])
    L, M, H = anchors["L"], anchors["M"], anchors["H"]
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f} {M:.2f} {H:.2f}")

    # construction §2c — flat multiple (M's) on every tier's numerator must still ladder.
    flat = {k: per_share(nopat[j] * pe_m - claims, inp)[0] for k, j in (("L", "low"), ("M", "mean"), ("H", "high"))}
    errors += ladder("flat-multiple", flat["L"], flat["M"], flat["H"])

    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, None)

    post = {"L": nopat["low"], "M": nopat["mean"] * (1 + g1), "H": nopat["high"] * (1 + g1)}
    print(f"formula_id={FORMULA_ID}  r={r:g} (篮 {baskets.get('r_perp')})  g2={g2:g} (peer median {inp['peer_g_median']:g} → cap {g_cap(r):g})  g1={g1:.4f} n={n}")
    print(f"addback {addback:.0f}  net debt {net_debt:.0f}  IC {ic:.0f}  claims {claims:.0f}")
    for k, j in (("L", "low"), ("M", "mean"), ("H", "high")):
        pe = {"L": pe_l, "M": pe_m, "H": pe_h}[k]
        print(f"{k}: NOPAT27 {nopat[j]:.0f}  ROIC27 {roic27[j]:.1%}  ROIC28 {roic28[j]:.1%}  PE(t=1) {pe:.2f}  "
              f"post-transition NOPAT {post[k]:.0f} → EV/NOPAT {ev[k] / post[k]:.2f}  EV {ev[k]:.0f}  "
              f"shares {shares[k]:.1f}  → {anchors[k]:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} width={(H - L) / (2 * M):.3f}  "
          f"numerator ratio L/M {post['L'] / post['M']:.3f} H/M {post['H'] / post['M']:.3f}; "
          f"multiple ratio L/M {(ev['L'] / post['L']) / (ev['M'] / post['M']):.3f} H/M {(ev['H'] / post['H']) / (ev['M'] / post['M']):.3f}")
    print(f"flat ladder (M multiple {pe_m:.2f} on each tier): {flat['L']:.2f} / {flat['M']:.2f} / {flat['H']:.2f}")

    # Disclosures (do not price).
    pe_m_retain = two_stage_pe(g1, n, g2, roic27["mean"], r)
    m_retain = per_share(nopat["mean"] * pe_m_retain - claims, inp)[0]
    print(f"cross two_stage_pe (stage-1 retention charged at ROIC27 {roic27['mean']:.1%}, payout {1 - g1 / roic27['mean']:.2f}): PE {pe_m_retain:.2f} → M {m_retain:.2f}")
    for label, gg in (("g2 −1pp", g2 - 0.01), ("defense cluster", inp["peer_g_defense"])):
        mm = per_share(nopat["mean"] * recovery_two_stage_pe(g1, n, gg, roic28["mean"], r) - claims, inp)[0]
        hh = per_share(nopat["high"] * recovery_two_stage_pe(g1, n, gg, roic28["high"], r) - claims, inp)[0]
        ll = per_share(nopat["low"] * perpetual_pe(gg, roic27["low"], r) - claims, inp)[0]
        print(f"sensitivity {label} g2={gg:.4f}: L {ll:.2f} M {mm:.2f} H {hh:.2f}")
    for k, j in (("L", "low"), ("M", "mean"), ("H", "high")):
        # Stage 1 (or L's first year) pays out 100% in the model; the company pays 0.
        deemed = nopat[j] / shares[k]
        print(f"deemed-paid, actually retained ({k}, 1 yr, A bucket): {deemed:.2f}/sh  k={ks[k]:g} → after k {deemed * (1 - ks[k]):.2f}")
    l_g0 = per_share(nopat["low"] * perpetual_pe(0.0, roic27["low"], r) - claims, inp)[0]
    print(f"L at g2=0 (pathological domain, PE {perpetual_pe(0.0, roic27['low'], r):.2f}): {l_g0:.2f}")
    rate_eps = inp["debt"] * 0.01 * (1 - t) / inp["shares_basic"]
    print(f"leverage gate: net debt/EBITDA FY25 {inp['net_debt_ebitda_fy25']:.2f}  interest/EBIT {inp['interest_ebit_fy25']:.0%}  "
          f"+100bp on total debt → EPS −{rate_eps:.2f} ({rate_eps / inp['eps27_mean']:.0%} of FY27 mean)")
    print(f"EV/EBITDA FY28: M {ev['M'] / inp['ebitda28_ms']:.1f}  H {ev['H'] / inp['ebitda28_ms']:.1f}  "
          f"| EV / FY28 FCF: M {ev['M'] / inp['fcf28_ms']:.1f}  H {ev['H'] / inp['fcf28_ms']:.1f}")

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_perp 1:1 — the only priced r; g1/g2, ROIC, NOPAT, claims and k stay put
    # (the conversion count still solves at each column's value).  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        rr = r + dr
        ev_r = {
            "L": nopat["low"] * perpetual_pe(g2, roic27["low"], rr),
            "M": nopat["mean"] * recovery_two_stage_pe(g1, n, g2, roic28["mean"], rr),
            "H": nopat["high"] * recovery_two_stage_pe(g1, n, g2, roic28["high"], rr),
        }
        lmh = [per_share(ev_r[k] - claims, inp)[0] * (1 - ks[k]) for k in ("L", "M", "H")]
        return lmh[0], lmh[1], lmh[2]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    # 0.05 = check_against_stated's default tolerance, the one the anchors are held to.
    if any(abs(x - y) > 0.05 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    # Only a clean run writes, so a FAIL never feeds the daily digest.
    if not errors:
        write_rf_readings("BA.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
