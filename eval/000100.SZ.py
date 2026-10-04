#!/usr/bin/env python3
"""000100.SZ (TCL科技) valuation eval — recompute anchors from frameworks/000100.SZ.md.

formula_id: tcl_sotp_fy28_consensus_gordon_v3

Four-leg SOTP, each leg Gordon at its own basket r, legs added (no blended r):

* display (TCL CSOT, attributable)  篮 6 13%
* PV / silicon (TCL Zhonghuan x 29.91%, inference)  篮 6 13%
* distribution (Highly, attributable)  篮 4 10%
* Bank of Shanghai 5.76% stake (equity-method income)  篮 5 11%

Panels are a commodity-price cyclical, but the post-2023 supply break makes the
forward consensus the mid-cycle numerator (user ruling 2026-10-04, A2).  M / H
= FY2028E company consensus mean / high (同花顺 17 houses) split into legs:
PV = Zhonghuan's own FY2028E consensus x stake; Bank of Shanghai and
distribution held at their latest actuals; display = the remainder.  FY2028
legs are discounted one year.  Multiples come from the payout policy
g = (1 - payout) x ROE (display ROE on segment net assets rolled to the start
of 2028 with retention 1 - payout; PV on Zhonghuan's consensus ROE).  The
bank stake is in the 病态区 with its policy g over the cap, so it takes the
observed-payout ruler.  L replays the display segment's measured ROE path
2022-2025 on today's base and stays at the 2025 level; PV 0 (a listed stake
cannot go below zero); distribution at its FY2023 trough; bank stake flat.
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
    capped_payout_pe, check_branch, check_g_cap, check_r, g_cap, payout, perpetual_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from eval.lib.zones import cut_points  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "000100.SZ.md"
FORMULA_ID = "tcl_sotp_fy28_consensus_gordon_v3"
R_LEGS = ("r_display", "r_pv", "r_dist", "r_shb")
REQUIRED = [
    "shares", "bps", "payout", *R_LEGS,
    "ni26_m", "ni27_m", "ni28_m", "ni26_h", "ni27_h", "ni28_h", "ni28_lo",
    "zh26_m", "zh27_m", "zh28_m", "zh26_h", "zh27_h", "zh28_h", "zh_share", "zh_roe28_m",
    "disp_share", "disp_na", "disp_att_2026h1", "roe_l1", "roe_l2", "roe_l3", "roe_l4",
    "ni_dist", "ni_dist_l", "roe_dist", "ni_shb", "roe_shb", "payout_shb", "v_opt",
]
YI = 1e8


def policy_pe(roe: float, r: float, po: float, dg: float = 0.0) -> tuple[float, float, float]:
    """(PE, g used, g raw) at policy g = (1 - payout) x ROE (+ dg for the sensitivity row)."""
    g_raw = (1 - po) * roe + dg
    cap = g_cap(r)
    if g_raw <= cap:
        return perpetual_pe(g_raw, roe, r), g_raw, g_raw
    if roe <= r + 0.03:
        return capped_payout_pe(g_raw, roe, r, po), cap, g_raw
    return perpetual_pe(cap, roe, r), cap, g_raw


def deck(i: dict[str, float], dg: float = 0.0) -> dict[str, dict]:
    sh, po = i["shares"], i["payout"]
    r6, r_pv, r4, r5 = i["r_display"], i["r_pv"], i["r_dist"], i["r_shb"]
    zs, sd = i["zh_share"], i["disp_share"]

    def disp_att(year: int, t: str) -> float:  # 亿, attributable
        return i[f"ni{year}_{t}"] - i[f"zh{year}_{t}"] * zs - i["ni_shb"] - i["ni_dist"]

    pe_d, g_d, _ = policy_pe(i["roe_dist"], r4, po, dg)
    g_shb_raw = (1 - i["payout_shb"]) * i["roe_shb"]
    pe_s = capped_payout_pe(g_shb_raw, i["roe_shb"], r5, i["payout_shb"])
    v_shb = i["ni_shb"] * pe_s
    v_dist = i["ni_dist"] * pe_d
    out: dict[str, dict] = {"dist": dict(pe=pe_d, g=g_d, roe=i["roe_dist"], v=v_dist),
                            "shb": dict(pe=pe_s, g_raw=g_shb_raw, v=v_shb)}
    roe_pv = {"m": i["zh_roe28_m"], "h": i["zh_roe28_m"] * i["zh28_h"] / i["zh28_m"]}
    for t in ("m", "h"):
        a26 = disp_att(26, t) - i["disp_att_2026h1"]
        a27, a28 = disp_att(27, t), disp_att(28, t)
        na = i["disp_na"] + (1 - po) * (a26 + a27) / sd
        roe = (a28 / sd) / na
        pe, g, g_raw = policy_pe(roe, r6, po, dg)
        pv = i[f"zh28_{t}"] * zs
        pe_pv, g_pv, g_pv_raw = policy_pe(roe_pv[t], r_pv, po, dg)
        v_disp, v_pv = a28 * pe / (1 + r6), pv * pe_pv / (1 + r_pv)
        out[t] = dict(att=a28, na=na, roe=roe, g=g, g_raw=g_raw, pe=pe, pv=pv, roe_pv=roe_pv[t],
                      g_pv=g_pv, g_pv_raw=g_pv_raw, pe_pv=pe_pv, v_disp=v_disp, v_pv=v_pv,
                      a=(v_disp + v_pv + v_dist + v_shb) * YI / sh)
    e = [x * i["disp_na"] * sd for x in (i["roe_l1"], i["roe_l2"], i["roe_l3"])]
    e4 = i["roe_l4"] * i["disp_na"] * sd
    gm, roem = out["m"]["g"], out["m"]["roe"]
    tail = payout(gm, roem) / (r6 - gm)
    v_disp_l = (sum(x / (1 + r6) ** (k + 1) for k, x in enumerate(e)) + e4 * tail / (1 + r6) ** 3) / (1 + r6)
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

    d = deck(inp)
    L, M, H = (d[t]["a"] for t in ("l", "m", "h"))
    A, B = cut_points(L, M, H)
    po = inp["payout"]
    errors += ladder("NI28", inp["ni28_lo"], inp["ni28_m"], inp["ni28_h"])
    errors += ladder("anchors", L, M, H)
    for t in ("m", "h"):
        x = d[t]
        errors += check_g_cap(x["g"], inp["r_display"], f"display g_{t}")
        errors += check_g_cap(x["g_pv"], inp["r_pv"], f"pv g_{t}")
        if x["g"] == x["g_raw"]:
            errors += check_branch(x["g"], x["roe"], inp["r_display"], po, f"display {t.upper()}")
    errors += check_g_cap(d["dist"]["g"], inp["r_dist"], "dist g")
    errors += check_branch(d["dist"]["g"], d["dist"]["roe"], inp["r_dist"], po, "dist")
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})
    if inp["v_opt"] != 0:
        errors.append("V_opt must stay 0 (A6) until a named quantity exists")

    sh = inp["shares"] / YI
    print(f"formula_id={FORMULA_ID}")
    for t in ("m", "h"):
        x = d[t]
        print(f"{t.upper()}: display att {x['att']:.2f}亿 NA(beg 2028) {x['na']:.1f} ROE {x['roe']:.2%} g {x['g']:.2%} "
              f"PE {x['pe']:.2f} → {x['v_disp'] / sh:.2f}/股 | PV att {x['pv']:.2f}亿 ROE {x['roe_pv']:.2%} "
              f"g {x['g_pv']:.2%} (raw {x['g_pv_raw']:.2%}) PE {x['pe_pv']:.2f} → {x['v_pv'] / sh:.2f}/股")
    x = d["dist"]
    print(f"dist: {inp['ni_dist']:.2f}亿 ROE {x['roe']:.2%} g {x['g']:.2%} PE {x['pe']:.2f} → {x['v'] / sh:.2f}/股")
    x = d["shb"]
    print(f"SHB: {inp['ni_shb']:.2f}亿 ROE {inp['roe_shb']:.2%} payout {inp['payout_shb']:.1%} g raw {x['g_raw']:.2%} "
          f"> cap {g_cap(inp['r_shb']):.0%} → PE {x['pe']:.2f} → {x['v'] / sh:.2f}/股")
    x = d["l"]
    print(f"L display path {', '.join(f'{v:.2f}' for v in x['e'])} then {x['e4']:.2f}亿 x tail {x['tail']:.2f} "
          f"→ {x['v_disp'] / sh:.2f}/股; dist L {x['v_dist'] / sh:.2f}/股")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} width={(H - L) / (2 * M):.2f} V_opt/M=0")
    for dg in (-0.01, 0.01):
        s = deck(inp, dg)
        print(f"g ±1pp {dg:+.0%}: L {s['l']['a']:.2f} M {s['m']['a']:.2f} H {s['h']['a']:.2f}")
    m = d["m"]
    e_over_r = (((m["att"] + m["pv"]) / inp["r_display"]) / (1 + inp["r_display"])
                + inp["ni_dist"] / inp["r_dist"] + inp["ni_shb"] / inp["r_shb"]) / sh
    print(f"cross: E_M/r (legwise) = {e_over_r:.2f}; M vs previous 3.90 = {M / 3.90 - 1:+.1%} (gate threshold 25%)")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
