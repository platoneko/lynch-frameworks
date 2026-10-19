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
    "tau", "eps26_cons", "eps_h1_26", "parent_share", "y1", "y2", "rs_own_cycle",
    "rs_fallback", "rs_own_cycle_ex_pension",
]
NUM_YEAR = 2027  # numerator FY2027 = calendar year; t_n = 2027-01-01


def three_segment_pe(t0: int, y1: int, y2: int, rs: float, g2: float, roe: float, r: float, *,
                     g1: float = 0.0, n: int = 0, recovery: bool = False) -> float:
    """Multiple on numerator-year earnings with the steady-return path (valuation-rules
    「经营价值与超额现金」② 稳态回报三段): RONIC = forward through calendar y1, linear to
    min(roe, rs) by y2, Gordon tail from y2.  Stage-1 years pay out in full when `recovery`
    (recovery_two_stage_pe form) else 1 - g1/roe.  With rs >= roe this equals
    perpetual_pe / recovery_two_stage_pe exactly.  (gordon.py three-segment helper is [待建].)"""
    rss = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rss
        return roe + (rss - roe) * (cal - y1) / (y2 - y1)

    pv, e, t = 0.0, 1.0, 1
    for _ in range(n):
        pv += e * (1.0 if recovery else 1.0 - g1 / roe) / (1 + r) ** t
        e *= 1 + g1
        t += 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g2 / rss) / ((r - g2) * (1 + r) ** (t - 1))
        pv += e * min(1.0, 1.0 - g2 / ron(cal)) / (1 + r) ** t
        e *= 1 + g2
        t += 1


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
    # The forward denominator carries the after-tax pension / OPEB deficit too, the same
    # invested-capital basis as the own-cycle steady reading (retention「回报口径」, user
    # 2026-10-19), so forward and steady returns compare like for like.
    net_debt = inp["debt"] - inp["cash"]
    pension_at = (inp["pension_def"] + inp["opeb_def"]) * (1 - t)
    ic = inp["equity"] + net_debt + pension_at
    roic27 = {k: v / ic for k, v in nopat.items()}
    roic28 = {k: v * (1 + g1) / ic for k, v in nopat.items()}

    # Step 3 — multiples on FY2027 NOPAT, on the steady-return path (A15): forward ROIC
    # through Y1, linear to the steady return by Y2.  Steady = max(own full cycle, mature peers
    # (empty: Textron is not the same business), business-model fallback), read on invested
    # capital incl. the after-tax pension / OPEB deficit (retention「回报口径」2026-10-19);
    # each tier then takes min(forward, steady) — L (11.6%) stays at forward, M / H fade.
    y1, y2 = int(inp["y1"]), int(inp["y2"])
    rs = max(inp["rs_own_cycle"], inp["rs_fallback"])
    if rs < r:
        errors.append(f"steady return {rs:.3f} < r {r}")
    if inp["rs_own_cycle"] >= inp["rs_own_cycle_ex_pension"]:
        errors.append("own-cycle reading with the pension deficit in capital must sit below the ex-pension one")
    rs_src = "own cycle" if inp["rs_own_cycle"] >= inp["rs_fallback"] else "fallback"

    def tier_pes(r_: float) -> dict[str, float]:
        return {
            "L": three_segment_pe(NUM_YEAR, y1, y2, rs, g2, roic27["low"], r_),
            "M": three_segment_pe(NUM_YEAR, y1, y2, rs, g2, roic28["mean"], r_, g1=g1, n=n, recovery=True),
            "H": three_segment_pe(NUM_YEAR, y1, y2, rs, g2, roic28["high"], r_, g1=g1, n=n, recovery=True),
        }

    pes = tier_pes(r)
    pe_l, pe_m, pe_h = pes["L"], pes["M"], pes["H"]
    if abs(pe_l - perpetual_pe(g2, roic27["low"], r)) > 1e-9 or abs(
            pe_m - recovery_two_stage_pe(g1, n, g2, roic28["mean"], r)) > 1e-9:
        print("note: steady-return path binds (rs below a tier's forward ROIC)")
    for tier, roic in (("M", roic28["mean"]), ("H", roic28["high"])):
        errors += check_branch(g2, roic, r, inp["payout_observed"], f"{tier} tail")

    # Step 4 — timing (A15): the Gordon value is at t_n = 2027-01-01; discount tau years to the
    # 2026-06-30 balance sheet and add the window's distributable NOPAT (2026H2 consensus,
    # x (1 - b): M / H stage 1 is the recovery form, b = 0; L b = g2 / ROIC27_L) at tau / 2.
    # EV → equity → per share; × (1 − k) (A bucket, k = 0 by source ②).
    tau = inp["tau"]
    win_nopat = (inp["eps26_cons"] - inp["eps_h1_26"]) * inp["shares_basic"] + addback / 2
    win_b = {"L": g2 / roic27["low"], "M": 0.0, "H": 0.0}
    claims = net_debt + pension_at
    ks = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}

    def tier_ev(pes_: dict[str, float], r_: float) -> dict[str, float]:
        return {k: nopat[j] * pes_[k] / (1 + r_) ** tau
                + max(win_nopat * (1 - win_b[k]), 0.0) * inp["parent_share"] / (1 + r_) ** (tau / 2)
                for k, j in (("L", "low"), ("M", "mean"), ("H", "high"))}

    ev = tier_ev(pes, r)
    anchors, shares = {}, {}
    for k, v in ev.items():
        value, shares[k] = per_share(v - claims, inp)
        anchors[k] = value * (1 - ks[k])
    L, M, H = anchors["L"], anchors["M"], anchors["H"]
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f} {M:.2f} {H:.2f}")

    # construction §2c — flat multiple (M's) on every tier's numerator must still ladder.
    flat_ev = tier_ev({"L": pe_m, "M": pe_m, "H": pe_m}, r)
    flat = {k: per_share(flat_ev[k] - claims, inp)[0] for k in ("L", "M", "H")}
    errors += ladder("flat-multiple", flat["L"], flat["M"], flat["H"])

    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    post = {"L": nopat["low"], "M": nopat["mean"] * (1 + g1), "H": nopat["high"] * (1 + g1)}
    print(f"formula_id={FORMULA_ID}  r={r:g} (篮 {baskets.get('r_perp')})  g2={g2:g} (peer median {inp['peer_g_median']:g} → cap {g_cap(r):g})  g1={g1:.4f} n={n}")
    print(f"addback {addback:.0f}  net debt {net_debt:.0f}  IC {ic:.0f}  claims {claims:.0f}")
    print(f"timing (A15): tau {tau:g}y → Gordon EV × {(1 + r) ** -tau:.4f}; window 2026H2 NOPAT {win_nopat:.0f} "
          f"× (1 − b) b L {win_b['L']:.3f} / M,H 0 × parent {inp['parent_share']:g} at tau/2; "
          f"steady path Y1 {y1} → Y2 {y2}, steady {rs:.1%} ({rs_src}; ex-pension reading "
          f"{inp['rs_own_cycle_ex_pension']:.1%} not used) → per tier: "
          + ", ".join(f"{k} {fw:.1%}→{min(fw, rs):.1%}" for k, fw in
                      (("L", roic27["low"]), ("M", roic28["mean"]), ("H", roic28["high"]))))
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
    ys = {k: per_share(nopat[j] * pes[k] - claims, inp)[0] for k, j in (("L", "low"), ("M", "mean"), ("H", "high"))}
    print(f"at numerator-year start 2027-01-01 (no tau, no window): EV M {nopat['mean'] * pe_m:.0f} H {nopat['high'] * pe_h:.0f}"
          f"  per share L {ys['L']:.2f} M {ys['M']:.2f} H {ys['H']:.2f}")
    pe_m_retain = two_stage_pe(g1, n, g2, roic27["mean"], r)
    m_retain = per_share(tier_ev({**pes, "M": pe_m_retain}, r)["M"] - claims, inp)[0]
    print(f"cross two_stage_pe (stage-1 retention charged at ROIC27 {roic27['mean']:.1%}, payout {1 - g1 / roic27['mean']:.2f}): PE {pe_m_retain:.2f} → M {m_retain:.2f}")
    for label, gg in (("g2 −1pp", g2 - 0.01), ("defense cluster", inp["peer_g_defense"])):
        pes_g = {
            "L": three_segment_pe(NUM_YEAR, y1, y2, rs, gg, roic27["low"], r),
            "M": three_segment_pe(NUM_YEAR, y1, y2, rs, gg, roic28["mean"], r, g1=g1, n=n, recovery=True),
            "H": three_segment_pe(NUM_YEAR, y1, y2, rs, gg, roic28["high"], r, g1=g1, n=n, recovery=True),
        }
        ev_g = tier_ev(pes_g, r)
        ll, mm, hh = (per_share(ev_g[k] - claims, inp)[0] for k in ("L", "M", "H"))
        print(f"sensitivity {label} g2={gg:.4f}: L {ll:.2f} M {mm:.2f} H {hh:.2f}")
    for lab, rs_alt in (("steady at mature-peer / fallback 15%", 0.15),):
        pes_s = {
            "L": three_segment_pe(NUM_YEAR, y1, y2, rs_alt, g2, roic27["low"], r),
            "M": three_segment_pe(NUM_YEAR, y1, y2, rs_alt, g2, roic28["mean"], r, g1=g1, n=n, recovery=True),
            "H": three_segment_pe(NUM_YEAR, y1, y2, rs_alt, g2, roic28["high"], r, g1=g1, n=n, recovery=True),
        }
        ev_s = tier_ev(pes_s, r)
        print(f"sensitivity {lab}: " + " / ".join(f"{per_share(ev_s[k] - claims, inp)[0]:.2f}" for k in ("L", "M", "H")))
    ic_x = ic - pension_at  # old basis: forward denominator without the pension deficit (A9)
    pes_x = {
        "L": three_segment_pe(NUM_YEAR, y1, y2, rs, g2, nopat["low"] / ic_x, r),
        "M": three_segment_pe(NUM_YEAR, y1, y2, rs, g2, nopat["mean"] * (1 + g1) / ic_x, r, g1=g1, n=n, recovery=True),
        "H": three_segment_pe(NUM_YEAR, y1, y2, rs, g2, nopat["high"] * (1 + g1) / ic_x, r, g1=g1, n=n, recovery=True),
    }
    ev_x = tier_ev(pes_x, r)
    print("disclosure forward ROIC denominator ex-pension (old basis): "
          + " / ".join(f"{per_share(ev_x[k] - claims, inp)[0]:.2f}" for k in ("L", "M", "H")))
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
        ev_r = tier_ev(tier_pes(rr), rr)
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
