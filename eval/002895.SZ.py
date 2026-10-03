#!/usr/bin/env python3
"""002895.SZ (Chuanheng) valuation eval.

frameworks/002895.SZ.md is the source of truth; this script re-derives
L/M/H / A/B and V_opt from its §3 Inputs table and exits 1 on mismatch.  The
doc states no current price or zone (the digest and the app zone on live
quotes).

formula_id: chuanheng_consensus_fy28_gordon_mines_opt_v4

Main ruler (2026-10-03 migration off the flat 15.34x own-median multiple):

  numerator  FY2028 sell-side consensus — the farthest year with >=2 houses
             and a low/mean/high range (6 post-interim houses, Eastmoney
             2026-10-03): M = mean, H = high.  L = FY2025 actual net profit on
             today's share count — the year the axis L rung (MAP 3,330) was
             actually printed, held flat ("growth stops, phosphate back to the
             2025 regime"; cyclical L uses own measured years, valuation-rules
             data-priority table).  FY2028 = current FY2026 + 2, so every tier
             is discounted one year at the basket r (construction §3).
  multiple   Gordon (1 - g/ROE)/(r - g), r = basket 6 (13%, commodity: 82%
             of revenue is market-priced phosphates and rock).  A same-day
             demotion to basket 4 (10%) was withdrawn under ③ step 1c -- its
             evidence compared the base without the options against a band
             that already priced them; the 10% band is printed as a control
             band only.  g = axis
             _AXIS.phosphate-chain perpetual g2 1.5% on all tiers; ROE = FY2028
             EPS / start-of-FY2028 BPS, BPS rolled from the 2026-06-30 book with
             retention b = g/ROE (iterated) — valuation-rules ③ step 2.
  ②-b       the old bottom-up MAP ladder (M 2.1669 / H 3.1551) is tested
             mechanically against the FY2028 consensus mean and fails both
             legs, which is why the consensus three points replace it.
  ③         the own PE band is trailing; the numerator is FY2028 and has no
             same-earnings weeks (TTM EPS never within ±12% of 3.58), so the
             band test does not apply (③ step 1) — printed, not enforced.
  ③ 1c      the band that drove the withdrawn demotion (L-tier same-earnings
             weeks, TTM EPS ~ FY2025) was printed while the three mines were
             already announced, so base + V_opt (p = 1, only mines announced
             before the window opened) is compared with it; back in band ->
             ③ is not triggered and the basket stays at 6.  Fails otherwise.

V_opt: three named phosphate mines under construction, quantity = named
capacity x look-through stake at full output, unit economics = this company's
own disclosed numbers read at full utilisation (2026H1 external ore price;
Fulin mining subsidiary all-in cost ex resource tax, its mines already running
above nameplate; resource tax 7.5%; 25% steady-state income tax), valued with
this ticker's own M-tier multiple in the first full year, less the stake's
share of capital not yet spent (Laohudong: the project loan), discounted to
today at the basket r.  Sensitivities include the ore price back at its cycle
centre (own 5-year average external realised price) and the FY2025 full-year
unit cost.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_PHOS, check_axis_g2_mount, check_phosphate_mount  # noqa: E402
from lib.gordon import BASKET_R, check_g_cap, check_r, payout_gap, perpetual_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "002895.SZ.md"
PEER = Path(__file__).resolve().parents[2] / "frameworks" / "600096.SH.md"
FORMULA_ID = "chuanheng_consensus_fy28_gordon_mines_opt_v4"
YI = 1e8
NUM_YEAR = 2028          # numerator year (FY2028 consensus)
TODAY_FY = 2026          # current fiscal year; FY2028 = +2 -> discount one year
P_TIERS = (0.0, 0.25, 1.0)  # table 3; p_M 无概率锚·拍值 (A9)
TOL = 0.05
B2_MAX_DEV = 0.20        # valuation-rules ②-b (ii)
SAME_EPS_MIN = 6         # ③ step 1: same-earnings months needed for a band test
MAIN_BASKET = 6          # 篮 6 周期商品 (A14)
R_CTL_BASKET = 4         # withdrawn same-day demotion (A14); control band only
GATE_BAND = 0.20         # correction reconciliation gate: within ±20% of a coordinate

REQUIRED = [
    "shares", "bps_h1", "dps_after_h1", "eps_h1", "np_fy25",
    "cons_fy26_m", "cons_fy26_h", "cons_fy27_m", "cons_fy27_h",
    "cons_fy28_l", "cons_fy28_m", "cons_fy28_h",
    "ladder_eps_m", "ladder_eps_h",
    "r_perp", "r_ctl", "g2_l", "g2_m", "g2_h", "disc_years", "payout_obs",
    "ttm_eps", "pe_own_min", "pe_own_med", "pe_own_p75", "same_eps_weeks_m",
    "pe_same_min_l", "pe_same_max_l", "band_l_start", "band_own_low", "pb_own_min",
    "map_l", "map_m", "map_h",
    "opt_price", "opt_cost", "opt_restax", "opt_tax", "opt_price_mid5", "opt_cost_fy25",
    "lhd_cap", "lhd_eq", "lhd_k", "lhd_t", "lhd_pub",
    "lzz_cap", "lzz_eq", "lzz_k", "lzz_t", "lzz_pub",
    "jgl_cap", "jgl_eq", "jgl_k", "jgl_t", "jgl_pub",
]


def stated_v_opt(sec: str) -> float | None:
    m = re.search(r"V_\{opt\}\\\)\s*=\s*\*\*([0-9.]+)\*\*", sec)
    return float(m.group(1)) if m else None


def stated_p_tiers(sec: str) -> tuple[float, float, float] | None:
    m = re.search(
        r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*[≈=]\s*\*{0,2}\s*"
        r"([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)",
        sec,
    )
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    # --- axis, basket, g -----------------------------------------------------
    errors += ladder("MAP", inp["map_l"], inp["map_m"], inp["map_h"])
    errors += check_phosphate_mount(
        (inp["map_l"], inp["map_m"], inp["map_h"]), peer_md=PEER.read_text(encoding="utf-8"),
    )
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell must name the basket (篮 N)")
    r = inp["r_perp"]
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    if baskets.get("r_perp") != MAIN_BASKET:
        errors.append(f"r_perp: basket is 篮 {MAIN_BASKET} (A14; got 篮 {baskets.get('r_perp')})")
    # The withdrawn demotion is a control band, not a basket declaration
    # (contracts.md「篮子声明」: disclosure-only r rows carry no `篮 N`).
    if "r_ctl" in baskets:
        errors.append("r_ctl: control-band row must not name a basket (篮 N)")
    r_ctl = inp["r_ctl"]
    if abs(r_ctl - BASKET_R[R_CTL_BASKET][1]) > 1e-12:
        errors.append(f"r_ctl {r_ctl:g} != 篮 {R_CTL_BASKET} {BASKET_R[R_CTL_BASKET][1]:g}")
    errors += check_axis_g2_mount(AXIS_PHOS, inp["g2_m"])
    for k in ("g2_l", "g2_m", "g2_h"):
        errors += check_g_cap(inp[k], r, k)
    if not (inp["g2_l"] == inp["g2_m"] == inp["g2_h"]):
        errors.append("g2 must be flat across tiers (axis row, A14)")
    if int(inp["disc_years"]) != NUM_YEAR - TODAY_FY - 1:
        errors.append(f"disc_years {inp['disc_years']:g} != FY{NUM_YEAR} - (FY{TODAY_FY}+1)")
    errors += ladder("FY2028 consensus", inp["cons_fy28_l"], inp["cons_fy28_m"], inp["cons_fy28_h"])
    if errors:
        return report(errors)

    shares_yi = inp["shares"] / YI
    eps_l = inp["np_fy25"] / shares_yi
    if not (eps_l < inp["cons_fy28_l"]):
        errors.append(f"L (FY2025 actual {eps_l:.4f}) must sit below the consensus low {inp['cons_fy28_l']}")

    # --- ②-b: does the old bottom-up ladder survive? --------------------------
    mean28 = inp["cons_fy28_m"]
    b2_i = inp["ladder_eps_m"] <= mean28 <= inp["ladder_eps_h"]
    b2_dev = inp["ladder_eps_m"] / mean28 - 1
    b2_ii = abs(b2_dev) <= B2_MAX_DEV
    if b2_i and b2_ii:
        errors.append("②-b passes — the MAP ladder would be admissible; numerator choice must be revisited")

    # --- the ruler (r is a parameter so the withdrawn 篮 4 control band uses the same code)
    bps0 = inp["bps_h1"] - inp["dps_after_h1"]
    tiers = {
        "L": (eps_l, eps_l, eps_l, inp["g2_l"]),
        "M": (inp["cons_fy28_m"], inp["cons_fy26_m"], inp["cons_fy27_m"], inp["g2_m"]),
        "H": (inp["cons_fy28_h"], inp["cons_fy26_h"], inp["cons_fy27_h"], inp["g2_h"]),
    }

    def ruler(rr: float, g=None, l_eps=None) -> dict[str, dict[str, float]]:
        out = {}
        for t, (e28, e26, e27, g0) in tiers.items():
            if t == "L" and l_eps is not None:
                e28 = e26 = e27 = l_eps
            gg = g0 if g is None else g
            roe = e28 / bps0
            for _ in range(100):  # BPS roll with b = g/ROE (valuation-rules ③ step 2)
                bps = bps0 + (gg / roe) * ((e26 - inp["eps_h1"]) + e27)
                roe = e28 / bps
            pe = perpetual_pe(gg, roe, rr)
            out[t] = dict(eps=e28, bps=bps, roe=roe, pe=pe, anchor=e28 * pe / (1 + rr) ** inp["disc_years"])
        return out

    def fmt(rs: dict[str, dict[str, float]]) -> str:
        return "/".join(f"{rs[t]['anchor']:.2f}" for t in "LMH")

    disc = (1 + r) ** inp["disc_years"]
    rows = ruler(r)
    L, M, H = (rows[t]["anchor"] for t in "LMH")
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}"])
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # --- V_opt: three named mines --------------------------------------------
    nit = (inp["opt_price"] * (1 - inp["opt_restax"]) - inp["opt_cost"]) * (1 - inp["opt_tax"])
    mine_keys = (("lhd", "老虎洞"), ("lzz", "老寨子"), ("jgl", "鸡公岭"))
    for key, name in mine_keys:
        if inp[f"{key}_t"] <= NUM_YEAR:
            errors.append(f"{name}: realisation year {inp[f'{key}_t']:g} must be after FY{NUM_YEAR} (consensus holds no output)")

    def vopt(nit_x: float, rr: float, keys=None) -> tuple[float, list]:
        """Equity tons x NI/t x this ticker's M-tier multiple at rr, less unspent capital,
        discounted at rr from the realisation year to FY2028 and one more year to today."""
        pe_x = ruler(rr)["M"]["pe"]
        tot, detail = 0.0, []
        for key, name in mine_keys:
            if keys is not None and key not in keys:
                continue
            t = inp[f"{key}_t"]
            tons = inp[f"{key}_cap"] * inp[f"{key}_eq"]          # 万吨/年, equity
            dni = tons * nit_x / 1e4                              # 亿
            k_eq = inp[f"{key}_k"] * inp[f"{key}_eq"]            # 亿
            val_t = dni * pe_x - k_eq
            pv = val_t / (1 + rr) ** (t - NUM_YEAR) / (1 + rr) ** inp["disc_years"]
            tot += pv
            detail.append((name, tons, dni, k_eq, val_t, t, pv))
        return tot / shares_yi, detail

    pe_opt = rows["M"]["pe"]
    v_opt, mines = vopt(nit, r)
    sec = md[md.find("### Outputs"):]
    said_v = stated_v_opt(sec)
    if said_v is None or abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    if stated_p_tiers(sec) != P_TIERS:
        errors.append(f"p_L/p_M/p_H stated {stated_p_tiers(sec)} vs {P_TIERS}")
    if [k for k in inp if k.startswith("p_")]:
        errors.append("Inputs carry probability fields — p_k belongs in table 3 only")
    opt = tuple(a + p * v_opt for a, p in zip((L, M, H), P_TIERS))
    A_v, B_v = cut_points(*opt)

    def nit_at(price: float, cost: float | None = None, tax: float | None = None) -> float:
        cost = inp["opt_cost"] if cost is None else cost
        tax = inp["opt_tax"] if tax is None else tax
        return (price * (1 - inp["opt_restax"]) - cost) * (1 - tax)

    # --- report --------------------------------------------------------------
    b = baskets["r_perp"]
    print(f"formula_id={FORMULA_ID}")
    print(f"axis OK: MAP {inp['map_l']:g}/{inp['map_m']:g}/{inp['map_h']:g} (not in formula); g2 = axis row {inp['g2_m']:g}")
    print(f"basket: r_perp 篮 {b} {BASKET_R[b][0]} r={r:g} (篮 {R_CTL_BASKET} demotion withdrawn, ③ 1c); g {inp['g2_l']:g} flat; "
          f"discount FY{NUM_YEAR} -> today ÷{disc:.2f}")
    print(f"②-b ladder test: FY28 mean {mean28:.4f} in [M {inp['ladder_eps_m']}, H {inp['ladder_eps_h']}]? {b2_i}; "
          f"M dev {b2_dev:+.1%} (<=20%? {b2_ii}) -> ladder replaced by consensus three points")
    for t in "LMH":
        x = rows[t]
        print(f"{t}: eps28={x['eps']:.4f} bps_start28={x['bps']:.4f} ROE={x['roe']:.2%} pe={x['pe']:.3f} "
              f"(÷{disc:.2f} -> {x['pe'] / disc:.2f}x) anchor={x['anchor']:.4f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"ratios: L/M={L / M:.4f} H/M={H / M:.4f} (H-L)/2M={(H - L) / (2 * M):.4f} | 分子比 "
          f"L={rows['L']['eps'] / rows['M']['eps']:.4f} H={rows['H']['eps'] / rows['M']['eps']:.4f} | 倍数比 "
          f"L={rows['L']['pe'] / rows['M']['pe']:.4f} H={rows['H']['pe'] / rows['M']['pe']:.4f} | V_opt/M {v_opt / M:.4f}")

    # Withdrawn demotion: control band, not in zone (valuation-rules ③ 留痕).
    ctl = ruler(r_ctl)
    v_ctl, _ = vopt(nit, r_ctl)
    g_ax = inp["g2_m"]
    ctl_pe = "/".join(f"{ctl[t]['pe']:.2f}" for t in "LMH")
    ctl_opt = "/".join(f"{ctl[t]['anchor'] + p * v_ctl:.2f}" for t, p in zip("LMH", P_TIERS))
    print(f"control band (withdrawn 篮 {R_CTL_BASKET} r={r_ctl:g}, not in zone): {fmt(ctl)} "
          f"(PE {ctl_pe}); V_opt {v_ctl:.2f}; table3 {ctl_opt}; "
          f"ceiling 1/(r-g) {1 / (r - g_ax):.2f}x at 篮 {MAIN_BASKET} vs {1 / (r_ctl - g_ax):.2f}x at 篮 {R_CTL_BASKET}")

    # ③ step 1c: the band printed while the mines were public already prices them.
    win = int(inp["band_l_start"])
    known = [k for k, _ in mine_keys if int(inp[f"{k}_pub"]) < win]
    v_known, _ = vopt(nit, r, keys=known)
    pe_base_l = L / eps_l
    pe_1c_l = (L + v_known) / eps_l
    lo, hi = inp["pe_same_min_l"], inp["pe_same_max_l"]
    in_band = lo <= pe_1c_l <= hi
    names = "+".join(n for k, n in mine_keys if k in known)
    print(f"③ 1c (L-tier same-earnings weeks from {win}, band {lo:g}-{hi:g}x TTM): mines announced before the window "
          f"[{names}] V_opt(p=1) {v_known:.2f}; base L {L:.2f} = {pe_base_l:.2f}x (out) -> L+V {L + v_known:.2f} = "
          f"{pe_1c_l:.2f}x ({'in band -> ③ not triggered, basket stays' if in_band else 'STILL OUT -> step 2'})")
    # V_opt is linear in NI/t: the NI/t (and ex-tax ore price) at which L+V touches the band floor.
    v0, v1 = vopt(0.0, r, keys=known)[0], v_known
    nit_be = nit * (lo * eps_l - L - v0) / (v1 - v0)
    px_be = (nit_be / (1 - inp["opt_tax"]) + inp["opt_cost"]) / (1 - inp["opt_restax"])
    print(f"③ 1c break-even: L+V reaches {lo:g}x at NI/t {nit_be:.0f} 元/吨 (ore {px_be:.0f} ex-VAT, {px_be * 1.13:.0f} incl.); "
          f"without 老虎洞 (scale announcement 待核) V {vopt(nit, r, keys=[k for k in known if k != 'lhd'])[0]:.2f} -> "
          f"{(L + vopt(nit, r, keys=[k for k in known if k != 'lhd'])[0]) / eps_l:.2f}x")
    if not in_band:
        errors.append(f"③ 1c: base L + announced V_opt = {pe_1c_l:.2f}x still outside {lo:g}-{hi:g}x — run ③ step 2")
    early = [k for k, _ in mine_keys if int(inp[f"{k}_pub"]) < int(inp["band_own_low"])]
    v_early, _ = vopt(nit, r, keys=early)
    print(f"③ 1c disclosure: M+V {M + v_opt:.2f} = {(M + v_opt) / inp['ttm_eps']:.2f}x TTM, H+V {H + v_opt:.2f} = "
          f"{(H + v_opt) / inp['ttm_eps']:.2f}x vs own monthly band min {inp['pe_own_min']:g} / med {inp['pe_own_med']:g} / "
          f"p75 {inp['pe_own_p75']:g}; at the band low ({int(inp['band_own_low'])}) only "
          f"{'+'.join(n for k, n in mine_keys if k in early)} were public: V {v_early:.2f}")

    same = int(inp["same_eps_weeks_m"])
    print(f"③ step 1: own band is trailing (min {inp['pe_own_min']:g}x); same-earnings weeks for FY28 EPS = {same} "
          f"(< {SAME_EPS_MIN}) -> band test {'n/a' if same < SAME_EPS_MIN else 'APPLIES'}; "
          f"M / TTM EPS {inp['ttm_eps']:g} = {M / inp['ttm_eps']:.2f}x, L / TTM = {L / inp['ttm_eps']:.2f}x")
    if same >= SAME_EPS_MIN:
        errors.append("same-earnings weeks now exist for the FY2028 numerator — run the ③ band test")

    # Correction reconciliation gate (M moves > 25% vs the same-day 10% draft).
    e_m = rows["M"]["eps"]
    coords = {
        "① prev M (篮4 10% draft)": ctl["M"]["anchor"],
        "② E_M/r": e_m / r / disc,
        "③ D_M/(r-g)": inp["payout_obs"] * e_m / (r - g_ax) / disc,
        "⑥ BPS x PB min": inp["bps_h1"] * inp["pb_own_min"],
    }
    inside = [k for k, v in coords.items() if k[0] != "①" and abs(M / v - 1) <= GATE_BAND]
    print("gate: M " + f"{ctl['M']['anchor']:.2f} -> {M:.2f} ({M / ctl['M']['anchor'] - 1:+.1%}); "
          + "; ".join(f"{k} {v:.2f} (M {M / v - 1:+.0%})" for k, v in coords.items())
          + f" -> {'PASS' if inside else 'BLOCKED'} ({', '.join(inside)})")
    if not inside:
        errors.append("correction gate: new M is >20% away from every independent coordinate")
    print(f"gate neutral band [{A:.2f}, {B:.2f}) as PE: TTM {inp['ttm_eps']:g} {A / inp['ttm_eps']:.1f}-{B / inp['ttm_eps']:.1f}x; "
          f"FY26E {inp['cons_fy26_m']:.2f} {A / inp['cons_fy26_m']:.1f}-{B / inp['cons_fy26_m']:.1f}x; "
          f"FY28E {e_m:.2f} {A / e_m:.1f}-{B / e_m:.1f}x")

    mod, gap = payout_gap(inp["g2_m"], rows["M"]["roe"], inp["payout_obs"])
    excess = 1 - inp["payout_obs"] - inp["g2_m"] / rows["M"]["roe"]
    print(f"payout: model {mod:.1%} vs observed {inp['payout_obs']:.1%} (gap {gap:+.1%}); excess retention "
          f"{excess:.1%} x EPS_M x 3.5y window (D bucket, mines, k=0) = {excess * rows['M']['eps'] * 3.5:.2f}/sh "
          f"(k前 = k后)")
    print(f"V_opt unit: ({inp['opt_price']:g} x (1-{inp['opt_restax']:g}) - {inp['opt_cost']:g}) x (1-{inp['opt_tax']:g}) "
          f"= {nit:.1f} 元/吨 NI; multiple = M-tier {pe_opt:.3f}x")
    for name, tons, dni, k_eq, val_t, t, pv in mines:
        print(f"  {name}: {tons:.1f}万吨 x {nit:.1f} = ΔNI {dni:.3f}亿 x {pe_opt:.3f} - K {k_eq:.3f} = {val_t:.2f}亿 @{t:g} "
              f"÷{1 + r:.2f}^{t - NUM_YEAR + inp['disc_years']:g} -> {pv:.2f}亿 = {pv / shares_yi:.3f}/sh")
    print(f"V_opt={v_opt:.4f}")
    roe_mine = perpetual_pe(inp["g2_m"], 1.0, r)
    print(f"V_opt multiple check: new-mine own ROE ~100% would give {roe_mine:.2f}x ({roe_mine / pe_opt - 1:+.1%} vs M-tier)")
    sens = (
        ("YTN IRR口径", 104.6), ("福麟内部结算", 252.7), ("15%税", nit_at(inp["opt_price"], tax=0.15)),
        ("矿价500含税", nit_at(500 / 1.13)),
        (f"矿价回到周期中枢(自身外销5年均值{inp['opt_price_mid5']:g})", nit_at(inp["opt_price_mid5"])),
        (f"FY2025全年成本{inp['opt_cost_fy25']:g}", nit_at(inp["opt_price"], cost=inp["opt_cost_fy25"])),
        ("矿价1025含税", nit_at(1025 / 1.13)),
    )
    print("V_opt unit sensitivity: " + " / ".join(f"{lab} {u:.0f}元/吨 -> {vopt(u, r)[0]:.2f}" for lab, u in sens))
    print("table3: " + " / ".join(f"{t} {b_:.2f}+{p:g}x{v_opt:.2f}={o:.2f}"
                                  for t, b_, p, o in zip("LMH", (L, M, H), P_TIERS, opt))
          + f"  A'={A_v:.2f} B'={B_v:.2f}")

    print(f"sensitivity: g2 0.5% {fmt(ruler(r, g=0.005))} | 2.5% {fmt(ruler(r, g=0.025))} | g2 0 {fmt(ruler(r, g=0.0))} | "
          f"r {r - 0.005:.1%} {fmt(ruler(r - 0.005))} | {r + 0.005:.1%} {fmt(ruler(r + 0.005))} | "
          f"L=cons low {fmt(ruler(r, l_eps=inp['cons_fy28_l']))} | L=FY26E mean {fmt(ruler(r, l_eps=inp['cons_fy26_m']))}")
    print(f"floor (disclosed only): PB 1.0 = {inp['bps_h1']:.2f}; FY2025 actual x 1/r ÷{disc:.2f} = {eps_l / r / disc:.2f}; "
          f"anchors as PB {L / inp['bps_h1']:.2f}/{M / inp['bps_h1']:.2f}/{H / inp['bps_h1']:.2f}")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
