#!/usr/bin/env python3
"""000100.SZ (TCL科技) valuation eval — recompute anchors from frameworks/000100.SZ.md.

formula_id: tcl_sotp_fy27_consensus_roic_gordon_v5

Four-leg SOTP, each leg Gordon at its own basket r, legs added (no blended r):

* display (TCL CSOT, attributable)  篮 5 value 11% borrowed via _AXIS.lcd-tv-panel
  (user ruling 2026-10-23; basket-6 13% kept as the axis review reference)
* PV / silicon (TCL Zhonghuan x 29.91%, inference)  篮 6 13%
* distribution (Highly, attributable)  篮 4 10%
* Bank of Shanghai 5.76% stake (equity-method income)  篮 5 11%

Panels are a commodity-price cyclical with a post-2023 supply break, so the
mid-cycle numerator is a forward consensus year (user ruling 2026-10-04, A2)
— the NEAREST qualifying one (valuation-rules「中枢 MUST 不落在低谷」,
2026-10-04 clause): FY2027 (FY+1, not discounted).  FY2026 is three quarters
realised, carries one-offs, the PV leg's trough and only four months of the
t9 buy-in.  FY2028 (price recovery + t8 ramp) goes to H only, discounted one
year.  Company consensus (同花顺 17 houses) is split into legs: PV =
Zhonghuan's own consensus x stake; Bank of Shanghai and distribution held at
their latest actuals; display = the remainder.

Leverage gate (valuation-rules「杠杆门」) is read at the mid-cycle year: FY2027
interest / EBIT > 1/3 → triggered, so every leg's retention earns ROIC, not
book ROE: g = (1 - payout) x ROIC, PE = payout / (r - g).  ROIC is the rough
segment reading the rule allows (segment net profit / segment assets, 2026H1
base; after tax, so biased low).  The ROE-side domain is printed alongside.
The bank stake is outside the gate (银行不适用) and keeps the observed-payout
ruler.  L replays the display segment's measured ROE path 2022-2025 on today's
base from FY2027 and stays at the 2025 level with the M-tier tail; PV 0 (a
listed stake cannot go below zero); distribution at its FY2023 trough.
V_opt = 0 (glass substrate / InP: no named quantity).

The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so nothing
here computes a zone or a market-implied r.

Run:  python3 frameworks/eval/000100.SZ.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import (  # noqa: E402
    capped_payout_pe, check_branch, check_g_cap, check_r, g_cap, perpetual_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from eval.lib.axes import axis_path  # noqa: E402
from eval.lib.zones import cut_points  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "000100.SZ.md"
FORMULA_ID = "tcl_sotp_fy27_consensus_roic_gordon_v5"
PREV_M = 4.58
PANEL_AXIS = axis_path("_AXIS.lcd-tv-panel")
AXIS_SHARED = {"r_display": "r_panel", "r_display_ref": "r_panel_ref"}  # framework row -> axis row
R_LEGS = ("r_display", "r_pv", "r_dist", "r_shb")
REQUIRED = [
    "shares", "bps", "payout", *R_LEGS,
    "ni26_m", "ni27_m", "ni28_m", "ni27_h", "ni28_h", "ni27_lo", "ni28_lo",
    "zh26_m", "zh27_m", "zh28_m", "zh27_h", "zh28_h", "zh_share", "zh_roe27_m", "zh_roe28_m",
    "disp_share", "disp_na", "disp_assets", "pv_assets", "disp_att_2026h1",
    "roe_l1", "roe_l2", "roe_l3", "roe_l4",
    "ni_dist", "ni_dist_l", "roe_dist", "roic_dist", "ni_shb", "roe_shb", "payout_shb",
    "ebt27_m", "ebt28_m", "interest_ann", "net_debt", "da_ann", "v_opt", "r_display_ref",
]
YI = 1e8


def retention_pe(ret: float, r: float, po: float, dg: float = 0.0) -> tuple[float, float]:
    """(PE, g) with retention earning `ret` (ROIC after the leverage gate): g = (1 - payout) x ret (+dg)."""
    g = min((1 - po) * ret + dg, g_cap(r))
    return perpetual_pe(g, ret, r), g


def deck(i: dict[str, float], dg: float = 0.0) -> dict[str, dict]:
    sh, po = i["shares"], i["payout"]
    r6, r_pv, r4, r5 = i["r_display"], i["r_pv"], i["r_dist"], i["r_shb"]
    zs, sd = i["zh_share"], i["disp_share"]

    def disp_att(year: int, t: str) -> float:  # 亿, attributable
        return i[f"ni{year}_{t}"] - i[f"zh{year}_{t}"] * zs - i["ni_shb"] - i["ni_dist"]

    pe_d, g_d = retention_pe(i["roic_dist"], r4, po, dg)
    g_shb_raw = (1 - i["payout_shb"]) * i["roe_shb"]
    pe_s = capped_payout_pe(g_shb_raw, i["roe_shb"], r5, i["payout_shb"])
    v_shb, v_dist = i["ni_shb"] * pe_s, i["ni_dist"] * pe_d
    out: dict[str, dict] = {"dist": dict(pe=pe_d, g=g_d, v=v_dist),
                            "shb": dict(pe=pe_s, g_raw=g_shb_raw, v=v_shb)}

    def tier(year: int, t: str, disc: bool) -> dict:
        att, zh = disp_att(year, t), i[f"zh{year}_{t}"]
        roic = (att / sd) / i["disp_assets"]
        pe, g = retention_pe(roic, r6, po, dg)
        roic_pv = zh / i["pv_assets"]
        pe_pv, g_pv = retention_pe(roic_pv, r_pv, po, dg)
        f, f_pv = (1 + r6, 1 + r_pv) if disc else (1.0, 1.0)
        v_disp, v_pv = att * pe / f, zh * zs * pe_pv / f_pv
        return dict(att=att, roic=roic, g=g, pe=pe, pv=zh * zs, roic_pv=roic_pv, g_pv=g_pv, pe_pv=pe_pv,
                    v_disp=v_disp, v_pv=v_pv, a=(v_disp + v_pv + v_dist + v_shb) * YI / sh)

    out["m"] = tier(27, "m", disc=False)   # FY+1: nearest qualifying consensus year
    out["h"] = tier(28, "m", disc=True)    # FY+2: further year → H only, one year back
    out["h27hi"] = tier(27, "h", disc=False)
    out["h28hi"] = tier(28, "h", disc=True)
    # ROE-side domain (disclosure): display ROE on segment net assets rolled to the start of the year
    a26 = disp_att(26, "m") - i["disp_att_2026h1"]
    na27 = i["disp_na"] + (1 - po) * a26 / sd
    na28 = na27 + (1 - po) * disp_att(27, "m") / sd
    out["m"]["roe"] = (out["m"]["att"] / sd) / na27
    out["h"]["roe"] = (out["h"]["att"] / sd) / na28
    e = [x * i["disp_na"] * sd for x in (i["roe_l1"], i["roe_l2"], i["roe_l3"])]
    e4 = i["roe_l4"] * i["disp_na"] * sd
    tail = out["m"]["pe"]
    v_disp_l = sum(x / (1 + r6) ** (k + 1) for k, x in enumerate(e)) + e4 * tail / (1 + r6) ** 3
    v_dist_l = i["ni_dist_l"] * pe_d
    out["l"] = dict(e=e, e4=e4, tail=tail, v_disp=v_disp_l, v_dist=v_dist_l,
                    a=(v_disp_l + v_dist_l + v_shb) * YI / sh)
    return out


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
    for leg in R_LEGS:
        if leg not in baskets:
            errors.append(f"{leg}: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
        errors += check_r(inp[leg], leg, baskets.get(leg))

    # shared scenario axis (_AXIS.lcd-tv-panel): the display leg's r is the axis' panel-leg rate
    if PANEL_AXIS.is_file():
        ax = parse_inputs(PANEL_AXIS.read_text(encoding="utf-8"))
        for k, ak in AXIS_SHARED.items():
            if ak not in ax or abs(ax[ak] - inp[k]) > 1e-12:
                errors.append(f"{k} {inp[k]:g} != _AXIS.lcd-tv-panel {ak} {ax.get(ak)} — the panel ruler drifted")
    else:
        errors.append("frameworks/axes/lcd-tv-panel.md missing — panel-leg r unchecked")

    # leverage gate at the mid-cycle year (EBIT = 报表营业利润 ≈ 利润总额 consensus)
    int_ebit27 = inp["interest_ann"] / inp["ebt27_m"]
    nd_ebitda27 = inp["net_debt"] / (inp["ebt27_m"] + inp["da_ann"])
    if not (int_ebit27 > 1 / 3 or nd_ebitda27 > 3):
        errors.append("leverage gate no longer triggered at FY2027 — the ROIC retention branch (A9) must be revisited")

    d = deck(inp)
    L, M, H = (d[t]["a"] for t in ("l", "m", "h"))
    A, B = cut_points(L, M, H)
    po = inp["payout"]
    errors += ladder("NI27", inp["ni27_lo"], inp["ni27_m"], inp["ni27_h"])
    errors += ladder("NI28", inp["ni28_lo"], inp["ni28_m"], inp["ni28_h"])
    errors += ladder("anchors", L, M, H)
    for t in ("m", "h"):
        x = d[t]
        errors += check_g_cap(x["g"], inp["r_display"], f"display g_{t}")
        errors += check_g_cap(x["g_pv"], inp["r_pv"], f"pv g_{t}")
        errors += check_branch(x["g"], x["roic"], inp["r_display"], po, f"display {t.upper()}")
        errors += check_branch(x["g_pv"], x["roic_pv"], inp["r_pv"], po, f"pv {t.upper()}")
    errors += check_g_cap(d["dist"]["g"], inp["r_dist"], "dist g")
    errors += check_branch(d["dist"]["g"], inp["roic_dist"], inp["r_dist"], po, "dist")
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})
    if inp["v_opt"] != 0:
        errors.append("V_opt must stay 0 (A6) until a named quantity exists")

    sh = inp["shares"] / YI
    print(f"formula_id={FORMULA_ID}")
    print(f"leverage gate @FY2027: interest/EBIT {int_ebit27:.1%} net debt/EBITDA {nd_ebitda27:.2f} → triggered; "
          f"@FY2028 {inp['interest_ann'] / inp['ebt28_m']:.1%} / {inp['net_debt'] / (inp['ebt28_m'] + inp['da_ann']):.2f}")
    for t, lab in (("m", "M FY2027 mean"), ("h", "H FY2028 mean /(1+r)")):
        x = d[t]
        print(f"{lab}: display att {x['att']:.2f}亿 ROIC {x['roic']:.2%} (ROE {x['roe']:.2%}) g {x['g']:.2%} PE {x['pe']:.2f} "
              f"→ {x['v_disp'] / sh:.2f}/股 | PV att {x['pv']:.2f}亿 ROIC {x['roic_pv']:.2%} g {x['g_pv']:.2%} "
              f"PE {x['pe_pv']:.2f} → {x['v_pv'] / sh:.2f}/股")
    x = d["dist"]
    print(f"dist: {inp['ni_dist']:.2f}亿 ROIC {inp['roic_dist']:.2%} g {x['g']:.2%} PE {x['pe']:.2f} → {x['v'] / sh:.2f}/股")
    x = d["shb"]
    print(f"SHB: {inp['ni_shb']:.2f}亿 ROE {inp['roe_shb']:.2%} payout {inp['payout_shb']:.1%} g raw {x['g_raw']:.2%} "
          f"> cap {g_cap(inp['r_shb']):.0%} → PE {x['pe']:.2f} → {x['v'] / sh:.2f}/股")
    x = d["l"]
    print(f"L display path {', '.join(f'{v:.2f}' for v in x['e'])} then {x['e4']:.2f}亿 x tail {x['tail']:.2f} "
          f"→ {x['v_disp'] / sh:.2f}/股; dist L {x['v_dist'] / sh:.2f}/股")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} width={(H - L) / (2 * M):.2f} V_opt/M=0")
    print(f"same-year (FY2027) H' = consensus high = {d['h27hi']['a']:.2f}; FY2028 high /(1+r) = {d['h28hi']['a']:.2f} (disclosure)")
    for dg in (-0.01, 0.01):
        s = deck(inp, dg)
        print(f"g ±1pp {dg:+.0%}: L {s['l']['a']:.2f} M {s['m']['a']:.2f} H {s['h']['a']:.2f}")
    ref = deck({**inp, "r_display": inp["r_display_ref"]})
    print(f"axis review base: same ruler at display r {inp['r_display_ref']:.0%} → L {ref['l']['a']:.2f} "
          f"M {ref['m']['a']:.2f} H {ref['h']['a']:.2f} (_AXIS.lcd-tv-panel §2 trigger)")
    m = d["m"]
    eps27 = inp["ni27_m"] / sh
    e_over_r = (m["att"] / inp["r_display"] + m["pv"] / inp["r_pv"] + inp["ni_dist"] / inp["r_dist"]
                + inp["ni_shb"] / inp["r_shb"]) / sh
    print(f"gate: M vs previous {PREV_M} = {M / PREV_M - 1:+.1%}; E_M/r (legwise) {e_over_r:.2f} ({M / e_over_r - 1:+.1%}); "
          f"company PE at M on FY2027E {M / eps27:.2f}x")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
