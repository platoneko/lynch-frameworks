#!/usr/bin/env python3
"""SPCX.US (SpaceX) valuation eval — recompute anchors from frameworks/SPCX.US.md.

frameworks/SPCX.US.md is the source of truth; this script re-derives
L/M/H / A/B and the candidate band from its §3 Inputs table and exits 1 on
mismatch.  The doc carries no current price (AGENTS.md「现价 — 禁写契约」): which
zone a quote falls in is derived live by the daily digest and the app, so nothing
here reads a price.

formula_id: spcx_sotp_fy27_starlink_b4_compute_b7_v1

Unlevered SOTP (USD bn → per share), every leg priced on FY2027 (t=1):

    Starlink   篮 4   FY2027 bottom-up NOPAT (subs × ARPU + E&G) × perpetual_pe(g2, ROIC, r)
    Launch     篮 4   external launch EBIT ex-Starship R&D, g = 0
    Compute    篮 7   Dec-2026 signed-contract run-rate NOPAT × 1/r (contracts are
                      90-day cancellable, so no basket pair) + consensus YE2027
                      capacity build at the company's own realized per-GW
                      economics net of its own realized per-GW capex, one year out
    Cursor / X+Grok   0 (earnings undisclosed or negative; floor 0, A-row)
    Closure           6/30 net cash + H2 EBITDA − H2 interest − H2 capex
                      − option carry (Grok + Starship R&D to end-2027)

Candidate band (A2e-7h): Starlink two-stage with g1 from the single-house JPM
2030 subscriber path; L′ copies the deck (no transition in the bad world).

Run:  python3 frameworks/eval/SPCX.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import check_g_cap, check_r, perpetual_pe, two_stage_pe  # noqa: E402
from lib.inputs import check_against_stated, check_missing, parse_baskets, parse_inputs, report  # noqa: E402
from lib.zones import cut_points  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "SPCX.US.md"
FORMULA_ID = "spcx_sotp_fy27_starlink_b4_compute_b7_v1"
TIERS = ("l", "m", "h")
REQUIRED = [
    "shares", "tax",
    "subs0", "eg0", "roic_starlink", "g2_starlink", "r_starlink",
    *[f"{f}_{t}" for f in ("adds_q", "arpu", "hw", "eg_g", "margin_c", "space_ebit", "rev_ctr", "gw", "h2_ebitda") for t in TIERS],
    "r_space", "g_space", "roic_space",
    "r_compute", "opex_pct", "gpu_life", "ai_capex_cum", "gw0",
    "cash", "mkt_sec", "debt", "h2_interest", "h2_capex", "carry_q", "carry_n",
    "v_opt", "subs_2030_jpm", "n_cand",
]
CAND_TOL = 0.05
LISTING_CCY = "USD"


def starlink_nopat(inp: dict, t: str) -> tuple[float, float]:
    """FY2027 Connectivity revenue and NOPAT from the subscriber / E&G ladder.

    Subscribers grow by adds_q per quarter from the 6/30 base: two quarters to
    YE2026, four more to YE2027; FY2027 consumer revenue uses the average of
    the two year-ends.  E&G compounds 1.5 years from the Q2 run-rate.
    """
    s26 = inp["subs0"] + 2 * inp[f"adds_q_{t}"]
    s27 = s26 + 4 * inp[f"adds_q_{t}"]
    consumer = (s26 + s27) / 2 * inp[f"arpu_{t}"] * 12 / 1000 + inp[f"hw_{t}"]
    eg = inp["eg0"] * (1 + inp[f"eg_g_{t}"]) ** 1.5
    rev = consumer + eg
    return rev, rev * inp[f"margin_c_{t}"] * (1 - inp["tax"])


def compute_leg(inp: dict, t: str, r7: float) -> tuple[float, float, float]:
    """Signed run-rate value + capacity build value (both USD bn).

    Per-GW unit economics are the company's own: signed M run-rate revenue over
    YE2026 GW, the same opex ratio and straight-line GPU depreciation on its
    own cumulative AI capex.  Each GW beyond YE2026 is worth its NOPAT at 1/r
    minus its own realized capex, received one year out.
    """
    da = inp["ai_capex_cum"] / inp["gpu_life"]

    def nopat(rev: float) -> float:
        return (rev * (1 - inp["opex_pct"]) - da) * (1 - inp["tax"])

    signed = nopat(inp[f"rev_ctr_{t}"]) / r7
    per_gw_value = nopat(inp["rev_ctr_m"]) / inp["gw0"] / r7
    per_gw_capex = inp["ai_capex_cum"] / inp["gw0"]
    build = (inp[f"gw_{t}"] - inp["gw0"]) * (per_gw_value - per_gw_capex) / (1 + r7)
    return signed, build, per_gw_value - per_gw_capex


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
    for field in ("r_starlink", "r_space", "r_compute"):
        if field not in baskets:
            errors.append(f"{field}: no 篮 N in the Inputs source cell")
        errors += check_r(inp[field], field, baskets.get(field))
    r4, r4s, r7 = inp["r_starlink"], inp["r_space"], inp["r_compute"]
    errors += check_g_cap(inp["g2_starlink"], r4, "g2_starlink")
    errors += check_g_cap(inp["g_space"], r4s, "g_space")

    sh = inp["shares"]
    pe_s = perpetual_pe(inp["g2_starlink"], inp["roic_starlink"], r4)
    pe_sp = perpetual_pe(inp["g_space"], inp["roic_space"], r4s)
    carry = inp["carry_q"] * inp["carry_n"]
    net_cash0 = inp["cash"] + inp["mkt_sec"] - inp["debt"]

    rows = {}
    for t in TIERS:
        rev_s, nopat_s = starlink_nopat(inp, t)
        signed, build, net_gw = compute_leg(inp, t, r7)
        closure = net_cash0 + inp[f"h2_ebitda_{t}"] - inp["h2_interest"] - inp["h2_capex"] - carry
        legs = {
            "starlink": nopat_s * pe_s,
            "launch": inp[f"space_ebit_{t}"] * (1 - inp["tax"]) * pe_sp,
            "compute": signed + build,
            "closure": closure,
        }
        rows[t] = {"legs": legs, "total": sum(legs.values()) / sh, "rev_s": rev_s, "nopat_s": nopat_s,
                   "signed": signed, "build": build, "net_gw": net_gw}

    L, M, H = (rows[t]["total"] for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f} {M:.2f} {H:.2f}")
    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # construction §2c: flat-multiple ladder — every leg already carries one
    # multiple across tiers, so the ladder must come from numerators alone.
    ns = [rows[t]["nopat_s"] for t in TIERS]
    if not (ns[0] < ns[1] < ns[2]):
        errors.append(f"flat ladder: Starlink NOPAT not increasing {ns}")

    if inp["v_opt"] != 0:
        errors.append("v_opt must be 0: no named option has a realized unit economics anchor (A13)")

    # Candidate band: Starlink transition g1 from JPM 2030 subscribers (single house).
    s27_m = inp["subs0"] + 6 * inp["adds_q_m"]
    g1 = (inp["subs_2030_jpm"] / s27_m) ** (1 / inp["n_cand"]) - 1
    pe_c = two_stage_pe(g1, int(inp["n_cand"]), inp["g2_starlink"], inp["roic_starlink"], r4)
    cand = {"l": L}
    for t in ("m", "h"):
        cand[t] = rows[t]["total"] + rows[t]["nopat_s"] * (pe_c - pe_s) / sh
    Lc, Mc, Hc = cand["l"], cand["m"], cand["h"]
    if not (Lc < Mc < Hc):
        errors.append(f"candidate L′<M′<H′ violated: {Lc:.2f} {Mc:.2f} {Hc:.2f}")
    for label, stated, val in (("L′", "L′", Lc), ("M′", "M′", Mc), ("H′", "H′", Hc)):
        m = re.search(stated + r"\s*=\s*\*\*([0-9.]+)\*\*", md)
        if not m:
            errors.append(f"candidate {label} not stated")
        elif abs(float(m.group(1)) - val) > CAND_TOL:
            errors.append(f"candidate {label} stated {m.group(1)} vs computed {val:.2f}")

    print(f"formula_id={FORMULA_ID}  shares {sh:.4f}bn  tax {inp['tax']:.0%}")
    print(f"r: starlink {r4:g} (篮 {baskets.get('r_starlink')})  launch {r4s:g} (篮 {baskets.get('r_space')})  compute {r7:g} (篮 {baskets.get('r_compute')})")
    print(f"PE: starlink {pe_s:.2f} (g2 {inp['g2_starlink']:g}, ROIC {inp['roic_starlink']:g})  launch {pe_sp:.2f}  compute 1/r {1 / r7:.2f}")
    for t in TIERS:
        row = rows[t]
        per = {k: round(v / sh, 2) for k, v in row["legs"].items()}
        print(f"{t.upper()}: {per} → {row['total']:.2f}  | starlink rev {row['rev_s']:.1f} NOPAT {row['nopat_s']:.2f}"
              f" | compute signed {row['signed']:.1f} build {row['build']:.1f} (net/GW {row['net_gw']:.2f})")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.3f} (Starlink 分子比 {ns[0] / ns[1]:.2f}) H/M={H / M:.3f} (分子比 {ns[2] / ns[1]:.2f}) width={(H - L) / (2 * M):.3f} V_opt/M=0")
    print(f"candidate (JPM 2030 subs {inp['subs_2030_jpm']:g}M, g1 {g1:.2%}, n {int(inp['n_cand'])}, stage-1 payout {1 - g1 / inp['roic_starlink']:+.2f} = 发股融资的增长): "
          f"PE {pe_c:.2f} → L′ {Lc:.2f} M′ {Mc:.2f} H′ {Hc:.2f}")
    for g2 in (inp["g2_starlink"] - 0.01, inp["g2_starlink"] + 0.01):
        d = (perpetual_pe(g2, inp["roic_starlink"], r4) - pe_s) / sh
        print(f"g2 {g2:.0%}: L/M/H {L + rows['l']['nopat_s'] * d:.2f}/{M + rows['m']['nopat_s'] * d:.2f}/{H + rows['h']['nopat_s'] * d:.2f}")
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves all
    # three leg baskets 1:1 (Starlink / launch Gordon, compute 1/r and its one-year
    # build discount); numerators, g, ROIC and the closure stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        tot = []
        for t in TIERS:
            row = rows[t]
            s = row["nopat_s"] * perpetual_pe(inp["g2_starlink"], inp["roic_starlink"], r4 + dr)
            sp = inp[f"space_ebit_{t}"] * (1 - inp["tax"]) * perpetual_pe(inp["g_space"], inp["roic_space"], r4s + dr)
            signed, build, _ = compute_leg(inp, t, r7 + dr)
            tot.append((s + sp + signed + build + row["legs"]["closure"]) / sh)
        return tot[0], tot[1], tot[2]

    rf = rf_block(LISTING_CCY, {"r_starlink": r4, "r_space": r4s, "r_compute": r7}, band_rf)
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    # Only a clean run feeds the daily digest (output/rates/).
    if not errors:
        write_rf_readings("SPCX.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
