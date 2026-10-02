#!/usr/bin/env python3
"""VIAV.US valuation eval — recompute anchors from frameworks/VIAV.US.md.

formula_id: viav_fy28_cons_gordon_blend_v1

One company-wide multiple on an FY28 numerator built two ways: M / H are the
FY28 consensus mean / high (7 houses — the furthest year with a >=2-house
*range*, valuation-rules 裁决顺序 ②); L is an FY28 digestion year built
bottom-up by segment from the 10-K segment table — NSE revenue falls by the
FY22->FY24 measured drop at the measured decremental margin off the FY27
consensus split, OSP falls back to its FY26 actual (A6).  Street EPS is
non-GAAP, so every tier is cut by the after-tax SBC share of FY28 M-tier NI
(FY26 SBC / revenue carried to FY28 consensus revenue, A9) and the after-tax
net interest on today's balance sheet is stripped; the balance sheet comes
back once as a closing item.

The multiple is generated, not borrowed: `perpetual_pe(g, ROE_x, r)`, r = 10%
(basket 4 常规经营 for both segments, A3), g = segment-profit-weighted blend
of NSE g2 (test-equipment peer cluster reverse-solved, truncated to g_cap) and
OSP g2 (own ten-year segment-profit CAGR, 无同业锚) — legitimate as one g
because both legs sit in the same basket (valuation-rules「腿归篮」), flat over
the three tiers (`cyclical`).  Segment assets are not disclosed, so the legs
cannot carry their own ROE (valuation-rules「分腿 ROE 来源优先序」③): the
company-wide ruler is the deck and the two-leg SOTP on the shared ROE is a
printed cross-check (A2).

The 2031 convertible is priced the way the holder would choose (valuation-
rules「杠杆门」归类): per tier the lower of the debt basis (principal off the
closing item, no conversion shares) and the if-converted basis (principal
stays, +conversion shares, coupon added back).  Cash retained beyond the
growth-required b1 = g/ROE is the B bucket; with a large M&A record the k
discount (default layer ②, k_L <= k_M <= k_H) comes off the anchor (A12).

The doc carries no current price (AGENTS.md「现价 — 禁写契约」).

Run:  python3 frameworks/eval/VIAV.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import check_capex_mount  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import check_g_cap, check_r, g_cap, perpetual_pe  # noqa: E402
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

FRAMEWORK = REPO_ROOT / "frameworks" / "VIAV.US.md"
FORMULA_ID = "viav_fy28_cons_gordon_blend_v1"
LISTING_CCY = "USD"
TOL = 0.05
MIN_R_MINUS_G = 0.02
TIERS = ("L", "M", "H")

REQUIRED = [
    "shares_basic", "dil_q4", "conv_shares", "conv_price", "conv_principal", "conv_carry",
    "px_q4_avg", "equity", "cash", "notes_2029", "contingent", "cash_yield",
    "coupon_2029", "coupon_conv", "tax",
    "eps_fy27_m", "rev_fy27_m", "eps_fy28_l", "eps_fy28_m", "eps_fy28_h", "rev_fy28_m",
    "eps_fy28_cand", "sbc_fy26", "rev_fy26",
    "osp_rev_q1g", "osp_om_q1g", "osp_oi_fy26", "osp_oi_fy17",
    "nse_rev_fy22", "nse_oi_fy22", "nse_rev_fy24", "nse_oi_fy24", "dc_share_nse",
    "r_perp", "g_nse", "g_peer_median", "g_osp", "k_l", "k_m", "k_h",
    "capex_l", "capex_m", "capex_h",
]


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
    errors += check_capex_mount((inp["capex_l"], inp["capex_m"], inp["capex_h"]))

    r, t = inp["r_perp"], inp["tax"]
    cap = g_cap(r)
    ks = (inp["k_l"], inp["k_m"], inp["k_h"])

    # ---- basket, g2 sources (A3, A7, A8) ----
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (A3)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(inp["g_nse"], r, "g_nse")
    if abs(inp["g_nse"] - min(inp["g_peer_median"], cap)) > 5e-5:
        errors.append(f"g_nse {inp['g_nse']:.4f} != min(peer median {inp['g_peer_median']:.4f}, cap {cap:.3f}) — A7")
    g_osp_own = (inp["osp_oi_fy26"] / inp["osp_oi_fy17"]) ** (1 / 9) - 1
    if abs(inp["g_osp"] - g_osp_own) > 5e-4:
        errors.append(f"g_osp {inp['g_osp']:.4f} != own FY17->FY26 segment-OI CAGR {g_osp_own:.4f} — A8")
    errors += ladder("FY28 consensus", inp["eps_fy28_l"], inp["eps_fy28_m"], inp["eps_fy28_h"])
    if not inp["eps_fy27_m"] < inp["eps_fy28_l"]:
        errors.append("FY27 consensus not below FY28 low: 同世界门 for a g >= 0 source fails (A7)")
    if not ks[0] <= ks[1] <= ks[2]:
        errors.append(f"k must ascend L<=M<=H for a cyclical (A12), got {ks}")
    if any(k.startswith("p_") for k in inp):
        errors.append("Inputs carry probability fields — p_k belongs in a zone+V table only")

    # ---- Step 1: share bases (A11) ----
    s_cons = inp["shares_basic"] + inp["dil_q4"]  # street EPS base: post-offering basic + Q4 dilution
    net_conv_q4 = inp["conv_shares"] * (1 - inp["conv_price"] / inp["px_q4_avg"])
    d_rsu = inp["dil_q4"] - net_conv_q4
    s_debt = inp["shares_basic"] + d_rsu
    s_conv = s_debt + inp["conv_shares"]
    if d_rsu <= 0:
        errors.append(f"implied RSU dilution {d_rsu / 1e6:.2f}M not positive — Q4 dilution split broken (A11)")

    # ---- Step 2-3: SBC haircut, net interest (A9, A10) ----
    sbc28_at = inp["sbc_fy26"] / inp["rev_fy26"] * inp["rev_fy28_m"] * (1 - t)  # $M after tax
    ni_m_street = inp["eps_fy28_m"] * s_cons / 1e6
    haircut = sbc28_at / ni_m_street
    net_int_pre = (inp["cash"] * inp["cash_yield"] - inp["notes_2029"] * inp["coupon_2029"]
                   - inp["conv_principal"] * inp["coupon_conv"])
    int_at = net_int_pre * (1 - t)
    coupon_at = inp["conv_principal"] * inp["coupon_conv"] * (1 - t)

    # ---- Step 4: L numerator, bottom-up FY28 digestion year (A6) ----
    osp27_rev = inp["osp_rev_q1g"] * 4
    osp27_oi = osp27_rev * inp["osp_om_q1g"]
    oi27 = inp["eps_fy27_m"] * s_cons / 1e6 / (1 - t) - net_int_pre
    nse27_rev = inp["rev_fy27_m"] - osp27_rev
    nse27_oi = oi27 - osp27_oi
    drop = 1 - inp["nse_rev_fy24"] / inp["nse_rev_fy22"]
    decr = (inp["nse_oi_fy22"] - inp["nse_oi_fy24"]) / (inp["nse_rev_fy22"] - inp["nse_rev_fy24"])
    nse_l = nse27_oi - decr * drop * nse27_rev
    osp_l = inp["osp_oi_fy26"]
    eps_l_street = (nse_l + osp_l + net_int_pre) * (1 - t) * 1e6 / s_cons
    street = {"L": eps_l_street, "M": inp["eps_fy28_m"], "H": inp["eps_fy28_h"]}
    if not eps_l_street < inp["eps_fy28_l"]:
        errors.append("L digestion EPS not below the FY28 consensus low — L would be a consensus point, not a measured bad (A6)")

    # ---- Step 5: blended g (A7, A8) ----
    osp28 = osp27_oi * (1 + inp["g_osp"])
    oi28_m = ni_m_street / (1 - t) - net_int_pre
    w_nse = (oi28_m - osp28) / oi28_m
    g = w_nse * inp["g_nse"] + (1 - w_nse) * inp["g_osp"]
    errors += check_g_cap(g, r, "g_blend")
    if r - g < MIN_R_MINUS_G:
        errors.append(f"r - g = {r - g:.2%} < 2% — at the pole")

    # ---- Step 6-8: per basis value, rolled ROE, Gordon PE, k (A10-A12) ----
    closing_conv = inp["cash"] - inp["notes_2029"] - inp["contingent"]
    bases = {
        "debt": dict(s=s_debt, extra=0.0, closing=closing_conv - inp["conv_principal"], eq=inp["equity"]),
        "conv": dict(s=s_conv, extra=coupon_at, closing=closing_conv, eq=inp["equity"] + inp["conv_carry"]),
    }

    def deck(rr: float, gg: float, eps: dict[str, float]) -> dict[str, dict]:
        out = {}
        for i, tier in enumerate(TIERS):
            best = None
            for name, b in bases.items():
                core = eps[tier] * s_cons / 1e6 * (1 - haircut) - int_at + b["extra"]
                unbooked = inp["eps_fy27_m"] * s_cons / 1e6 * (1 - haircut) - int_at + b["extra"]
                op0 = b["eq"] - b["closing"]
                share = gg * unbooked / core
                if share >= 1:
                    raise ValueError(f"book roll diverges at {tier}/{name}: g·N/core = {share:.2f}")
                book = op0 / (1 - share)
                roe = core / book
                pe = perpetual_pe(gg, roe, rr)
                pre_k = (core * pe + b["closing"]) / b["s"] * 1e6
                excess = (1 - gg / roe) * unbooked / b["s"] * 1e6
                val = pre_k - ks[i] * excess
                row = dict(basis=name, core_ps=core / b["s"] * 1e6, roe=roe, pe=pe, pre_k=pre_k,
                           excess=excess, val=val, core=core, book=book)
                if best is None or val < best["val"]:
                    best = row
            out[tier] = best
        return out

    d = deck(r, g, street)
    L, M, H = (d[x]["val"] for x in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H failed: {L:.2f} {M:.2f} {H:.2f}")
        return report(errors)
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)

    # ---- flat ladder (A2e-2c): all tiers at PE_M on the M basis ----
    pe_m = d["M"]["pe"]
    flat = [(d[x]["core"] * pe_m + bases[d["M"]["basis"]]["closing"]) / bases[d["M"]["basis"]]["s"] * 1e6
            for x in TIERS]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")

    # ---- candidate band (A16): H numerator -> single-house FY28 EPS ----
    cand_eps = dict(street)
    cand_eps["H"] = inp["eps_fy28_cand"]
    dc = deck(r, g, cand_eps)
    cand = (L, M, dc["H"]["val"])
    stated = load_framework(FRAMEWORK).candidate
    if stated is None:
        errors.append("候选带 line missing from Outputs (A16)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), stated, cand):
            if abs(said - got) > TOL:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")

    # ---- report ----
    print(f"formula_id={FORMULA_ID}")
    print(f"r={r:g} (篮 {baskets.get('r_perp')})  g_nse={inp['g_nse']:.4f} (peer median {inp['g_peer_median']:.4f} -> cap {cap:.3f})  "
          f"g_osp={inp['g_osp']:.4f} (own CAGR {g_osp_own:.4f})  w_nse={w_nse:.3f} -> g={g:.4f} (flat over tiers)")
    print(f"shares: street base {s_cons / 1e6:.2f}M | Q4 convert net shares {net_conv_q4 / 1e6:.2f}M, RSU {d_rsu / 1e6:.2f}M | "
          f"debt basis {s_debt / 1e6:.2f}M | if-converted {s_conv / 1e6:.2f}M")
    print(f"SBC FY28 after tax {sbc28_at:.1f}M -> haircut {haircut:.4f}; net interest pre-tax {net_int_pre:.2f}M (after tax {int_at:.2f}M stripped)")
    print(f"FY27 split: OI {oi27:.1f}M = NSE {nse27_oi:.1f}M on {nse27_rev:.0f}M ({nse27_oi / nse27_rev:.1%}) + OSP {osp27_oi:.1f}M on {osp27_rev:.0f}M")
    print(f"L digestion: NSE rev -{drop:.1%} @ decremental {decr:.1%} -> NSE OI {nse_l:.1f}M ({nse_l / (nse27_rev * (1 - drop)):.1%}); "
          f"OSP {osp_l:.1f}M -> street-basis EPS {eps_l_street:.4f}")
    for x in TIERS:
        row = d[x]
        print(f"{x}: street {street[x]:.4f} core/sh {row['core_ps']:.4f} [{row['basis']}] opening book {row['book']:.1f}M "
              f"ROE {row['roe']:.4f} PE {row['pe']:.3f} pre-k {row['pre_k']:.3f} - k {ks[TIERS.index(x)]:g} x B-bucket {row['excess']:.3f} = {row['val']:.3f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M {L / M:.3f} (num {d['L']['core_ps'] / d['M']['core_ps']:.3f} x pe {d['L']['pe'] / pe_m:.3f}) | "
          f"H/M {H / M:.3f} (num {d['H']['core_ps'] / d['M']['core_ps']:.3f} x pe {d['H']['pe'] / pe_m:.3f}) | width {(B - A) / M:.3f} | (H-L)/2M {(H - L) / (2 * M):.3f}")
    print(f"flat ladder @ PE_M {pe_m:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    for dg in (-0.01, 0.01):
        alt = deck(r, g + dg, street)
        print(f"g {g + dg:.4f}: {alt['L']['val']:.2f}/{alt['M']['val']:.2f}/{alt['H']['val']:.2f}")
    print(f"候选带 H′ (eps {inp['eps_fy28_cand']:g}): ROE {dc['H']['roe']:.4f} PE {dc['H']['pe']:.3f} -> {dc['H']['val']:.2f}")
    # SOTP cross-check on the shared ROE (A2): NSE at g_nse, OSP at g_osp, pre-k
    for x in TIERS:
        row = d[x]
        b = bases[row["basis"]]
        oi = street[x] * s_cons / 1e6 / (1 - t) - net_int_pre
        osp_share = (osp_l if x == "L" else osp28) / oi
        v = (row["core"] * (1 - osp_share) * perpetual_pe(inp["g_nse"], row["roe"], r)
             + row["core"] * osp_share * perpetual_pe(inp["g_osp"], row["roe"], r) + b["closing"]) / b["s"] * 1e6
        osp_ps = row["core"] * osp_share * perpetual_pe(inp["g_osp"], row["roe"], r) / b["s"] * 1e6
        print(f"SOTP cross {x}: {v:.2f} vs company pre-k {row['pre_k']:.2f} ({v / row['pre_k'] - 1:+.1%}); OSP share {osp_share:.2f}, OSP {osp_ps:.2f}/sh")
    dc_rev = inp["dc_share_nse"] * (inp["rev_fy28_m"] - osp27_rev * (1 + inp["g_osp"]))
    print(f"capex axis implied share (NSE data-center ~{inp['dc_share_nse']:.0%} of FY28 NSE revenue {dc_rev:.0f}M): {dc_rev * 1e6 / inp['capex_m']:.3%}")

    # r_f readings (_AXIS.rates): Δr_f moves r_perp 1:1; numerator, g, ROE, k stay put.
    def band_rf(dr: float) -> tuple[float, float, float]:
        dd = deck(r + dr, g, street)
        return dd["L"]["val"], dd["M"]["val"], dd["H"]["val"]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    if not errors:
        write_rf_readings("VIAV.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
