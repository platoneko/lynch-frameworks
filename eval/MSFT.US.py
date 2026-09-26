#!/usr/bin/env python3
"""MSFT.US (Microsoft) valuation eval — recompute anchors from frameworks/MSFT.US.md.

frameworks/MSFT.US.md is the source of truth; this script re-derives
L/M/H / A/B from the §3 Inputs table and exits 1 on mismatch.  The doc carries no
current price (AGENTS.md「现价 — 禁写契约」): which zone a quote falls in is
derived live by the daily digest and the app, so nothing here reads a price.

formula_id: msft_fwd_numerator_gordon_ai_dc_openai_v1

Ruler (a): SOTP on a FORWARD numerator — the FY2028E sell-side EPS range
(33 houses) carried onto the two NEW reporting segments (FY2027 recast:
Agents & Infrastructure / Devices & Consumer) by one scalar per tier —
priced at ONE growth rate per leg.  Four Gordon legs + asset legs:

    Azure · non-OpenAI      篮 4 r 10%   retention at Azure's MARGINAL steady-state ROIC
    Azure · OpenAI          篮 7→4 pair  (revenue from a counterparty MSFT itself funds today;
                                         a paying customer once OpenAI makes it — capitalised
                                         at 10%, arrival risk in the shared k_lab)
    A&I rest (M365 etc.)    篮 4 r 10%   retention at its own average ROE
    Devices & Consumer      篮 4 r 10%   retention at its own average ROE
    OpenAI stake + other equity investments (discount band, net of DTL)
    net cash

Cross-check (b): the FY26 three OLD segments (PBP / IC / MPC), each with its
own g and allocated capital, the IC leg retaining at the same marginal ROIC.
Printed and compared to (a) as an anchor-to-anchor reading; it sets nothing.

Run:  python3 frameworks/eval/MSFT.US.py
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

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "MSFT.US.md"
FORMULA_ID = "msft_fwd_numerator_gordon_ai_dc_openai_v1"
TOL = 0.05
BN = 1e3
MIN_R_MINUS_G = 0.02
K_LADDER_TOL = 1e-4
IC_SENSITIVITY = (1.20, 1.40)
MAX_LEG_ROE = 0.60
LISTING_CCY = "USD"


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
    "oi_total_fy26", "share_ai_oi", "rev_azure_fy26", "rev_ic_fy26", "oi_ic_fy26", "rev_openai_fy26",
    "r_perp", "r_az_lab", "r_az_lab_t", "k_lab",
    "ic_group", "ic_azure", "ic_dc", "roic_marg_az",
    "g2_ai", "g2_dc",
    "eps_adj_fy26", "eps_fy27e", "k_eps_l", "k_eps_m", "k_eps_h",
    "eps_fy28e_low", "eps_fy28e_consensus", "eps_fy28e_high",
    "cash_sti", "lt_debt",
    "openai_book", "openai_post", "openai_stake", "other_eq_inv", "dtl_rate",
    "d_oai_l", "d_oai_m", "d_oai_h",
    "payout_3y", "k_l", "k_m", "k_h",
    "pe_own_top", "pe_own_p50",
    "capex_fy26", "net_debt_ebitda", "interest_ebit",
    "oi_pbp_fy26", "oi_mpc_fy26", "ic_pbp", "g_b_pbp", "g_b_mpc",
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

    r4, r7, r7t = inp["r_perp"], inp["r_az_lab"], inp["r_az_lab_t"]
    # The OpenAI sub-leg is a basket PAIR (valuation-rules「篮子对」): 篮 7 is what
    # the counterparty is today, 篮 4 what it is if it makes it.  Every leg here is
    # single-stage, so the steady state capitalises at the terminal rate and the
    # shared k_lab carries all of the arrival risk (_AXIS.frontier-lab-funding §3).
    errors += check_basket_pair(r7, r7t, "lab", baskets.get("r_az_lab"), baskets.get("r_az_lab_t"))
    errors += check_k_declared(r7, r7t, (inp["k_lab"],) * 3, "k_lab")
    errors += [f"axis: {e}" for e in check_lab_mount(inp["k_lab"])]
    for field, r in (("r_perp", r4), ("r_az_lab", r7), ("r_az_lab_t", r7t)):
        if field not in baskets:
            errors.append(f"{field}: Inputs source cell names no 篮 N")
        errors += check_r(r, field, baskets.get(field))
    for field, g, r in (("g2_ai", inp["g2_ai"], r4), ("g2_ai@lab", inp["g2_ai"], r7), ("g2_dc", inp["g2_dc"], r4)):
        errors += check_g_cap(g, r, field)
        if r - g < MIN_R_MINUS_G:
            errors.append(f"{field}: r - g = {r - g:.2%} < {MIN_R_MINUS_G:.0%}")
    if not (inp["k_eps_l"] < inp["k_eps_m"] < inp["k_eps_h"]):
        errors.append("k_eps_* ladder not increasing")
    mean = inp["eps_fy28e_consensus"]
    for tier, endpoint in (("l", "eps_fy28e_low"), ("h", "eps_fy28e_high")):
        want, got = inp[endpoint] / mean, inp[f"k_eps_{tier}"] / inp["k_eps_m"]
        if abs(got - want) > K_LADDER_TOL:
            errors.append(f"k_eps_{tier}/k_eps_m = {got:.5f} != {endpoint}/consensus = {want:.5f}")
    if abs(inp["k_eps_m"] - mean / inp["eps_adj_fy26"]) > K_LADDER_TOL:
        errors.append("k_eps_m != eps_fy28e_consensus / eps_adj_fy26")
    if not (1.0 >= inp["d_oai_l"] > inp["d_oai_m"] > inp["d_oai_h"] >= 0.0):
        errors.append("d_oai_* must be a decreasing band inside [0,1]")
    if not all(0.0 <= inp[f"k_{t}"] <= 1.0 for t in "lmh"):
        errors.append("k_* haircut outside [0,1]")
    if abs(inp["ic_azure"] + inp["ic_dc"] - inp["ic_group"]) > inp["ic_group"]:
        errors.append("capital split inconsistent")
    if inp["net_debt_ebitda"] > 3.0 or inp["interest_ebit"] > 1.0 / 3.0:
        errors.append("杠杆门 triggered — framework must carry the ROIC decomposition")

    # --- Step 1: FY26 base on the recast segments
    keep = 1.0 - inp["tax_rate"]
    sh = inp["shares_diluted"]
    oi_ai = inp["oi_total_fy26"] * inp["share_ai_oi"]
    oi_dc = inp["oi_total_fy26"] * (1 - inp["share_ai_oi"])
    azure_om = inp["oi_ic_fy26"] / inp["rev_ic_fy26"]           # proxy (待补)
    oi_azure = inp["rev_azure_fy26"] * azure_om
    share_az = oi_azure / oi_ai
    share_lab_az = inp["rev_openai_fy26"] / inp["rev_azure_fy26"]
    nopat_ai, nopat_dc = oi_ai * keep, oi_dc * keep
    core_eps = (nopat_ai + nopat_dc) / sh
    ic_rest = inp["ic_group"] - inp["ic_azure"] - inp["ic_dc"]
    k27 = inp["eps_fy27e"] / inp["eps_adj_fy26"]                 # FY27 unbooked bridge

    # --- asset legs
    openai_gross = inp["openai_post"] * inp["openai_stake"]
    openai_net = openai_gross - (openai_gross - inp["openai_book"]) * inp["dtl_rate"]
    net_cash = inp["cash_sti"] - inp["lt_debt"]

    def roe_open(e: float, ic0: float, g: float, unbooked: float) -> float:
        if g * unbooked / e >= 1.0:
            raise ValueError("opening-capital roll diverges")
        return e / (ic0 / (1.0 - g * unbooked / e))

    def tier(t: str, k: float, ic_scale: float = 1.0, roic_marg: float | None = None,
             share_lab: float | None = None, r_lab: float | None = None, k_lab: float | None = None,
             g_ai: float | None = None, g_dc: float | None = None, flat: dict | None = None) -> dict:
        roic_marg = inp["roic_marg_az"] if roic_marg is None else roic_marg
        share_lab = share_lab_az if share_lab is None else share_lab
        r_lab = r7t if r_lab is None else r_lab
        k_lab = inp["k_lab"] if k_lab is None else k_lab
        g_ai = inp["g2_ai"] if g_ai is None else g_ai
        g_dc = inp["g2_dc"] if g_dc is None else g_dc
        n_az, n_rest = nopat_ai * share_az, nopat_ai * (1 - share_az)
        out: dict = {}
        legs = (
            ("az", n_az * (1 - share_lab), inp["ic_azure"] * ic_scale * (1 - share_lab), g_ai, r4, roic_marg),
            ("lab", n_az * share_lab, inp["ic_azure"] * ic_scale * share_lab, g_ai, r_lab, roic_marg),
            ("rest", n_rest, ic_rest * ic_scale, g_ai, r4, None),
            ("dc", nopat_dc, inp["ic_dc"] * ic_scale, g_dc, r4, None),
        )
        for name, n, ic, g, r, rm in legs:
            e, unb = n * k, n * k27                          # unbooked FY27
            roe_avg = roe_open(e, ic, g, unb)
            roe_ret = roe_avg if rm is None else rm          # A4: Azure retains at the marginal ROIC
            pe = perpetual_pe(g, roe_ret, r) if flat is None else flat[name]
            # k_lab leaves the OpenAI sub-leg's value only, never its multiple (axis §3b).
            haircut = (1.0 - k_lab) if name == "lab" else 1.0
            out[name] = dict(e=e, roe=roe_avg, roe_ret=roe_ret, pe=pe, b1=g / roe_ret, unb=unb,
                             val=e * pe * haircut / sh)
        d = inp[f"d_oai_{t}"]
        out["oai"] = dict(val=(openai_net + inp["other_eq_inv"]) * (1 - d) / sh, d=d)
        out["cash"] = dict(val=net_cash / sh)
        deemed = sum(max(1 - inp["payout_3y"] - out[n]["b1"], 0.0) * out[n]["unb"] for n in ("az", "lab", "rest", "dc")) / sh
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
        for name in ("az", "lab", "rest", "dc"):
            b1 = base[t][name]["b1"]
            if not (0.0 < b1 < 1.0):
                errors.append(f"{name} {t}: b1 = {b1:.3f} outside (0,1)")
        # The >60% leg-ROE guard is judged on the M tier (the leg's own state);
        # L/H are scenario numerators on the same capital and are only printed.
        for name in ("rest", "dc"):
            if t == "m" and base[t][name]["roe"] > MAX_LEG_ROE:
                errors.append(f"{name} {t}: derived ROE {base[t][name]['roe']:.1%} > {MAX_LEG_ROE:.0%}")
        # Per dollar of earnings the OpenAI sub-leg must never be worth more than the
        # rest of Azure: same terminal basket, so the haircut keeps it below.
        if base[t]["lab"]["pe"] * (1.0 - inp["k_lab"]) > base[t]["az"]["pe"] + 1e-9:
            errors.append(f"tier {t}: OpenAI sub-leg after k_lab out-values the non-OpenAI sub-leg per unit of earnings")
    if H / core_eps > inp["pe_own_top"]:
        errors.append(f"生成的倍数越出自身实测带: H/core_eps {H / core_eps:.2f}x > {inp['pe_own_top']:.2f}x")
    flat = {n: base["m"][n]["pe"] for n in ("az", "lab", "rest", "dc")}
    fb = band(flat=flat)
    flat_l, flat_h = fb["l"]["total"], fb["h"]["total"]
    if not (flat_l < M < flat_h):
        print(f"FAIL: flat-multiple ladder collapsed: {flat_l:.2f}/{M:.2f}/{flat_h:.2f}", file=sys.stderr)
        return 1

    # --- cross-check (b): FY26 old segments
    share_lab_ic = inp["rev_openai_fy26"] / inp["rev_ic_fy26"]
    ic_old = {"pbp": inp["ic_pbp"], "ic": inp["ic_azure"] * inp["rev_ic_fy26"] / inp["rev_azure_fy26"], "mpc": inp["ic_dc"]}
    oi_old = {"pbp": inp["oi_pbp_fy26"], "ic": inp["oi_ic_fy26"], "mpc": inp["oi_mpc_fy26"]}
    g_old = {"pbp": inp["g_b_pbp"], "ic": inp["g2_ai"], "mpc": inp["g_b_mpc"]}

    def tier_b(t: str) -> tuple[float, dict]:
        k = inp[f"k_eps_{t}"]
        out: dict = {}
        for name in ("pbp", "ic", "mpc"):
            n, ic, g = oi_old[name] * keep, ic_old[name], g_old[name]
            parts = ((name, n, ic, r4, None),) if name != "ic" else (
                ("ic-non", n * (1 - share_lab_ic), ic * (1 - share_lab_ic), r4, inp["roic_marg_az"]),
                ("ic-lab", n * share_lab_ic, ic * share_lab_ic, r7t, inp["roic_marg_az"]),
            )
            for pn, nn, icc, r, rm in parts:
                e, unb = nn * k, nn * k27
                roe = roe_open(e, icc, g, unb)
                pe = perpetual_pe(g, roe if rm is None else rm, r)
                haircut = (1.0 - inp["k_lab"]) if pn == "ic-lab" else 1.0
                out[pn] = dict(e=e, roe=roe, pe=pe, b1=g / (roe if rm is None else rm), unb=unb,
                               val=e * pe * haircut / sh)
        d = inp[f"d_oai_{t}"]
        deemed = sum(max(1 - inp["payout_3y"] - v["b1"], 0.0) * v["unb"] for v in out.values()) / sh
        total = sum(v["val"] for v in out.values()) + (openai_net + inp["other_eq_inv"]) * (1 - d) / sh + net_cash / sh - inp[f"k_{t}"] * deemed
        return total, out

    bres = {t: tier_b(t) for t in "lmh"}
    Lb, Mb, Hb = (bres[t][0] for t in "lmh")

    out_sec = md.split("### Outputs", 1)[-1]
    stated = {k: first_float(rf"{k} = \*\*([0-9.]+)\*\*", out_sec) for k in ("L", "M", "H", "A", "B")}
    for k, v in {"L": L, "M": M, "H": H, "A": A, "B": B}.items():
        s = stated.get(k)
        if s is None:
            errors.append(f"stated {k} not found")
        elif abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")
    if inp["v_opt"] != 0:
        errors.append("v_opt must be 0: no consensus-referenced option anchor")

    # ---------------------------------------------------------------- report
    print(f"formula_id={FORMULA_ID}")
    print(f"FY26 base: A&I OI {oi_ai / BN:.1f}B ({inp['share_ai_oi']:.0%}) of which Azure {oi_azure / BN:.1f}B ({share_az:.1%}, margin proxy {azure_om:.1%}) | D&C {oi_dc / BN:.1f}B"
          f" | OpenAI = {share_lab_az:.1%} of Azure revenue | core EPS {core_eps:.2f} vs adj EPS {inp['eps_adj_fy26']}")
    print(f"k_eps {inp['k_eps_l']:.5f}/{inp['k_eps_m']:.5f}/{inp['k_eps_h']:.5f} (FY28E {inp['eps_fy28e_low']}/{inp['eps_fy28e_consensus']}/{inp['eps_fy28e_high']} ÷ {inp['eps_adj_fy26']}); FY27 bridge {k27:.4f}")
    print(f"IC0($B): Azure {inp['ic_azure'] / BN:.1f} rest {ic_rest / BN:.1f} D&C {inp['ic_dc'] / BN:.1f} = {inp['ic_group'] / BN:.1f}"
          f" | avg ROIC on IC0: Azure {nopat_ai * share_az / inp['ic_azure']:.1%} rest {nopat_ai * (1 - share_az) / ic_rest:.1%} D&C {nopat_dc / inp['ic_dc']:.1%}"
          f" | Azure retention at marginal ROIC {inp['roic_marg_az']:.1%} (A4)")
    print(f"asset legs $/sh: OpenAI 25% x {inp['openai_post'] / BN:.0f}B = {openai_gross / BN:.0f}B gross, net of DTL {openai_net / sh:.2f}; other eq inv {inp['other_eq_inv'] / sh:.2f}; net cash {net_cash / sh:.2f}")
    print("  tier  k_eps   Azure-non PE(ROEavg/ret)  lab PE   rest PE(ROE)     D&C PE(ROE)     oai(d)   cash  deemed(k)   total")
    for t in "lmh":
        x = base[t]
        print(f"    {t.upper()}  {inp[f'k_eps_{t}']:.4f}  {x['az']['val']:6.2f} {x['az']['pe']:5.2f}x({x['az']['roe']:.1%}/{x['az']['roe_ret']:.1%})"
              f"  {x['lab']['val']:5.2f} {x['lab']['pe']:4.2f}x  {x['rest']['val']:6.2f} {x['rest']['pe']:5.2f}x({x['rest']['roe']:.1%})"
              f"  {x['dc']['val']:5.2f} {x['dc']['pe']:5.2f}x({x['dc']['roe']:.1%})  {x['oai']['val']:5.2f}(-{x['oai']['d']:.0%}) {x['cash']['val']:5.2f}"
              f"  {x['deemed']:5.2f}(k{inp[f'k_{t}']:.2f})  {x['total']:7.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat-multiple ladder (A2e-2c): {flat_l:.2f}/{M:.2f}/{flat_h:.2f}")
    print(f"ratios: L/M {L / M:.3f} H/M {H / M:.3f} (H-L)/2M {(H - L) / 2 / M:.3f} | numerator ratio L/M {inp['k_eps_l'] / inp['k_eps_m']:.3f} H/M {inp['k_eps_h'] / inp['k_eps_m']:.3f}")
    print(f"guardrail: H/core_eps {H / core_eps:.2f}x vs own 5y band top {inp['pe_own_top']:.2f}x (p50 {inp['pe_own_p50']:.2f}x) — {'OK' if H / core_eps <= inp['pe_own_top'] else '越出'};"
          f" L/M/H on core EPS {L / core_eps:.1f}/{M / core_eps:.1f}/{H / core_eps:.1f}x; M on FY28E mean {M / mean:.1f}x")
    print(f"cross-check (b) FY26 old segments: L/M/H {Lb:.2f}/{Mb:.2f}/{Hb:.2f} (M {Mb / M - 1:+.1%} vs a)")
    print("    " + " | ".join(f"{n} {v['val']:.2f}({v['pe']:.2f}x ROE {v['roe']:.1%})" for n, v in bres["m"][1].items())
          + "  [PBP ROE > 60% = allocation artefact; b is a cross-check only]")

    sens = [
        ("Azure marginal ROIC 20% (consensus-implied FY26→28)", dict(roic_marg=0.20)),
        ("Azure marginal ROIC 10% (= r; realised first-year lower bound)", dict(roic_marg=0.10)),
        ("OpenAI share of Azure 30% (FY28 ramp of the $250B commitment)", dict(share_lab=0.30)),
        ("k_lab = 0 (no arrival haircut)", dict(k_lab=0.0)),
        ("single-basket OpenAI (篮 7 15%, no k — the pre-pair ruler)", dict(r_lab=r7, k_lab=0.0)),
        ("g2_ai −0.5pp", dict(g_ai=inp["g2_ai"] - 0.005)),
        ("g2_ai −1pp", dict(g_ai=inp["g2_ai"] - 0.01)),
        ("g2_dc ±1pp", dict(g_dc=inp["g2_dc"] + 0.01)),
    ] + [(f"opening IC x{s:.1f} (A4 待补 capital path)", dict(ic_scale=s)) for s in IC_SENSITIVITY]
    for label, kw in sens:
        b = band(**kw)
        sL, sM, sH = (b[t]["total"] for t in "lmh")
        print(f"敏感区 {label}: L/M/H {sL:.2f}/{sM:.2f}/{sH:.2f}")
    print(f"杠杆门: net debt/EBITDA {inp['net_debt_ebitda']:.2f}, interest/EBIT {inp['interest_ebit']:.1%} — not triggered"
          f" | capex axis constituent: FY26 capex ${inp['capex_fy26'] / 1e9:.0f}B (FY27 guide 待补)")
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves every
    # priced r 1:1 — r_perp (Azure-non / rest / D&C) and the OpenAI sub-leg's terminal
    # basket r_az_lab_t (r_az_lab only gates g, it prices nothing).  g, ROE, k_lab, the
    # asset legs and the numerator stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        nonlocal r4, r7t
        saved = r4, r7t
        r4, r7t = r4 + dr, r7t + dr
        try:
            b = band()
            return b["l"]["total"], b["m"]["total"], b["h"]["total"]
        finally:
            r4, r7t = saved

    rf = rf_block(LISTING_CCY, {"r_perp": r4, "r_az_lab_t": r7t}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1
    # Only a clean run writes, so a FAIL never feeds the daily digest.
    write_rf_readings("MSFT.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
