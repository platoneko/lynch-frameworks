#!/usr/bin/env python3
"""603799.SH (Huayou Cobalt) valuation eval — recompute anchors from frameworks/603799.SH.md.

frameworks/603799.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on any mismatch.

formula_id: huayou_eight_leg_gp_bridge_conv_ladder_gordon_v2

What makes this ticker's ruler different from the other two A-share cyclicals:
the scenario ladder does NOT live in the multiple, and it does not live in a
single commodity price either.  Eight legs each ride their own measured
half-year series (only copper is shifted by a price ladder), and the step that
actually moves the anchors is `conv` — the pretax-to-parent conversion rate,
which fell from 73.4% (FY2025) to 55.7% (2026H1) to 38.8% (2026Q2) because the
fastest-growing assets are the ones with the largest minority stakes
(Chengdu BAMO 63.14%, Huafei 49%, Huayue 40%).  Holding `conv` constant would
hide the single biggest variable in the story, so it is laddered from the 2026
quarterly prints — same year, same source, three quantiles (skill A2e-2b).

The multiple is GENERATED (A13, skill A2e-5b): perpetual_pe(g2, ROE_x, r) with
one g2 shared by all tiers — the copper and lithium peer clusters reverse-solved
and blended by gross-profit weight, the six legs without a cluster at 0 — and
the tier ROE from parent net profit over parent book.  The ladder therefore
lives entirely in the numerator; the tiny spread in multiples is ROE mechanics,
not a counter-cyclical policy on top of the conv ladder (that would price the
cycle twice).  The guardrail is NOT the own 5y PE band (printed at a far lower
earnings level, A17) but the months whose market-visible TTM EPS matched the M
tier (A18, valuation-rules ④): the M multiple must sit inside that print band,
and the zone must survive g2 ±1pp and the print evidence range.

The L anchor is an asset floor, not an earnings scenario: every plausible opex
treatment puts the earnings scenario below the measured PB floor of 1.0228
(printed at the 2024-06 low of 20.82).  Guard 6 below is the skill A2e-1 test —
if the earnings scenario drops below 30% of M, the earnings ruler has failed at
L and the framework must go back to conversation rather than quietly ship.

Pomalaa (12 kt/yr Ni, first output ~end-2026) never enters the base: it is an
option priced at k=1 x the ticker's own realised MHP unit gross profit,
discounted one year (A11); 表3 = base_k + p_k x V_opt with P_K an eval constant.

Gross-profit style inputs are in 亿 CNY and already annualised (2026H1 x 2).

Run:  python3 eval/603799.SH.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.lib.axes import load_au_cu_rungs  # noqa: E402
from eval.lib.gordon import check_g_cap, check_r, implied_g, perpetual_pe  # noqa: E402
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    outputs_section,
    parse_inputs,
)
from eval.lib.zones import zone_of  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FRAMEWORK = REPO / "frameworks" / "603799.SH.md"
PEER = REPO / "frameworks" / "601899.SH.md"
FORMULA_ID = "huayou_eight_leg_gp_bridge_conv_ladder_gordon_v2"
YI = 1e8

# Audited baseline: 2026 interim net profit to parent x 2 (35.074054亿 x 2).
# The M scenario re-uses the interim segment table verbatim, so its recomputed
# net profit must land back on this number — that is what welds the eight-leg
# bridge to the filing.
BASE_NP_PARENT_YI = 70.1481
BASE_NP_TOL_YI = 0.5

# skill A2e-1: floor may win, but if the earnings scenario falls below this
# share of M the earnings ruler has failed at L and must be re-opened.
SCENARIO_L_MIN_RATIO = 0.30

G2_TOL = 1e-4             # stated g2 must equal the cluster blend recomputed from its parts (A13)
MIN_PRINT_MONTHS = 6      # A18: fewer EPS-matched months than this -> corroboration only, not a g2 source
G2_LEVER_PP = 0.01        # valuation-rules: zone must hold at g2 ± this
TOL = 0.05
# 表3 per-tier credit on the Pomalaa option (A11): 拍值, never an Input, never the base.
P_K = (0.0, 0.25, 1.0)

# The shared USD copper ladder: our field -> the peer framework's field.
SHARED_LADDER = {"p_cu_l": "lme_cu_l", "p_cu_m": "lme_cu_m", "p_cu_h": "lme_cu_h"}

REQUIRED = [
    "price", "shares", "bps", "pb_floor",
    "gp_ni_prod_m", "gp_ni_prod_h",
    "gp_ni_mhp_m", "gp_ni_mhp_h",
    "gp_co_m", "gp_li_m", "gp_cam_m",
    "gp_pcam_m", "gp_pcam_h",
    "gp_trade_m",
    "rev_cu_base", "cost_cu_base",
    "p_cu_l", "p_cu_m", "p_cu_h",
    "opex", "pretax_l",
    "conv_l", "conv_m", "conv_h",
    "equity_parent", "r_perp", "g_cu_cluster", "g_li_cluster", "w_cu_gp", "w_li_gp", "g2",
    "pe_print_lo", "pe_print_hi", "g_print_m", "g_print_lo", "g_print_hi", "n_print_m",
    "pomalaa_kt", "mhp_unit_gp", "t_opt",
    "eps_cons_lo", "eps_cons_mean", "eps_cons_hi",
]
CONSENSUS_BAND = 0.20  # ②-b: |EPS_M / consensus mean - 1| beyond this needs a named measured variable

# Legs that are already at their measured peak in the interim print, so the H
# scenario leaves them where they are (see A7 / A8 / A9 / A5).
FLAT_LEGS = ("gp_co_m", "gp_li_m", "gp_cam_m", "gp_trade_m")


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    # --- sanity guards (see §3 校验步骤) -------------------------------------
    errors += ladder("copper price", inp["p_cu_l"], inp["p_cu_m"], inp["p_cu_h"])
    errors += ladder("conv", inp["conv_l"], inp["conv_m"], inp["conv_h"])
    # Perpetuity inputs (A13): r on a repo tier, g2 under the cap and equal to
    # the gross-profit-weighted cluster blend it claims to be.
    errors += check_r(inp["r_perp"], "r_perp")
    errors += check_g_cap(inp["g2"], "g2")
    g2_blend = inp["g_cu_cluster"] * inp["w_cu_gp"] + inp["g_li_cluster"] * inp["w_li_gp"]
    if abs(inp["g2"] - g2_blend) > G2_TOL:
        errors.append(f"g2={inp['g2']} != cluster blend {g2_blend:.5f} (A13)")
    if inp["g2"] < 0:
        errors.append("g2 < 0 contradicts the same-world gate: consensus FY25->FY26E is up (A1/A13)")
    if not (0 < inp["pe_print_lo"] < inp["pe_print_hi"]):
        errors.append("print band malformed (A18)")
    # `p_cu_*` is the copper price ladder; the banned names are the option credits.
    leaked = [k for k in inp if k in ("p", "p_l", "p_m", "p_h") or k.startswith("p_k")]
    if leaked:
        errors.append(f"p-class fields in Inputs (A2e-7a): {leaked}")
    for leg in ("gp_ni_prod", "gp_ni_mhp", "gp_pcam"):
        if inp[f"{leg}_h"] < inp[f"{leg}_m"]:
            errors.append(f"{leg}: H ({inp[f'{leg}_h']}) below M ({inp[f'{leg}_m']})")
    for k in ("conv_l", "conv_m", "conv_h"):
        if not (0.0 < inp[k] < 1.0):
            errors.append(f"{k}={inp[k]} outside (0,1)")
    if inp["cost_cu_base"] >= inp["rev_cu_base"]:
        errors.append("copper leg: cost exceeds revenue at base — check 口径")
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    # --- shared-ladder guard vs the axis file (A10), then vs 601899.SH --------
    # The axis is the source of truth; the peer comparison stays as a second
    # line so a drift on either side of the mount shows up here.
    axis_cu = load_au_cu_rungs()["cu"]
    for ours, tier in (("p_cu_l", "L"), ("p_cu_m", "M"), ("p_cu_h", "H")):
        if abs(inp[ours] - axis_cu[tier]) > 1e-6:
            errors.append(
                f"copper rung {tier}: stated {inp[ours]:g} vs "
                f"_AXIS.fed-path-gold-copper {axis_cu[tier]:g}"
            )
    peer = parse_inputs(PEER.read_text(encoding="utf-8"))
    for ours, theirs in SHARED_LADDER.items():
        if theirs not in peer:
            errors.append(f"peer 601899.SH missing {theirs}")
        elif abs(inp[ours] - peer[theirs]) > 1e-6:
            errors.append(
                f"shared ladder drift: {ours}={inp[ours]} vs 601899.{theirs}={peer[theirs]}"
            )
    if errors:
        print("FAIL (shared ladder):", "; ".join(errors), file=sys.stderr)
        return 1

    # --- the ruler -----------------------------------------------------------
    def copper_leg(price_usd_t: float) -> float:
        """Annualised copper gross profit, 亿 CNY — the only price-shifted leg."""
        return inp["rev_cu_base"] * price_usd_t / inp["p_cu_m"] - inp["cost_cu_base"]

    def gross_profit(suffix: str, p_cu: float) -> float:
        legs = sum(inp[k] for k in FLAT_LEGS)
        legs += sum(inp[f"{leg}_{suffix}"] for leg in ("gp_ni_prod", "gp_ni_mhp", "gp_pcam"))
        return legs + copper_leg(p_cu)

    r, g2 = inp["r_perp"], inp["g2"]

    def anchor(pretax: float, conv: float, g: float) -> tuple[float, float, float, float, float]:
        # Tier ROE on parent book; the multiple is Gordon on that ROE with the
        # shared g (A13). ROE <= r pins the multiple at 1/r — a result, not a bug.
        np_parent = pretax * conv
        eps = np_parent * YI / inp["shares"]
        roe = np_parent / inp["equity_parent"]
        pe = perpetual_pe(g, roe, r)
        return np_parent, eps, roe, pe, eps * pe

    gp_m = gross_profit("m", inp["p_cu_m"])
    gp_h = gross_profit("h", inp["p_cu_h"])
    pretax_m, pretax_h = gp_m - inp["opex"], gp_h - inp["opex"]

    def tiers(g: float) -> tuple[tuple, tuple, tuple]:
        # H carries g <= M's (post-peak normalisation, A13) — equal here.
        return (
            anchor(inp["pretax_l"], inp["conv_l"], g),
            anchor(pretax_m, inp["conv_m"], g),
            anchor(pretax_h, inp["conv_h"], min(g, g)),
        )

    (np_l, eps_l, roe_l, pe_l, scenario_l), (np_m, eps_m, roe_m, pe_m, M), (np_h, eps_h, roe_h, pe_h, H) = tiers(g2)

    floor = inp["pb_floor"] * inp["bps"]
    L = max(scenario_l, floor)
    floor_wins = floor > scenario_l

    # Guardrail (A18, valuation-rules ④): the M multiple must sit inside the
    # band the market actually printed at this earnings level. The own 5y PE
    # band is not the target for a cyclical — it was printed at EPS <= 2.9.
    if not (inp["pe_print_lo"] - 1e-9 <= pe_m <= inp["pe_print_hi"] + 1e-9):
        errors.append(
            f"M multiple {pe_m:.2f}x outside the EPS-matched print band "
            f"[{inp['pe_print_lo']:g}, {inp['pe_print_hi']:g}] (A18) — do not force g, reopen"
        )
    print_is_evidence = inp["n_print_m"] >= MIN_PRINT_MONTHS

    # Baseline closure: M must reproduce the filed net profit to parent.
    if abs(np_m - BASE_NP_PARENT_YI) > BASE_NP_TOL_YI:
        errors.append(
            f"baseline closure broken: M net profit {np_m:.4f}亿 vs filed "
            f"{BASE_NP_PARENT_YI}亿 (2026H1 x 2)"
        )

    # skill A2e-1: an earnings scenario this far below M means the earnings
    # ruler no longer describes the downside — that is a conversation, not a
    # number to ship.
    ratio = scenario_l / M if M else 0.0
    if floor_wins and ratio < SCENARIO_L_MIN_RATIO:
        errors.append(
            f"A2e-1: floor wins and scenario_L/M={ratio:.3f} < {SCENARIO_L_MIN_RATIO} "
            "— earnings ruler has failed at L, reopen the framework"
        )

    # 裁决顺序 ②-b (valuation-rules): a bottom-up ladder may stand in for the
    # consensus three points only if the consensus mean sits inside [M, H] and
    # M is within 20% of it — or, beyond 20%, a measured structural variable
    # (here conv) is named with a falsification trigger (the ②-b tag in §2).
    if not (eps_m <= inp["eps_cons_mean"] <= eps_h):
        errors.append(
            f"②-b: consensus FY26E mean {inp['eps_cons_mean']} outside [EPS_M {eps_m:.3f}, EPS_H {eps_h:.3f}]"
            " — H must be the market-base world"
        )
    cons_dev = eps_m / inp["eps_cons_mean"] - 1.0
    if abs(cons_dev) > CONSENSUS_BAND and "②-b" not in md:
        errors.append(f"②-b: M deviates {cons_dev:+.1%} from consensus mean with no ②-b named-variable row in §2")

    # skill A2e-2c: the three tiers must already be a ladder in the numerator,
    # so re-run them all at the M multiple and check the ordering survives.
    flat = (eps_l * pe_m, eps_m * pe_m, eps_h * pe_m)
    errors += ladder("flat-multiple", *flat)

    A, B = (L + M) / 2, (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # g2 leverage (valuation-rules「g2 的杠杆 MUST 显式」): the zone has to hold
    # at g2 ± 1pp and across the print evidence range; a zone that flips inside
    # the evidence is a BLOCKED framework, not a number to pick.
    def zone_at(g: float) -> tuple[str, float, float, float]:
        (_, _, _, _, sc), (_, _, _, _, m_), (_, _, _, _, h_) = tiers(g)
        l_ = max(sc, floor)
        return zone_of(inp["price"], l_, m_, h_), l_, m_, h_

    lever = {}
    for tag, g in (("-1pp", g2 - G2_LEVER_PP), ("+1pp", g2 + G2_LEVER_PP), ("print_lo", inp["g_print_lo"]), ("print_hi", inp["g_print_hi"])):
        lever[tag] = zone_at(g)
        if lever[tag][0] != zone:
            errors.append(f"zone flips to {lever[tag][0]} at g2 {g:+.2%} ({tag}) — BLOCKED per valuation-rules, reopen")

    # --- Pomalaa option (A11): own realised MHP unit x 12 kt, conv_m, M multiple, one year ---
    v_opt = inp["pomalaa_kt"] * inp["mhp_unit_gp"] * inp["conv_m"] * pe_m * YI / inp["shares"] / (1 + r) ** inp["t_opt"]
    adj = tuple(x + p * v_opt for x, p in zip((L, M, H), P_K))
    adj_a, adj_b = (adj[0] + adj[1]) / 2, (adj[1] + adj[2]) / 2
    adj_zone = zone_of(inp["price"], *adj)
    out_sec = outputs_section(md)
    import re
    vo = re.search(r"V_\{opt\}\\?\)?\s*=\s*\*\*([0-9.]+)\*\*", out_sec)
    if vo is None:
        errors.append("stated V_opt not found in Outputs")
    elif abs(float(vo.group(1)) - v_opt) > TOL:
        errors.append(f"V_opt: stated {vo.group(1)} vs recomputed {v_opt:.4f}")
    if abs(adj[0] - L) > 1e-9:
        errors.append("p leaked into the base: 表3 L row != base L")
    if "表3" not in out_sec:
        errors.append("V_opt > 0 but Outputs has no 表3")

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(
        "shared ladder OK vs _AXIS.fed-path-gold-copper and 601899.SH: cu "
        + "/".join(f"{inp[k]:g}" for k in ("p_cu_l", "p_cu_m", "p_cu_h"))
        + " $/t"
    )
    print(
        f"gordon: r={r:g} g2={g2:.4f} (= cu {inp['g_cu_cluster']:.4f}x{inp['w_cu_gp']:.4f} + li {inp['g_li_cluster']:.4f}x{inp['w_li_gp']:.4f} = {g2_blend:.5f}; six legs no cluster -> 0)"
        f"  ROE L/M/H {roe_l:.4%}/{roe_m:.4%}/{roe_h:.4%} -> PE {pe_l:.4f}/{pe_m:.4f}/{pe_h:.4f}"
    )
    print(
        f"guardrail (A18 盈利配对): M PE {pe_m:.2f}x in print band [{inp['pe_print_lo']:g}, {inp['pe_print_hi']:g}] OK; "
        f"print median g {inp['g_print_m']:+.2%} over {inp['n_print_m']:.0f} months "
        f"({'evidence' if print_is_evidence else 'corroboration only, n < ' + str(MIN_PRINT_MONTHS)}) vs g2 {g2:+.2%}: "
        f"M at g_print {eps_m * perpetual_pe(inp['g_print_m'], roe_m, r):.2f}"
    )
    print(
        f"L: pretax={inp['pretax_l']:7.2f} conv={inp['conv_l']:.4f} np={np_l:7.2f}亿 "
        f"eps={eps_l:.4f} roe={roe_l:.4%} pe={pe_l:.4f} scenario_L={scenario_l:.4f}"
    )
    print(
        f"   floor={floor:.4f} (pb {inp['pb_floor']:g} x bps {inp['bps']:g}) "
        f"-> L={L:.4f} ({'floor' if floor_wins else 'scenario'} wins), "
        f"scenario_L/M={ratio:.3f}"
    )
    for tag, gp, pretax, conv, np_, eps, roe, pe, anc in (
        ("M", gp_m, pretax_m, inp["conv_m"], np_m, eps_m, roe_m, pe_m, M),
        ("H", gp_h, pretax_h, inp["conv_h"], np_h, eps_h, roe_h, pe_h, H),
    ):
        print(
            f"{tag}: gp={gp:7.2f} cu_leg={copper_leg(inp['p_cu_m'] if tag == 'M' else inp['p_cu_h']):6.2f} "
            f"pretax={pretax:7.2f} conv={conv:.4f} np={np_:7.2f}亿 eps={eps:.4f} roe={roe:.4%} "
            f"pe={pe:.4f} anchor={anc:.4f}"
        )
    print(f"flat-multiple ladder @pe_M={pe_m:.4f}: " + " < ".join(f"{v:.2f}" for v in flat))
    print(f"②-b: consensus FY26E {inp['eps_cons_lo']}/{inp['eps_cons_mean']}/{inp['eps_cons_hi']} vs EPS tiers {eps_l:.3f}/{eps_m:.3f}/{eps_h:.3f}: "
          f"mean inside [M, H] {eps_m <= inp['eps_cons_mean'] <= eps_h}; M dev {cons_dev:+.1%} (named variable: conv, A1/A3/A4)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.4f} H/M={H / M:.4f} (H-L)/2M={(H - L) / (2 * M) * 100:.2f}%  V_opt/M={v_opt / M:.4f}")
    # A2e-5 decomposition: L is an asset floor, so its numerator ratio is n/a.
    print(f"分子比 L=n/a (地板胜出) H={eps_h / eps_m:.4f} | 倍数比 L=n/a H={pe_h / pe_m:.4f} (ROE mechanics only, flat policy)")
    for tag, (z, l_, m_, h_) in lever.items():
        print(f"  g2 lever {tag:>8}: L/M/H {l_:.2f}/{m_:.2f}/{h_:.2f}  A {(l_ + m_) / 2:.2f}  zone {z}")
    g_flip, _ = implied_g((2 * inp["price"] - floor) / eps_m, roe_m, r)
    print(f"  zone flips to conservative only if M > {2 * inp['price'] - floor:.2f} (PE_M > {(2 * inp['price'] - floor) / eps_m:.2f}x, g2 > {g_flip:+.2%})")
    # Sensitivities the doc quotes (conv / trade leg / copper / g2), Gordon-consistent.
    def m_at(pretax: float, conv: float, g: float = g2) -> float:
        return anchor(pretax, conv, g)[4]
    print(f"  sens conv_m +1pp -> M {m_at(pretax_m, inp['conv_m'] + 0.01):.2f} ({m_at(pretax_m, inp['conv_m'] + 0.01) - M:+.2f});"
          f" conv_h +1pp -> H {anchor(pretax_h, inp['conv_h'] + 0.01, g2)[4]:.2f};"
          f" conv 73.36% (FY2025) -> M {m_at(pretax_m, 0.7336):.2f}")
    print(f"  sens trade leg -10亿 -> M {m_at(pretax_m - 10, inp['conv_m']):.2f} ({m_at(pretax_m - 10, inp['conv_m']) - M:+.2f}), H {anchor(pretax_h - 10, inp['conv_h'], g2)[4]:.2f}")
    d_cu = copper_leg(inp["p_cu_m"] + 1000) - copper_leg(inp["p_cu_m"])
    print(f"  sens LME Cu +1000 $/t -> gp {d_cu:+.2f}亿 -> M {m_at(pretax_m + d_cu, inp['conv_m']):.2f} ({m_at(pretax_m + d_cu, inp['conv_m']) - M:+.2f})")
    print(f"  sens g2 -1pp/+1pp -> M {lever['-1pp'][2]:.2f}/{lever['+1pp'][2]:.2f} ({lever['-1pp'][2] - M:+.2f}/{lever['+1pp'][2] - M:+.2f})")
    g_px, ok = implied_g(inp["price"] / eps_m, roe_m, r)
    print(f"  price {inp['price']} / EPS_M = {inp['price'] / eps_m:.2f}x -> implied g {g_px:+.2%} ({'well' if ok else 'ill'}-conditioned); implied conv at PE_M {inp['price'] / pe_m * inp['shares'] / YI / pretax_m:.1%}")
    print(f"option Pomalaa: {inp['pomalaa_kt']:g} 万吨 x {inp['mhp_unit_gp']:.4f} 亿/万吨 x conv_m {inp['conv_m']:.4f} x PE_M {pe_m:.2f} / shares / (1+r)^{inp['t_opt']:g} -> V_opt {v_opt:.4f}")
    print(f"表3  p_k={P_K[0]:.2f}/{P_K[1]:.2f}/{P_K[2]:.2f}  L'/M'/H' = {adj[0]:.2f}/{adj[1]:.2f}/{adj[2]:.2f}  A'={adj_a:.2f} B'={adj_b:.2f}  zone+V = {adj_zone}")
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
