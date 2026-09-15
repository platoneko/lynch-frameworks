#!/usr/bin/env python3
"""0883.HK (CNOOC) valuation eval.

frameworks/0883.HK.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: cnooc_hk_brent_axis_ddm_v1

Main ruler: dividend discount (valuation-rules「DDM 主尺例外」, this ticker is
the worked example).  The numerator is still the shared Brent axis
(_AXIS.brent-oil.md, 68 / 75 / 85) pushed through the company's OWN measured
per-barrel earnings elasticity,

    NI/bbl_FY25 = NI_FY25 / liquids sold FY25                      = 207.2 RMB/bbl
    k           = (NI/bbl 2026H1 - NI/bbl FY25) / (realised 2026H1 - realised FY25)
                                                                    = 3.968 RMB/bbl per US$1
    NI_x        = liquids_2027 x [NI/bbl_FY25 + k (rho Brent_x - realised FY25)]

and the axis M rung IS the mid-cycle numerator (2027 house median = the
2020-2025 realised Brent mean, not the current 87.6 print): the framework has
to show TTM EPS / EPS_M <= 1.15 and a production-normalised full-cycle EPS
mean within 20% of EPS_M (valuation-rules「周期票的中枢分子」).

Why not Gordon: every tier ROE (14.4 / 16.3 / 19.0%) sits 3pp+ above r, the
monotonic regime, where the retention-branch multiple is >= 10x for any
g in [0, 6%] -- and the realised 5y monthly TTM band tops out at 9.89x.  Rule
③ says BLOCKED, not "twist r".  With a written payout floor (45% for
2025-2027, annual report), the DDM exception applies:

    P_x = 0.45 x EPS_x / (r - g_d),   r = 10%,   one g_d for all tiers

g_d comes from the same-ruler, same-day peer reverse-solve
g_d = r - payout / fPE(FY2027E), monotonic-regime peers only, samples above
G_CAP or on the wrong branch dropped (never clipped into the median).  The
DDM-implied PE 0.45/(r - g_d) MUST fall inside the realised band -- that is
this ruler's guardrail -- and the zone must not move across the g_d evidence
interval.  The retention-branch Gordon band, the 10x zero-growth band and the
FCF-yield ruler are printed as cross-checks, together with the rule's
mandatory disclosure: market-implied marginal ROE (g_d / retention) against
book ROE_M.

Run:  python3 eval/0883.HK.py
"""

from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import AXIS_BRENT  # noqa: E402
from lib.gordon import (  # noqa: E402
    G_CAP, check_branch, check_g_cap, check_r, implied_g_retaining, payout_gap,
    perpetual_pe, recovery_two_stage_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points, zone_of  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
FRAMEWORK = REPO / "frameworks" / "0883.HK.md"
FORMULA_ID = "cnooc_hk_brent_axis_ddm_v1"
TICKER = "0883.HK"

TIERS = ("l", "m", "h")
MN = 1e6                    # Inputs money fields are RMB million
G_TOL = 5e-5
PE_EDGE_TOL = 0.01          # evidence-interval ends may sit exactly on the band edge
MIN_R_MINUS_G = 0.02
CONS_DEV_MAX = 0.20         # ②-b: M within 20% of the consensus mean
MID_CYCLE_MAX = 1.15        # 中枢: current / mid-cycle above this makes the current print an upper-side coordinate
CYCLE_MEAN_DEV_MAX = 0.20   # 中枢: axis-bridged M vs own full-cycle (production-normalised) EPS mean
MONOTONIC_GAP = 0.03        # ROE - r >= this is the monotonic regime (gordon._ROE_NEAR_R)
CYCLE_YEARS = ("2020", "2021", "2022", "2023", "2024")
PAYOUT_FLOOR_QUOTE = "不低于 45%"

REQUIRED = [
    "price", "price_a", "shares", "equity", "fx_hkdcny",
    "ni_fy25", "eps_fy25", "ni_h1_25", "ni_h1_26",
    "liq_fy25", "real_fy25", "liq_h1_26", "real_h1_26",
    "prod_2026_mid", "liq_share", "sales_ratio",
    "brent_2025", "brent_l", "brent_m", "brent_h",
    "payout_policy", "dps_fy25_cny", "dps_fy25_hkd", "dps_fy19_hkd", "dps_fy25_final_hkd", "dps_h1_26_hkd",
    "r_perp", "g2_d", "g_evid_min", "g_evid_max", "gd_peer_cvx", "gd_peer_tte", "gd_peer_1088",
    "pe_own_min", "pe_own_max", "pe_own_med",
    "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi", "tp_cons_h",
    "fcf_fy25",
    *[f"eps_fy{y}" for y in CYCLE_YEARS], *[f"prod_fy{y}" for y in CYCLE_YEARS], "prod_fy25",
]
# Reference rows: present in Inputs, never in an anchor path (校验步骤 13).
NOT_FORMULA = (
    "pe_own_med", "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi",
    "tp_cons_h", "fcf_fy25", "dps_fy25_final_hkd", "dps_h1_26_hkd",
    *[f"eps_fy{y}" for y in CYCLE_YEARS], *[f"prod_fy{y}" for y in CYCLE_YEARS], "prod_fy25",
)

# _AXIS.brent-oil.md §1 rung rows: | **L** | regime | **68** | sources | as-of |
_AXIS_RUNG = re.compile(r"^\|\s*\*\*([LMH])\*\*\s*\|")
# _AXIS.brent-oil.md §3 transmission rows: | L | 68 | 0857 NI | 0857 EPS | 0857 ROE | 0883 NI | 0883 EPS | 0883 ROE |
_AXIS_TIER = re.compile(r"^\|\s*([LMH])\s*\|")


def _cell(s: str) -> float:
    return float(s.strip("* ").replace(",", "").rstrip("%")) / (100.0 if s.strip().endswith("%") else 1.0)


def load_brent_rungs(path: Path = AXIS_BRENT) -> dict[str, float]:
    """{tier: Brent US$/bbl} from the axis §1 table (column 2, 0-based)."""
    rungs: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _AXIS_RUNG.match(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        try:
            rungs[m.group(1)] = _cell(cells[2])
        except ValueError:
            continue
    missing = {"L", "M", "H"} - rungs.keys()
    if missing:
        raise ValueError(f"{path.name}: rungs missing {sorted(missing)}")
    if not (rungs["L"] < rungs["M"] < rungs["H"]):
        raise ValueError(f"{path.name}: rungs not ordered {rungs}")
    return rungs


def load_axis_transmission(path: Path = AXIS_BRENT) -> dict[str, tuple[float, float, float]]:
    """{tier: (NI mn, EPS, ROE)} for this ticker from the axis §3 table (columns 5-7)."""
    out: dict[str, tuple[float, float, float]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _AXIS_TIER.match(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 8:
            continue
        try:
            out[m.group(1)] = (_cell(cells[5]), _cell(cells[6]), _cell(cells[7]))
        except ValueError:
            continue
    missing = {"L", "M", "H"} - out.keys()
    if missing:
        raise ValueError(f"{path.name}: §3 transmission rows missing {sorted(missing)} for {TICKER}")
    return out


def check_brent_mount(stated: tuple[float, float, float], ni: dict[str, float], eps: dict[str, float],
                      roe: dict[str, float]) -> list[str]:
    """The mount restates the axis rungs exactly, the axis declares the mount, and the
    axis §3 transmission table carries this ticker's tier NI / EPS / ROE as computed here."""
    if not AXIS_BRENT.exists():
        return [f"axis file missing: {AXIS_BRENT.name}"]
    rungs = load_brent_rungs()
    errors = [
        f"{tier} Brent rung: stated {got:g} vs axis {rungs[tier]:g}"
        for tier, got in zip(("L", "M", "H"), stated)
        if abs(got - rungs[tier]) > 1e-9
    ]
    if TICKER not in AXIS_BRENT.read_text(encoding="utf-8"):
        errors.append(f"{TICKER} is not declared on {AXIS_BRENT.name} — a mount has to exist on both sides")
    for tier, (a_ni, a_eps, a_roe) in load_axis_transmission().items():
        t = tier.lower()
        if abs(a_ni - ni[t]) > 0.5:
            errors.append(f"axis §3 {tier} NI {a_ni:,.0f} vs computed {ni[t]:,.0f} ({TICKER})")
        if abs(a_eps - eps[t]) > 1e-4:
            errors.append(f"axis §3 {tier} EPS {a_eps:.4f} vs computed {eps[t]:.4f} ({TICKER})")
        if abs(a_roe - roe[t]) > 1e-4:
            errors.append(f"axis §3 {tier} ROE {a_roe:.2%} vs computed {roe[t]:.2%} ({TICKER})")
    return errors


def ddm_pe(payout_policy: float, g: float, r: float) -> float:
    """PE-equivalent of the dividend ruler: payout / (r - g)."""
    return payout_policy / (r - g)


def band_at(g: float, d1: dict[str, float], r: float, fx: float) -> tuple[float, float, float]:
    """L/M/H in HKD for one shared dividend growth g (flat multiple, cyclical)."""
    return tuple(d1[t] / (r - g) / fx for t in TIERS)  # type: ignore[return-value]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    leaked_p = [k for k in inp if k.startswith("p_")]
    if leaked_p:
        errors.append(f"probability fields in Inputs {leaked_p} (A2e-7a)")
    r, fx, pay = inp["r_perp"], inp["fx_hkdcny"], inp["payout_policy"]

    # --- Step 1: numerators through the measured per-barrel elasticity, axis mount --
    brent = {"l": inp["brent_l"], "m": inp["brent_m"], "h": inp["brent_h"]}
    nib_fy25 = inp["ni_fy25"] / inp["liq_fy25"]
    nib_h1 = inp["ni_h1_26"] / inp["liq_h1_26"]
    k = (nib_h1 - nib_fy25) / (inp["real_h1_26"] - inp["real_fy25"])
    rho = inp["real_fy25"] / inp["brent_2025"]
    liq_2027 = inp["prod_2026_mid"] * inp["liq_share"] * inp["sales_ratio"]
    real = {t: rho * brent[t] for t in TIERS}
    ni = {t: liq_2027 * (nib_fy25 + k * (real[t] - inp["real_fy25"])) for t in TIERS}
    eps = {t: ni[t] * MN / inp["shares"] for t in TIERS}
    roe = {t: ni[t] / inp["equity"] for t in TIERS}
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    errors += check_brent_mount((brent["l"], brent["m"], brent["h"]), ni, eps, roe)
    if errors:
        return report(errors, "FAIL (axis / numerators)")

    # --- Step 2: mid-cycle numerator (A4) -----------------------------------------
    eps_ttm = (inp["ni_fy25"] - inp["ni_h1_25"] + inp["ni_h1_26"]) * MN / inp["shares"]
    mid_ratio = eps_ttm / eps["m"]
    if mid_ratio > MID_CYCLE_MAX:
        errors.append(f"中枢: TTM EPS {eps_ttm:.4f} / EPS_M {eps['m']:.4f} = {mid_ratio:.3f} > {MID_CYCLE_MAX} — "
                      f"the current print is above mid-cycle, M must move to the 中枢 (valuation-rules「周期票的中枢分子」)")
    h1_ann_ratio = 2.0 * inp["ni_h1_26"] * MN / inp["shares"] / eps["m"]
    cycle_eps = [inp[f"eps_fy{y}"] for y in CYCLE_YEARS] + [inp["eps_fy25"]]
    cycle_prod = [inp[f"prod_fy{y}"] for y in CYCLE_YEARS] + [inp["prod_fy25"]]
    cycle_mean_raw = sum(cycle_eps) / len(cycle_eps)
    cycle_mean_norm = sum(e * inp["prod_2026_mid"] / p for e, p in zip(cycle_eps, cycle_prod)) / len(cycle_eps)
    cycle_dev = eps["m"] / cycle_mean_norm - 1.0
    if abs(cycle_dev) > CYCLE_MEAN_DEV_MAX:
        errors.append(f"中枢: axis-bridged EPS_M {eps['m']:.4f} deviates {cycle_dev:+.1%} from the production-normalised "
                      f"full-cycle mean {cycle_mean_norm:.4f} (> {CYCLE_MEAN_DEV_MAX:.0%}) — back to the conversation (A4)")

    # --- Step 3: the three DDM preconditions (A6) ---------------------------------
    gordon_min = {t: min(perpetual_pe(g / 1000.0, roe[t], r) for g in range(0, int(G_CAP * 1000) + 1)) for t in TIERS}
    for t in TIERS:
        if gordon_min[t] <= inp["pe_own_max"] + 1e-9:
            errors.append(f"DDM precondition (a) fails: retention-branch Gordon reaches {gordon_min[t]:.3f}x <= band top "
                          f"{inp['pe_own_max']} at ROE_{t} {roe[t]:.2%} — Gordon is not BLOCKED, DDM exception does not apply")
        if roe[t] - r < MONOTONIC_GAP - 1e-12:
            errors.append(f"DDM precondition (c) fails: ROE_{t} {roe[t]:.2%} - r = {(roe[t] - r) * 100:.2f}pp < 3pp — not the monotonic regime")
    if PAYOUT_FLOOR_QUOTE not in md:
        errors.append(f"DDM precondition (b): framework does not quote the written payout floor ({PAYOUT_FLOOR_QUOTE!r})")
    if not (0.0 < pay <= 1.0):
        errors.append(f"payout_policy {pay} outside (0, 1]")
    payout_fy25 = inp["dps_fy25_cny"] * inp["shares"] / (inp["ni_fy25"] * MN)
    if abs(payout_fy25 - pay) > 0.02:
        errors.append(f"FY2025 paid payout {payout_fy25:.1%} is more than 2pp from the policy floor {pay:.0%} — re-anchor D1 (A7)")
    if errors:
        return report(errors, "FAIL (中枢 / DDM preconditions)")

    # --- Step 4: g_d — cap, peer median, evidence interval, gate, branch ----------
    g_d = inp["g2_d"]
    peers = {"cvx": inp["gd_peer_cvx"], "tte": inp["gd_peer_tte"], "1088": inp["gd_peer_1088"]}
    errors += check_r(r, "r_perp")
    errors += check_g_cap(g_d, "g2_d")
    if r - g_d < MIN_R_MINUS_G:
        errors.append(f"g2_d {g_d:+.4f}: r-g < {MIN_R_MINUS_G} (裁决顺序 ①)")
    for name, g in peers.items():
        if not (0.0 < g <= G_CAP + 1e-9):
            errors.append(f"gd_peer_{name} {g:+.4%} is not a usable same-regime sample (must be in (0, {G_CAP:.0%}]) — drop it, never clip (A8)")
    peer_median = statistics.median(peers.values())
    if abs(g_d - peer_median) > G_TOL:
        errors.append(f"g2_d {g_d} vs peer DDM reverse-solve median {peer_median:.5f} (A8)")
    if not (inp["g_evid_min"] - 1e-9 <= g_d <= inp["g_evid_max"] + 1e-9):
        errors.append(f"g2_d {g_d} outside evidence interval [{inp['g_evid_min']}, {inp['g_evid_max']}] (A9)")
    dps_cagr = (inp["dps_fy25_hkd"] / inp["dps_fy19_hkd"]) ** (1.0 / 6.0) - 1.0
    if dps_cagr <= 0.0 and g_d > 0.0:
        errors.append(f"same-world gate: own cross-cycle DPS CAGR {dps_cagr:+.2%} is not positive, a positive g_d is not usable (A11)")
    errors += check_branch(g_d, roe["m"], r, payout_fy25, "g2_d")

    # Guardrail of this ruler: the DDM-implied PE must sit inside the realised band.
    pe_eq = ddm_pe(pay, g_d, r)
    if not (inp["pe_own_min"] - 1e-9 <= pe_eq <= inp["pe_own_max"] + 1e-9):
        errors.append(f"guardrail: DDM-implied PE {pe_eq:.3f} outside realised band [{inp['pe_own_min']}, {inp['pe_own_max']}] — STOP (A9)")
    for g in (inp["g_evid_min"], inp["g_evid_max"]):
        pe_g = ddm_pe(pay, g, r)
        if not (inp["pe_own_min"] - PE_EDGE_TOL <= pe_g <= inp["pe_own_max"] + PE_EDGE_TOL):
            errors.append(f"evidence end g_d {g:+.2%} implies PE {pe_g:.3f} outside the band — the interval is wider than the guardrail allows (A9)")
    if errors:
        return report(errors, "FAIL (growth 口径)")

    # --- Step 5: anchors, zone, stability, ②-b, flat ladder ----------------------
    d1 = {t: pay * eps[t] for t in TIERS}                      # CNY
    m_d = 1.0 / (r - g_d)
    L, M, H = band_at(g_d, d1, r, fx)
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}"])
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    evid = {g: band_at(g, d1, r, fx) for g in (inp["g_evid_min"], inp["g_evid_max"])}
    for g, b in evid.items():
        if zone_of(inp["price"], *b) != zone:
            errors.append(f"zone flips to {zone_of(inp['price'], *b)} at g_d={g:+.2%} inside the evidence interval — BLOCKED (A9)")

    cons_mean = inp["eps_cons_fy27_mean"]
    cons_dev = eps["m"] / cons_mean - 1.0
    if cons_mean > eps["h"]:
        errors.append(f"②-b: consensus FY27 mean {cons_mean} above EPS_H {eps['h']:.4f} — H must become the market-baseline world")
    if abs(cons_dev) > CONS_DEV_MAX:
        errors.append(f"②-b: M deviates {cons_dev:+.1%} from consensus FY27 mean (> {CONS_DEV_MAX:.0%}) — switch numerators to the consensus three points")
    if cons_mean < eps["m"] and "②-b" not in md:
        errors.append("②-b: consensus FY27 mean below EPS_M with no named-variable row in the framework (A5)")
    nib_cons = cons_mean * inp["shares"] / MN / liq_2027
    brent_cons = (inp["real_fy25"] + (nib_cons - nib_fy25) / k) / rho

    pe_flat = {t: pe_eq for t in TIERS}
    flat_errs, flat_cny = flat_multiple_ladder((eps["l"], eps["m"], eps["h"]), pe_eq)
    errors += flat_errs
    flat = tuple(v / fx for v in flat_cny)

    if abs(inp["pe_own_med"] - pe_eq) < 1e-9:
        errors.append("pe_own_med leaked into the multiple path — it is a comparison field")
    leaked = [key for key in NOT_FORMULA if key not in inp]
    if leaked:
        errors.append(f"reference rows missing from Inputs: {leaked}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- Gordon cross (retention branch, sign only — monotonic regime) ------------
    g_ret_raw = (1.0 - payout_fy25) * roe["m"]
    g_ret = min(g_ret_raw, G_CAP)
    errors += check_branch(g_ret, roe["m"], r, payout_fy25, "gordon cross g2")
    modelled, gap = payout_gap(g_ret, roe["m"], payout_fy25)
    gordon = tuple(eps[t] * perpetual_pe(g_ret, roe[t], r) / fx for t in TIERS)
    zg = tuple(eps[t] * 10.0 / fx for t in TIERS)
    g_edge, ok_edge = implied_g_retaining(inp["pe_own_max"], roe["m"], r)

    # --- report ----------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"axis _AXIS.brent-oil OK: Brent {brent['l']:g}/{brent['m']:g}/{brent['h']:g}; base {inp['brent_2025']} (rho {rho:.4f}); "
          f"axis §3 transmission rows for {TICKER} match")
    print(f"k = (NI/bbl H1 {nib_h1:.2f} − FY25 {nib_fy25:.2f}) / (realised {inp['real_h1_26']} − {inp['real_fy25']}) = {k:.4f} RMB/bbl per US$1; "
          f"liq_2027 = {inp['prod_2026_mid']:.0f} × {inp['liq_share']} × {inp['sales_ratio']} = {liq_2027:.1f} mmbbl; ΔEPS/$1 = {liq_2027 * k * rho * MN / inp['shares']:.4f} CNY")
    print(f"{'档':<3}{'Brent':>7}{'实现价':>8}{'NI/bbl':>8}{'NI(mn)':>10}{'EPS':>9}{'ROE':>8}{'D1 CNY':>8}{'D1 HKD':>8}{'m_d':>7}{'PE_eq':>7}{'HKD':>8}")
    for t, a in zip(TIERS, (L, M, H)):
        print(f"{t.upper():<3}{brent[t]:7.0f}{real[t]:8.2f}{ni[t] / liq_2027:8.1f}{ni[t]:10,.0f}{eps[t]:9.4f}{roe[t]:8.2%}"
              f"{d1[t]:8.4f}{d1[t] / fx:8.4f}{m_d:7.2f}{pe_eq:7.2f}{a:8.2f}")
    print(f"中枢 (A4): TTM EPS {eps_ttm:.4f} ÷ EPS_M {eps['m']:.4f} = {mid_ratio:.3f} (≤ {MID_CYCLE_MAX} ✓, M stays); "
          f"2026H1 annualised ÷ 中枢 = {h1_ann_ratio:.3f} ({'optimistic-side coordinate' if h1_ann_ratio > MID_CYCLE_MAX else 'inside'}); "
          f"FY26E ÷ 中枢 = {inp['eps_cons_fy26_mean'] / eps['m']:.3f}; full-cycle EPS mean raw {cycle_mean_raw:.4f} (M/raw {eps['m'] / cycle_mean_raw:.3f}), "
          f"production-normalised {cycle_mean_norm:.4f} (M dev {cycle_dev:+.1%} ✓)")
    print(f"DDM preconditions (A6): (a) retention Gordon min over g∈[0,6%] = {gordon_min['l']:.2f}/{gordon_min['m']:.2f}/{gordon_min['h']:.2f}x > band top {inp['pe_own_max']} ✓ "
          f"(band-edge reverse-solve g {g_edge:+.2%}, conditioned={ok_edge}); (b) payout floor {pay:.0%} quoted ✓ (FY2025 paid {payout_fy25:.2%}); "
          f"(c) ROE−r = {(roe['l'] - r) * 100:.2f}/{(roe['m'] - r) * 100:.2f}/{(roe['h'] - r) * 100:.2f}pp ≥ 3 ✓ (单调区)")
    print(f"g_d (A8): peer DDM reverse-solve CVX {peers['cvx']:+.3%} / TTE {peers['tte']:+.3%} / 1088.HK {peers['1088']:+.3%} → median {peer_median:+.3%} = g2_d {g_d:+.2%} (cap {G_CAP:.0%}); "
          f"own DPS CAGR FY19→25 {dps_cagr:+.2%} (gate: positive ✓; > cap → not usable on this ruler); "
          f"band edges: top {r - pay / inp['pe_own_max']:+.2%} / med {r - pay / inp['pe_own_med']:+.2%} / bottom {r - pay / inp['pe_own_min']:+.2%}")
    print(f"guardrail (A9): DDM-implied PE {pay:.2f}/({r:.0%}−{g_d:.2%}) = {pe_eq:.2f}x ∈ [{inp['pe_own_min']}, {inp['pe_own_max']}] ✓; "
          f"evidence [{inp['g_evid_min']:+.2%}, {inp['g_evid_max']:+.2%}] → PE {ddm_pe(pay, inp['g_evid_min'], r):.2f}–{ddm_pe(pay, inp['g_evid_max'], r):.2f}x")
    print(f"check_branch ✓ (sign only, 单调区): g2_d {g_d:+.2%} on payout {payout_fy25:.1%}; gordon cross g raw (1−payout)×ROE_M = {g_ret_raw:+.2%} → cap {g_ret:.0%}; "
          f"payout_gap: modelled {modelled:.1%} vs paid {payout_fy25:.1%} = {gap:+.1%} (book ≠ marginal ROE, disclosure)")
    d = decompose((L, M, H), (pe_flat["l"], pe_flat["m"], pe_flat["h"]))
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.1%} | 分子比 L={d['num_lm']:.3f} H={d['num_hm']:.3f} | 倍数比 L={d['pe_lm']:.3f} H={d['pe_hm']:.3f} (dividend ruler flat)")
    print(f"flat-multiple @PE_eq={pe_eq:.2f}: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f} — 带宽 {(flat[2] - flat[0]) / (2 * flat[1]):.1%}")
    print(f"②-b: 共识 FY27 {inp['eps_cons_fy27_lo']}/{cons_mean}/{inp['eps_cons_fy27_hi']} vs EPS {eps['l']:.4f}/{eps['m']:.4f}/{eps['h']:.4f}; "
          f"均值 {'in [M,H]' if eps['m'] <= cons_mean <= eps['h'] else ('below M' if cons_mean < eps['m'] else 'above H')}, M dev {cons_dev:+.1%}, 均值 ↔ Brent {brent_cons:.1f}")
    pe_px = inp["price"] * fx / eps["m"]
    gd_px = r - pay / pe_px
    d0_ttm = inp["dps_fy25_final_hkd"] + inp["dps_h1_26_hkd"]
    gd_yield = r - d0_ttm / inp["price"]
    r_full = 1.0 / pe_px
    r_ret6 = (1.0 - G_CAP / roe["m"]) / pe_px + G_CAP
    print(f"price(H)={inp['price']} zone={zone} | 现价 = {pe_px:.2f}x M 档 EPS: DDM-implied g_d {gd_px:+.2%} (yield form, D0 TTM {d0_ttm:.2f} HKD: {gd_yield:+.2%}); "
          f"Gordon 单调区不可达 → full-payout r {r_full:.1%} / retention g 6% r {r_ret6:.1%} (A10)")
    print(f"市场隐含边际 ROE (A10 disclosure): g_d {g_d:.2%} ÷ retention {1 - pay:.0%} = {g_d / (1 - pay):.2%}; at market g_d {gd_px:.2%} → {gd_px / (1 - pay):.2%}; "
          f"book ROE_M {roe['m']:.2%} → gap {(roe['m'] - g_d / (1 - pay)) * 100:.1f} / {(roe['m'] - gd_px / (1 - pay)) * 100:.1f}pp")
    for g, b in evid.items():
        print(f"证据区间 g_d={g:+.2%}: {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    for g in (g_d - 0.01, g_d + 0.01, 0.0):
        b = band_at(g, d1, r, fx)
        pe_g = ddm_pe(pay, g, r)
        print(f"敏感性 g_d {g:+.2%}: PE_eq {pe_g:.2f}x {'in band' if inp['pe_own_min'] <= pe_g <= inp['pe_own_max'] else 'OUT of band'} → {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    for p2 in (0.40, 0.50):
        b = tuple(p2 * eps[t] / (r - g_d) / fx for t in TIERS)
        print(f"敏感性 payout {p2:.0%}: {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    print(f"每 US$1 Brent ≈ M {liq_2027 * k * rho * MN / inp['shares'] * pay * m_d / fx:+.2f} HKD; 2026H1 annualised NI {2 * inp['ni_h1_26']:,.0f} ↔ 本尺 Brent {(inp['real_fy25'] + (2 * inp['ni_h1_26'] / liq_2027 - nib_fy25) / k) / rho:.1f}")
    print(f"对照带 (自身实测带外·不作锚): 留存 Gordon g {g_ret:.0%} PE {'/'.join(f'{perpetual_pe(g_ret, roe[t], r):.2f}' for t in TIERS)} → {'/'.join(f'{x:.2f}' for x in gordon)} (zone {zone_of(inp['price'], *gordon)}); "
          f"零增长 10x {'/'.join(f'{x:.2f}' for x in zg)} (zone {zone_of(inp['price'], *zg)}); own 中位 {inp['pe_own_med']}x flat → {'/'.join(f'{eps[t] * inp['pe_own_med'] / fx:.2f}' for t in TIERS)}")
    bps = inp["equity"] * MN / inp["shares"]
    print(f"交叉尺: FCF 收益率 {inp['fcf_fy25'] * MN / (inp['price'] * fx * inp['shares']):.2%}, P/FCF 10x = {inp['fcf_fy25'] * MN / inp['shares'] * 10 / fx:.2f} HKD; "
          f"BPS {bps:.2f} CNY = {bps / fx:.2f} HKD, PB at price {inp['price'] * fx / bps:.2f}, at L/M/H {L * fx / bps:.2f}/{M * fx / bps:.2f}/{H * fx / bps:.2f}; "
          f"TP 均值 {inp['tp_cons_h']} = {inp['tp_cons_h'] * fx / eps['m']:.2f}x M EPS ↔ g_d {r - pay / (inp['tp_cons_h'] * fx / eps['m']):+.2%}; H/TP {H / inp['tp_cons_h']:.2f} M/TP {M / inp['tp_cons_h']:.2f}")
    g1 = (inp["eps_fy2022"] / inp["eps_fy2020"]) ** 0.5 - 1.0
    pe_rec = recovery_two_stage_pe(g1, 2, g_ret, roe["m"], r)
    print(f"谷底坐标 (A3): 回归段 2020->2022 g1 {g1:.1%} n=2 -> {pe_rec:.1f}x on FY2020 EPS {inp['eps_fy2020']} = {inp['eps_fy2020'] * pe_rec / fx:.2f} HKD (坐标, 不作锚); "
          f"谷底 x 1/r = {inp['eps_fy2020'] / r / fx:.2f} HKD (deep_discount 压力坐标)")
    la, ma, ha = L * fx, M * fx, H * fx
    print(f"A股对照(CNY): L={la:.2f} M={ma:.2f} H={ha:.2f} | price_a={inp['price_a']} zone_a={zone_of(inp['price_a'], la, ma, ha)} "
          f"(A 股 = {inp['price_a'] / eps['m']:.2f}x M EPS ↔ g_d {r - pay / (inp['price_a'] / eps['m']):+.2%}) | H/A = {inp['price'] * fx / inp['price_a']:.3f}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
