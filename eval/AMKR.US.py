#!/usr/bin/env python3
"""AMKR.US valuation eval — recompute anchors from frameworks/AMKR.US.md.

formula_id: amkr_fy27_cons_gordon_opeq_v1

One operating leg on the FY27 consensus EPS range (9 houses; the furthest year
with a >=2-house *range*, valuation-rules 裁决顺序 ②; A2).  Street EPS is GAAP
(Amkor reports no adjusted EPS; SBC ~$20M/yr is already expensed), so no SBC
haircut (A4).  Multiples are generated: `perpetual_pe(g2, ROE_x, r)` with g2 =
the Taiwan OSAT peer cluster's reverse-solved median truncated to g_cap(r)
(A7), r = 10% — basket 4 常规经营 (packaging / test is priced per contract,
the cycle is customers' unit volumes and utilisation, not a commodity price;
Apple 29.8% + Qualcomm 11.1% stay under the basket-7 thresholds, A9) — and
tier ROE = FY27 core EPS over the FY27 OPENING *operating* book (book equity
plus net debt at 2026-06-30, rolled over the FY26 second half not yet booked
at b1 = g2/ROE, A6).  After-tax net interest is stripped from the numerator,
net debt (incl. leases and the 0% 2031 convertible at par, A11) is a closing
item, and the Arizona phase-1 capital not yet earning in FY27 is charged at
(ROIC_proj / r - 1) x net capital as a second closing item (D bucket, A10).

Framework correction 2026-10-16 (valuation-rules「经营价值与超额现金」, A18):
  * steady-state-return path (② 稳态回报三段): RONIC = tier forward ROE through
    Y1 = FY2027 (visible end), linear to the steady 15% (OSAT, user-set) by
    Y2 = 2031 (barrier 中 -> 4 years), capped at the tier's forward value;
  * time alignment (③): the Gordon value sits at the start of FY27; today =
    V_op / (1+r)^tau + window distributable profit (FY26H2 unbooked core EPS x
    (1 - b1), at tau/2), tau = 2026-06-30 -> 2027-01-01 = 0.5;
  * the deemed-distribution k is dropped (it multiplied the whole operating value).
anchor_x = core_x x path_pe x (1+r)^-tau + window_x + closing.

V_opt: the count comes only from a quantity Amkor itself named — the 2030
revenue target less the FY27 consensus revenue already priced in H (A16).
Unit economics = FY27 mean-consensus core earnings per revenue dollar; valued
at the H path multiple (folded by tau) in 2030 and discounted back three years
at the basket r.

The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so nothing
here reads one.

Run:  python3 frameworks/eval/AMKR.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    check_branch,
    check_g_cap,
    check_r,
    g_cap,
    payout_gap,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_baskets,
    parse_inputs,
    report,
)
from eval.lib.rf_report import rf_block  # noqa: E402
from eval.lib.zones import cut_points  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "AMKR.US.md"
FORMULA_ID = "amkr_fy27_cons_gordon_opeq_v1"
LISTING_CCY = "USD"
TOL = 0.05
MILLION = 1e6  # money inputs are in $M, share counts are absolute
MIN_R_MINUS_G = 0.02
P_TIERS = (0.0, 0.25, 1.0)  # A16 — table 3 only, never an input
PEER_PE_SAME_RULER = (18.65, 20.33)  # A12 ⑤: PTI / ASE at r 10%, g 6% (KYEC 19.99 inside)

REQUIRED = [
    "shares", "shares_out", "equity", "cash", "debt", "lease_fin", "lease_op", "net_cash",
    "int_q", "tax", "eps_fy26_m", "eps_h1_26", "eps_fy27_l", "eps_fy27_m", "eps_fy27_h",
    "payout_3y", "r_perp", "g2", "g_peer_median", "g_peer_low",
    "az_rev", "az_gm", "opex_ratio", "az_tax", "az_capex", "az_itc", "az_grant",
    "mgmt_rev_2030", "mgmt_eps_2030", "rev_fy27_m", "rev_fy27_h", "t_opt", "t_num",
    "pb_low", "band_pe_min", "band_pe_max",
    "tau", "y1", "y2", "rs_steady",
]
TIERS = ("L", "M", "H")


def path_pe(g: float, roe: float, r: float, t0: int, y1: int, y2: int, rs: float) -> float:
    """Gordon multiple on the steady-state-return path (valuation-rules「经营价值与超额现金」②
    稳态回报三段; gordon.py's three-segment function is not built yet, so it lives here).

    Calendar years, t = 1 is the numerator year t0; the retention of year c earns from c+1.
    RONIC = the tier's forward value through Y1, falls linearly to the steady value R_s by Y2,
    and stays there (R_s capped at the tier's forward value).  With R_s >= forward this is
    exactly perpetual_pe(g, roe, r)."""
    rs_eff = min(roe, rs)

    def ron(cal: int) -> float:
        if cal <= y1:
            return roe
        if cal >= y2:
            return rs_eff
        return roe + (rs_eff - roe) * (cal - y1) / (y2 - y1)

    if r - g <= 0:
        raise ValueError(f"perpetuity diverges: g={g} >= r={r}")
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * min(1.0, 1.0 - g / rs_eff) / ((r - g) * (1 + r) ** (t - 1))
        pv += e * min(1.0, 1.0 - g / ron(cal)) / (1 + r) ** t
        e *= 1 + g
        t += 1


def sanity_checks(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    errs: list[str] = []

    # A9: one leg, r is the basket's value; the basket is named in the Inputs source cell.
    if "r_perp" not in baskets:
        errs.append("r_perp: Inputs source cell names no 篮 N (A9)")
    errs += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))

    # A7: g2 is the peer median truncated to g_cap(r); the cluster's low end is the evidence range.
    cap = g_cap(inp["r_perp"])
    errs += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    if abs(inp["g2"] - min(inp["g_peer_median"], cap)) > 5e-5:
        errs.append(f"g2={inp['g2']:.4f} != min(peer median {inp['g_peer_median']:.4f}, cap {cap:.3f}) — A7")
    if not inp["g_peer_low"] <= inp["g2"]:
        errs.append("g_peer_low must not exceed g2 (A8 evidence range)")
    if inp["r_perp"] - inp["g2"] < MIN_R_MINUS_G:
        errs.append(f"r - g2 = {inp['r_perp'] - inp['g2']:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")

    # 裁决顺序 ④ 同世界门 (A7): FY26 -> FY27 consensus up, so a g2 >= 0 source is admissible.
    if not inp["eps_fy26_m"] < inp["eps_fy27_m"]:
        errs.append("FY26 consensus not below FY27: the same-world gate for g2 >= 0 no longer holds (A7)")

    errs += ladder("numerator", inp["eps_fy27_l"], inp["eps_fy27_m"], inp["eps_fy27_h"])

    # A5 / A11: the closing item is what the book is grossed up by.
    nc = inp["cash"] - inp["debt"] - inp["lease_fin"] - inp["lease_op"]
    if abs(nc - inp["net_cash"]) > 0.05:
        errs.append(f"net_cash {inp['net_cash']} != cash - debt - leases {nc:.1f} (A5)")

    # A18: the steady-state-return path and the time alignment.
    if not int(inp["t_num"]) <= int(inp["y1"]) < int(inp["y2"]):
        errs.append("need t_num <= y1 < y2 (A18)")
    if not inp["r_perp"] <= inp["rs_steady"]:
        errs.append("rs_steady must not fall below r (A18)")
    if not 0.0 <= inp["tau"] < 2.0:
        errs.append(f"tau {inp['tau']} out of range (A18)")
    if any(k in inp for k in ("k_l", "k_m", "k_h")):
        errs.append("k_* rows present — the k on the whole operating value was dropped (A18)")

    # A10: Arizona capital nets positive after credits and grants.
    if not inp["az_capex"] > inp["az_itc"] + inp["az_grant"] > 0:
        errs.append("Arizona net capital must be positive (A10)")

    # A16: the option counts only what the target adds above consensus already in H.
    if not inp["mgmt_rev_2030"] > inp["rev_fy27_h"] >= inp["rev_fy27_m"] > 0:
        errs.append("mgmt_rev_2030 must exceed FY27 consensus revenue (H >= M > 0) (A16)")
    if not inp["t_opt"] > inp["t_num"]:
        errs.append("t_opt must fall after the numerator year t_num (A16)")

    p_fields = [k for k in inp if k.startswith("p_")]
    if p_fields:
        errs.append(f"Inputs carry probability fields {p_fields} — p_k belongs in table 3 only")
    return errs


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    baskets = parse_baskets(md)
    errors = sanity_checks(inp, baskets)

    r, g2 = inp["r_perp"], inp["g2"]
    cap = g_cap(r)
    street = {"L": inp["eps_fy27_l"], "M": inp["eps_fy27_m"], "H": inp["eps_fy27_h"]}
    tau, t0 = inp["tau"], int(inp["t_num"])
    y1, y2, rs = int(inp["y1"]), int(inp["y2"]), inp["rs_steady"]

    # ---- Step 1: core EPS with the after-tax net interest stripped (A5) ----
    int_ps = inp["int_q"] * 4 * (1.0 - inp["tax"]) * MILLION / inp["shares"]
    core = {t: street[t] - int_ps for t in TIERS}

    # ---- Step 2: closing items — net debt and the Arizona D-bucket charge (A5, A10) ----
    cash_ps = inp["net_cash"] * MILLION / inp["shares"]
    az_capital = inp["az_capex"] - inp["az_itc"] - inp["az_grant"]
    az_roic = inp["az_rev"] * (inp["az_gm"] - inp["opex_ratio"]) * (1.0 - inp["az_tax"]) / az_capital
    az_ps = (az_roic / r - 1.0) * az_capital * MILLION / inp["shares"]
    closing = cash_ps + az_ps

    # ---- Step 3-5: tier ROE on the FY27 opening operating book, Gordon multiple ----
    equity_op = inp["equity"] - inp["net_cash"]
    bps0 = equity_op * MILLION / inp["shares"]
    n_unbooked = inp["eps_fy26_m"] - inp["eps_h1_26"] - int_ps / 2

    def opening_bps(core_x: float, g: float) -> float:
        share = g * n_unbooked / core_x
        if share >= 1.0:
            raise ValueError(f"book roll diverges: g·N/core = {share:.2f} >= 1 (BLOCKED-by-rule)")
        return bps0 / (1.0 - share)

    def gordon_today(g: float, roe_x: float, rr: float) -> float:
        """Path Gordon at the start of FY27 folded back tau years (no window)."""
        return path_pe(g, roe_x, rr, t0, y1, y2, rs) * (1.0 + rr) ** -tau

    def window(g: float, roe_x: float, rr: float) -> float:
        """FY26H2 unbooked core EPS x (1 - b1), floored at 0, at tau/2 (A18)."""
        return max(n_unbooked * (1.0 - g / roe_x), 0.0) * (1.0 + rr) ** -(tau / 2)

    def deck(g: float, rr: float) -> tuple[dict[str, float], dict[str, float], dict[str, float], dict[str, float]]:
        bps_ = {t: opening_bps(core[t], g) for t in TIERS}
        roe_ = {t: core[t] / bps_[t] for t in TIERS}
        # today's operating multiple: path Gordon folded by tau + window per unit of core EPS
        pe_ = {t: gordon_today(g, roe_[t], rr) + window(g, roe_[t], rr) / core[t] for t in TIERS}
        val = {t: core[t] * pe_[t] + closing for t in TIERS}
        return bps_, roe_, pe_, val

    bps, roe, pes, scen = deck(g2, r)
    win = {t: window(g2, roe[t], r) for t in TIERS}
    b1 = {t: g2 / roe[t] for t in TIERS}
    ret_actual = 1.0 - inp["payout_3y"]
    excess_cash = {t: (ret_actual - b1[t]) * n_unbooked for t in TIERS}  # disclosure only

    # Branch guard: the L tier sits in the 病态区 (ROE within 3pp of r); D bucket named (A10).
    for t in TIERS:
        errors += check_branch(g2, roe[t], r, inp["payout_3y"], f"branch {t}")

    L, M, H = scen["L"], scen["M"], scen["H"]
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")
        return report(errors)

    # ---- A2e-2c flat ladder + decomposition ----
    if not (core["L"] < core["M"] < core["H"]):
        errors.append(f"numerator ladder broken: core EPS {core['L']:.3f}/{core['M']:.3f}/{core['H']:.3f}")
    flat = [core[t] * pes["M"] + closing for t in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")
    ex_close = {t: core[t] * pes[t] for t in TIERS}

    # ---- ③ guardrail (A12): M multiple vs the same-earnings band, and the reconciliation coordinates ----
    if pes["M"] < inp["band_pe_min"]:
        errors.append(f"③ 出带: PE_M {pes['M']:.2f}x below own same-earnings band floor {inp['band_pe_min']:g}x — run the ③ flow")
    e_over_r = core["M"] / r + closing
    band_hi = core["M"] * inp["band_pe_max"] + closing
    peer_lo, peer_hi = (core["M"] * pe + closing for pe in PEER_PE_SAME_RULER)
    bvps = inp["equity"] * MILLION / inp["shares_out"]
    asset_coord = inp["pb_low"] * bvps
    coords = [e_over_r, band_hi, peer_lo, peer_hi, asset_coord]
    if not min(coords) * 0.8 <= M <= max(coords) * 1.2:
        errors.append(f"对账门: M {M:.2f} outside every coordinate by >20% {coords}")

    # ---- g2 leverage: -1pp and the evidence range's low end, L/M/H only ----
    _, _, _, lo = deck(g2 - 0.01, r)
    _, _, _, ev = deck(inp["g_peer_low"], r)

    # ---- Option ceiling and zone+V (probabilities only here) ----
    d_rev = inp["mgmt_rev_2030"] - inp["rev_fy27_h"]
    core_margin = core["M"] * inp["shares"] / (inp["rev_fy27_m"] * MILLION)
    d_core = d_rev * MILLION * core_margin / inp["shares"]
    years = inp["t_opt"] - inp["t_num"]
    # A16 (2026-10-19): the option is valued in its realisation year on that year's return path --
    # the H path is calendar (Y1 2027 / Y2 2031), so by 2030 three quarters of the fall is done.
    # The increment is the same packaging business already shipping at scale, so no fresh period.
    # Was gordon_today (the FY27-start multiple), which priced 2030 earnings at 2027 returns.
    t_opt = int(inp["t_opt"])
    pe_opt = path_pe(g2, roe["H"], r, t_opt, y1, y2, rs) * (1.0 + r) ** -tau
    pe_opt_fy27 = gordon_today(g2, roe["H"], r)
    v_opt = d_core * pe_opt / (1.0 + r) ** years
    v_opt_fy27 = d_core * pe_opt_fy27 / (1.0 + r) ** years
    if pe_opt > pe_opt_fy27 + 1e-12:
        errors.append("option multiple at t_opt above the FY27-start multiple -- the fall cannot restart")
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    meta = load_framework(FRAMEWORK)
    if meta.v_opt is None or abs(meta.v_opt - v_opt) > TOL:
        errors.append(f"V_opt: stated {meta.v_opt} vs recomputed {v_opt:.4f}")
    if meta.p_tiers != P_TIERS:
        errors.append(f"p_L/p_M/p_H stated {meta.p_tiers} vs A16 {P_TIERS}")
    opt = tuple(anchor + p * v_opt for anchor, p in zip((L, M, H), P_TIERS))
    a2, b2 = cut_points(*opt)
    if meta.candidate is not None:
        errors.append("候选带 line present — the 2030 target already sizes V_opt (A16)")

    # ---- Report ----
    print(f"formula_id={FORMULA_ID}")
    print(f"r={r:g} (篮 {baskets.get('r_perp')}) g2={g2:.4f} (peer median {inp['g_peer_median']:.4f} truncated to g_cap(r) {cap:.3f}; "
          f"cluster low {inp['g_peer_low']:.4f})")
    print(f"operating equity {equity_op:.1f}M = book {inp['equity']:g} - net cash {inp['net_cash']:g}; "
          f"interest stripped {int_ps:.4f}/sh; net cash {cash_ps:+.4f}/sh; Arizona ROIC_proj {az_roic:.4f} on net "
          f"{az_capital:g}M -> {az_ps:+.4f}/sh; closing {closing:+.4f}/sh")
    for t in TIERS:
        modelled, gap = payout_gap(g2, roe[t], inp["payout_3y"])
        print(f"{t}: street {street[t]:.4f} -> core {core[t]:.4f}  BPS_op {bps[t]:.3f}  ROE {roe[t]:.4f}  "
              f"payout {modelled:.3f} (paid {inp['payout_3y']:.3f}, gap {gap:+.3f})  today PE {pes[t]:.4f}x "
              f"(path Gordon {gordon_today(g2, roe[t], r) * core[t]:.4f} + window {win[t]:.4f}) + closing = {scen[t]:.4f}")
    print(f"path (A18): forward ROE through Y1 {y1}, linear to R_s {rs:.0%} (capped at forward) by Y2 {y2}; "
          f"tau {tau:g}, window = FY26H2 unbooked x (1 - b1) at tau/2")
    print(f"ROE basis (A6): op BPS 2026-06-30 {bps0:.3f} rolled over FY26H2 unbooked {n_unbooked:.4f}/sh at b1 "
          f"{b1['L']:.2f}/{b1['M']:.2f}/{b1['H']:.2f}")
    print(f"retained beyond the model (actual retention {ret_actual:.0%} − b1) × FY26H2 unbooked → "
          f"{excess_cash['L']:+.2f}/{excess_cash['M']:+.2f}/{excess_cash['H']:+.2f} USD/sh (no k; disclosure only)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat-multiple ladder @ PE_M {pes['M']:.2f}x (+closing): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"③ same-earnings band [{inp['band_pe_min']:g}, {inp['band_pe_max']:g}]x; PE_M {pes['M']:.2f}x above the band (not 出带)")
    print(f"对账门 coordinates: E_M/r {e_over_r:.2f}; band top x core_M {band_hi:.2f}; peer same ruler "
          f"{peer_lo:.2f}–{peer_hi:.2f}; asset pb_low {inp['pb_low']:g} x BVPS {bvps:.2f} = {asset_coord:.2f}")
    print(f"L/M {L / M:.3f} (ex-closing {ex_close['L'] / ex_close['M']:.3f}) | H/M {H / M:.3f} "
          f"(ex-closing {ex_close['H'] / ex_close['M']:.3f}) | width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}")
    print(f"numerator ratio L {core['L'] / core['M']:.3f} H {core['H'] / core['M']:.3f}; "
          f"multiple ratio L {pes['L'] / pes['M']:.3f} H {pes['H'] / pes['M']:.3f}")
    print(f"g2 -1pp ({g2 - 0.01:.2f}) -> {lo['L']:.2f}/{lo['M']:.2f}/{lo['H']:.2f}; "
          f"cluster low ({inp['g_peer_low']:.4f}) -> {ev['L']:.2f}/{ev['M']:.2f}/{ev['H']:.2f}; +1pp exceeds cap")
    for rr, tag in ((0.13, "篮 6 13% (not adopted)"), (0.15, "篮 7 15% (not adopted)")):
        _, _, _, s = deck(g2, rr)
        print(f"contrast r {tag}: {s['L']:.2f}/{s['M']:.2f}/{s['H']:.2f}")
    no_az = [scen[t] - az_ps for t in TIERS]
    print(f"without the Arizona charge: {no_az[0]:.2f}/{no_az[1]:.2f}/{no_az[2]:.2f}")
    print(f"V_opt={v_opt:.2f} = (target {inp['mgmt_rev_2030']:g}M - FY27 H consensus {inp['rev_fy27_h']:g}M = {d_rev:g}M) "
          f"x core margin {core_margin:.2%} = dEPS {d_core:.4f} x PE_H(path @{t_opt}, tau) {pe_opt:.2f}x = {d_core * pe_opt:.2f} / {1 + r:g}^{years:g}"
          f"  (FY27-start multiple {pe_opt_fy27:.2f}x, pre-2026-10-19 read: {v_opt_fy27:.2f})")
    c30 = inp["mgmt_eps_2030"] - int_ps
    print(f"V_opt cross-check on the target EPS (company margin, not used): ({c30:.4f} - H {core['H']:.4f}) x PE_H / "
          f"{1 + r:g}^{years:g} = {(c30 - core['H']) * pe_opt / (1.0 + r) ** years:.2f}")
    print(f"zone+V band: {opt[0]:.2f}/{opt[1]:.2f}/{opt[2]:.2f}  A'={a2:.2f} B'={b2:.2f}")
    for tp in (65.0, 73.5, 92.0):
        target = (tp - closing) / core["M"]
        lo_g, hi_g = -0.30, r - 1e-4
        for _ in range(200):
            mid = (lo_g + hi_g) / 2
            v = gordon_today(mid, roe["M"], r) + window(mid, roe["M"], r) / core["M"]
            lo_g, hi_g = (mid, hi_g) if v < target else (lo_g, mid)
        print(f"street TP {tp:g} on this ruler (A17): implied perpetual g {(lo_g + hi_g) / 2:.4f} (same path, book held)")

    # r_f readings (_AXIS.rates): Δr_f moves r_perp 1:1; the Arizona charge is held at the basket r.
    def band_rf(dr: float) -> tuple[float, float, float]:
        s = [core[t] * (gordon_today(g2, roe[t], r + dr) + window(g2, roe[t], r + dr) / core[t]) + closing for t in TIERS]
        return s[0], s[1], s[2]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    if not errors:
        write_rf_readings("AMKR.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
