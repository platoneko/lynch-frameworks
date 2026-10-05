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

V_opt (A13 ③, valuation-rules「未建模期权」2026-10-05): Starlink Mobile next-gen
direct-to-cell on _AXIS.direct-to-cell (per-user wholesale price, full-scale EBIT
margin).  L = company 25M-user target x axis L price; M = Deutsche Bank 2030 D2D
revenue (single house); H = max(full capacity = 15,000 named V2 sats x own V1
devices per sat x axis H price, M).  Revenue already in the base E&G line is
deducted; valued in 2030 at the Starlink ruler (r, g2, ROE on spectrum + sats),
discounted to FY2027, net of unspent spectrum consideration (cash, debt service,
shares at the contract's fixed value) and unbuilt satellites.  Floor 0 per tier.

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
from lib.frameworks import load_framework  # noqa: E402

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
    "subs_2030_jpm", "n_cand",
]
AXES = Path(__file__).resolve().parents[1] / "axes"
# Rows copied from the peer-ruler axis (contracts.md「同业尺轴」): one source per field.
AXIS_ROWS = {"direct-to-cell": ["d2c_px_l", "d2c_px_m", "d2c_px_h", "d2c_margin"]}
OPT_REQUIRED = [
    "d2c_users0", "d2c_v1_sats", "d2c_users_l", "d2c_rev_db", "d2c_sats_first", "d2c_sats_full",
    "d2c_sat_cost", "d2c_spec_cap", "d2c_spec_unspent", "d2c_years",
] + [k for ks in AXIS_ROWS.values() for k in ks]
OPT_TOL = 0.01
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


def d2c_option(inp: dict) -> dict:
    """Direct-to-cell V_opt per tier, USD per share (A13 ③).

    Revenue (USD bn, realisation year) less what the base already carries
    (today's devices x axis L price, grown with the base E&G line for 1.5 years
    and g2 to the realisation year) -> NOPAT at the axis margin.  Capital = the
    spectrum consideration + the tier's satellites at SpaceX's own realised
    per-satellite capex; Gordon on the Starlink ruler (1/r when ROE < r - 3pp),
    discounted to FY2027, less unspent spectrum consideration (closing Nov 2027,
    not discounted) and satellites (built 2027-28, one year).  Per share on today's
    count (the 261.8M consideration shares are costed at their fixed contract value).
    """
    r, g2, tax = inp["r_starlink"], inp["g2_starlink"], inp["tax"]
    yrs = inp["d2c_years"]
    in_base = (inp["d2c_users0"] * inp["d2c_px_l"] * 12 / 1000
               * (1 + inp["eg_g_m"]) ** 1.5 * (1 + g2) ** yrs)
    per_sat_users = inp["d2c_users0"] / inp["d2c_v1_sats"]  # M devices per thousand sats

    def leg(rev: float, sats: float) -> dict:
        nopat = max(rev - in_base, 0.0) * inp["d2c_margin"] * (1 - tax)
        k = inp["d2c_spec_cap"] + sats * inp["d2c_sat_cost"]
        roe = nopat / k
        pe = perpetual_pe(g2, roe, r) if roe >= r - 0.03 else 1 / r
        v = (nopat * pe / (1 + r) ** yrs - inp["d2c_spec_unspent"]
             - sats * inp["d2c_sat_cost"] / (1 + r))
        return {"rev": rev, "nopat": nopat, "k": k, "roe": roe, "pe": pe, "v": v, "ps": v / inp["shares"]}

    out = {
        "l": leg(inp["d2c_users_l"] * inp["d2c_px_l"] * 12 / 1000, inp["d2c_sats_first"]),
        "m": leg(inp["d2c_rev_db"], inp["d2c_sats_first"]),
        "cap": leg(inp["d2c_sats_full"] * per_sat_users * inp["d2c_px_h"] * 12 / 1000, inp["d2c_sats_full"]),
    }
    out["h"] = max(out["cap"], out["m"], key=lambda d: d["ps"])
    out["in_base"], out["per_sat_users"] = in_base, per_sat_users
    for t in "lmh":
        out[t]["credit"] = max(out[t]["ps"], 0.0)
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

    # --- V_opt (A13 ③): direct-to-cell on _AXIS.direct-to-cell -----------------
    errors += check_missing(inp, OPT_REQUIRED)
    if errors:
        return report(errors)
    for axis, keys in AXIS_ROWS.items():
        path = AXES / f"{axis}.md"
        if not path.is_file():
            errors.append(f"frameworks/axes/{axis}.md missing — the leg ruler is unchecked")
            continue
        peer = parse_inputs(path.read_text(encoding="utf-8"))
        for k in keys:
            if k not in peer or abs(peer[k] - inp[k]) > 1e-9:
                errors.append(f"{k} {inp[k]:g} != _AXIS.{axis} {peer.get(k)} — the leg ruler drifted")
    opt = d2c_option(inp)
    v_l, v_m, v_h = (opt[t]["credit"] for t in "lmh")
    if not 0 <= v_l <= v_m <= v_h or v_h <= 0:
        errors.append(f"V_opt tiers not ordered / zero: {v_l:.2f}/{v_m:.2f}/{v_h:.2f}")
    p_rule = (v_l / v_h, v_m / v_h, 1.0) if v_h > 0 else (0.0, 0.0, 1.0)
    meta = load_framework(FRAMEWORK)
    if meta.v_opt is None or abs(meta.v_opt - v_h) > OPT_TOL:
        errors.append(f"V_opt stated {meta.v_opt} vs recomputed V_H {v_h:.4f}")
    if meta.p_tiers is None or any(abs(a - b) > 0.005 for a, b in zip(meta.p_tiers, p_rule)):
        errors.append(f"p_L/p_M/p_H stated {meta.p_tiers} vs V_k/V_H {tuple(round(p, 3) for p in p_rule)}")

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
    print(f"L/M={L / M:.3f} (Starlink 分子比 {ns[0] / ns[1]:.2f}) H/M={H / M:.3f} (分子比 {ns[2] / ns[1]:.2f}) width={(H - L) / (2 * M):.3f} V_opt/M={v_h / M:.3f}")
    print(f"D2C in-base revenue {opt['in_base']:.3f}bn  own devices per thousand V1 sats {opt['per_sat_users']:.2f}M")
    for t in ("l", "m", "cap", "h"):
        d = opt[t]
        print(f"D2C {t.upper()}: rev {d['rev']:.2f}bn NOPAT {d['nopat']:.2f}bn K {d['k']:.2f}bn ROE {d['roe']:.1%} "
              f"PE {d['pe']:.2f} V {d['v']:.2f}bn → {d['ps']:+.2f}/sh")
    print(f"V_opt={v_h:.2f} p_L/p_M/p_H={p_rule[0]:.3f}/{p_rule[1]:.3f}/1.0 "
          f"(V_L {v_l:.2f} · V_M {v_m:.2f} · V_H {v_h:.2f}; zone+V {L + v_l:.2f}/{M + v_m:.2f}/{H + v_h:.2f})")
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
