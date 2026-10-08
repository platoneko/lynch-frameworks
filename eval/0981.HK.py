#!/usr/bin/env python3
"""0981.HK (中芯国际 / SMIC) valuation eval — recompute anchors from
frameworks/0981.HK.md.

frameworks/0981.HK.md is the source of truth; this script re-derives L/M/H,
A/B, the advanced-node option and the +V band from the §3 Inputs table and
exits 1 on mismatch.  The doc carries no current price (AGENTS.md「现价 —
禁写契约」), so nothing here reads a quote.

formula_id: smic_fy27_gordon_g0_adv_node_opt_v1

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
hence k = 0 and check_branch's full-payout red light is downgraded to the
payout_gap disclosure (valuation-rules「分支差的合法解释」).

Advanced-node leg (A12–A15): 2030 capacity x wafer price x the peer-ruler
margins of `_AXIS.leading-edge-foundry`, scarcity rent as a finite annuity,
valued on the leg's own ROIC at t_align and discounted to FY2027, less the
unspent capital and less the FY2027 advanced profit already in the base.
A negative tier value is the window capex destroying value and goes into the
base anchor (as INTC.US carries pre-breakeven losses); a positive one is the
option, p_k = V_k / V_H.

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
FORMULA_ID = "smic_fy27_gordon_g0_adv_node_opt_v1"
LISTING_CCY = "HKD"
TOL = 0.05
NUM_YEAR = 2027
TIERS = ("L", "M", "H")

REQUIRED = [
    "r_perp", "g2", "shares", "eq_h1_cny", "ni_h1_cny", "fx_usdhkd", "fx_hkdcny",
    "ni_fy26_usd", "roe_trough", "eps_fy27_lo", "eps_fy27_m", "eps_fy27_h", "rev_fy27_m",
    "payout_obs", "k_l", "k_m", "k_h", "window_years",
    "adv_rev_25", "adv_cagr", "cap_built_k", "cap_full_k", "asp_wafer", "util",
    "opm_weak_peer", "opm_strong_peer", "yield_discount", "g2_foundry_src", "g2_foundry_h_src",
    "t_align", "n_rent_m", "n_rent_h", "tax_opt", "kpk_l", "kpk_m", "kpk_h", "capex_years",
]
AXIS_ROWS = ("opm_weak_peer", "opm_strong_peer", "yield_discount",
             "g2_foundry_src", "g2_foundry_h_src", "t_align")


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
    if not 0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] < 1:
        e.append("k must satisfy 0 <= k_L <= k_M <= k_H < 1 (cyclical)")
    if inp["t_align"] <= NUM_YEAR:
        e.append("option alignment year must lie after the numerator year")
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

    def leg_value(t: str, asp: float | None = None, kpk: float | None = None) -> tuple[float, dict]:
        cap, mn, mr, n, gl, kk = leg[t]
        asp = inp["asp_wafer"] if asp is None else asp
        kk = kk if kpk is None else kpk
        rev = cap * 1e3 * 12 * asp * inp["util"]
        capital = cap * kk * 1e9
        nopat = rev * mn * (1 - inp["tax_opt"])
        roic = nopat / capital
        pe_leg = perpetual_pe(gl, roic, r) if roic > r else 1 / r
        rent = rev * (mr - mn) * (1 - inp["tax_opt"]) * annuity_factor(0.0, r, n) if n else 0.0
        unspent = (cap - inp["cap_built_k"]) * kk * 1e9
        pv_unspent = sum(unspent / n_cap / (1 + r) ** (i + 0.5) for i in range(n_cap))
        npm = eps[t] * sh / (inp["rev_fy27_m"] * 1e6)
        overlap = adv27 * npm * info[t][1]
        v = (nopat * pe_leg + rent) / (1 + r) ** yrs_disc - pv_unspent - overlap
        return v / sh * hkd, dict(rev=rev, roic=roic, pe=pe_leg, nopat=nopat, rent=rent,
                                   pv_unspent=pv_unspent, overlap=overlap, npm=npm, mn=mn, mr=mr, n=n, gl=gl)

    vraw, legs = {}, {}
    for t in TIERS:
        vraw[t], legs[t] = leg_value(t)
    carry = {t: min(vraw[t], 0.0) for t in TIERS}
    pos = {t: max(vraw[t], 0.0) for t in TIERS}
    base = {t: pre[t] + carry[t] for t in TIERS}
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
                                f"(gap {gap:+.0%}; D 桶 window to {inp['t_align']:.0f}, k = 0, A9)")

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
              f"PE {d['pe']:.2f} (g {d['gl']:.2%}); rent ({d['mr']:.1%}-{d['mn']:.1%}) x {d['n']}y = ${d['rent'] / 1e9:.2f}B; "
              f"/1.1^{yrs_disc:.0f} - unspent PV ${d['pv_unspent'] / 1e9:.2f}B - overlap ${d['overlap'] / 1e9:.2f}B "
              f"(adv FY27 ${adv27 / 1e9:.2f}B x npm {d['npm']:.1%} x {info[t][1]:.0f}x) = {vraw[t]:+.2f} HKD")
    print(f"flat ladder @ 1/r: {pre['L']:.2f}/{pre['M']:.2f}/{pre['H']:.2f} (numerator ratio L/M {eps['L'] / eps['M']:.3f},"
          f" H/M {eps['H'] / eps['M']:.3f})")
    print(f"L/M {L / M:.3f} | H/M {H / M:.3f} | width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}")
    for msg in branch_notes:
        print("  payout_gap (disclosure, not error): " + msg)
    print("视同派出、实际留存 (D 桶 window {:.0f}y; k 前 / k 后 equal, k = 0): ".format(inp["window_years"])
          + " ".join(f"{t} {eps[t] * inp['window_years'] * hkd:.2f}" for t in TIERS))
    print(f"FY27 consensus low {inp['eps_fy27_lo']} -> {inp['eps_fy27_lo'] * 10 * hkd:.2f} HKD at 1/r (cross for L)")

    # ---- Sensitivities (anchors only) ----
    for g in (g2 - 0.01, g2 + 0.01):
        pre_g, _ = base_band(g)
        print(f"  sens g2={g:+.2%}: base pre-carry {pre_g['L']:.2f}/{pre_g['M']:.2f}/{pre_g['H']:.2f} "
              f"(carry unchanged -> M {pre_g['M'] + carry['M']:.2f})")
    for asp in (10000.0, 13000.0):
        vs = {t: leg_value(t, asp=asp)[0] for t in TIERS}
        b_ = {t: pre[t] + min(vs[t], 0) for t in TIERS}
        vh = max(vs["H"], 0)
        pv_ = tuple(b_[t] + (max(vs[t], 0) / vh if vh else 0) * vh for t in TIERS)
        print(f"  sens wafer ${asp:.0f}: base {b_['L']:.2f}/{b_['M']:.2f}/{b_['H']:.2f}  V_opt {vh:.2f}  "
              f"+V {pv_[0]:.2f}/{pv_[1]:.2f}/{pv_[2]:.2f}")
    for kk in (inp["kpk_h"], inp["kpk_l"]):
        vs = {t: leg_value(t, kpk=kk)[0] for t in ("M", "H")}
        print(f"  sens capital ${kk:.3f}B per 1k wpm on all tiers: leg M {vs['M']:+.2f} H {vs['H']:+.2f}")

    # ---- r_f readings (_AXIS.rates HKD -> USD segment); the leg moves with r too ----
    def band_rf(dr: float) -> tuple[float, float, float]:
        rr = r + dr
        pre_r, info_r = base_band(g2, rr)
        out = []
        for t in TIERS:
            cap, mn, mr, n, gl, kk = leg[t]
            rev = cap * 1e3 * 12 * inp["asp_wafer"] * inp["util"]
            capital = cap * kk * 1e9
            nopat = rev * mn * (1 - inp["tax_opt"])
            roic = nopat / capital
            pe_leg = perpetual_pe(gl, roic, rr) if roic > rr else 1 / rr
            rent = rev * (mr - mn) * (1 - inp["tax_opt"]) * annuity_factor(0.0, rr, n) if n else 0.0
            unspent = (cap - inp["cap_built_k"]) * kk * 1e9
            pv_u = sum(unspent / n_cap / (1 + rr) ** (i + 0.5) for i in range(n_cap))
            npm = eps[t] * sh / (inp["rev_fy27_m"] * 1e6)
            v = ((nopat * pe_leg + rent) / (1 + rr) ** yrs_disc - pv_u - adv27 * npm * info_r[t][1]) / sh * hkd
            out.append(pre_r[t] + min(v, 0.0))
        return out[0], out[1], out[2]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    if not errors:
        write_rf_readings("0981.HK", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
