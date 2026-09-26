#!/usr/bin/env python3
"""0700.HK — Tencent: FY2027E consensus EPS x Gordon multiple + NAV (1-d) + net cash.

formula_id = 0700_sotp_dom_intl_ads_fbs_nav_v4_gordon_v2

Truth source: frameworks/0700.HK.md §3.

gordon_v2: the numerator is the furthest fiscal year >= 2 houses can see
(FY2027E, 33-house low/mean/high in CNY, converted at `fx`; valuation-rules
「构造规则冲突的裁决顺序」②).  FY2028E has a single house (HSBC), so there is no
g1 stage in the deck and `check_transition_years` does not apply; the single
house goes into the candidate band instead -- one extra year at HSBC's own
2026E->2028E CAGR (`g1_fy28_hsbc`, A1c) on the cloud-free operating leg via
two_stage_pe, everything else unchanged.  FY2027 is FY+1, so no discounting
(A2e-3).  One perpetual g2 (peer cross-section reverse-solve, A6,
self excluded) is shared by all three tiers; each tier's ROE is its own FY27
EPS over the book at the OPENING of FY2027 (= end-2026, E_{n+1}/B_n): the
H1'26 book rolled over the 2H26 earnings not yet booked (FY2026E consensus
minus 1H26 actual non-IFRS NI) at the growth-required retention b1 = g/ROE
-- g2 in the deck (no g1 window), the HSBC g1 in the candidate band --
closed form BPS = BPS0 / (1 - g N / EPS) (valuation-rules 裁决表 ② as of
2026-09-21; A6b).  So the multiple only drifts with the numerator.  The four
business legs share that multiple and are split by revenue weight for display
only (A1b).  r is the basket rate: the Inputs `r_perp` row names 篮 4 龙头制造
(A14) and `check_r` requires r to equal that basket's value; g2 is capped at
`g_cap(r)` = min(6%, r - 4%).  The realised 5-year monthly PE band [pe_own_min, pe_own_max]
(IFRS-basis series, denominator `eps_ttm_ifrs`) is a guardrail, never an input.

Run:  python3 frameworks/eval/0700.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import check_g_cap, check_r, implied_g, perpetual_pe, two_stage_pe  # noqa: E402
from eval.lib.inputs import check_missing, ladder, parse_baskets, parse_inputs, report  # noqa: E402
from eval.lib.zones import cut_points, zone_of  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "0700.HK.md"
FORMULA_ID = "0700_sotp_dom_intl_ads_fbs_nav_v4_gordon_v2"
LISTING_CCY = "HKD"
TOL = 0.05  # anchors stated to 1 decimal
LEG_TOL = 0.1  # per-leg table is rounded to 1 decimal
MIN_R_MINUS_G = 0.02  # valuation-rules: below this the multiple sits at the pole

LEGS = ("dom", "intl", "ads", "fbs")
TIERS = ("l", "m", "h")

REQUIRED = [
    "price", "shares", "fx",
    "eps27_l_cny", "eps27_m_cny", "eps27_h_cny", "bps_hkd", "eps26_m_cny", "ni_1h26_cny", "payout_3y",
    "r_perp", "g2", "g1_fy28_hsbc", "n_fy28_cand", "pe_own_min", "pe_own_max", "eps_ttm_ifrs",
    "w_dom", "w_intl", "w_ads", "w_fbs",
    "nav_hkd", "d_l", "d_m", "d_h", "net_cash_cny",
]


def eps_hkd(inp: dict[str, float], tag: str) -> float:
    """FY2027E consensus point in HKD (source is CNY, A1 / A8)."""
    return inp[f"eps27_{tag}_cny"] * inp["fx"]


def scenario(inp: dict[str, float], tag: str, pe_override: float | None = None,
             candidate: bool = False) -> dict[str, float]:
    """One tier -> Gordon multiple, per-leg HKD/share contributions and the anchor.

    `candidate` swaps the perpetual multiple for the A1c two-stage one (HSBC's
    single-house FY2028E year); nothing else in the chain moves.
    """
    eps = eps_hkd(inp, tag)
    # ROE = E_{n+1} / B_n: FY27 EPS over the OPENING-2027 book (= end-2026), not
    # the H1'26 book and not the end-2027 book (that would put retention the
    # year has not yet earned into the denominator; valuation-rules 裁决表 ②
    # as of 2026-09-21; A6b).  The H1'26 book is rolled over the 2H26
    # earnings not yet booked at the GROWTH-REQUIRED retention b1 = g/ROE --
    # g2 in the deck (no g1 window), the HSBC g1 in the candidate band (the
    # growth its stage 1 charges next) -- never at the actual payout
    # complement.  ROE and BPS depend on each other; closed form
    # BPS = BPS0 / (1 - g N / EPS).  FY2027's own retention is NOT rolled.
    g_roll = inp["g1_fy28_hsbc"] if candidate else inp["g2"]
    unbooked = (inp["eps26_m_cny"] - inp["ni_1h26_cny"] / inp["shares"]) * inp["fx"]  # HKD/share, 2H26 only
    bps_open = inp["bps_hkd"] / (1.0 - g_roll * unbooked / eps)
    roe = eps / bps_open
    b1 = g_roll / roe
    excess_cash = ((1.0 - inp["payout_3y"]) - b1) * unbooked  # B bucket: disclosure only, not in BPS
    if pe_override is not None:
        pe = pe_override
    elif candidate:
        pe = two_stage_pe(inp["g1_fy28_hsbc"], int(inp["n_fy28_cand"]), inp["g2"], roe, inp["r_perp"])
    else:
        pe = perpetual_pe(inp["g2"], roe, inp["r_perp"])
    ops = eps * pe
    legs = {leg: ops * inp[f"w_{leg}"] for leg in LEGS}
    nav = inp["nav_hkd"] * (1.0 - inp[f"d_{tag}"]) / inp["shares"]
    cash = inp["net_cash_cny"] * inp["fx"] / inp["shares"]
    out = dict(legs)
    out.update(eps=eps, roe=roe, pe=pe, ops=ops, nav=nav, cash=cash, anchor=ops + nav + cash,
               g_roll=g_roll, unbooked=unbooked, bps_open=bps_open, b1=b1, excess_cash=excess_cash)
    return out


def stated_leg_table(md: str) -> dict[str, list[float]]:
    """Rows of 表1: 档 | 经营腿倍数 | 国内 | 国际 | 广告 | FBS | 经营合计 | NAV | 净现金 | 合计.

    Returns the shared multiple (`PE=x`) followed by the eight HKD/share cells.
    """
    out: dict[str, list[float]] = {}
    for line in md.splitlines():
        if not re.match(r"\|\s*[LMH]\s*\|", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 10:
            continue
        pe = re.search(r"PE=([0-9]+(?:\.[0-9]+)?)", cells[1])
        if not pe:
            continue
        nums: list[float] = [float(pe.group(1))]
        for c in cells[2:10]:
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)", c.replace("**", ""))
            if not m:
                break
            nums.append(float(m.group(1)))
        if len(nums) == 9:
            out[cells[0]] = nums
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

    # --- input discipline ---------------------------------------------------
    # The operating leg is ordinary platform cash flow: the framework names its
    # basket on the r_perp row (A14) and r must be that basket's value.
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (A14)")
    errors += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    if inp["r_perp"] - inp["g2"] < MIN_R_MINUS_G:
        errors.append(f"r_perp - g2 = {inp['r_perp'] - inp['g2']:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    errors += ladder("eps27", inp["eps27_l_cny"], inp["eps27_m_cny"], inp["eps27_h_cny"])
    w_sum = sum(inp[f"w_{leg}"] for leg in LEGS)
    if abs(w_sum - 1.0) > 1e-3:
        errors.append(f"leg weights sum to {w_sum:.4f}, not 1")
    if not (inp["d_l"] > inp["d_m"] > inp["d_h"]):
        errors.append(f"NAV discount must fall L>M>H: {inp['d_l']}/{inp['d_m']}/{inp['d_h']}")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields in Inputs (A2e-7a): {leaked}")
    if errors:
        return report(errors)

    S = {t: scenario(inp, t) for t in TIERS}
    for t in TIERS:
        # b1 in (0,1): the deck prices no negative stage-1 payout, so b1 >= 1 would be an unpriced equity raise
        if not (0.0 < S[t]["b1"] < 1.0):
            errors.append(f"ROE basis {t.upper()}: b1 = g/ROE = {S[t]['b1']:.3f} outside (0,1) — roll diverges, BLOCKED")
    if not (0 < inp["ni_1h26_cny"] / inp["shares"] < inp["eps26_m_cny"]):
        errors.append("1H26 booked NI/share must sit inside the FY2026E consensus")
    if errors:
        return report(errors)
    L, M, H = (S[t]["anchor"] for t in TIERS)
    if not (L < M < H):
        return report([f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}"])
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    # --- valuation-rules guardrail (裁决顺序 ③): whole-ticker multiple on the
    # IFRS TTM EPS that Longbridge's PE series uses, inside the realised band
    for t in TIERS:
        own = S[t]["anchor"] / inp["eps_ttm_ifrs"]
        if not (inp["pe_own_min"] - 1e-9 <= own <= inp["pe_own_max"] + 1e-9):
            errors.append(
                f"guardrail: {t.upper()} = {own:.2f}x trailing adj EPS outside own band "
                f"[{inp['pe_own_min']}, {inp['pe_own_max']}] — stop, back to the conversation"
            )

    # --- A2e-2c flat ladder: every tier at the M-tier multiple -------------
    flat = {t: scenario(inp, t, pe_override=S["m"]["pe"])["anchor"] for t in TIERS}
    if not (flat["l"] < flat["m"] < flat["h"]):
        errors.append(f"flat-multiple ladder broken: {flat}")

    # --- A1c candidate band: one extra year at the single house's CAGR --------
    cand_S = {t: scenario(inp, t, candidate=True) for t in TIERS}
    cand = {t: cand_S[t]["anchor"] for t in TIERS}
    if not (cand["l"] < cand["m"] < cand["h"]):
        errors.append(f"candidate band not ordered: {cand}")

    # --- stated anchors / cut points / zone ---------------------------------
    out_sec = md.split("### Outputs", 1)[-1]
    cm = re.findall(r"候选带（[^）]+）[^\n]*?L′ = \*\*([0-9.]+)\*\*[^\n]*?M′ = \*\*([0-9.]+)\*\*[^\n]*?H′ = \*\*([0-9.]+)\*\*", out_sec)
    if len(cm) != 1:
        errors.append(f"expected exactly one 候选带 line, found {len(cm)}")
    else:
        for tag, stated_c in zip(("l", "m", "h"), cm[0]):
            if abs(float(stated_c) - cand[tag]) > TOL:
                errors.append(f"候选带 {tag.upper()}′: stated {stated_c} vs recomputed {cand[tag]:.4f}")
    for key, val in (("L", L), ("M", M), ("H", H), ("A", A), ("B", B)):
        m = re.search(rf"{key} = \*\*([0-9.]+)\*\*", out_sec)
        if not m:
            errors.append(f"stated {key} not found")
        elif abs(float(m.group(1)) - val) > TOL:
            errors.append(f"{key}: stated {m.group(1)} vs recomputed {val:.4f}")
    zm = re.search(r"zone = \*\*`([a-z_]+)`\*\*", out_sec)
    if not zm or zm.group(1) != zone:
        errors.append(f"zone: stated {zm.group(1) if zm else None} vs recomputed {zone}")

    stated_legs = stated_leg_table(out_sec)
    names = ("国内", "国际", "广告", "FBS", "经营合计", "NAV", "净现金", "合计")
    for tag in ("L", "M", "H"):
        row = stated_legs.get(tag)
        s = S[tag.lower()]
        if row is None:
            errors.append(f"leg table row {tag} not found")
            continue
        if abs(row[0] - s["pe"]) > 0.01:
            errors.append(f"leg table {tag}/PE: stated {row[0]} vs recomputed {s['pe']:.3f}")
        want = [s["dom"], s["intl"], s["ads"], s["fbs"], s["ops"], s["nav"], s["cash"], s["anchor"]]
        for name, got, exp in zip(names, row[1:], want):
            if abs(got - exp) > LEG_TOL:
                errors.append(f"leg table {tag}/{name}: stated {got} vs recomputed {exp:.2f}")

    zone_nums: set[float] = set()
    for line in out_sec.splitlines():
        if line.startswith("| `"):
            cells = line.strip().strip("|").split("|")
            if len(cells) >= 3:
                zone_nums.update(float(x) for x in re.findall(r"([0-9]+\.[0-9]+)", cells[2]))
    for name, val in (("L", L), ("A", A), ("B", B), ("H", H)):
        if not any(abs(val - z) <= TOL for z in zone_nums):
            errors.append(f"zone table missing boundary {name}={val:.1f}")

    # --- report -------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"g2={inp['g2']:.4f} (peer reverse-solve, self excluded) r={inp['r_perp']} (篮 {baskets['r_perp']})  cap ok; "
          f"numerator FY2027E (furthest >=2-house year; FY2028 single house -> no g1)")
    for t in TIERS:
        s = S[t]
        print(f"{t.upper()}: eps27 {inp[f'eps27_{t}_cny']:.2f} CNY = {s['eps']:.2f} HKD roe {s['roe']:.4f} pe {s['pe']:.3f}"
              f"  ops {s['ops']:.1f} nav {s['nav']:.1f} cash {s['cash']:.1f} -> {s['anchor']:.1f}"
              f"  | own-band {s['anchor'] / inp['eps_ttm_ifrs']:.2f}x in [{inp['pe_own_min']}, {inp['pe_own_max']}]")
    print(f"ROE basis: BPS_open 2027 = {'/'.join(f'{S[t]['bps_open']:.2f}' for t in TIERS)} HKD "
          f"(H1'26 book {inp['bps_hkd']:.2f} rolled over unbooked 2H26 {S['m']['unbooked']:.2f} HKD at "
          f"b1 = g/ROE = {'/'.join(f'{S[t]['b1']:.3f}' for t in TIERS)}, g_roll {S['m']['g_roll']:.2%}); "
          f"old basis (H1'26 book) would read ROE {'/'.join(f'{S[t]['eps'] / inp['bps_hkd']:.2%}' for t in TIERS)}")
    print(f"B bucket: (actual retention {1 - inp['payout_3y']:.0%} − b1) × unbooked = "
          f"{'/'.join(f'{S[t]['excess_cash']:.2f}' for t in TIERS)} HKD/share modelled-as-distributed, "
          f"actually retained (disclosure only; not a leg, not in BPS)")
    print(f"flat ladder @ PE_M: {flat['l']:.1f}/{flat['m']:.1f}/{flat['h']:.1f}")
    print(f"candidate (FY2028E HSBC single, g1 {inp['g1_fy28_hsbc']:.4f} x {int(inp['n_fy28_cand'])}y): "
          f"{cand['l']:.1f}/{cand['m']:.1f}/{cand['h']:.1f}  (book rolled at g1: ROE "
          f"{'/'.join(f'{cand_S[t]['roe']:.2%}' for t in TIERS)}, b1 {'/'.join(f'{cand_S[t]['b1']:.3f}' for t in TIERS)})")
    # A2e-3: a two-stage leg reports its multiple on the post-transition-year
    # numerator; the FY2027 reading carries (1+g1) and is a cross line only
    post = (1.0 + inp["g1_fy28_hsbc"]) ** int(inp["n_fy28_cand"])
    print("  candidate PE on FY2027 numerator: " + "/".join(f"{cand_S[t]['pe']:.3f}" for t in TIERS)
          + "  | on FY2028 (post-transition) numerator: " + "/".join(f"{cand_S[t]['pe'] / post:.3f}" for t in TIERS))
    print(f"decompose: L/M {L / M:.3f} = num {S['l']['eps'] / S['m']['eps']:.3f} x pe "
          f"{S['l']['pe'] / S['m']['pe']:.3f} (+NAV d) | H/M {H / M:.3f} = num "
          f"{S['h']['eps'] / S['m']['eps']:.3f} x pe {S['h']['pe'] / S['m']['pe']:.3f} (+NAV d)")
    # 裁决顺序 ③「带即证据」: g the band edges pay at the M-tier ROE
    for edge in (inp["pe_own_min"], inp["pe_own_max"]):
        pe_edge = (edge * inp["eps_ttm_ifrs"] - S["m"]["nav"] - S["m"]["cash"]) / S["m"]["eps"]
        g_edge, ok = implied_g(pe_edge, S["m"]["roe"], inp["r_perp"])
        print(f"  band edge {edge}x -> ops PE {pe_edge:.2f} -> g {g_edge:+.2%}{'' if ok else ' (ill-conditioned)'}")
    print(f"L={L:.1f} M={M:.1f} H={H:.1f} A={A:.1f} B={B:.1f}")
    print(f"price={inp['price']} zone={zone}")
    for g in (inp["g2"] - 0.01, inp["g2"] + 0.01):
        alt = {t: scenario(dict(inp, g2=g), t)["anchor"] for t in TIERS}
        print(f"  sens g2={g:.4f}: {alt['l']:.1f}/{alt['m']:.1f}/{alt['h']:.1f}")
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_perp 1:1 on the operating leg; g2, EPS, NAV discounts and net cash stay
    # put.  Disclosure only — the anchors above are the 中枢 column.
    def band_rf(dr: float) -> tuple[float, float, float]:
        shifted = dict(inp, r_perp=inp["r_perp"] + dr)
        return tuple(scenario(shifted, t)["anchor"] for t in TIERS)

    rf = rf_block(LISTING_CCY, {"r_perp": inp["r_perp"]}, band_rf, inp["price"])
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    if errors:
        return report(errors)
    # Only a clean run feeds the daily digest.
    write_rf_readings("0700.HK", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
