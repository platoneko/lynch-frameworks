#!/usr/bin/env python3
"""000338.SZ (Weichai Power) valuation eval — recompute anchors from frameworks/000338.SZ.md.

frameworks/000338.SZ.md is the source of truth; this script re-derives
L/M/H / A/B and V_opt from its §3 Inputs table and exits 1 on mismatch.  The
doc carries no current price (AGENTS.md「现价 — 禁写契约」), so nothing here
computes a zone or a market-implied reading.

formula_id: weichai_consensus_fy28_three_leg_gordon_v8

Main ruler (2026-10-04, user ruling): an asymmetric three-leg SOTP on the
FY2028 sell-side consensus, on the operating basis since the 2026-10-15
framework correction (valuation-rules「经营价值与超额现金」): the excess cash
(extended net cash − the declared interim dividend − the operating-cash
anchor) is added at face value (λ 1) to every tier, its after-tax income comes
out of the core leg's numerator, and the per-tier ROE (same roll as before)
loses the cash in both numerator and denominator (RONIC).  No peak guard.

  numerator  FY2028 company consensus (Eastmoney F10, 13 houses published
             after the 2026-08-27 interim report; CMBI taken at its 08-31
             update): M = mean, H = high.
             FY2028 = current FY2026 + 2 -> the consensus legs are discounted
             one year at the basket r (construction §3).  ②-b: the old
             run-rate ladder (TTM / Q2 x 4) fails both tests and is replaced.
  legs       * power leg (scope widened 2026-10-04 v7: large-bore diesel
               backup + gas gensets + SOFC; not turbines).  M = mean of the
               three houses that print an FY2028 revenue on this scope (CMBI
               08-31 large-bore 209.43 + AIDC gas gensets 160; 诚通 新兴业务 557;
               中国银河 AI 发电 20% of revenue, minutes) x the CMBI diesel-segment
               margin after tax (16.67%), cross-checked against the public
               power-energy profit share.  H = the house with the highest
               SOTP (长江, also the highest EPS): its own split from the team's
               flash note (2027 profit = 主业 110 + AIDC 110亿; 主业 carried flat
               to 2028), power NI = FY2028 NP - 主业.  g2 = power-generation peer
               cross-section reverse-solved on this ruler (CMI / Generac /
               Jereh; CAT and Wärtsilä exceed the cap and are dropped,
               Rolls-Royce mtu is inseparable) -> median 4.41%.
             * KION leg = run-rate equity NI (1H26 x 2 x 46.52%) x KGX.DE
               forward PE refreshed 2026-10-04 (7.98); today's market value,
               not discounted.
             * core = consensus - power leg - KION run-rate; g2 = 0: the
               same-world Chinese truck peers (Sinotruk A/H) price below 1/r
               and have no retention-branch solution; the US cluster's 4.74%
               is a different country and only a control.
  RONIC      company forward operating return (no leg equity is disclosed):
             FY2028 EPS less the excess-cash income over the start-of-2028
             operating BPS (book less the interim dividend less the excess
             cash, rolled with retention b = g/RONIC on operating EPS; only the
             power leg grows).  Per tier, as the existing framework did.
  L          FY2022 trough: core on recovery_two_stage_pe (own realised
             recovery to the TTM level, 3.5 years, then g2 = 0), the trough
             year less its own FY2022 excess-cash income, the TTM end less
             today's; KION halved; power leg at FY2025 actual units.  Not
             discounted (trough year = t=1).  Excess cash added as in M / H.
  ③          the own PE band is trailing and the FY2028 numerator was never
             printed (no same-earnings months) -> band test n/a, printed.
  中枢        demand-cycle core (trucks / engines): rule「周期票的中枢分子」does
             not apply (scope set 2026-10-04: commodity-price cyclicals only),
             so M stays on consensus; the FY2028 core vs the 5-year mean is
             disclosed with a 中枢 coordinate and a falsification trigger
             (trigger -> back to conversation, no automatic switch).
  gate       correction reconciliation gate printed and enforced.

2026-10-16 framework correction (valuation-rules「经营价值与超额现金」):
  * parent share of the excess cash 98.22%: KION's own extended net debt (net
    financial debt + the lease line) at the 46.52% stake, the rest at the
    ex-KION equity ratio (subsidiary-disclosure reading; equity-ratio 70.2% is
    a reference only).  Scales C_ex, its income and the operating book.
  * time alignment: core + power legs discounted tau = 1.5 years (2026-06-30
    -> 2028-01-01) instead of one whole year; plus the window distributable
    profit (2H26 + FY2027 unbooked operating EPS x (1 - b)) at tau / 2.
    KION (today's run-rate x today's PE) and L (trough from today) are n/a.
  * three-stage return on the power leg: forward RONIC through Y1 2028,
    linear to the steady return by Y2 2032 (medium entry barrier), then
    perpetual.  Steady = mature same-business peers' through-cycle median
    (Cummins 23.0% / Generac 24.1% / Caterpillar 40.3%, >= 5 years each) =
    24.1%; own cycle not on the same formula -> unused; floor 15%.
    Power g2 4.41% is not re-solved (A17).  No k on this ticker.

V_opt: AIDC capacity increment and SOFC are zero (their vesting year 2027 is
inside the consensus horizon; >=2 houses state that SOFC is in their
forecasts).  Only the M-series aftermarket stays: k=1 x own measured M-series
revenue x Cummins' realised aftermarket share x the power-leg margin, on the
power-leg multiple, vesting at the alignment year FY2028 + 2 = 2030 (无时点锚),
discounted to FY2028 and tau more years to today.

Run:  python3 frameworks/eval/000338.SZ.py
"""

from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_SOUTHBOUND  # noqa: E402
from lib.gordon import (  # noqa: E402
    check_branch, check_g_cap, check_r, g_cap, payout, payout_gap, recovery_two_stage_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "000338.SZ.md"
FORMULA_ID = "weichai_consensus_fy28_three_leg_gordon_v8"
YI = 1e8
NUM_YEAR = 2028
TODAY_FY = 2026
P_TIERS = (0.0, 0.0, 1.0)
TOL = 0.05
KION_SHARE_BAND = (0.08, 0.12)   # 属性 A, on the measured TTM numerator
B2_MAX_DEV = 0.20                # ②-b (ii)
MID_MAX = 1.15                   # 周期票中枢 threshold; disclosure only here (demand-cycle, rule n/a)
GATE_BAND = 0.20
MARGIN_XCHK = 0.25               # sell-side leg margin vs public cross-check

REQUIRED = [
    "shares", "bps", "dps_after_h1", "eps_h1", "fx_hkdcny", "fx_eurcny",
    "cons_fy26_m", "cons_fy26_h", "cons_fy27_m", "cons_fy27_h",
    "cons_fy28_l", "cons_fy28_m", "cons_fy28_h",
    "np_l", "np_ttm", "np_q2x4", "np_mid5", "n_rec_l",
    "kion_np_h1_eur", "kion_stake", "kion_l_factor", "pe_kion",
    "ms_units_l", "ms_units_m", "ms_price",
    "lb_rev_fy28", "pw_rev_cmbi", "pw_rev_ct", "pw_rev_yh", "cj_main", "seg_margin", "seg_tax", "power_np_share_h1", "power_rev_h1",
    "equity", "r_perp", "g2_core", "g2_core_us", "pe_sinotruk_a", "pe_sinotruk_h",
    "g2_pw_cmi", "g2_pw_gnrc", "g2_pw_jereh", "g2_power", "payout_obs", "tau",
    "parent_eq_h1", "minority_h1", "kion_nfd_eur", "lease_liab_h1", "kion_eq_eur", "parent_ratio",
    "y1_power", "y2_power", "ronic_ss_cmi", "ronic_ss_gnrc", "ronic_ss_cat", "ronic_ss_power", "ronic_ss_floor",
    "pe_own_min", "pe_own_max", "pe_ownyear_l", "pe_ownyear_m", "pe_ownyear_h", "pb_own_min",
    "aft_share_peer", "t_align", "t_aft",
    "net_cash_ext_h1", "div_declared", "ncx_min", "rev_min", "rev_fy25", "c_ex", "cash_yield", "tax_eff",
    "ncx_l", "rev_l", "cash_yield_l", "tax_eff_l", "cash_inc_mid5", "payout_op",
]
NOT_FORMULA = ("pe_ownyear_l", "pe_ownyear_m", "pe_ownyear_h", "g2_core_us", "lb_rev_fy28",
               "cons_fy28_l", "np_q2x4", "pb_own_min", "cash_inc_mid5")
PREV_M = 32.86                   # M before the 2026-10-16 correction, gate coordinate ①
EX_TRIGGER = 0.15                # C_ex >= 15% of parent equity -> own line
CASH_CAP = 2 / 12                # anchor ratio capped at two months of revenue
GATE_TRIGGER = 0.25              # gate is mandatory when |ΔM| > 25%
VAL_DATE = (2026, 6)             # balance-sheet date of the excess cash (month end)


def path_pe(g2: float, roe: float, r: float, t0: int, y1: int, y2: int, r_ss: float) -> float:
    """Three-stage retention Gordon (valuation-rules ② 稳态回报三段): RONIC = roe through calendar
    y1, linear to min(roe, r_ss) by y2, perpetual from y2 on.  Value at the start of year t0 per
    unit of year-t0 earnings; equals perpetual_pe when roe <= r_ss."""
    if r - g2 <= 0:
        raise ValueError("r <= g2")
    ss = min(roe, r_ss)
    pv, e, t = 0.0, 1.0, 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * payout(g2, ss) / ((r - g2) * (1 + r) ** (t - 1))
        ro = roe if cal <= y1 else roe + (ss - roe) * (cal - y1) / (y2 - y1)
        pv += e * payout(g2, ro) / (1 + r) ** t
        e *= 1 + g2
        t += 1


def stated_v_opt(md: str) -> float | None:
    sec = md[md.find("### Outputs"):]
    m = re.search(r"V_\{opt\}\\\)\s*=\s*\*\*([0-9.]+)\*\*", sec)
    return float(m.group(1)) if m else None


def check_southbound_mount(md: str) -> list[str]:
    if not AXIS_SOUTHBOUND.exists():
        return [f"axis file missing: {AXIS_SOUTHBOUND.name}"]
    errors: list[str] = []
    if "000338.SZ" not in AXIS_SOUTHBOUND.read_text(encoding="utf-8"):
        errors.append("000338.SZ is not declared on _AXIS.southbound-repricing.md")
    if "H 股对照带" not in md:
        errors.append("framework lacks the H-share companion band (axis §3 rule 3)")
    return errors


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    errors += check_southbound_mount(md)
    baskets = parse_baskets(md)
    r = inp["r_perp"]
    sh = inp["shares"]

    # --- basket, g ------------------------------------------------------------
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    for k in ("g2_core", "g2_power"):
        errors += check_g_cap(inp[k], r, k)
    if inp["g2_core"] != 0.0:
        errors.append("g2_core must be 0 (same-world Chinese truck peers have no retention-branch solution)")
    if not all(p < 1.0 / r for p in (inp["pe_sinotruk_a"], inp["pe_sinotruk_h"])):
        errors.append("a Sinotruk forward PE is now >= 1/r — the core g2 = 0 reading must be redone (A14)")
    peer_g = [inp["g2_pw_cmi"], inp["g2_pw_gnrc"], inp["g2_pw_jereh"]]
    if any(g > g_cap(r) for g in peer_g):
        errors.append("a power peer g exceeds g_cap — it must be dropped, not capped")
    g_pw = statistics.median(peer_g)
    if abs(g_pw - inp["g2_power"]) > 5e-5:
        errors.append(f"g2_power {inp['g2_power']} != peer median {g_pw:.5f}")
    tau = inp["tau"]
    tau_calc = ((NUM_YEAR - VAL_DATE[0]) * 12 - VAL_DATE[1]) / 12     # balance-sheet date -> start of FY2028
    if abs(tau - tau_calc) > 1e-9:
        errors.append(f"tau {tau:g} != months from {VAL_DATE[0]}-{VAL_DATE[1]:02d} to {NUM_YEAR}-01 / 12 = {tau_calc:g}")
    if not (inp["y1_power"] == NUM_YEAR and inp["y2_power"] == inp["y1_power"] + 4):
        errors.append("power leg Y1 must be the visible year 2028 and Y2 = Y1 + 4 (medium entry barrier)")
    peer_ss = [inp["ronic_ss_cmi"], inp["ronic_ss_gnrc"], inp["ronic_ss_cat"]]
    ss_want = max(statistics.median(peer_ss), inp["ronic_ss_floor"])
    if abs(inp["ronic_ss_power"] - ss_want) > 5e-4:
        errors.append(f"ronic_ss_power {inp['ronic_ss_power']} != max(mature-peer median, floor) {ss_want:.3f}")
    if inp["t_aft"] != inp["t_align"] + 2 or inp["t_align"] != NUM_YEAR:
        errors.append("t_align must be the numerator year and t_aft = t_align + 2 (无时点锚)")
    errors += ladder("FY2028 consensus", inp["cons_fy28_l"], inp["cons_fy28_m"], inp["cons_fy28_h"])
    if errors:
        return report(errors, "FAIL (basket / g)")

    # --- ②-b: the old run-rate ladder against the FY2028 mean -----------------
    eps_ttm, eps_q2 = inp["np_ttm"] / sh, inp["np_q2x4"] / sh
    mean28 = inp["cons_fy28_m"]
    b2_i = eps_ttm <= mean28 <= eps_q2
    b2_dev = eps_ttm / mean28 - 1
    if b2_i and abs(b2_dev) <= B2_MAX_DEV:
        errors.append("②-b passes — the run-rate ladder would be admissible; numerator choice must be revisited")

    # --- excess cash (经营价值与超额现金 ①②) ------------------------------------------
    if abs(inp["div_declared"] - inp["dps_after_h1"] * sh) > 1e6:
        errors.append("div_declared != dps_after_h1 x shares")
    rho = min(max(inp["ncx_min"] / inp["rev_min"], 0.0), CASH_CAP)   # lowest net-cash / revenue in FY2019–25
    anchor = rho * inp["rev_fy25"]
    c_ex_tot = inp["net_cash_ext_h1"] - inp["div_declared"] - anchor
    if abs(c_ex_tot - inp["c_ex"]) > 1e6:
        errors.append(f"c_ex {inp['c_ex']:.4e} != net_cash_ext_h1 − div_declared − anchor {c_ex_tot:.4e}")
    # parent share (① 归母份额), subsidiary-disclosure reading: KION's own extended net debt (its net
    # financial debt + the whole lease line, upper bound) at the 46.52% stake; the rest of the excess cash
    # at the ex-KION equity ratio.
    fx = inp["fx_eurcny"]
    kion_nc = -(inp["kion_nfd_eur"] * fx + inp["lease_liab_h1"])
    kion_eq = inp["kion_eq_eur"] * fx
    eq_par = inp["parent_eq_h1"] - inp["div_declared"]
    par_x = eq_par - inp["kion_stake"] * kion_eq
    min_x = inp["minority_h1"] - (1 - inp["kion_stake"]) * kion_eq
    pr = ((c_ex_tot - kion_nc) * par_x / (par_x + min_x) + kion_nc * inp["kion_stake"]) / c_ex_tot
    pr_eqm = eq_par / (eq_par + inp["minority_h1"])
    if abs(pr - inp["parent_ratio"]) > 5e-4:
        errors.append(f"parent_ratio {inp['parent_ratio']} != recomputed {pr:.4f}")
    c_ex = c_ex_tot * pr
    if c_ex < EX_TRIGGER * inp["equity"]:
        errors.append("parent-share c_ex below 15% of parent equity: the excess-cash line should not exist")
    c_inc = c_ex * inp["cash_yield"] * (1 - inp["tax_eff"])   # after-tax income, out of every forward numerator
    cps = c_ex / sh
    c_ex_l = max(inp["ncx_l"] - rho * inp["rev_l"], 0.0) * pr  # FY2022's own excess cash, parent share
    c_inc_l = c_ex_l * inp["cash_yield_l"] * (1 - inp["tax_eff_l"])
    r_ss = inp["ronic_ss_power"]

    def pp(g2: float, roe: float) -> float:
        return path_pe(g2, roe, r, NUM_YEAR, int(inp["y1_power"]), int(inp["y2_power"]), r_ss)

    # --- legs -------------------------------------------------------------------
    disc = (1 + r) ** tau
    disc_w = (1 + r) ** (tau / 2)                             # window profit sits mid-window
    npm = inp["seg_margin"] * (1 - inp["seg_tax"])
    pw_revs = [inp["pw_rev_cmbi"], inp["pw_rev_ct"], inp["pw_rev_yh"]]
    if len(pw_revs) < 2:
        errors.append("power leg needs >= 2 houses with a same-scope FY2028 revenue")
    errors += ladder("power-leg FY2028 revenue (3 houses)", min(pw_revs), statistics.mean(pw_revs), max(pw_revs))
    pw_rev_m = statistics.mean(pw_revs)
    pw_ni = {"m": pw_rev_m * npm, "h": inp["cons_fy28_h"] * inp["shares"] - inp["cj_main"]}
    if not pw_ni["h"] >= pw_ni["m"]:
        errors.append("H power NI (长江 split) below the M power NI")
    if inp["pw_rev_cmbi"] < inp["lb_rev_fy28"]:
        errors.append("CMBI power-scope revenue must include its large-bore line")
    pw_ni_l = inp["ms_units_l"] * inp["ms_price"] * npm
    npm_pub = inp["power_np_share_h1"] * inp["eps_h1"] * sh / inp["power_rev_h1"]
    if abs(npm / npm_pub - 1) > MARGIN_XCHK:
        errors.append(f"power-leg margin {npm:.1%} vs public cross-check {npm_pub:.1%} (> {MARGIN_XCHK:.0%})")
    kion = inp["kion_np_h1_eur"] * 2 * inp["kion_stake"] * inp["fx_eurcny"]
    kion_share = kion / inp["np_ttm"]
    lo, hi = KION_SHARE_BAND
    if not (lo <= kion_share <= hi):
        errors.append(f"KION run-rate is {kion_share:.1%} of TTM NP, outside {lo:.0%}-{hi:.0%} (属性 A)")

    obps0 = inp["bps"] - inp["dps_after_h1"] - cps   # operating book: less the interim dividend and the excess cash
    ci = c_inc / sh
    cons = {"m": (inp["cons_fy26_m"], inp["cons_fy27_m"], inp["cons_fy28_m"]),
            "h": (inp["cons_fy26_h"], inp["cons_fy27_h"], inp["cons_fy28_h"])}
    rows = {}
    for t, (e26, e27, e28) in cons.items():
        o26, o27, o28 = e26 - ci, e27 - ci, e28 - ci        # operating EPS (cash income out, all years)
        o_h1 = inp["eps_h1"] - ci / 2
        np28 = o28 * sh
        roe = o28 / obps0
        unb = (o26 - o_h1) + o27                             # unbooked operating EPS, 2H26 + FY2027
        for _ in range(300):  # operating BPS roll, b = g/RONIC; only the power leg funds growth
            b = inp["g2_power"] * (pw_ni[t] / np28) / roe
            bps28 = obps0 + b * unb
            roe = o28 / bps28
        b = inp["g2_power"] * (pw_ni[t] / np28) / roe
        pe_c = pp(inp["g2_core"], roe)
        pe_p = pp(inp["g2_power"], roe)
        core = np28 - kion - pw_ni[t]
        w = max(unb * (1 - b), 0.0) / disc_w                 # window distributable profit (③ 时点对齐)
        parts = (core * pe_c / disc / sh, kion * inp["pe_kion"] / sh, pw_ni[t] * pe_p / disc / sh, cps, w)
        rows[t] = dict(np=np28, roe=roe, bps=bps28, b=b, pe_c=pe_c, pe_p=pe_p, core=core, parts=parts,
                       anchor=sum(parts), win=unb, w=w)
        errors += check_branch(inp["g2_power"], roe, r, inp["payout_op"], f"g2_power ({t.upper()})")
        if roe - r < 0.03:
            errors.append(f"{t.upper()}: RONIC {roe:.1%} not in the monotone zone")
        if b > 1 - inp["payout_obs"]:
            errors.append(f"{t.upper()}: b {b:.1%} > 1 − d (约束 1)")
        if inp["g2_power"] > (1 - inp["payout_obs"]) * roe:
            errors.append(f"{t.upper()}: g2_power above (1 − d) x RONIC (约束 2)")

    np_ttm_op = inp["np_ttm"] - c_inc
    eq_op = inp["equity"] - inp["div_declared"] - c_ex
    np_l_op = inp["np_l"] - c_inc_l
    roe_mid = np_ttm_op / eq_op
    if np_l_op / eq_op >= r:
        errors.append("RONIC_L >= r: L is not a trough tier (valuation-rules「谷底档」)")
    g1 = (np_ttm_op / np_l_op) ** (1 / inp["n_rec_l"]) - 1
    pe_l = recovery_two_stage_pe(g1, inp["n_rec_l"], inp["g2_core"], roe_mid, r)
    pe_p_l = pp(inp["g2_power"], roe_mid)
    kion_l = kion * inp["kion_l_factor"]
    core_l = np_l_op - kion_l - pw_ni_l
    if core_l <= 0:
        errors.append("L core profit <= 0")
    parts_l = (core_l * pe_l / sh, kion_l * inp["pe_kion"] / sh, pw_ni_l * pe_p_l / sh, cps)
    L = sum(parts_l)
    M, H = rows["m"]["anchor"], rows["h"]["anchor"]
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.3f} {M:.3f} {H:.3f}"])
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # shape (裁决顺序 ⑤): the cyclical core leg must be reverse or flat
    if not (pe_l > rows["m"]["pe_c"] and abs(rows["h"]["pe_c"] - rows["m"]["pe_c"]) < 1e-9):
        errors.append("core multiple shape is not reverse/flat (cyclical, 裁决顺序 ⑤)")
    # flat-multiple ladder: every tier on the M-tier multiples
    flat_l = (core_l * rows["m"]["pe_c"] + kion_l * inp["pe_kion"] + pw_ni_l * rows["m"]["pe_p"]) / sh + cps
    flat = [flat_l] + [(rows[t]["core"] * rows["m"]["pe_c"] / disc + kion * inp["pe_kion"]
                        + pw_ni[t] * rows["m"]["pe_p"] / disc) / sh + cps + rows[t]["w"] for t in ("m", "h")]
    errors += ladder("flat-multiple", *flat)

    # --- V_opt: aftermarket only ------------------------------------------------
    rev_ms = inp["ms_units_m"] * inp["ms_price"]
    v_aft_t = rev_ms * inp["aft_share_peer"] * npm * rows["m"]["pe_p"] / sh
    v_opt = v_aft_t / (1 + r) ** (inp["t_aft"] - NUM_YEAR) / disc   # to FY2028, then tau to today
    said = stated_v_opt(md)
    if said is None or abs(said - v_opt) > TOL:
        errors.append(f"V_opt stated {said} vs recomputed {v_opt:.4f}")
    if [k for k in inp if k == "p" or k.startswith("p_")]:
        errors.append("p-class fields must not appear in Inputs")
    adj = [a + p * v_opt for a, p in zip((L, M, H), P_TIERS)]
    A2, B2 = cut_points(*adj)

    # --- ③ band test: n/a without same-earnings months --------------------------
    same_eps_months = 0 if np_ttm_op / sh < 0.88 * (mean28 - ci) else None   # operating basis; TTM = all-time high
    if same_eps_months is None:
        errors.append("TTM EPS is now within 12% of the FY2028 numerator — run the ③ band test")

    # --- 周期票中枢 check on the core leg ---------------------------------------
    core_mid = inp["np_mid5"] - inp["cash_inc_mid5"] - kion - pw_ni_l   # each year less its own C_ex(t) income
    mid_ratio = rows["m"]["core"] / core_mid
    m_mid = (core_mid * rows["m"]["pe_c"] + kion * inp["pe_kion"]) / sh + rows["m"]["parts"][2] + cps + rows["m"]["w"]

    # --- correction reconciliation gate ------------------------------------------
    e_m = mean28
    coords = {
        "① 上一版 M": PREV_M,
        "② E_op,M/r + c": (e_m - ci) / r / disc + cps,
        "③ D_M/(r-g)": inp["payout_obs"] * e_m / (r - inp["g2_core"]) / disc,
        "⑥ BPS x PB低点": inp["bps"] * inp["pb_own_min"],
    }
    inside = [k for k, v in coords.items() if not k.startswith("①") and abs(M / v - 1) <= GATE_BAND]
    gate_on = abs(M / PREV_M - 1) > GATE_TRIGGER
    if gate_on and not inside:
        errors.append("correction gate: new M is >20% away from every independent coordinate — BLOCKED")
    missing_ref = [k for k in NOT_FORMULA if k not in inp]
    if missing_ref:
        errors.append(f"reference rows missing: {missing_ref}")

    # --- report -------------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"basket: r_perp 篮 {baskets['r_perp']} r={r:g}; FY{NUM_YEAR} consensus legs ÷{disc:.2f}; "
          f"g2 core {inp['g2_core']:g} (Sinotruk A/H fPE {inp['pe_sinotruk_a']}/{inp['pe_sinotruk_h']} < 1/r; "
          f"US cluster {inp['g2_core_us']:.2%} control only); g2 power median({', '.join(f'{g:.2%}' for g in peer_g)}) = {g_pw:.2%}")
    print(f"②-b: FY28 mean {mean28} in [TTM {eps_ttm:.3f}, Q2x4 {eps_q2:.3f}]? {b2_i}; TTM dev {b2_dev:+.1%} -> consensus three points")
    print(f"power leg revenue FY2028 (大缸径+气发+SOFC): CMBI 08-31 {inp['pw_rev_cmbi'] / YI:.2f} (大缸径 {inp['lb_rev_fy28'] / YI:.2f} + 气发) | "
          f"诚通 {inp['pw_rev_ct'] / YI:.2f} | 银河 {inp['pw_rev_yh'] / YI:.2f} (纪要) -> L/M/H {min(pw_revs) / YI:.1f}/{pw_rev_m / YI:.1f}/{max(pw_revs) / YI:.1f}亿")
    print(f"power margin {inp['seg_margin']:.1%}x(1-{inp['seg_tax']:.1%}) = {npm:.2%}; public cross {inp['power_np_share_h1']:.0%} x 1H NP / "
          f"{inp['power_rev_h1'] / YI:.1f}亿 = {npm_pub:.1%} | NI M {pw_ni['m'] / YI:.2f}亿; H (长江 NP28 {inp['cons_fy28_h'] * sh / YI:.2f} - 主业 "
          f"{inp['cj_main'] / YI:.0f}) {pw_ni['h'] / YI:.2f}亿 = {pw_ni['h'] / (inp['cons_fy28_h'] * sh):.0%} of NP; 3-house top x margin "
          f"{max(pw_revs) * npm / YI:.1f}亿; L = FY2025 {inp['ms_units_l']:.0f} units -> {pw_ni_l / YI:.2f}亿")
    print(f"KION run-rate {kion / YI:.2f}亿 = {kion_share:.1%} of TTM NP; pe_kion {inp['pe_kion']}")
    print(f"超额现金: 扩展口径净现金 {inp['net_cash_ext_h1'] / YI:.2f}亿 − 已宣派未付中期股息 {inp['div_declared'] / YI:.2f}亿 "
          f"− 锚 {anchor / YI:.2f}亿（FY2019 净现金/收入 {rho:.2%} x FY2025 收入 {inp['rev_fy25'] / YI:.1f}亿；2 个月上限 {CASH_CAP:.1%}）"
          f"= C_ex {c_ex_tot / YI:.2f}亿 × 归母比例 {pr:.4f}（凯傲那块 {kion_nc / YI:.1f}亿 × {inp['kion_stake']:.2%}，"
          f"其余 × 剔凯傲权益比 {par_x / (par_x + min_x):.4f}；权益法参照 {pr_eqm:.4f}）= {c_ex / YI:.2f}亿"
          f"（每股 {cps:.3f}，占归母权益 {c_ex / inp['equity']:.1%}，λ 1）；"
          f"税后收益 {c_ex / YI:.1f} x {inp['cash_yield']:.2%} x (1−{inp['tax_eff']:.2%}) = {c_inc / YI:.2f}亿 从核心盘分子扣除；"
          f"L 档 FY2022 自身 C_ex {c_ex_l / YI:.1f}亿 → {c_inc_l / YI:.2f}亿")
    for t in ("m", "h"):
        x = rows[t]
        print(f"{t.upper()}: 经营NP {x['np'] / YI:.1f} core {x['core'] / YI:.1f} | 经营BPS28 {x['bps']:.3f} RONIC {x['roe']:.2%} b {x['b']:.1%} | "
              f"PE core {x['pe_c']:.2f} power {x['pe_p']:.2f}（三段 Y1 {inp['y1_power']:g}/Y2 {inp['y2_power']:g}，稳态 {r_ss:.1%}）| "
              f"per share core {x['parts'][0]:.2f} + KION {x['parts'][1]:.2f} + power {x['parts'][2]:.2f} + 现金 {cps:.2f} "
              f"+ 窗口 {x['win']:.3f}x(1−{x['b']:.1%})÷1.1^{tau / 2:g} {x['w']:.2f} = {x['anchor']:.2f}")
    print(f"L: trough 经营 {np_l_op / YI:.2f}亿 core {core_l / YI:.2f} x recovery PE {pe_l:.2f} (g1 {g1:+.2%} n {inp['n_rec_l']:g}, "
          f"段二 RONIC {roe_mid:.1%} = TTM 经营 {np_ttm_op / YI:.1f} / 经营股权 {eq_op / YI:.1f}, g2 0) + KION {kion_l / YI:.2f}x{inp['pe_kion']} "
          f"+ power {pw_ni_l / YI:.2f}x{pe_p_l:.2f} -> {parts_l[0]:.2f} + {parts_l[1]:.2f} + {parts_l[2]:.2f} + 现金 {cps:.2f} = {L:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%} V_opt/M={v_opt / M:.1%} | "
          f"经营分子比 L/M {np_l_op / rows['m']['np']:.2f} H/M {rows['h']['np'] / rows['m']['np']:.2f}")
    print(f"flat-multiple (M-tier multiples): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(f"V_opt = aftermarket {rev_ms / YI:.2f}亿 x {inp['aft_share_peer']:.0%} x {npm:.2%} x PE {rows['m']['pe_p']:.2f} "
          f"@{inp['t_aft']:g} ÷1.1^{inp['t_aft'] - NUM_YEAR + tau:g} = {v_opt:.2f} (AIDC increment 0, SOFC 0: inside consensus)")
    print("表3 " + " / ".join(f"{n} {b:.2f}+{p:g}x{v_opt:.2f}={a:.2f}" for n, b, p, a in zip("LMH", (L, M, H), P_TIERS, adj))
          + f"  A'={A2:.2f} B'={B2:.2f}")
    print(f"③ band test n/a: TTM 经营 EPS {np_ttm_op / sh:.4f} (all-time high) < 0.88 x FY28 经营 {mean28 - ci:.4f} — no same-earnings months; "
          f"L trough-basis PE {pe_l:.2f} vs own monthly band [{inp['pe_own_min']}, {inp['pe_own_max']}] (L disclosed only)")
    print(f"周期中枢: core FY28 M {rows['m']['core'] / YI:.1f}亿 vs core 中枢 {core_mid / YI:.1f}亿 "
          f"(5y mean {inp['np_mid5'] / YI:.1f} - own C_ex(t) income {inp['cash_inc_mid5'] / YI:.2f} - KION - power FY25) = {mid_ratio:.2f}x "
          f"({'> 1.15: demand-cycle, 中枢 rule n/a (2026-10-04), disclosed + trigger' if mid_ratio > MID_MAX else 'ok'}); M coordinate with core at 中枢 {m_mid:.2f} (disclosure only)")
    print(f"gate ({'triggered' if gate_on else 'not triggered: |dM| <= 25%, printed for the record'}): M {PREV_M} -> " + f"{M:.2f} ({M / PREV_M - 1:+.0%}); "
          + "; ".join(f"{k} {v:.2f} (M {M / v - 1:+.0%})" for k, v in coords.items())
          + f"; ④ same-earnings months none; ⑤ n/a -> "
          + ('PASS (' + ', '.join(inside) + ')' if inside else ('BLOCKED' if gate_on else 'no coordinate within 20% (gate not triggered, record only)')))
    print(f"gate neutral [{A:.2f}, {B:.2f}) as PE: TTM {eps_ttm:.3f} {A / eps_ttm:.1f}-{B / eps_ttm:.1f}x; "
          f"FY26E {inp['cons_fy26_m']} {A / inp['cons_fy26_m']:.1f}-{B / inp['cons_fy26_m']:.1f}x; "
          f"FY28E {mean28} {A / mean28:.1f}-{B / mean28:.1f}x")
    mod, gap = payout_gap(rows["m"]["b"] * rows["m"]["roe"], rows["m"]["roe"], inp["payout_op"])
    excess = (1 - rows["m"]["b"]) - inp["payout_obs"]
    win = rows["m"]["win"]
    print(f"payout: model {mod:.1%} vs 经营口径 {inp['payout_op']:.1%} (gap {gap:+.1%}); 实付 {inp['payout_obs']:.0%}; "
          f"多留部分 = {excess:.1%} x 窗口经营 EPS {win:.3f} = {excess * win:.2f}/sh（落在超额现金，λ 1，PV 不进锚点）")
    print(f"归母比例参照（只披露）: 主读法子公司披露 {pr:.4f}；权益法 {pr_eqm:.4f}（凯傲按市值单列、其现金是净债务，权益法会把凯傲少数股东的权益当成现金份额，不用）")

    def band_at(g_pw: float | None = None, g_core: float | None = None, kion_pe: float | None = None,
                rs: float | None = None):
        gp = inp["g2_power"] if g_pw is None else g_pw
        gc = inp["g2_core"] if g_core is None else g_core
        kp = inp["pe_kion"] if kion_pe is None else kion_pe
        rss = r_ss if rs is None else rs
        y1, y2 = int(inp["y1_power"]), int(inp["y2_power"])
        out = []
        for t in ("m", "h"):
            x = rows[t]
            out.append((x["core"] * path_pe(gc, x["roe"], r, NUM_YEAR, y1, y2, rss) / disc + kion * kp
                        + pw_ni[t] * path_pe(gp, x["roe"], r, NUM_YEAR, y1, y2, rss) / disc) / sh + cps + x["w"])
        ll = (core_l * recovery_two_stage_pe(g1, inp["n_rec_l"], gc, roe_mid, r) + kion_l * kp
              + pw_ni_l * path_pe(gp, roe_mid, r, NUM_YEAR, y1, y2, rss)) / sh + cps
        return "/".join(f"{v:.2f}" for v in [ll] + out)

    print(f"敏感性: g2_power {inp['g2_pw_cmi']:.2%} {band_at(g_pw=inp['g2_pw_cmi'])} | {inp['g2_pw_gnrc']:.2%} {band_at(g_pw=inp['g2_pw_gnrc'])} "
          f"| power ±1pp {band_at(g_pw=inp['g2_power'] - 0.01)} / {band_at(g_pw=inp['g2_power'] + 0.01)} "
          f"| core +1pp {band_at(g_core=0.01)} | core = US 4.74% {band_at(g_core=inp['g2_core_us'])} | pe_kion 9.97 {band_at(kion_pe=9.97)} "
          f"| 稳态 兜底 {inp['ronic_ss_floor']:.0%} {band_at(rs=inp['ronic_ss_floor'])} / 不回落 {band_at(rs=1.0)}")
    own = [(core_l * inp["pe_ownyear_l"] + kion_l * inp["pe_kion"] + pw_ni_l * pe_p_l) / sh + cps] + [
        (rows[t]["core"] * inp[f"pe_ownyear_{t}"] / disc + kion * inp["pe_kion"] + pw_ni[t] * rows[t]["pe_p"] / disc) / sh
        + cps + rows[t]["w"] for t in ("m", "h")]
    print(f"交叉尺 own-year 经营倍数反向带 {inp['pe_ownyear_l']}/{inp['pe_ownyear_m']}/{inp['pe_ownyear_h']} on core: "
          + "/".join(f"{v:.2f}" for v in own))
    core_lo = inp['cons_fy28_l'] * sh - c_inc - kion - pw_ni['m']
    print(f"FY2028 共识下沿 {inp['cons_fy28_l']} 作 M 分子 -> core {core_lo / YI:.1f}亿 -> M "
          f"{(core_lo * rows['m']['pe_c'] / disc + kion * inp['pe_kion'] + pw_ni['m'] * rows['m']['pe_p'] / disc) / sh + cps + rows['m']['w']:.2f}")

    def m_with_pw(ni_pw: float, t: str = "m") -> float:
        x = rows[t]
        return ((x["np"] - kion - ni_pw) * x["pe_c"] / disc + kion * inp["pe_kion"] + ni_pw * x["pe_p"] / disc) / sh + cps + x["w"]
    rep2 = statistics.mean(pw_revs[:2]) * npm
    print(f"电力腿口径敏感性: M 只认报告表两家 (招银+诚通) {m_with_pw(rep2):.2f} | M 电力取三家下沿 {m_with_pw(min(pw_revs) * npm):.2f} "
          f"/ 上沿 {m_with_pw(max(pw_revs) * npm):.2f} | M 电力回 v6 招银大缸径 {m_with_pw(inp['lb_rev_fy28'] * npm):.2f} | "
          f"H 长江主业 2028 +5% {m_with_pw(pw_ni['h'] - 0.05 * inp['cj_main'], 'h'):.2f} | H 电力改三家上沿 {m_with_pw(max(pw_revs) * npm, 'h'):.2f}")
    print(f"压力坐标 谷底经营利润 x 1/r + 现金 = {np_l_op / sh / r + cps:.2f}; 地板 PB 1.0 x BPS = {inp['bps']:.2f}")
    fx = inp["fx_hkdcny"]
    print(f"H股对照(HKD): L={L / fx:.2f} M={M / fx:.2f} H={H / fx:.2f} A={A / fx:.2f} B={B / fx:.2f}")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
