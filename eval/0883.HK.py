#!/usr/bin/env python3
"""0883.HK (CNOOC) valuation eval.

frameworks/0883.HK.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: cnooc_hk_brent_axis_gordon_retention_v2

Main ruler: Gordon retention branch at the basket r (valuation-rules「§r 篮子」,
whole company in 篮 7 国别重, 15% -- the NS-CMIC investment ban is a
nameable country-risk item, A17; 篮 6 13% is the "sanction discount fades"
cross band).  The numerator is the shared Brent axis
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

Multiple (A18, 留存三桶): maintenance capex ~ D&A so E_owner ~ NI; the capex
above D&A funds named production growth (+5-8%/yr) -> g2 = 4.5% with a growth
retention ratio b_g = 25%; the rest of retention piles up as cash and earns no
credit (disclosed per share, never added).  Hence

    PE = (1 - b_g) / (r - g2) = 0.75 / (15% - 4.5%) = 7.14x, flat across tiers

which must sit inside the realised 5y monthly TTM PE band [2.90, 9.89] -- the
guardrail.  Why Gordon and not the DDM exception this ticker used to be the
worked example of: at the basket r, 1/r = 6.67x <= band top 9.89x, so the
retention branch IS reachable and precondition (a) of「DDM 主尺例外」fails
(A6).  The DDM band (45% x EPS / (r - g_d)), the 1/r zero-growth band, the
fallback basket 6 band (制裁折价消失) and the FCF-yield ruler are printed as cross-checks;
the price is only used to read the implied r (A10) -- never to fit anchors.
The g2 +/-1pp sensitivity is printed, and a zone flip there is a disclosure
(⚠敏感区), not a failure.

Run:  python3 frameworks/eval/0883.HK.py
"""

from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_BRENT  # noqa: E402
from lib.gordon import (  # noqa: E402
    NEAR_FULL_PAYOUT, basket_r, check_branch, check_g_cap, check_r, g_cap, implied_g_retaining, justified_pb,
    payout_gap,
    recovery_two_stage_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points, zone_of  # noqa: E402

# rf_report / bands_io import eval.lib.*, so the repo root must be importable too.
sys.path.append(str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FRAMEWORK = REPO / "frameworks" / "0883.HK.md"
FORMULA_ID = "cnooc_hk_brent_axis_gordon_retention_v2"
TICKER = "0883.HK"
LISTING_CCY = "HKD"

TIERS = ("l", "m", "h")
MN = 1e6                    # Inputs money fields are RMB million
G_TOL = 5e-5
MIN_R_MINUS_G = 0.02
CONS_DEV_MAX = 0.20         # ②-b: M within 20% of the consensus mean
MID_CYCLE_MAX = 1.15        # 中枢: current / mid-cycle above this makes the current print an upper-side coordinate
CYCLE_MEAN_DEV_MAX = 0.20   # 中枢: axis-bridged M vs own full-cycle (production-normalised) EPS mean
MONOTONIC_GAP = 0.03        # ROE - r >= this is the monotonic regime (gordon._ROE_NEAR_R)
FALLBACK_BASKET = 6         # A17: 篮 6 13% = 制裁折价消失 world, printed as a cross band
CYCLE_YEARS = ("2020", "2021", "2022", "2023", "2024")
PAYOUT_FLOOR_QUOTE = "不低于 45%"

REQUIRED = [
    "price", "price_a", "shares", "equity", "fx_hkdcny",
    "ni_fy25", "eps_fy25", "ni_h1_25", "ni_h1_26",
    "liq_fy25", "real_fy25", "liq_h1_26", "real_h1_26",
    "prod_2026_mid", "liq_share", "sales_ratio",
    "brent_2025", "brent_l", "brent_m", "brent_h",
    "payout_policy", "dps_fy25_cny", "dps_fy25_hkd", "dps_fy19_hkd", "dps_fy25_final_hkd", "dps_h1_26_hkd",
    "r_perp", "g2", "b_growth", "capex_fy25", "da_fy25", "cash_fy25",
    "g2_d", "g_evid_min", "g_evid_max", "gd_peer_cvx", "gd_peer_tte", "gd_peer_1088",
    "pe_own_min", "pe_own_max", "pe_own_med",
    "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi", "tp_cons_h",
    "fcf_fy25",
    *[f"eps_fy{y}" for y in CYCLE_YEARS], *[f"prod_fy{y}" for y in CYCLE_YEARS], "prod_fy25",
]
# Reference rows: present in Inputs, never in an anchor path (校验步骤 13).
NOT_FORMULA = (
    "pe_own_med", "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi",
    "tp_cons_h", "fcf_fy25", "dps_fy25_final_hkd", "dps_h1_26_hkd", "capex_fy25", "da_fy25", "cash_fy25",
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


def retention_pe(b_growth: float, g: float, r: float) -> float:
    """Gordon multiple crediting only the growth retention (A18): (1 - b_g) / (r - g)."""
    return (1.0 - b_growth) / (r - g)


def fmt_band(band: tuple[float, ...]) -> str:
    return "/".join(f"{x:.2f}" for x in band)


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
    g2, b_g = inp["g2"], inp["b_growth"]
    baskets = parse_baskets(md)

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

    # --- Step 3: ruler-form gate (A6) — Gordon reachable at the basket r ------------
    # The DDM exception applies only while the retention branch cannot reach the
    # realised band; at 1/r <= band top it can, so DDM stays a cross-check.
    if 1.0 / r > inp["pe_own_max"] + 1e-9:
        errors.append(f"ruler form: 1/r = {1.0 / r:.2f}x > band top {inp['pe_own_max']} — retention-branch Gordon is BLOCKED "
                      f"again, DDM exception (a) holds; back to the conversation (A6)")
    if PAYOUT_FLOOR_QUOTE not in md:
        errors.append(f"framework does not quote the written payout floor ({PAYOUT_FLOOR_QUOTE!r}) — A7 needs it")
    if not (0.0 < pay <= 1.0):
        errors.append(f"payout_policy {pay} outside (0, 1]")
    payout_fy25 = inp["dps_fy25_cny"] * inp["shares"] / (inp["ni_fy25"] * MN)
    if abs(payout_fy25 - pay) > 0.02:
        errors.append(f"FY2025 paid payout {payout_fy25:.1%} is more than 2pp from the policy floor {pay:.0%} — re-anchor (A7)")
    if errors:
        return report(errors, "FAIL (中枢 / ruler form)")

    # --- Step 4: growth 口径 — basket r, g cap, sustainability, branch --------------
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(g2, r, "g2")
    if r - g2 < MIN_R_MINUS_G:
        errors.append(f"g2 {g2:+.4f}: r-g < {MIN_R_MINUS_G} (裁决顺序 ①)")
    g_sustain = (1.0 - payout_fy25) * roe["m"]
    if g2 > g_sustain + 1e-9:
        errors.append(f"g2 {g2:.2%} exceeds the sustainable ceiling (1−payout)×ROE_M = {g_sustain:.2%} — growth would eat the dividend (A7)")
    # Branch guard on the "视同派出" payout 1 - b_growth, not the paid 44.6%: A18 classes the
    # extra ~30pp of retention as the financial bucket (cash pile, no g credit), so the
    # payout the retention branch implies at g2 must reconcile with 1 - b_g; the gap to the
    # paid ratio IS the third bucket and is printed, not failed.  Sign test on the paid ratio.
    if payout_fy25 >= NEAR_FULL_PAYOUT and g2 > 0.0:
        errors.append(f"g2 {g2:+.2%} is the retention branch but the company pays out {payout_fy25:.0%} (反解分支)")
    errors += check_branch(g2, roe["m"], r, 1.0 - b_g, "g2 (vs 视同派出 1−b_growth)")
    payout_modelled, fin_bucket_gap = payout_gap(g2, roe["m"], payout_fy25)
    if not (0.0 < b_g < 1.0):
        errors.append(f"b_growth {b_g} outside (0, 1)")
    if not (inp["g_evid_min"] - 1e-9 <= g2 <= inp["g_evid_max"] + 1e-9):
        errors.append(f"g2 {g2} outside evidence interval [{inp['g_evid_min']}, {inp['g_evid_max']}] (A9)")
    dps_cagr = (inp["dps_fy25_hkd"] / inp["dps_fy19_hkd"]) ** (1.0 / 6.0) - 1.0
    if dps_cagr <= 0.0 and g2 > 0.0:
        errors.append(f"same-world gate: own cross-cycle DPS CAGR {dps_cagr:+.2%} is not positive, a positive g2 is not usable (A11)")
    # DDM cross-check inputs stay internally consistent (A8) even though they never touch the anchors.
    g_d = inp["g2_d"]
    peers = {"cvx": inp["gd_peer_cvx"], "tte": inp["gd_peer_tte"], "1088": inp["gd_peer_1088"]}
    for name, g in peers.items():
        if not (0.0 < g <= g_cap(r) + 1e-9):
            errors.append(f"gd_peer_{name} {g:+.4%} is not a usable same-regime sample (must be in (0, {g_cap(r):.0%}]) — drop it, never clip (A8)")
    peer_median = statistics.median(peers.values())
    if abs(g_d - peer_median) > G_TOL:
        errors.append(f"g2_d {g_d} vs peer DDM reverse-solve median {peer_median:.5f} (A8)")

    # Guardrail of this ruler: the generated PE must sit inside the realised band.
    pe = retention_pe(b_g, g2, r)
    if not (inp["pe_own_min"] - 1e-9 <= pe <= inp["pe_own_max"] + 1e-9):
        errors.append(f"guardrail: generated PE {pe:.3f} outside realised band [{inp['pe_own_min']}, {inp['pe_own_max']}] — STOP (A9)")
    if errors:
        return report(errors, "FAIL (growth 口径)")

    # --- Step 5: anchors, zone, ②-b, flat ladder ----------------------------------
    def band_at(pe_x: float) -> tuple[float, float, float]:
        return tuple(eps[t] * pe_x / fx for t in TIERS)  # type: ignore[return-value]

    L, M, H = band_at(pe)
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}"])
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

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

    flat_errs, flat_cny = flat_multiple_ladder((eps["l"], eps["m"], eps["h"]), pe)
    errors += flat_errs
    flat = tuple(v / fx for v in flat_cny)

    if abs(inp["pe_own_med"] - pe) < 1e-9:
        errors.append("pe_own_med leaked into the multiple path — it is a comparison field")
    leaked = [key for key in NOT_FORMULA if key not in inp]
    if leaked:
        errors.append(f"reference rows missing from Inputs: {leaked}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- Cross bands and disclosures (never asserted against the price) -----------
    ddm = tuple(pay * eps[t] / (r - g_d) / fx for t in TIERS)
    zero_g = band_at(1.0 / r)
    fallback = band_at(retention_pe(b_g, g2, basket_r(FALLBACK_BASKET)))
    own_med = band_at(inp["pe_own_med"])
    cash_ps_hkd = inp["cash_fy25"] * MN / inp["shares"] / fx
    pe_px = inp["price"] * fx / eps["m"]
    implied_r = (1.0 - b_g) / pe_px + g2
    eps_px = inp["price"] * fx / pe
    brent_px = (inp["real_fy25"] + (eps_px * inp["shares"] / MN / liq_2027 - nib_fy25) / k) / rho
    g_edge, well = implied_g_retaining(inp["pe_own_max"], roe["m"], r)

    print(f"弹性: NI/bbl FY25 {nib_fy25:.2f} → 2026H1 {nib_h1:.2f} RMB; k {k:.3f} RMB/bbl per US$1; ρ {rho:.4f}; liq_2027 {liq_2027:.1f} mmbbl")
    print(f"分子: Brent {brent['l']}/{brent['m']}/{brent['h']} → realised {real['l']:.2f}/{real['m']:.2f}/{real['h']:.2f} → "
          f"NI {ni['l']:,.0f}/{ni['m']:,.0f}/{ni['h']:,.0f} mn → EPS {eps['l']:.4f}/{eps['m']:.4f}/{eps['h']:.4f} CNY; "
          f"ROE {roe['l']:.2%}/{roe['m']:.2%}/{roe['h']:.2%} (ROE−r {(roe['l'] - r) * 100:+.2f}/{(roe['m'] - r) * 100:+.2f}/{(roe['h'] - r) * 100:+.2f}pp; "
          f"monotonic ≥ {MONOTONIC_GAP * 100:.0f}pp: {'/'.join('Y' if roe[t] - r >= MONOTONIC_GAP - 1e-12 else 'near-r' for t in TIERS)})")
    print(f"中枢 (A4): TTM EPS {eps_ttm:.4f} / EPS_M = {mid_ratio:.3f} (≤ {MID_CYCLE_MAX} ✓); 2026H1 annualised / EPS_M = {h1_ann_ratio:.3f}; "
          f"cycle mean raw {cycle_mean_raw:.4f} / production-normalised {cycle_mean_norm:.4f} → M dev {cycle_dev:+.1%} (≤ {CYCLE_MEAN_DEV_MAX:.0%} ✓)")
    print(f"ruler form (A6): 1/r = {1.0 / r:.2f}x ≤ band top {inp['pe_own_max']} → retention-branch Gordon reachable, DDM exception (a) fails; "
          f"band-top implied g (ROE_M) {g_edge:+.2%} well_conditioned={well}")
    print(f"篮子: r_perp {r:.0%} = 篮 {baskets.get('r_perp')} (check_r ✓); g2 {g2:.2%} ≤ cap {g_cap(r):.2%} ✓; r−g2 {r - g2:.2%}; "
          f"sustainable (1−payout {payout_fy25:.1%})×ROE_M = {g_sustain:.2%} ≥ g2 ✓; check_branch ✓ vs 视同派出 {1.0 - b_g:.0%} (modelled {payout_modelled:.1%}; gap to paid {fin_bucket_gap:+.1%} = 财务性留存桶, A18); DPS CAGR FY19→25 {dps_cagr:+.2%} (gate ✓)")
    print(f"倍数: PE = (1−{b_g:.0%})/({r:.0%}−{g2:.1%}) = {pe:.3f}x ∈ [{inp['pe_own_min']}, {inp['pe_own_max']}] ✓ (guardrail A9)")
    d = decompose((L, M, H), (pe, pe, pe))
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.1%} | 分子比 L={d['num_lm']:.3f} H={d['num_hm']:.3f} | 倍数比 L={d['pe_lm']:.3f} H={d['pe_hm']:.3f} (flat)")
    print(f"flat-multiple @PE={pe:.2f}: {fmt_band(flat)} — 带宽 {(flat[2] - flat[0]) / (2 * flat[1]):.1%}")
    print(f"②-b: 共识 FY27 {inp['eps_cons_fy27_lo']}/{cons_mean}/{inp['eps_cons_fy27_hi']} vs EPS {eps['l']:.4f}/{eps['m']:.4f}/{eps['h']:.4f}; "
          f"均值 {'in [M,H]' if eps['m'] <= cons_mean <= eps['h'] else ('below M' if cons_mean < eps['m'] else 'above H')}, M dev {cons_dev:+.1%}, 均值 ↔ Brent {brent_cons:.1f}")
    print(f"price(H)={inp['price']} zone={zone} | 现价 = {pe_px:.2f}x M 档 EPS → 隐含 r(P) {implied_r:.1%} (A10; "
          f"共识 FY27 {inp['price'] * fx / cons_mean:.2f}x → {(1.0 - b_g) / (inp['price'] * fx / cons_mean) + g2:.1%}, TTM {inp['price'] * fx / eps_ttm:.2f}x → {(1.0 - b_g) / (inp['price'] * fx / eps_ttm) + g2:.1%}); "
          f"市价反推 EPS {eps_px:.2f} ↔ Brent {brent_px:.1f}")
    for g in (g2 - 0.01, g2 + 0.01):
        pe_g = retention_pe(b_g, g, r)
        b = band_at(pe_g)
        in_band = inp["pe_own_min"] <= pe_g <= inp["pe_own_max"]
        flag = " ⚠敏感区" if zone_of(inp["price"], *b) != zone else ""
        print(f"敏感性 g2 {g:+.2%}: PE {pe_g:.2f}x {'in band' if in_band else 'OUT of band (不可用)'} → {fmt_band(b)} zone={zone_of(inp['price'], *b)}{flag}")
    for b2 in (0.20, 0.30):
        b = band_at(retention_pe(b2, g2, r))
        print(f"敏感性 b_growth {b2:.0%}: {fmt_band(b)} zone={zone_of(inp['price'], *b)}")
    for r2 in (r - 0.005, r + 0.005):
        b = band_at(retention_pe(b_g, g2, r2))
        print(f"敏感性 r {r2:.1%}: {fmt_band(b)} zone={zone_of(inp['price'], *b)}")
    print(f"敏感性 篮 {FALLBACK_BASKET} r {basket_r(FALLBACK_BASKET):.0%}: {fmt_band(fallback)} zone={zone_of(inp['price'], *fallback)}; "
          f"g=0 全派息 1/r {1.0 / r:.2f}x: {fmt_band(zero_g)} zone={zone_of(inp['price'], *zero_g)}")
    print(f"每 US$1 Brent ≈ {liq_2027 * k * rho * MN / inp['shares'] * pe / fx:+.2f} HKD; 2026H1 annualised NI {2 * inp['ni_h1_26']:,.0f} ↔ 本尺 Brent {(inp['real_fy25'] + (2 * inp['ni_h1_26'] / liq_2027 - nib_fy25) / k) / rho:.1f}")
    print(f"对照带 (不入盘): DDM 45%×EPS/({r:.0%}−{g_d:.2%}) = {pay / (r - g_d):.2f}x → {fmt_band(ddm)} (zone {zone_of(inp['price'], *ddm)}); "
          f"own 中位 {inp['pe_own_med']}x flat → {fmt_band(own_med)} (zone {zone_of(inp['price'], *own_med)}); "
          f"现金 {inp['cash_fy25']:,.0f} mn = {inp['cash_fy25'] * MN / inp['shares']:.2f} CNY = {cash_ps_hkd:.2f} HKD/股 ({cash_ps_hkd / inp['price']:.0%} of price, 只披露不加); "
          f"capex {inp['capex_fy25']:,.0f} vs D&A {inp['da_fy25']:,.0f} → growth capex {inp['capex_fy25'] - inp['da_fy25']:,.0f} = {(inp['capex_fy25'] - inp['da_fy25']) / inp['ni_fy25']:.0%} of NI (b_growth {b_g:.0%})")
    bps = inp["equity"] * MN / inp["shares"]
    print(f"交叉尺: FCF 收益率 {inp['fcf_fy25'] * MN / (inp['price'] * fx * inp['shares']):.2%}, P/FCF 10x = {inp['fcf_fy25'] * MN / inp['shares'] * 10 / fx:.2f} HKD; "
          f"BPS {bps:.2f} CNY = {bps / fx:.2f} HKD (地板只披露), PB at price {inp['price'] * fx / bps:.2f}, at L/M/H {L * fx / bps:.2f}/{M * fx / bps:.2f}/{H * fx / bps:.2f}, "
          f"Gordon PB (ROE−g)/(r−g) {'/'.join(f'{justified_pb(g2, roe[t], r):.2f}' for t in TIERS)}; "
          f"TP 均值 {inp['tp_cons_h']} = {inp['tp_cons_h'] * fx / eps['m']:.2f}x M EPS (zone {zone_of(inp['tp_cons_h'], L, M, H)}); H/TP {H / inp['tp_cons_h']:.2f} M/TP {M / inp['tp_cons_h']:.2f}")
    g1 = (inp["eps_fy2022"] / inp["eps_fy2020"]) ** 0.5 - 1.0
    pe_rec = recovery_two_stage_pe(g1, 2, g2, roe["m"], r)
    print(f"谷底坐标 (A3): 回归段 2020->2022 g1 {g1:.1%} n=2 -> {pe_rec:.1f}x on FY2020 EPS {inp['eps_fy2020']} = {inp['eps_fy2020'] * pe_rec / fx:.2f} HKD (坐标, 不作锚); "
          f"谷底 x 1/r = {inp['eps_fy2020'] / r / fx:.2f} HKD (deep_discount 压力坐标)")
    la, ma, ha = L * fx, M * fx, H * fx
    print(f"A股对照(CNY): L={la:.2f} M={ma:.2f} H={ha:.2f} | price_a={inp['price_a']} zone_a={zone_of(inp['price_a'], la, ma, ha)} "
          f"(A 股 = {inp['price_a'] / eps['m']:.2f}x M EPS ↔ 隐含 r {(1.0 - b_g) / (inp['price_a'] / eps['m']) + g2:.1%}) | H/A = {inp['price'] * fx / inp['price_a']:.3f}")
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_perp 1:1 in the retention multiple; the Brent rungs, EPS, b_growth and g2
    # stay put.  The DDM band discounts at the same r_perp but is a cross band,
    # not L/M/H.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        return band_at(retention_pe(b_g, g2, r + dr))

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf, inp["price"])
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    # Only a clean run feeds the daily digest.
    if not errors:
        write_rf_readings(TICKER, rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
