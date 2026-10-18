#!/usr/bin/env python3
"""0981.HK (中芯国际 / SMIC) valuation eval — recompute anchors from
frameworks/0981.HK.md.

frameworks/0981.HK.md is the source of truth; this script re-derives L/M/H,
A/B, the advanced-node option and the +V band from the §3 Inputs table and
exits 1 on mismatch.  The doc carries no current price (AGENTS.md「现价 —
禁写契约」), so nothing here reads a quote.

formula_id: smic_fy27_gordon_g0_adv_node_mature_reroe_opt_v2

Whole-company ruler: the filings have one operating segment and no node
breakdown since 2021, so the mature / advanced split is a cross only
(valuation-rules「分腿 ROE 来源优先序」③).  Numerator FY2027 = furthest year
with a >=2-house consensus range (yfinance +1y, 18 houses); FY2027 = FY+1, no
discount.  L = the FY2024 trough ROE (A-share weighted 2.5%) on the FY2027
opening book (cyclical L exception).

Every tier sits at ROE <= r + 3pp (L / M below r, H 0.6pp above), so growth
creates no value and g2 = 0 is named (same rule as `_AXIS.leading-edge-
foundry` ②).  Retention audit = D bucket: the 2027–2030 capex window is
priced in the advanced-node leg, which charges the unspent capital in full;
hence no discount k (A25: a k on the 多留部分 is the wrong object and was
removed) and check_branch's full-payout red light is downgraded to the
payout_gap disclosure (valuation-rules「分支差的合法解释」).

Advanced-node leg (A12–A15): 2030 capacity x wafer price x the peer-ruler
margins of `_AXIS.leading-edge-foundry`; the scarcity margin fades along the
high-return path (A25, user 2026-10-18: the M 5 / H 10 years are years at the
full shortage margin from 2030, the 6-year fade comes after, and neither Y1 nor
Y2 may precede TSMC's 2030 / 2035 axis floor -> M 2034 / 2040, H 2039 / 2045)
and the new-investment return falls to
min(normal ROIC, axis 16.9%); valued at t_align and discounted to FY2027, less the
unspent capital and less the FY2027 advanced profit already in the base.
A negative tier value is the window capex destroying value and goes into the
base anchor (as INTC.US carries pre-breakeven losses); a positive one is the
option.

Mature re-ROE component (A22–A24): from 2031 the FY2027 opening book less the
built advanced capacity (already valued in the leg) earns the UMC-measured
steady ROE instead of the tier's FY2027 ROE; H adds a shortage rent at
UMC's 2021–22 ROE for the user's 5 years 2031–2035, then a 4-year fade
(barrier 中; A25: Y1 = 2035, Y2 = 2039).  Base and option are then backed tau years to the
balance-sheet date and the 2026H2 funding gap comes off every base tier (A25).  Steady ROE sits within r ± 3pp, so its multiple is 1/r.
It is option-only and never nets against a negative leg in the base.
V_k = max(V_leg,k, 0) + V_mat,k; V_opt = V_H; p_k = V_k / V_H.

Run:  python3 frameworks/eval/0981.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    annuity_factor,
    check_branch,
    check_g_cap,
    check_r,
    payout_gap,
    perpetual_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    parse_baskets,
    parse_inputs,
    report,
)
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "0981.HK.md"
AXIS_LEF = REPO_ROOT / "frameworks" / "axes" / "leading-edge-foundry.md"
FORMULA_ID = "smic_fy27_gordon_g0_adv_node_mature_reroe_opt_v2"
LISTING_CCY = "HKD"
TOL = 0.05
NUM_YEAR = 2027
MATURE_FIRST = 2031  # mature re-ROE / shortage block starts after the 2027–2030 window (A22)
TIERS = ("L", "M", "H")

REQUIRED = [
    "r_perp", "g2", "shares", "eq_h1_cny", "ni_h1_cny", "fx_usdhkd", "fx_hkdcny",
    "ni_fy26_usd", "roe_trough", "eps_fy27_lo", "eps_fy27_m", "eps_fy27_h", "rev_fy27_m",
    "payout_obs", "window_years",
    "adv_rev_25", "adv_cagr", "cap_built_k", "cap_full_k", "asp_wafer", "util",
    "opm_weak_peer", "opm_strong_peer", "yield_discount", "g2_foundry_src", "g2_foundry_h_src",
    "t_align", "n_rent_m", "n_rent_h", "tax_opt", "kpk_l", "kpk_m", "kpk_h", "capex_years",
    "roe_ss_m", "roe_ss_h", "roe_short", "n_short",
    "tau", "gap_h2_usd", "parent_ratio", "ss_return_foundry", "fall_years_foundry", "fall_years_mature",
    "y1_floor_foundry", "y2_floor_foundry",
]
AXIS_ROWS = ("opm_weak_peer", "opm_strong_peer", "yield_discount",
             "g2_foundry_src", "g2_foundry_h_src", "t_align", "ss_return_foundry", "fall_years_foundry",
             "y1_floor_foundry", "y2_floor_foundry")


def path_counts(first: int, n_full: int, fade: int, y1_floor: int | None = None,
                y2_floor: int | None = None) -> tuple[int, int, int, int]:
    """High-return path (A25, user 2026-10-18): the user's shortage years n_full are years at
    the full shortage value from `first` (the fade comes after, not inside); Y1 = first +
    n_full - 1, Y2 = Y1 + fade, each lifted to the axis floor when given (TSMC's 2030 / 2035
    for the advanced-node leg).  Returns (years at full incl. Y1, fade years, Y1, Y2)."""
    y1 = first + n_full - 1
    if y1_floor is not None:
        y1 = max(y1, y1_floor)
    y2 = y1 + fade
    if y2_floor is not None:
        y2 = max(y2, y2_floor)
    return y1 - first + 1, y2 - y1, y1, y2


def fade_weights(n_short: int, n_dec: int):
    """Weight of the shortage premium in year k (k = 1 is the first year): 1 through Y1,
    linear to 0 at Y2, 0 after."""
    def w(k: int) -> float:
        if k <= n_short:
            return 1.0
        if k < n_short + n_dec:
            return 1.0 - (k - n_short) / n_dec
        return 0.0
    return w


def first_float(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def axis_check(inp: dict[str, float]) -> list[str]:
    """Peer-ruler rows (contracts.md「同业尺轴」): the axis file is the single source."""
    if not AXIS_LEF.is_file():
        return [f"{AXIS_LEF.name} missing — _AXIS.leading-edge-foundry unchecked"]
    ax = parse_inputs(AXIS_LEF.read_text(encoding="utf-8"))
    return [f"{k} {inp[k]:g} != _AXIS.leading-edge-foundry {ax.get(k)} — the ruler drifted"
            for k in AXIS_ROWS if k not in ax or abs(ax[k] - inp[k]) > 1e-9]


def sanity(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    e: list[str] = []
    if "r_perp" not in baskets:
        e.append("r_perp: Inputs source cell names no 篮 N")
    e += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    e += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    e += check_g_cap(inp["g2_foundry_src"], inp["r_perp"], "g2_foundry_src")
    e += check_g_cap(inp["g2_foundry_h_src"], inp["r_perp"], "g2_foundry_h_src")
    if not inp["eps_fy27_lo"] < inp["eps_fy27_m"] < inp["eps_fy27_h"]:
        e.append("FY27 consensus range must be ordered low < mean < high")
    if not inp["kpk_h"] < inp["kpk_m"] < inp["kpk_l"]:
        e.append("capital per 1k wpm must fall from L to H (same range, two ends + middle)")
    leaked_k = sorted(k for k in inp if k in ("k_l", "k_m", "k_h"))
    if leaked_k:  # A25: the k = 0 on the D-bucket retention sat on the 多留部分 -> removed
        e.append(f"discount k rows must not reappear (A25): {leaked_k}")
    if inp["t_align"] <= NUM_YEAR:
        e.append("option alignment year must lie after the numerator year")
    if not inp["roe_ss_m"] < inp["roe_ss_h"] < inp["roe_short"]:
        e.append("mature ROE ladder must be steady M < steady H < shortage")
    if inp["roe_ss_m"] <= inp["r_perp"]:
        e.append("roe_ss_m must exceed r — a steady ROE at or below r adds no value over the 1/r base")
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
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    baskets = parse_baskets(md)
    errors = sanity(inp, baskets) + axis_check(inp)

    r, g2, sh = inp["r_perp"], inp["g2"], inp["shares"] * 1e6
    hkd = inp["fx_usdhkd"]
    usdcny = hkd * inp["fx_hkdcny"]

    # ---- FY2027 opening book (USD/share): H1'26 book + unbooked 2H26 consensus, b = 1 ----
    bps0 = inp["eq_h1_cny"] * 1e6 / usdcny / sh
    ni_h2 = inp["ni_fy26_usd"] * 1e6 - inp["ni_h1_cny"] * 1e6 / usdcny
    bps27 = bps0 + ni_h2 / sh

    eps = {"L": inp["roe_trough"] * bps27, "M": inp["eps_fy27_m"], "H": inp["eps_fy27_h"]}

    def base_band(g: float = g2, rr: float = r) -> tuple[dict, dict]:
        pre, info = {}, {}
        for t in TIERS:
            roe = eps[t] / bps27
            pe = perpetual_pe(g, roe, rr) if roe > g else float("nan")
            pre[t] = eps[t] * pe * hkd
            info[t] = (roe, pe)
        return pre, info

    pre, info = base_band()

    # ---- Advanced-node leg per tier (A12–A15), HKD/share ----
    m_l = inp["opm_weak_peer"]
    m_h = inp["opm_strong_peer"] - inp["yield_discount"]
    m_m = (m_l + m_h) / 2
    leg = {  # capacity k wpm, normal margin, rent margin, rent years, leg g2, capital per 1k wpm ($B)
        "L": (inp["cap_built_k"], m_l, m_l, 0, inp["g2_foundry_src"], inp["kpk_l"]),
        "M": (inp["cap_full_k"], m_m, m_h, int(inp["n_rent_m"]), inp["g2_foundry_src"], inp["kpk_m"]),
        "H": (inp["cap_full_k"], m_h, inp["opm_strong_peer"], int(inp["n_rent_h"]),
              inp["g2_foundry_h_src"], inp["kpk_h"]),
    }
    adv27 = inp["adv_rev_25"] * 1e6 * (1 + inp["adv_cagr"]) ** 2
    yrs_disc = inp["t_align"] - NUM_YEAR
    n_cap = int(inp["capex_years"])

    def leg_value(t: str, asp: float | None = None, kpk: float | None = None,
                  rr: float | None = None) -> tuple[float, dict]:
        """Leg value at FY2027 (HKD/share).  The scarcity margin no longer steps down
        (A14 / A25, valuation-rules「未建模期权」+「经营价值与超额现金」② 稳态回报三段): the user's
        5 / 10 years are full-shortage years from 2030, the axis fade comes after, and Y1 / Y2 are
        lifted to the axis floor (TSMC 2030 / 2035; user 2026-10-18);
        margin and new-investment return stay at the shortage values to Y1, fade linearly to Y2,
        then normal margin and the steady return min(normal ROIC, axis 16.9%)."""
        rr = r if rr is None else rr
        cap, mn, mr, n, gl, kk = leg[t]
        asp = inp["asp_wafer"] if asp is None else asp
        kk = kk if kpk is None else kpk
        rev = cap * 1e3 * 12 * asp * inp["util"]
        capital = cap * kk * 1e9
        tax = inp["tax_opt"]
        nopat = rev * mn * (1 - tax)
        roic = nopat / capital
        gg = gl if roic > rr else 0.0          # ROIC <= r: growth creates no value -> 1/r
        pe_leg = perpetual_pe(gl, roic, rr) if roic > rr else 1 / rr
        if n:
            n_short, n_dec, _, _ = path_counts(int(inp["t_align"]), n, int(inp["fall_years_foundry"]),
                                               int(inp["y1_floor_foundry"]), int(inp["y2_floor_foundry"]))
            ron_short = rev * mr * (1 - tax) / capital
            ron_ss = min(roic, inp["ss_return_foundry"])
            w = fade_weights(n_short, n_dec)
            pv, e, k_ = 0.0, 1.0, 1
            while True:
                wt = w(k_)
                e_t = rev * (1 + gg) ** (k_ - 1) * (mn + (mr - mn) * wt) * (1 - tax)
                ron = ron_ss + (ron_short - ron_ss) * wt
                pay = (1 - gg / ron) if gg > 0 else 1.0
                if wt == 0.0:
                    pv += e_t * pay / ((rr - gg) * (1 + rr) ** (k_ - 1))
                    break
                pv += e_t * pay / (1 + rr) ** k_
                k_ += 1
            stream = pv
        else:
            stream = nopat * pe_leg
        rent = stream - nopat * pe_leg      # value of the shortage path over the normal perpetuity
        unspent = (cap - inp["cap_built_k"]) * kk * 1e9
        pv_unspent = sum(unspent / n_cap / (1 + rr) ** (i + 0.5) for i in range(n_cap))
        npm = eps[t] * sh / (inp["rev_fy27_m"] * 1e6)
        pe_base = perpetual_pe(g2, eps[t] / bps27, rr) if eps[t] / bps27 > g2 else float("nan")
        overlap = adv27 * npm * pe_base
        v = stream / (1 + rr) ** yrs_disc - pv_unspent - overlap
        return v / sh * hkd, dict(rev=rev, roic=roic, pe=pe_leg, nopat=nopat, rent=rent,
                                   pv_unspent=pv_unspent, overlap=overlap, npm=npm, mn=mn, mr=mr, n=n, gl=gl)

    vraw, legs = {}, {}
    for t in TIERS:
        vraw[t], legs[t] = leg_value(t)

    # ---- Mature re-ROE component (A22–A24), HKD/share; option only ----
    roe_ss = {"L": None, "M": inp["roe_ss_m"], "H": inp["roe_ss_h"]}

    def mature_value(t: str, n_short: int | None = None) -> tuple[float, dict]:
        n_short = int(inp["n_short"]) if n_short is None else n_short
        book = bps27 - inp["cap_built_k"] * leg[t][5] * 1e9 / sh
        if roe_ss[t] is None:
            return 0.0, dict(book=book, up=0.0, rent=0.0)
        pe_ss = perpetual_pe(g2, roe_ss[t], r)
        up = max(roe_ss[t] - info[t][0], 0.0) * book * pe_ss
        # shortage premium fades along the high-return path (A25): user's n_short years at full
        # from 2031, then mature node barrier 中 -> fall_years_mature years of fade (no TSMC floor:
        # that floor belongs to the advanced-node axis)
        ns, nd, _, _ = path_counts(MATURE_FIRST, n_short, int(inp["fall_years_mature"]))
        w = fade_weights(ns, nd)
        rent = ((inp["roe_short"] - roe_ss[t]) * book * sum(w(k) / (1 + r) ** k for k in range(1, ns + nd + 1))
                if t == "H" else 0.0)
        d = (1 + r) ** yrs_disc
        return (up + rent) / d * hkd, dict(book=book, up=up / d * hkd, rent=rent / d * hkd, pe=pe_ss)

    vmat, mats = {}, {}
    for t in TIERS:
        vmat[t], mats[t] = mature_value(t)
    carry = {t: min(vraw[t], 0.0) for t in TIERS}
    # Timing (A25, valuation-rules「经营价值与超额现金」③): everything above sits at the numerator
    # year's opening 2027-01-01 -> back tau years to the balance-sheet date; the window's
    # distributable profit is 0 (roll b1 = 1, nothing paid).  Funding gap 2026H2 (capex beyond
    # OCF, capacity online inside FY2027) is a debt-like item x parent ratio (no cash line).
    tdisc = (1 + r) ** inp["tau"]
    gap_ps = inp["gap_h2_usd"] * 1e9 / sh * hkd * inp["parent_ratio"]
    pos = {t: (max(vraw[t], 0.0) + vmat[t]) / tdisc for t in TIERS}
    base = {t: (pre[t] + carry[t]) / tdisc - gap_ps for t in TIERS}
    L, M, H = base["L"], base["M"], base["H"]
    A, B = (L + M) / 2, (M + H) / 2
    v_opt = pos["H"]
    p = {t: (pos[t] / v_opt if v_opt > 0 else 0.0) for t in TIERS}
    plus_v = tuple(base[t] + p[t] * v_opt for t in TIERS)

    if not L < M < H:
        errors.append(f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}")
    if not pre["L"] < pre["M"] < pre["H"]:
        errors.append("flat ladder (A2e-2c): pre-carry anchors not ordered at the shared 1/r multiple")
    if not plus_v[0] < plus_v[1] < plus_v[2]:
        errors.append("+V band not ordered")
    if vraw["H"] <= 0:
        errors.append("H-tier advanced leg is not positive — no option to state")

    # D bucket (A9): the full-payout branch's red light is priced by the window, so disclose it.
    branch_notes = []
    for t in TIERS:
        for msg in check_branch(g2, info[t][0], r, inp["payout_obs"], f"g2@{t}"):
            mod, gap = payout_gap(g2, info[t][0], inp["payout_obs"])
            branch_notes.append(f"{t}: model payout {mod:.0%} vs paid {inp['payout_obs']:.0%} "
                                f"(gap {gap:+.0%}; D 桶 window to {inp['t_align']:.0f}, no k, A9 / A25)")

    # ---- Reconcile stated Outputs ----
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    out_sec = md.split("### Outputs", 1)[-1]
    said_v = first_float(r"V_\{opt\}\\\) = \*\*([0-9.]+)\*\*", out_sec)
    if said_v is None or abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    p_line = re.search(r"p_L/p_M/p_H\\\) = \*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*", out_sec)
    if p_line is None:
        errors.append("Outputs p_L/p_M/p_H line not found")
    else:
        for t, said in zip(TIERS, (float(x) for x in p_line.groups())):
            if abs(said - p[t]) > 0.0015:
                errors.append(f"p_{t}: stated {said} vs recomputed {p[t]:.4f}")

    # ---- Report ----
    print(f"formula_id={FORMULA_ID}")
    print(f"r {r:g} (篮 {baskets.get('r_perp')}); g2 {g2:.2%} (named: ROE <= r + 3pp, growth creates no value); "
          f"FX USD/HKD {hkd} x HKD/CNY {inp['fx_hkdcny']} = USD/CNY {usdcny:.4f}")
    print(f"BPS: H1'26 {bps0:.4f} USD + 2H26 unbooked {ni_h2 / 1e6:.0f}M / sh = FY27 opening {bps27:.4f} USD "
          f"({bps27 * hkd:.2f} HKD)")
    for t in TIERS:
        roe, pe = info[t]
        print(f"{t}: EPS {eps[t]:.4f} USD ROE {roe:.2%} PE {pe:.2f} -> {pre[t]:.2f} HKD; "
              f"PB {pre[t] / (bps27 * hkd):.2f}; leg {vraw[t]:+.2f} -> carry {carry[t]:+.2f} / option {pos[t]:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"V_opt {v_opt:.2f}  p {p['L']:.4f}/{p['M']:.4f}/{p['H']:.4f}  +V {plus_v[0]:.2f}/{plus_v[1]:.2f}/{plus_v[2]:.2f}"
          f"  A' {(plus_v[0] + plus_v[1]) / 2:.2f} B' {(plus_v[1] + plus_v[2]) / 2:.2f}")
    for t in TIERS:
        d = legs[t]
        print(f"  leg {t}: cap {leg[t][0]:.0f}k x 12 x ${inp['asp_wafer']:.0f} x {inp['util']} = rev ${d['rev'] / 1e9:.2f}B; "
              f"margin {d['mn']:.1%} -> NOPAT ${d['nopat'] / 1e9:.2f}B; ROIC {d['roic']:.1%}; "
              f"PE {d['pe']:.2f} (g {d['gl']:.2%}); premium ({d['mr']:.1%}-{d['mn']:.1%}, {d['n']}y full + fade) =${d['rent'] / 1e9:.2f}B; "
              f"/1.1^{yrs_disc:.0f} - unspent PV ${d['pv_unspent'] / 1e9:.2f}B - overlap ${d['overlap'] / 1e9:.2f}B "
              f"(adv FY27 ${adv27 / 1e9:.2f}B x npm {d['npm']:.1%} x {info[t][1]:.0f}x) = {vraw[t]:+.2f} HKD")
    for t in TIERS:
        d = mats[t]
        ss = f"{roe_ss[t]:.2%}" if roe_ss[t] is not None else "no recovery"
        print(f"  mature {t}: book {d['book']:.4f} USD (BPS less built adv {inp['cap_built_k']:.0f}k x {leg[t][5]}); "
              f"ROE {info[t][0]:.2%} -> {ss}; steady +{d['up']:.2f} + shortage rent {d['rent']:.2f} "
              f"({inp['roe_short']:.2%}, {inp['n_short']:.0f}y full + fade, H only) /1.1^{yrs_disc:.0f} = {vmat[t]:.2f} HKD")
    print(f"flat ladder @ 1/r: {pre['L']:.2f}/{pre['M']:.2f}/{pre['H']:.2f} (numerator ratio L/M {eps['L'] / eps['M']:.3f},"
          f" H/M {eps['H'] / eps['M']:.3f})")
    print(f"L/M {L / M:.3f} | H/M {H / M:.3f} | width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}")
    for msg in branch_notes:
        print("  payout_gap (disclosure, not error): " + msg)
    print("视同派出、实际留存 (D 桶 window {:.0f}y; no discount k, A25): ".format(inp["window_years"])
          + " ".join(f"{t} {eps[t] * inp['window_years'] * hkd:.2f}" for t in TIERS))
    print(f"FY27 consensus low {inp['eps_fy27_lo']} -> {inp['eps_fy27_lo'] * 10 * hkd:.2f} HKD at 1/r (cross for L)")

    # ---- Sensitivities (anchors only) ----
    for g in (g2 - 0.01, g2 + 0.01):
        pre_g, _ = base_band(g)
        print(f"  sens g2={g:+.2%}: base pre-carry {pre_g['L']:.2f}/{pre_g['M']:.2f}/{pre_g['H']:.2f} "
              f"(carry unchanged -> M {(pre_g['M'] + carry['M']) / tdisc - gap_ps:.2f} after tau and gap)")
    for asp in (10000.0, 13000.0):
        vs = {t: leg_value(t, asp=asp)[0] for t in TIERS}
        b_ = {t: (pre[t] + min(vs[t], 0)) / tdisc - gap_ps for t in TIERS}
        vh = (max(vs["H"], 0) + vmat["H"]) / tdisc
        pv_ = tuple(b_[t] + (max(vs[t], 0) + vmat[t]) / tdisc for t in TIERS)
        print(f"  sens wafer ${asp:.0f}: base {b_['L']:.2f}/{b_['M']:.2f}/{b_['H']:.2f}  V_opt {vh:.2f}  "
              f"+V {pv_[0]:.2f}/{pv_[1]:.2f}/{pv_[2]:.2f}")
    for kk in (inp["kpk_h"], inp["kpk_l"]):
        vs = {t: leg_value(t, kpk=kk)[0] for t in ("M", "H")}
        print(f"  sens capital ${kk:.3f}B per 1k wpm on all tiers: leg M {vs['M']:+.2f} H {vs['H']:+.2f}")
    vm3 = mature_value("H", n_short=3)[0]
    print(f"  sens mature shortage 3y (+ fade): mature H {vm3 / tdisc:.2f}  V_opt {pos['H'] + (vm3 - vmat['H']) / tdisc:.2f}  "
          f"+V H {H + pos['H'] + (vm3 - vmat['H']) / tdisc:.2f}")
    print(f"timing (A25): tau {inp['tau']:g}y ÷{tdisc:.4f} on base and option; window distributable 0 (b1 = 1); "
          f"funding gap 2026H2 ${inp['gap_h2_usd']:g}B x parent {inp['parent_ratio']:.4f} = {gap_ps:.3f} HKD/share off every tier")
    fl = (int(inp["y1_floor_foundry"]), int(inp["y2_floor_foundry"]))
    paths = {t: path_counts(int(inp["t_align"]), int(inp[f"n_rent_{t.lower()}"]), int(inp["fall_years_foundry"]), *fl)
             for t in ("M", "H")}
    mp = path_counts(MATURE_FIRST, int(inp["n_short"]), int(inp["fall_years_mature"]))
    print(f"high-return path (A25; full years first, fade after; axis floor Y1 >= {fl[0]}, Y2 >= {fl[1]}): "
          + "; ".join(f"leg {t} Y1 {p[2]} / Y2 {p[3]}" for t, p in paths.items())
          + f"; mature H Y1 {mp[2]} / Y2 {mp[3]}; leg H steady return min(normal ROIC, {inp['ss_return_foundry']:.1%})")

    # ---- r_f readings (_AXIS.rates HKD -> USD segment); the leg moves with r too ----
    def band_rf(dr: float) -> tuple[float, float, float]:
        rr = r + dr
        pre_r, _ = base_band(g2, rr)
        out = [(pre_r[t] + min(leg_value(t, rr=rr)[0], 0.0)) / (1 + rr) ** inp["tau"] - gap_ps for t in TIERS]
        return out[0], out[1], out[2]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    if not errors:
        write_rf_readings("0981.HK", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
