#!/usr/bin/env python3
"""AMZN.US (Amazon) valuation eval — recompute anchors from frameworks/AMZN.US.md.

frameworks/AMZN.US.md is the source of truth; this script re-derives
L/M/H / A/B from the §3 Inputs table and exits 1 on mismatch.  The doc carries no
current price (AGENTS.md「现价 — 禁写契约」): which zone a quote falls in is
derived live by the daily digest and the app, so nothing here reads a price.

formula_id: amzn_fwd_numerator_gordon_aws_retail_portfolio_v1

Ruler: SOTP on a FORWARD numerator — the FY2027E sell-side EPS range carried
onto the segment legs by one scalar per tier — priced at ONE growth rate per
leg.  Three Gordon legs + two asset legs:

    AWS · non-lab   篮 4 r 10%   retention at the MARGINAL steady-state ROIC
    AWS · lab       篮 7→4 pair  (OpenAI + Anthropic revenue: circular financing today;
                                 a paying customer once the lab makes it — capitalised
                                 at 10%, arrival risk in the shared k_lab)
    Retail (NA+Intl) 篮 4 r 10%  retention at its own average ROE (net capital)
    portfolio (Anthropic / OpenAI stakes) net of DTL, discount band
    net cash (cash + debt securities − long-term debt)

Why the cloud legs retain at the marginal ROIC and not the average ROE: the
capital the growth actually consumes is the capex wave (data centres), whose
return is the cloud segment's marginal ROIC (HSBC 2027E AWS 18.9%), not the
blended return of the fleet plus the retail float.  FY2027 is the peak of the
build-out, so the FY27 profit / FY27-start capital snapshot is not a steady
state either — it is printed as a disclosure (A4).

The L tier additionally retreats the AWS numerator to the FY2025 realised
segment margin (A5); L and H are the two ends of the same 52-house FY2027E
distribution (A2e-2a).  No V_opt: the post-FY2027 second stage has no
consensus anchor; the single-house FY2028E point estimate is a candidate band.

Run:  python3 frameworks/eval/AMZN.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import check_lab_mount  # noqa: E402
from eval.lib.gordon import check_basket_pair, check_g_cap, check_k_declared, check_r, perpetual_pe  # noqa: E402
from eval.lib.inputs import parse_baskets  # noqa: E402
from eval.lib.zones import cut_points  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "AMZN.US.md"
FORMULA_ID = "amzn_fwd_numerator_gordon_aws_retail_portfolio_v1"
LISTING_CCY = "USD"
TOL = 0.05
BN = 1e3
# 10-Q 2026-06-30 Note 8: H1 consolidated operating income ($M)
H1_TOTAL_OPERATING_INCOME = 51313.0
MIN_R_MINUS_G = 0.02
K_LADDER_TOL = 1e-4
IC_SENSITIVITY = (1.20, 1.40)
# A leg whose derived ROE exceeds this is a capital-allocation artefact, not a
# business (valuation-rules「分腿 ROE 来源优先序」护栏) — refuse, do not price.
MAX_LEG_ROE = 0.60


def parse_inputs(md: str) -> dict[str, float]:
    out: dict[str, float] = {}
    in_inputs = False
    for line in md.splitlines():
        if line.startswith("### Inputs"):
            in_inputs = True
            continue
        if in_inputs and line.startswith("### "):
            break
        if not in_inputs or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        key, raw = cells[0], cells[1]
        if raw in ("待补", "", "—", "取值"):
            continue
        try:
            out[key] = float(raw.replace(",", ""))
        except ValueError:
            continue
    return out


def first_float(pattern: str, md: str) -> float | None:
    m = re.search(pattern, md)
    return float(m.group(1)) if m else None


REQUIRED = [
    "shares_diluted", "tax_rate",
    "oi_na_h1", "oi_intl_h1", "oi_aws_h1", "rev_aws_h1", "net_interest_h1",
    "r_perp", "r_aws_lab", "r_aws_lab_t", "k_lab",
    "ic_group", "ic_aws", "roic_marg_aws", "share_lab_aws",
    "g2_aws", "g2_ret",
    "k_eps_l", "k_eps_m", "k_eps_h",
    "eps_fy27e_low", "eps_fy27e_consensus", "eps_fy27e_high",
    "aws_om_l", "aws_om_now",
    "cash", "mkt_sec", "mkt_equity_sec", "lt_debt",
    "port_gross", "port_cost", "dtl_rate",
    "d_port_l", "d_port_m", "d_port_h",
    "payout_3y", "k_l", "k_m", "k_h",
    "pe_own_top", "pe_own_p50",
    "capex_guide", "net_debt_ebitda", "interest_ebit",
    "eps_fy28e_single", "r_disc",
    "v_opt",
]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    missing = [k for k in REQUIRED if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1
    baskets = parse_baskets(md)
    errors: list[str] = []

    # --- r is a basket, not a dial (valuation-rules「§r 篮子」)
    r4, r7, r7t = inp["r_perp"], inp["r_aws_lab"], inp["r_aws_lab_t"]
    for field, r in (("r_perp", r4), ("r_aws_lab", r7), ("r_aws_lab_t", r7t)):
        if field not in baskets:
            errors.append(f"{field}: Inputs source cell names no 篮 N")
        errors += check_r(r, field, baskets.get(field))
    # The lab sub-leg is a basket PAIR (valuation-rules「篮子对」): 篮 7 is what the
    # customer is today, 篮 4 what it is if it makes it.  Every leg here is
    # single-stage, so the journey rate has no exponent to act in -- the steady
    # state capitalises at the terminal rate and the shared k_lab carries all of
    # the arrival risk (_AXIS.frontier-lab-funding §3).
    errors += check_basket_pair(r7, r7t, "lab", baskets.get("r_aws_lab"), baskets.get("r_aws_lab_t"))
    errors += check_k_declared(r7, r7t, (inp["k_lab"],) * 3, "k_lab")
    errors += [f"axis: {e}" for e in check_lab_mount(inp["k_lab"])]
    for field, g, r in (("g2_aws", inp["g2_aws"], r4), ("g2_ret", inp["g2_ret"], r4), ("g2_aws@lab", inp["g2_aws"], r7)):
        errors += check_g_cap(g, r, field)
        if r - g < MIN_R_MINUS_G:
            errors.append(f"{field}: r - g = {r - g:.2%} < {MIN_R_MINUS_G:.0%}")

    # --- tier ladder must be the consensus range itself (A2e-2a)
    if not (inp["k_eps_l"] < inp["k_eps_m"] < inp["k_eps_h"]):
        errors.append("k_eps_* ladder not increasing")
    mean = inp["eps_fy27e_consensus"]
    for tier, endpoint in (("l", "eps_fy27e_low"), ("h", "eps_fy27e_high")):
        want, got = inp[endpoint] / mean, inp[f"k_eps_{tier}"] / inp["k_eps_m"]
        if abs(got - want) > K_LADDER_TOL:
            errors.append(f"k_eps_{tier}/k_eps_m = {got:.5f} != {endpoint}/consensus = {want:.5f}")
    if not (1.0 >= inp["d_port_l"] > inp["d_port_m"] > inp["d_port_h"] >= 0.0):
        errors.append("d_port_* must be a decreasing band inside [0,1]")
    if not (0.0 <= inp["k_l"] <= 1.0 and 0.0 <= inp["k_m"] <= 1.0 and 0.0 <= inp["k_h"] <= 1.0):
        errors.append("k_* haircut outside [0,1]")
    if not (0.0 < inp["share_lab_aws"] < 1.0):
        errors.append("share_lab_aws outside (0,1)")
    seg_sum = inp["oi_na_h1"] + inp["oi_intl_h1"] + inp["oi_aws_h1"]
    if abs(seg_sum - H1_TOTAL_OPERATING_INCOME) > 1.0:
        errors.append(f"segment identity: {seg_sum:.0f} != H1 operating income {H1_TOTAL_OPERATING_INCOME:.0f}")
    if inp["net_debt_ebitda"] > 3.0 or inp["interest_ebit"] > 1.0 / 3.0:
        errors.append("杠杆门 triggered — framework must carry the ROIC decomposition (valuation-rules「杠杆门」)")

    # --- Step 1: trailing base (H1 x2, normalised tax)
    keep = 1.0 - inp["tax_rate"]
    sh = inp["shares_diluted"]
    nopat_aws = inp["oi_aws_h1"] * 2 * keep
    nopat_ret = (inp["oi_na_h1"] + inp["oi_intl_h1"]) * 2 * keep
    core_eps = (nopat_aws + nopat_ret + inp["net_interest_h1"] * 2 * keep) / sh
    ic_ret = inp["ic_group"] - inp["ic_aws"]
    aws_retreat = inp["aws_om_l"] / inp["aws_om_now"]

    # --- Step 4: asset legs
    net_cash = inp["cash"] + (inp["mkt_sec"] - inp["mkt_equity_sec"]) - inp["lt_debt"]
    port_net = inp["port_gross"] - (inp["port_gross"] - inp["port_cost"]) * inp["dtl_rate"]

    def roe_open(e: float, ic0: float, g: float, unbooked: float) -> float:
        if g * unbooked / e >= 1.0:
            raise ValueError("opening-capital roll diverges")
        return e / (ic0 / (1.0 - g * unbooked / e))

    def tier(t: str, k: float, ic_scale: float = 1.0, roic_marg: float | None = None,
             share_lab: float | None = None, r_lab: float | None = None, k_lab: float | None = None,
             g_aws: float | None = None, g_ret: float | None = None, flat: dict | None = None,
             retreat: bool = True) -> dict:
        roic_marg = inp["roic_marg_aws"] if roic_marg is None else roic_marg
        share_lab = inp["share_lab_aws"] if share_lab is None else share_lab
        r_lab = r7t if r_lab is None else r_lab
        k_lab = inp["k_lab"] if k_lab is None else k_lab
        g_aws = inp["g2_aws"] if g_aws is None else g_aws
        g_ret = inp["g2_ret"] if g_ret is None else g_ret
        scale = aws_retreat if (t == "l" and retreat) else 1.0
        n_aws = nopat_aws * scale
        out: dict = {}
        legs = (
            ("aws", n_aws * (1 - share_lab), inp["ic_aws"] * ic_scale * (1 - share_lab), g_aws, r4, roic_marg * scale),
            ("lab", n_aws * share_lab, inp["ic_aws"] * ic_scale * share_lab, g_aws, r_lab, roic_marg * scale),
            ("ret", nopat_ret, ic_ret * ic_scale, g_ret, r4, None),
        )
        for name, n, ic, g, r, rm in legs:
            e, unb = n * k, n / 2.0                      # unbooked 2H26
            roe_avg = roe_open(e, ic, g, unb)
            roe_ret = roe_avg if rm is None else rm      # A4: cloud retains at the marginal ROIC
            pe = perpetual_pe(g, roe_ret, r) if flat is None else flat[name]
            # k_lab leaves the lab sub-leg's value only, never its multiple (axis §3b).
            haircut = (1.0 - k_lab) if name == "lab" else 1.0
            out[name] = dict(e=e, roe=roe_avg, roe_ret=roe_ret, pe=pe, b1=g / roe_ret, unb=unb,
                             val=e * pe * haircut / sh)
        d = inp[f"d_port_{t}"]
        out["port"] = dict(val=port_net * (1 - d) / sh, d=d)
        out["cash"] = dict(val=net_cash / sh)
        deemed = sum(max(1 - inp["payout_3y"] - out[n]["b1"], 0.0) * out[n]["unb"] for n in ("aws", "lab", "ret")) / sh
        pre = sum(v["val"] for v in out.values())
        out["deemed"], out["pre"] = deemed, pre
        out["total"] = pre - inp[f"k_{t}"] * deemed
        return out

    def band(**kw) -> dict:
        return {t: tier(t, inp[f"k_eps_{t}"], **kw) for t in "lmh"}

    base = band()
    L, M, H = (base[t]["total"] for t in "lmh")
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)

    for t in "lmh":
        for name in ("aws", "lab", "ret"):
            b1 = base[t][name]["b1"]
            if not (0.0 < b1 < 1.0):
                errors.append(f"{name} {t}: b1 = g/ROE = {b1:.3f} outside (0,1)")
        if base[t]["ret"]["roe"] > MAX_LEG_ROE:
            errors.append(f"retail {t}: derived ROE {base[t]['ret']['roe']:.1%} > {MAX_LEG_ROE:.0%} — capital allocation artefact")
        # Per dollar of earnings the lab sub-leg must never be worth more than the
        # non-lab one: same terminal basket, so the haircut is what keeps it below.
        if base[t]["lab"]["pe"] * (1.0 - inp["k_lab"]) > base[t]["aws"]["pe"] + 1e-9:
            errors.append(f"tier {t}: lab sub-leg after k_lab out-values the non-lab sub-leg per unit of earnings")

    # A2e-2c: every tier at the M multiples — the ladder must still stand
    flat = {n: base["m"][n]["pe"] for n in ("aws", "lab", "ret")}
    fb = band(flat=flat)
    flat_l, flat_h = fb["l"]["total"], fb["h"]["total"]
    if not (flat_l < M < flat_h):
        print(f"FAIL: flat-multiple ladder collapsed: {flat_l:.2f}/{M:.2f}/{flat_h:.2f}", file=sys.stderr)
        return 1

    # Candidate band: single-house FY2028E point estimate swapped into the M
    # numerator, tier ratios kept, discounted one year (FY+2, r_disc).
    kk = {t: inp["eps_fy28e_single"] / core_eps * (inp[f"k_eps_{t}"] / inp["k_eps_m"]) for t in "lmh"}
    cand = {t: tier(t, kk[t])["total"] / (1 + inp["r_disc"]) for t in "lmh"}

    out_sec = md.split("### Outputs", 1)[-1]
    stated = {
        "L": first_float(r"L = \*\*([0-9.]+)\*\*", out_sec),
        "M": first_float(r"M = \*\*([0-9.]+)\*\*", out_sec),
        "H": first_float(r"H = \*\*([0-9.]+)\*\*", out_sec),
        "A": first_float(r"A = \*\*([0-9.]+)\*\*", out_sec),
        "B": first_float(r"B = \*\*([0-9.]+)\*\*", out_sec),
        "L′": first_float(r"L′ = \*\*([0-9.]+)\*\*", out_sec),
        "M′": first_float(r"M′ = \*\*([0-9.]+)\*\*", out_sec),
        "H′": first_float(r"H′ = \*\*([0-9.]+)\*\*", out_sec),
    }
    for k, v in {"L": L, "M": M, "H": H, "A": A, "B": B, "L′": cand["l"], "M′": cand["m"], "H′": cand["h"]}.items():
        s = stated.get(k)
        if s is None:
            errors.append(f"stated {k} not found")
        elif abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")
    if inp["v_opt"] != 0:
        errors.append("v_opt must be 0: no consensus-referenced option anchor (A13)")

    # ---------------------------------------------------------------- report
    print(f"formula_id={FORMULA_ID}")
    print(f"run-rate NOPAT($B) AWS={nopat_aws / BN:.1f} (lab {nopat_aws * inp['share_lab_aws'] / BN:.1f}) retail={nopat_ret / BN:.1f}"
          f" | core EPS {core_eps:.2f} | k_eps {inp['k_eps_l']:.4f}/{inp['k_eps_m']:.4f}/{inp['k_eps_h']:.4f}"
          f" (FY27E {inp['eps_fy27e_low']}/{inp['eps_fy27e_consensus']}/{inp['eps_fy27e_high']})")
    print(f"IC0($B): AWS {inp['ic_aws'] / BN:.1f} retail {ic_ret / BN:.1f} | avg ROIC on IC0: AWS {nopat_aws / inp['ic_aws']:.1%} retail {nopat_ret / ic_ret:.1%}"
          f" | AWS retention at marginal ROIC {inp['roic_marg_aws']:.1%} (A4)")
    print(f"asset legs $/sh: portfolio net {port_net / sh:.2f} (gross {inp['port_gross'] / BN:.1f}B − DTL) | net cash {net_cash / sh:.2f}")
    print("  tier  k_eps   AWS-non PE(ROEavg/ret)   lab PE   retail PE(ROE)   port(d)   cash   deemed  total")
    for t in "lmh":
        x = base[t]
        print(f"    {t.upper()}  {inp[f'k_eps_{t}']:.4f}  {x['aws']['val']:7.2f} {x['aws']['pe']:5.2f}x({x['aws']['roe']:.1%}/{x['aws']['roe_ret']:.1%})"
              f"  {x['lab']['val']:6.2f} {x['lab']['pe']:5.2f}x  {x['ret']['val']:6.2f} {x['ret']['pe']:5.2f}x({x['ret']['roe']:.1%})"
              f"  {x['port']['val']:6.2f}(-{x['port']['d']:.0%}) {x['cash']['val']:6.2f}  {x['deemed']:5.2f}x k{inp[f'k_{t}']:.2f}  {x['total']:7.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat-multiple ladder (A2e-2c): {flat_l:.2f}/{M:.2f}/{flat_h:.2f}")
    print(f"ratios: L/M {L / M:.3f} H/M {H / M:.3f} (H-L)/2M {(H - L) / 2 / M:.3f} | numerator ratio L/M {inp['k_eps_l'] / inp['k_eps_m']:.3f} H/M {inp['k_eps_h'] / inp['k_eps_m']:.3f}"
          f" | AWS L retreat x{aws_retreat:.4f}")
    print(f"guardrail: own 5y trailing PE band top {inp['pe_own_top']:.2f}x / p50 {inp['pe_own_p50']:.2f}x is DISTORTED (2022 loss year) — disclosure only;"
          f" L/M/H on core EPS {L / core_eps:.1f}/{M / core_eps:.1f}/{H / core_eps:.1f}x; M on FY27E mean {M / inp['eps_fy27e_consensus']:.1f}x")
    print(f"candidate band (JPM FY2028E {inp['eps_fy28e_single']}, single house, 1y @{inp['r_disc']:.0%}): L′={cand['l']:.2f} M′={cand['m']:.2f} H′={cand['h']:.2f}")
    sens = [
        ("AWS marginal ROIC 16.4% (own realised avg-asset basis)", dict(roic_marg=0.164)),
        ("AWS marginal ROIC 13% (realised first-year lower bound)", dict(roic_marg=0.13)),
        ("lab share 48% (= RPO share)", dict(share_lab=0.48)),
        ("lab share 15% (= AI ARR share today)", dict(share_lab=0.15)),
        ("k_lab = 0 (no arrival haircut)", dict(k_lab=0.0)),
        ("single-basket lab (篮 7 15%, no k — the pre-pair ruler)", dict(r_lab=r7, k_lab=0.0)),
        ("g2_aws −1pp", dict(g_aws=inp["g2_aws"] - 0.01)),
        ("g2_ret −1pp", dict(g_ret=inp["g2_ret"] - 0.01)),
        ("g2_ret +1pp", dict(g_ret=inp["g2_ret"] + 0.01)),
        ("no AWS margin retreat in L", dict(retreat=False)),
    ] + [(f"opening IC x{s:.1f} (A4 待补 capital path)", dict(ic_scale=s)) for s in IC_SENSITIVITY]
    for label, kw in sens:
        b = band(**kw)
        sL, sM, sH = (b[t]["total"] for t in "lmh")
        print(f"敏感区 {label}: L/M/H {sL:.2f}/{sM:.2f}/{sH:.2f}")
    print(f"杠杆门: net debt/EBITDA {inp['net_debt_ebitda']:.2f}, interest/EBIT {inp['interest_ebit']:.1%} — not triggered"
          f" | capex axis constituent: 2026 guide ${inp['capex_guide'] / 1e9:.0f}B")

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # every priced r 1:1 — r_perp (AWS non-lab + retail) and the lab sub-leg's
    # terminal basket r_aws_lab_t.  The journey rate r_aws_lab prices nothing in
    # the base deck and r_disc only the candidate band, so neither moves; g, ROE,
    # k_lab, k and the asset legs stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        nonlocal r4
        saved = r4
        r4 = r4 + dr
        try:
            b = band(r_lab=r7t + dr)
            return b["l"]["total"], b["m"]["total"], b["h"]["total"]
        finally:
            r4 = saved

    rf = rf_block(LISTING_CCY, {"r_perp": r4, "r_aws_lab_t": r7t}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1
    # Only a clean run writes, so a FAIL never feeds the daily digest.
    write_rf_readings("AMZN.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
