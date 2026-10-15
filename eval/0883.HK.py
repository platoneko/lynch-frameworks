#!/usr/bin/env python3
"""0883.HK (CNOOC) valuation eval.

frameworks/0883.HK.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The
framework carries no current price (AGENTS.md「现价 — 禁写契约」): this
script neither reads a price nor derives or checks a zone -- the daily
digest derives the zone from live quotes.

formula_id: cnooc_hk_brent_axis_opvalue_gordon_v3

Main ruler: operating value Gordon + excess cash (valuation-rules「经营价值与
超额现金」, 2026-10-15 框架纠正) at the basket r (whole company in 篮 7 国别重,
15% -- the NS-CMIC investment ban is a nameable country-risk item, A17; 篮 6
13% is the "sanction discount fades" cross band).  The numerator is the shared
Brent axis (_AXIS.brent-oil.md, 68 / 75 / 85) pushed through the company's OWN
measured per-barrel earnings elasticity,

    NI/bbl_FY25 = NI_FY25 / liquids sold FY25                      = 207.2 RMB/bbl
    k           = (NI/bbl 2026H1 - NI/bbl FY25) / (realised 2026H1 - realised FY25)
                                                                    = 3.968 RMB/bbl per US$1
    NI_x        = liquids_2027 x [NI/bbl_FY25 + k (rho Brent_x - realised FY25)]

and the axis M rung IS the mid-cycle numerator (2027 house median = the
2020-2025 realised Brent mean, not the current 87.6 print): the framework has
to show TTM EPS / EPS_M <= 1.15 and a production-normalised full-cycle EPS
mean within 20% of EPS_M (valuation-rules「周期票的中枢分子」).

Operating basis (A19):
    C_ex   = extended net cash 2026-06 - declared unpaid FY2025 final dividend
             - ex-dividend unpaid 2026 interim dividend - anchor 0
    E_op_x = NI_x - C_ex x cash_yield x (1 - tax_eff)
    RONIC   = E_op_M / (equity - interim dividend - C_ex)   (2026-06-30
             denominator as before; no peak-proofing: the commodity price comes
             from the axis, which carries the pessimistic rung).  The settled
             one-multiple-for-all-tiers form (cyclical flat) is kept: all three
             tiers use the M-tier operating return; L / H returns are printed only.
    PE     = perpetual_pe(g2, RONIC, r)            (flat across tiers)
    anchor_x = (E_op_x x PE + C_ex x lambda) / shares / fx,  lambda = 1

g2 = 4.5% stays (user-confirmed); the replaced "growth retention 25%" pick is
now b = g2 / RONIC, capped by (1 - d) x RONIC (constraint 2).  Historical
multiples (the realised band, the same-earnings months) are on the operating
basis: (price - excess cash per share then) / operating TTM EPS then.

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
    payout_gap, perpetual_pe, recovery_two_stage_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points, zone_of  # noqa: E402

# rf_report / bands_io import eval.lib.*, so the repo root must be importable too.
sys.path.append(str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FRAMEWORK = REPO / "frameworks" / "0883.HK.md"
FORMULA_ID = "cnooc_hk_brent_axis_opvalue_gordon_v3"
TICKER = "0883.HK"
LISTING_CCY = "HKD"

TIERS = ("l", "m", "h")
MN = 1e6                    # Inputs money fields are RMB million
G_TOL = 5e-5
MIN_R_MINUS_G = 0.02
CONS_DEV_MAX = 0.20         # ②-b: M within 20% of the consensus mean
MID_CYCLE_MAX = 1.15        # 中枢: current / mid-cycle above this makes the current print an upper-side coordinate
CYCLE_MEAN_DEV_MAX = 0.20   # 中枢: axis-bridged M vs own full-cycle (production-normalised) EPS mean
MONOTONIC_GAP = 0.03        # RONIC - r >= this is the monotonic regime (gordon._ROE_NEAR_R)
EXCESS_CASH_GATE = 0.15     # C_ex >= 15% of equity → excess-cash line exists (valuation-rules ①)
LAMBDA = 1.0                # A19: no named evidence that the cash cannot reach shareholders
FALLBACK_BASKET = 6         # A17: 篮 6 13% = 制裁折价消失 world, printed as a cross band
CYCLE_YEARS = ("2020", "2021", "2022", "2023", "2024")
PAYOUT_FLOOR_QUOTE = "不低于 45%"

REQUIRED = [
    "shares", "equity", "fx_hkdcny",
    "ni_fy25", "eps_fy25", "ni_h1_25", "ni_h1_26",
    "liq_fy25", "real_fy25", "liq_h1_26", "real_h1_26",
    "prod_2026_mid", "liq_share", "sales_ratio",
    "brent_2025", "brent_l", "brent_m", "brent_h",
    "payout_policy", "dps_fy25_cny", "dps_fy25_hkd", "dps_fy19_hkd", "dps_fy25_final_hkd", "dps_h1_26_hkd",
    "r_perp", "g2", "capex_fy25", "da_fy25",
    "net_cash_ext_h1", "div_declared", "div_exdiv", "c_ex", "cash_yield", "tax_eff",
    "ret_d", "ret_c", "ret_i", "payout_op", "op_ret_fy23", "op_ret_fy24", "op_ret_fy25",
    "g2_d", "g_evid_min", "g_evid_max", "gd_peer_cvx", "gd_peer_tte", "gd_peer_1088",
    "pe_op_min", "pe_op_max", "pe_op_med", "pe_same_med",
    "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi", "tp_cons_h",
    "fcf_fy25",
    *[f"eps_fy{y}" for y in CYCLE_YEARS], *[f"prod_fy{y}" for y in CYCLE_YEARS], "prod_fy25",
]
# Reference rows: present in Inputs, never in an anchor path (校验步骤 13).
NOT_FORMULA = (
    "pe_op_med", "pe_same_med", "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi",
    "tp_cons_h", "fcf_fy25", "dps_fy25_final_hkd", "dps_h1_26_hkd", "capex_fy25", "da_fy25",
    "ret_i", "op_ret_fy23", "op_ret_fy24", "op_ret_fy25",
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
    axis §3 transmission table carries this ticker's tier NI / EPS / book ROE as computed here."""
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
    r, fx, pay, sh = inp["r_perp"], inp["fx_hkdcny"], inp["payout_policy"], inp["shares"]
    g2 = inp["g2"]
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
    eps = {t: ni[t] * MN / sh for t in TIERS}
    roe = {t: ni[t] / inp["equity"] for t in TIERS}   # book ROE: axis §3 table + disclosure only
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    errors += check_brent_mount((brent["l"], brent["m"], brent["h"]), ni, eps, roe)
    if errors:
        return report(errors, "FAIL (axis / numerators)")

    # --- Step 2: excess cash and the operating basis (A19) ---------------------------
    c_ex = inp["net_cash_ext_h1"] - inp["div_declared"] - inp["div_exdiv"]   # anchor 0
    if abs(c_ex - inp["c_ex"]) > 1.0:
        errors.append(f"c_ex {inp['c_ex']:,.0f} != net_cash_ext_h1 − div_declared − div_exdiv {c_ex:,.0f}")
    if c_ex < EXCESS_CASH_GATE * inp["equity"]:
        errors.append(f"c_ex {c_ex / inp['equity']:.1%} of equity < {EXCESS_CASH_GATE:.0%}: the excess-cash line should not exist")
    c_inc = c_ex * inp["cash_yield"] * (1.0 - inp["tax_eff"])     # after-tax income, out of every numerator
    e_op = {t: ni[t] - c_inc for t in TIERS}
    eps_op = {t: e_op[t] * MN / sh for t in TIERS}
    op_eq = inp["equity"] - inp["div_exdiv"] - c_ex                 # 2026-06-30 book after the ex-div interim
    ronic_tier = {t: e_op[t] / op_eq for t in TIERS}       # per-tier returns: disclosure only
    ronic = {t: ronic_tier["m"] for t in TIERS}            # settled flat form: M-tier RONIC on every tier
    cps_hkd = c_ex * MN / sh / fx * LAMBDA

    # --- Step 3: mid-cycle numerator (A4) -----------------------------------------
    eps_ttm = (inp["ni_fy25"] - inp["ni_h1_25"] + inp["ni_h1_26"]) * MN / sh
    mid_ratio = eps_ttm / eps["m"]
    if mid_ratio > MID_CYCLE_MAX:
        errors.append(f"中枢: TTM EPS {eps_ttm:.4f} / EPS_M {eps['m']:.4f} = {mid_ratio:.3f} > {MID_CYCLE_MAX} — "
                      f"the current print is above mid-cycle, M must move to the 中枢 (valuation-rules「周期票的中枢分子」)")
    h1_ann_ratio = 2.0 * inp["ni_h1_26"] * MN / sh / eps["m"]
    cycle_eps = [inp[f"eps_fy{y}"] for y in CYCLE_YEARS] + [inp["eps_fy25"]]
    cycle_prod = [inp[f"prod_fy{y}"] for y in CYCLE_YEARS] + [inp["prod_fy25"]]
    cycle_mean_raw = sum(cycle_eps) / len(cycle_eps)
    cycle_mean_norm = sum(e * inp["prod_2026_mid"] / p for e, p in zip(cycle_eps, cycle_prod)) / len(cycle_eps)
    cycle_dev = eps["m"] / cycle_mean_norm - 1.0
    if abs(cycle_dev) > CYCLE_MEAN_DEV_MAX:
        errors.append(f"中枢: axis-bridged EPS_M {eps['m']:.4f} deviates {cycle_dev:+.1%} from the production-normalised "
                      f"full-cycle mean {cycle_mean_norm:.4f} (> {CYCLE_MEAN_DEV_MAX:.0%}) — back to the conversation (A4)")

    # --- Step 4: ruler-form gate (A6) — Gordon reachable at the basket r ------------
    if 1.0 / r > inp["pe_op_max"] + 1e-9:
        errors.append(f"ruler form: 1/r = {1.0 / r:.2f}x > operating band top {inp['pe_op_max']} — retention-branch Gordon "
                      f"is BLOCKED again, DDM exception (a) holds; back to the conversation (A6)")
    if PAYOUT_FLOOR_QUOTE not in md:
        errors.append(f"framework does not quote the written payout floor ({PAYOUT_FLOOR_QUOTE!r}) — A7 needs it")
    if not (0.0 < pay <= 1.0):
        errors.append(f"payout_policy {pay} outside (0, 1]")
    payout_fy25 = inp["dps_fy25_cny"] * sh / (inp["ni_fy25"] * MN)
    if abs(payout_fy25 - pay) > 0.02:
        errors.append(f"FY2025 paid payout {payout_fy25:.1%} is more than 2pp from the policy floor {pay:.0%} — re-anchor (A7)")
    if errors:
        return report(errors, "FAIL (excess cash / 中枢 / ruler form)")

    # --- Step 5: growth 口径 — basket r, g cap, RONIC, constraint 2, branch ----------
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(g2, r, "g2")
    if r - g2 < MIN_R_MINUS_G:
        errors.append(f"g2 {g2:+.4f}: r-g < {MIN_R_MINUS_G} (裁决顺序 ①)")
    if not (inp["g_evid_min"] - 1e-9 <= g2 <= inp["g_evid_max"] + 1e-9):
        errors.append(f"g2 {g2} outside evidence interval [{inp['g_evid_min']}, {inp['g_evid_max']}] (A9)")
    d_paid = max(payout_fy25, inp["ret_d"])
    for t in TIERS:
        if ronic[t] - r < MONOTONIC_GAP - 1e-12:
            errors.append(f"{t.upper()}: RONIC {ronic[t]:.2%} not in the monotone zone (RONIC − r < {MONOTONIC_GAP:.0%}) — revisit the domain")
        g_ceiling = (1.0 - d_paid) * ronic[t]
        if g2 > g_ceiling + 1e-9:
            errors.append(f"{t.upper()}: g2 {g2:.2%} > (1 − d {d_paid:.1%}) × RONIC {ronic[t]:.2%} = {g_ceiling:.2%} (③ 约束 2)")
        if g2 / ronic[t] > 1.0 - d_paid + 1e-9:
            errors.append(f"{t.upper()}: b = g/RONIC {g2 / ronic[t]:.1%} > 1 − d {1.0 - d_paid:.1%} (③ 约束 1)")
    if all(inp[f"op_ret_fy{y}"] < r for y in (23, 24, 25)) and ronic["m"] > r:
        errors.append("持续失败: FY2023–25 operating returns all < r — RONIC must stay at the forward value, never above it")
    if abs(inp["payout_op"] - (inp["ret_d"] + inp["ret_c"])) > 0.0015:
        errors.append(f"payout_op {inp['payout_op']} != ret_d + ret_c {inp['ret_d'] + inp['ret_c']:.4f} (③ 经营口径派息率)")
    if payout_fy25 >= NEAR_FULL_PAYOUT and g2 > 0.0:
        errors.append(f"g2 {g2:+.2%} is the retention branch but the company pays out {payout_fy25:.0%} (反解分支)")
    for t in TIERS:
        errors += check_branch(g2, ronic[t], r, inp["payout_op"], f"g2 ({t.upper()}, 经营口径派息率)")
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

    # Guardrail: each generated operating multiple sits inside the realised operating band.
    pe = {t: perpetual_pe(g2, ronic[t], r) for t in TIERS}
    if not (pe["l"] >= pe["m"] - 1e-9 and pe["m"] >= pe["h"] - 1e-9):
        errors.append(f"multiple shape {pe['l']:.3f}/{pe['m']:.3f}/{pe['h']:.3f} is not reverse/flat (cyclical, 裁决顺序 ⑤)")
    for t in TIERS:
        if not (inp["pe_op_min"] - 1e-9 <= pe[t] <= inp["pe_op_max"] + 1e-9):
            errors.append(f"guardrail: {t.upper()} operating PE {pe[t]:.3f} outside realised operating band "
                          f"[{inp['pe_op_min']}, {inp['pe_op_max']}] — STOP (A9)")
    if errors:
        return report(errors, "FAIL (growth 口径)")

    # --- Step 6: anchors, ②-b ------------------------------------------------------
    def band(g: float = g2, rr: float = r) -> tuple[float, float, float]:
        return tuple(eps_op[t] * perpetual_pe(g, ronic[t], rr) / fx + cps_hkd for t in TIERS)  # type: ignore[return-value]

    L, M, H = band()
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}"])
    A, B = cut_points(L, M, H)

    cons_mean = inp["eps_cons_fy27_mean"]
    cons_dev = eps["m"] / cons_mean - 1.0
    if cons_mean > eps["h"]:
        errors.append(f"②-b: consensus FY27 mean {cons_mean} above EPS_H {eps['h']:.4f} — H must become the market-baseline world")
    if abs(cons_dev) > CONS_DEV_MAX:
        errors.append(f"②-b: M deviates {cons_dev:+.1%} from consensus FY27 mean (> {CONS_DEV_MAX:.0%}) — switch numerators to the consensus three points")
    if cons_mean < eps["m"] and "②-b" not in md:
        errors.append("②-b: consensus FY27 mean below EPS_M with no named-variable row in the framework (A5)")
    nib_cons = cons_mean * sh / MN / liq_2027
    brent_cons = (inp["real_fy25"] + (nib_cons - nib_fy25) / k) / rho

    # flat ladder (A2e-2c): all tiers at the M multiple, the numerator ladder must survive
    flat = tuple(eps_op[t] * pe["m"] / fx + cps_hkd for t in TIERS)
    errors += ladder("flat-multiple", *flat)

    if abs(inp["pe_op_med"] - pe["m"]) < 1e-9 or abs(inp["pe_same_med"] - pe["m"]) < 1e-9:
        errors.append("pe_op_med / pe_same_med leaked into the multiple path — they are comparison fields")
    leaked = [key for key in NOT_FORMULA if key not in inp]
    if leaked:
        errors.append(f"reference rows missing from Inputs: {leaked}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # --- Cross bands and disclosures (printed, never asserted) ---------------------
    ddm = tuple(pay * eps[t] / (r - g_d) / fx for t in TIERS)
    zero_g = tuple(eps_op[t] / r / fx + cps_hkd for t in TIERS)
    fallback = band(rr=basket_r(FALLBACK_BASKET))
    own_med = tuple(eps_op[t] * inp["pe_op_med"] / fx + cps_hkd for t in TIERS)
    same_med = tuple(eps_op[t] * inp["pe_same_med"] / fx + cps_hkd for t in TIERS)
    g_edge, well = implied_g_retaining(inp["pe_op_max"], ronic["m"], r)

    print(f"formula_id={FORMULA_ID}")
    print(f"弹性: NI/bbl FY25 {nib_fy25:.2f} → 2026H1 {nib_h1:.2f} RMB; k {k:.3f} RMB/bbl per US$1; ρ {rho:.4f}; liq_2027 {liq_2027:.1f} mmbbl")
    print(f"分子: Brent {brent['l']}/{brent['m']}/{brent['h']} → realised {real['l']:.2f}/{real['m']:.2f}/{real['h']:.2f} → "
          f"NI {ni['l']:,.0f}/{ni['m']:,.0f}/{ni['h']:,.0f} mn → EPS {eps['l']:.4f}/{eps['m']:.4f}/{eps['h']:.4f} CNY; "
          f"账面 ROE {roe['l']:.2%}/{roe['m']:.2%}/{roe['h']:.2%} (axis §3, 只披露)")
    print(f"超额现金 (A19): 扩展口径净现金 {inp['net_cash_ext_h1']:,.0f} − 已宣派未付末期 {inp['div_declared']:,.0f} − 已除息中期 {inp['div_exdiv']:,.0f} "
          f"− 锚 0 = C_ex {c_ex:,.0f} mn ({c_ex / inp['equity']:.1%} of equity ≥ {EXCESS_CASH_GATE:.0%}); 每股 {c_ex * MN / sh:.3f} CNY = {cps_hkd:.2f} HKD; λ {LAMBDA:g}; "
          f"税后收益 {c_inc:,.0f} mn (收益率 {inp['cash_yield']:.2%} × (1 − {inp['tax_eff']:.2%}))")
    print(f"经营口径: E_op {e_op['l']:,.0f}/{e_op['m']:,.0f}/{e_op['h']:,.0f} mn → EPS_op {eps_op['l']:.4f}/{eps_op['m']:.4f}/{eps_op['h']:.4f}; "
          f"经营股权 {op_eq:,.0f} (= equity − 中期 − C_ex); RONIC (三档统一用 M) {ronic['m']:.2%} "
          f"(RONIC−r {(ronic['m'] - r) * 100:+.2f}pp, 单调区); 按档经营回报 (只披露) "
          f"{'/'.join(f'{ronic_tier[t]:.2%}' for t in TIERS)}; 近 3 年经营回报 "
          f"{inp['op_ret_fy23']:.2%}/{inp['op_ret_fy24']:.2%}/{inp['op_ret_fy25']:.2%} (> r, 不触发持续失败)")
    print(f"中枢 (A4): TTM EPS {eps_ttm:.4f} / EPS_M = {mid_ratio:.3f} (≤ {MID_CYCLE_MAX} ✓); 2026H1 annualised / EPS_M = {h1_ann_ratio:.3f}; "
          f"cycle mean raw {cycle_mean_raw:.4f} / production-normalised {cycle_mean_norm:.4f} → M dev {cycle_dev:+.1%} (≤ {CYCLE_MEAN_DEV_MAX:.0%} ✓)")
    print(f"ruler form (A6): 1/r = {1.0 / r:.2f}x ≤ 经营带顶 {inp['pe_op_max']} → retention-branch Gordon reachable; "
          f"带顶反解 g (RONIC_M) {g_edge:+.2%} well_conditioned={well} (只打印)")
    b = {t: g2 / ronic[t] for t in TIERS}
    print(f"篮子: r_perp {r:.0%} = 篮 {baskets.get('r_perp')} (check_r ✓); g2 {g2:.2%} ≤ cap {g_cap(r):.2%} ✓; r−g2 {r - g2:.2%}; "
          f"b = g/RONIC {'/'.join(f'{b[t]:.1%}' for t in TIERS)} ≤ 1 − d {1.0 - d_paid:.1%} ✓; "
          f"约束 2 (1−d)×RONIC {'/'.join(f'{(1.0 - d_paid) * ronic[t]:.2%}' for t in TIERS)} ≥ g2 ✓; "
          f"check_branch vs 经营口径派息 {inp['payout_op']:.1%} ✓; DPS CAGR FY19→25 {dps_cagr:+.2%} (gate ✓)")
    print(f"留存三分 (FY2020–24): d {inp['ret_d']:.1%} / c {inp['ret_c']:.1%} / i {inp['ret_i']:.1%}; |i − b_M| "
          f"{abs(inp['ret_i'] - b['m']) * 100:.1f}pp (扩张期, 只披露)")
    excess = 1.0 - b["m"] - payout_fy25
    print(f"多留部分 (M): 1 − b {b['m']:.1%} − 实付 {payout_fy25:.1%} = {excess:.1%} × EPS_op_M {eps_op['m']:.4f} = "
          f"{excess * eps_op['m']:.3f} CNY = {excess * eps_op['m'] / fx:.2f} HKD/股/年 (落在超额现金, λ 1, PV 不进锚点)")
    print(f"倍数: PE_op = (1 − g/RONIC)/(r − g) = {pe['l']:.3f}/{pe['m']:.3f}/{pe['h']:.3f}x ∈ 经营带 [{inp['pe_op_min']}, {inp['pe_op_max']}] ✓ (guardrail A9)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"经营价值 {'/'.join(f'{eps_op[t] * pe[t] / fx:.2f}' for t in TIERS)} + 现金 {cps_hkd:.2f} HKD")
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.1%} | 经营分子比 L={e_op['l'] / e_op['m']:.3f} "
          f"H={e_op['h'] / e_op['m']:.3f} | 倍数比 L={pe['l'] / pe['m']:.3f} H={pe['h'] / pe['m']:.3f} "
          f"(flat, cyclical 裁决顺序 ⑤ ✓)")
    print(f"flat-multiple @PE_M={pe['m']:.2f} (= 三档同用 RONIC_M 的对照): {fmt_band(flat)}")
    print(f"同等盈利 (M 档经营 EPS ±12%, 36 月): 经营倍数中位 {inp['pe_same_med']}x vs 模型 PE_M {pe['m']:.2f}x "
          f"({pe['m'] / inp['pe_same_med'] - 1:+.1%}); 按中位给价 → {fmt_band(same_med)}")
    print(f"②-b: 共识 FY27 {inp['eps_cons_fy27_lo']}/{cons_mean}/{inp['eps_cons_fy27_hi']} vs EPS {eps['l']:.4f}/{eps['m']:.4f}/{eps['h']:.4f}; "
          f"均值 {'in [M,H]' if eps['m'] <= cons_mean <= eps['h'] else ('below M' if cons_mean < eps['m'] else 'above H')}, M dev {cons_dev:+.1%}, 均值 ↔ Brent {brent_cons:.1f}")
    for g in (g2 - 0.01, g2 + 0.01):
        pes = [perpetual_pe(g, ronic[t], r) for t in TIERS]
        in_band = all(inp["pe_op_min"] <= p <= inp["pe_op_max"] for p in pes)
        print(f"敏感性 g2 {g:+.2%} ⚠敏感区: PE {'/'.join(f'{p:.2f}' for p in pes)}x {'in band' if in_band else 'OUT of band (不可用)'} → {fmt_band(band(g=g))}")
    for r2 in (r - 0.005, r + 0.005):
        print(f"敏感性 r {r2:.1%}: {fmt_band(band(rr=r2))}")
    print(f"敏感性 篮 {FALLBACK_BASKET} r {basket_r(FALLBACK_BASKET):.0%}: {fmt_band(fallback)}; 篮 4 r 10%: {fmt_band(band(rr=basket_r(4)))}; "
          f"g=0 全派息 1/r {1.0 / r:.2f}x + 现金: {fmt_band(zero_g)}")
    print(f"敏感性 λ 0 (现金按 0): {fmt_band(tuple(x - cps_hkd for x in (L, M, H)))}; λ 0.5: {fmt_band(tuple(x - cps_hkd / 2 for x in (L, M, H)))}")
    print(f"每 US$1 Brent ≈ {liq_2027 * k * rho * MN / sh * pe['m'] / fx:+.2f} HKD (M 倍数); 2026H1 annualised NI {2 * inp['ni_h1_26']:,.0f} ↔ 本尺 Brent "
          f"{(inp['real_fy25'] + (2 * inp['ni_h1_26'] / liq_2027 - nib_fy25) / k) / rho:.1f}")
    print(f"对照带 (不入盘): DDM 45%×EPS/({r:.0%}−{g_d:.2%}) = {pay / (r - g_d):.2f}x → {fmt_band(ddm)}; "
          f"经营带中位 {inp['pe_op_med']}x + 现金 → {fmt_band(own_med)}; "
          f"capex {inp['capex_fy25']:,.0f} vs D&A {inp['da_fy25']:,.0f} → capex 超出 D&A {inp['capex_fy25'] - inp['da_fy25']:,.0f} = "
          f"{(inp['capex_fy25'] - inp['da_fy25']) / inp['ni_fy25']:.0%} of NI")
    bps = inp["equity"] * MN / sh
    tp = inp["tp_cons_h"]
    tp_pe_op = (tp * fx - c_ex * MN / sh) / eps_op["m"]
    tp_r = g2 + (1.0 - g2 / ronic["m"]) / tp_pe_op
    print(f"交叉尺: P/FCF 10x = {inp['fcf_fy25'] * MN / sh * 10 / fx:.2f} HKD; "
          f"BPS {bps:.2f} CNY = {bps / fx:.2f} HKD (地板只披露), PB at L/M/H {L * fx / bps:.2f}/{M * fx / bps:.2f}/{H * fx / bps:.2f}, "
          f"经营 PB (RONIC−g)/(r−g) {'/'.join(f'{justified_pb(g2, ronic[t], r):.2f}' for t in TIERS)}; "
          f"市值 L/M/H {L * sh / 1e8:,.0f}/{M * sh / 1e8:,.0f}/{H * sh / 1e8:,.0f} 亿 HKD")
    print(f"卖方: TP 均值 {tp} → 经营倍数 {tp_pe_op:.2f}x on M ↔ 同尺 r {tp_r:.1%} (A12; TP 落 {zone_of(tp, L, M, H)}); H/TP {H / tp:.2f} M/TP {M / tp:.2f}")
    g1 = (inp["eps_fy2022"] / inp["eps_fy2020"]) ** 0.5 - 1.0
    pe_rec = recovery_two_stage_pe(g1, 2, g2, ronic["m"], r)
    print(f"谷底坐标 (A3): 回归段 2020->2022 g1 {g1:.1%} n=2 -> {pe_rec:.1f}x on FY2020 EPS {inp['eps_fy2020']} = {inp['eps_fy2020'] * pe_rec / fx:.2f} HKD (坐标, 不作锚); "
          f"谷底 x 1/r = {inp['eps_fy2020'] / r / fx:.2f} HKD (deep_discount 压力坐标; 2020 年末无超额现金)")
    la, ma, ha = L * fx, M * fx, H * fx
    fa, fb = cut_points(la, ma, ha)
    print(f"A股对照(CNY): L={la:.2f} M={ma:.2f} H={ha:.2f} A={fa:.2f} B={fb:.2f}; 篮 6 对照 A 股 {fmt_band(tuple(x * fx for x in fallback))}")
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_perp 1:1 in the operating multiple; the Brent rungs, E_op, RONIC, g2 and the
    # excess cash stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        return band(rr=r + dr)

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    # Only a clean run feeds the daily digest.
    if not errors:
        write_rf_readings(TICKER, rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
