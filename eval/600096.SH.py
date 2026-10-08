#!/usr/bin/env python3
"""600096.SH (Yuntianhua) valuation eval.

frameworks/600096.SH.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading — the digest and the app zone on live quotes.

formula_id: ytn_realized_earnings_regime_gordon_v6

Main ruler: three *already-printed or already-consensus* annual net profits,
each at the same flat multiple 1/(r - g2):

    L = FY2023 actual 45.22亿  (pricing management tightened, exports shrank)
        -> that regime persisting.  FY2023 is this company's own trough year,
           so the 谷底档 recovery form would apply — but the filings show the
           recovery took ONE year (FY2024 53.37 already above M), and
           recovery_two_stage_pe with n=1 degenerates to L >= M; a version
           that used n=3 (a calendar span, not a measured recovery) was
           rolled back.  A15 records the alternatives.
    M = FY2026E consensus       (EPS 2.875 x shares)
    H = FY2022 actual 60.21亿  (management loosened, exports opened, global peak)

r is the leg's basket value (A20: basket 5, reached from the initial basket 6
by the ③-out-of-band step-down rule — 13% gives 8.70x, below the company's own
1y daily PE floor 8.83x); g2 is the shared axis row (IFA, 1.5%) on all three
tiers.  The multiple is 1/(r - g) rather than the retention form because
growth here is not funded by retention (A18: capex 2023-25 < D&A, retained
cash goes to debt paydown) — ROE is disclosed, not used.  The retention-form
band is printed as a cross-check.

Why not a price scenario: this company's measured elasticity to the MAP ladder
is 0.049 — MAP rose 33.6% between 2025 and 2026 while net profit rose 1.6%.
Running a price scenario through that slope collapses the three tiers onto one
number, which is exactly the "分子比 ≈ 1.00" red line AGENTS.md draws for
cyclicals.  So the ticker still mounts _AXIS.phosphate-chain (the regime
definition and tier numbering are shared, and the ladder is cross-checked
against both the axis file and the peer mount 002895.SZ), but its numerator
comes from the other transmission path of the same regime.

V_opt (A9): the 35% stake in the Wanchang phosphate mine (1,000万吨/年, total
capex 81.69亿, company-stated after-tax IRR 12.81%), valued with this ticker's
own ruler — stake x (capex x IRR x PE - (capex - spent)) at the same
1/(r - g2) — in the first full year after completion (2032) and discounted back
to FY2026 at the basket r.  Borrow quantity, never price (valuation-rules
「未建模期权」2026-10-03).  Only the capital not yet spent is deducted (rule of
2026-10-04): the 9.81亿 already paid for the exploration / mining rights is
sunk.  The IRR is the project's unlevered after-tax IRR on the whole budget, so
the "IRR x capex" profit belongs to every source of funds — the unspent
deduction therefore includes whatever the JV will borrow (loans repaid by the
project count as unspent, as with 002895.SZ 老虎洞); deducting only equity
would under-deduct, and adding the sunk rights fee back would over-deduct.

The beta guard below is what keeps that honest: if the measured elasticity ever
climbs above 0.20, the "does not transmit" premise has failed and the ruler has
to be rebuilt rather than quietly re-fitted.

Run:  python3 frameworks/eval/600096.SH.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import (  # noqa: E402
    AXIS_PHOS, PHOS_INERT_BETA_CEILING, check_axis_g2_mount, check_phosphate_mount,
)
from lib.gordon import BASKET_R, check_g_cap, check_r, perpetual_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.frameworks import load_framework  # noqa: E402
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "600096.SH.md"
PEER = Path(__file__).resolve().parents[2] / "frameworks" / "002895.SZ.md"
FORMULA_ID = "ytn_realized_earnings_regime_gordon_v6"
YI = 1e8

NP_PEAK_FY2022_YI = 60.21  # highest annual net profit the company has printed
NUM_YEAR = 2026  # numerator year of M (FY2026E consensus)
P_TIERS = (0.0, 0.25, 1.0)  # table 3; p_M 无概率锚·拍值 (A9)
TOL = 0.05


def stated_v_opt(md: str) -> float | None:
    m = re.search(r"V_\{opt\}\\\)\s*=\s*\*\*([0-9.]+)\*\*", md)
    return float(m.group(1)) if m else None


def stated_p_tiers(md: str) -> tuple[float, float, float] | None:
    m = re.search(
        r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*[≈=]\s*\*{0,2}\s*"
        r"([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)",
        md,
    )
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None

REQUIRED = [
    "shares", "np_l", "eps_m_consensus", "np_h",
    "equity", "r_perp", "g2_l", "g2_m", "g2_h", "eps_fy27_single",
    "pe_own_min", "pe_own_max", "map_l", "map_m", "map_h", "beta_map", "bps",
    "opt_capex", "opt_spent", "opt_stake", "opt_irr", "t_opt",
]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell must name the basket (篮 N)")

    errors += ladder("MAP", inp["map_l"], inp["map_m"], inp["map_h"])
    errors += check_phosphate_mount(
        (inp["map_l"], inp["map_m"], inp["map_h"]),
        peer_md=PEER.read_text(encoding="utf-8"),
    )
    # The numerator deliberately does NOT ride the ladder (A6).  That premise is
    # only valid while the measured elasticity stays near zero.
    if inp["beta_map"] >= PHOS_INERT_BETA_CEILING:
        errors.append(
            f"beta_map={inp['beta_map']:g} >= {PHOS_INERT_BETA_CEILING:g}: this "
            "ticker's numerator is not driven by the MAP ladder (A6) — if it now "
            "transmits, the main ruler must be rebuilt, not re-fitted"
        )
    errors += check_axis_g2_mount(AXIS_PHOS, inp["g2_m"])
    r = inp["r_perp"]
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    for k in ("g2_l", "g2_m", "g2_h"):
        errors += check_g_cap(inp[k], r, k)
    # A2e-5 cyclical: the g ladder is flat-or-reverse; L shares the axis row.
    if abs(inp["g2_l"] - inp["g2_m"]) > 1e-9:
        errors.append(f"g2_l {inp['g2_l']} must equal g2_m {inp['g2_m']} (axis 永续 g2, flat; A15)")
    if inp["g2_h"] > inp["g2_m"]:
        errors.append(f"g2_h {inp['g2_h']} > g2_m {inp['g2_m']} — H may not grow faster than M (cyclical, flat-or-reverse)")
    if abs(inp["np_h"] - NP_PEAK_FY2022_YI) > 0.01:
        errors.append(
            f"np_h={inp['np_h']:g}亿 must be the FY2022 realised peak "
            f"{NP_PEAK_FY2022_YI}亿 — H is that peak itself, not an extrapolation"
        )
    if errors:
        return report(errors)

    # --- the ruler -------------------------------------------------------------
    np_m = inp["eps_m_consensus"] * inp["shares"] / YI
    roe = {"L": inp["np_l"] / inp["equity"], "M": np_m / inp["equity"], "H": inp["np_h"] / inp["equity"]}
    # A18: growth is not retention-funded, so the multiple is 1/(r - g) on every
    # tier; the retention form is only a cross-check below.
    pe = {t: 1.0 / (r - inp[f"g2_{t.lower()}"]) for t in ("L", "M", "H")}
    for tag, val in pe.items():
        if not (inp["pe_own_min"] <= val <= inp["pe_own_max"]):
            errors.append(
                f"{tag} multiple {val:.2f} outside own realised band "
                f"[{inp['pe_own_min']}, {inp['pe_own_max']}] — ③ 出带: step the basket down, do not force g or r"
            )
    tiers = (("L", inp["np_l"], pe["L"]), ("M", np_m, pe["M"]), ("H", inp["np_h"], pe["H"]))
    computed = {}
    rows = []
    for tag, npp, mult in tiers:
        eps = npp * YI / inp["shares"]
        computed[tag] = eps * mult
        rows.append((tag, npp, eps, mult, eps * mult))

    errors += ladder("net profit", inp["np_l"], np_m, inp["np_h"])
    L, M, H = computed["L"], computed["M"], computed["H"]
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}"])

    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # Candidate band (A17): the broker's FY2027E is an ordinary base forecast = growth type
    # (construction §7h): its step over the FY2026E mean is shared by M and H; the L regime
    # (FY2023 actual) bears no transition. Disclosed, not judged.
    g1_cand = inp["eps_fy27_single"] / inp["eps_m_consensus"] - 1
    m_cand = inp["eps_fy27_single"] * pe["M"]
    h_cand = H * (1 + g1_cand)
    if not (L < m_cand < h_cand):
        errors.append(f"candidate band collapsed: L {L:.2f} < M' {m_cand:.2f} < H' {h_cand:.2f} fails (A17)")
    stated_cand = load_framework(FRAMEWORK).candidate
    if stated_cand is None:
        errors.append("候选带 line missing from Outputs (A17)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), stated_cand, (L, m_cand, h_cand)):
            if abs(said - got) > 0.05:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")

    # V_opt (A9): own ruler, discounted from the realisation year to the numerator year.
    if inp["t_opt"] <= NUM_YEAR:
        errors.append(f"t_opt {inp['t_opt']:g} must lie after the numerator year {NUM_YEAR} (A9)")
    p_fields = [k for k in inp if k.startswith("p_")]
    if p_fields:
        errors.append(f"Inputs carry probability fields {p_fields} — p_k belongs in table 3 only")
    if not (0 <= inp["opt_spent"] < inp["opt_capex"]):
        errors.append(f"opt_spent {inp['opt_spent']:g} must lie in [0, opt_capex {inp['opt_capex']:g})")
    k_share = inp["opt_stake"] * inp["opt_capex"]          # earns the IRR (whole budget, unlevered)
    k_remain = inp["opt_stake"] * (inp["opt_capex"] - inp["opt_spent"])  # still to be spent, debt included
    dni_opt = k_share * inp["opt_irr"]
    v_at_t = (dni_opt * pe["M"] - k_remain) * YI / inp["shares"]
    disc = (1 + r) ** (inp["t_opt"] - NUM_YEAR)
    v_opt = v_at_t / disc
    v_g0 = (dni_opt / r - k_remain) * YI / inp["shares"] / disc
    v_full_k = (dni_opt * pe["M"] - k_share) * YI / inp["shares"] / disc  # pre-2026-10-04 (sunk fee re-deducted)
    # Contrast: unspent capital spread evenly over the build years (2027 .. t_opt-1), each discounted to FY2026.
    build = range(NUM_YEAR + 1, int(inp["t_opt"]))
    k_pv_spread = sum(k_remain / len(build) / (1 + r) ** (y - NUM_YEAR) for y in build)
    v_spread = (dni_opt * pe["M"] / disc - k_pv_spread) * YI / inp["shares"]
    said_v = stated_v_opt(md[md.find("### Outputs"):])
    if said_v is None or abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    if stated_p_tiers(md[md.find("### Outputs"):]) != P_TIERS:
        errors.append(f"p_L/p_M/p_H stated {stated_p_tiers(md)} vs {P_TIERS}")
    opt = tuple(a + p * v_opt for a, p in zip((L, M, H), P_TIERS))
    A_v, B_v = cut_points(*opt)

    # --- report ----------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(
        f"axis OK vs _AXIS.phosphate-chain and peer 002895.SZ: MAP "
        f"{inp['map_l']:g}/{inp['map_m']:g}/{inp['map_h']:g} 元/吨 "
        f"(beta={inp['beta_map']:g} < {PHOS_INERT_BETA_CEILING:g}: numerator does not ride it)"
    )
    b = baskets["r_perp"]
    print(f"basket: r_perp 篮 {b} {BASKET_R[b][0]} r={r:g}; g ladder L {inp['g2_l']:g} / M {inp['g2_m']:g} / H {inp['g2_h']:g} (flat); "
          f"PE = 1/(r-g) = {pe['M']:.3f}x  guardrail [{inp['pe_own_min']}, {inp['pe_own_max']}] OK")
    labels = {
        "L": "FY2023 actual  (regime)   ",
        "M": "FY2026E consensus         ",
        "H": "FY2022 actual  (loosened) ",
    }
    for tag, npp, eps, mult, anchor in rows:
        print(f"{tag}: {labels[tag]}  np={npp:6.2f}亿  eps={eps:.4f}  ROE={roe[tag]:.2%} (disclosed)  pe={mult:.3f}  anchor={anchor:.4f}  PB={anchor / inp['bps']:.3f}")
    ret = {t: perpetual_pe(inp[f"g2_{t.lower()}"], roe[t], r) for t in ("L", "M", "H")}
    print("retention-form cross-check (1-g/ROE)/(r-g): "
          + " / ".join(f"{ret[t]:.2f}x" for t in "LMH") + " -> "
          + " / ".join(f"{rows[i][2] * ret[t]:.2f}" for i, t in enumerate("LMH")))
    print(f"deep_discount 压力坐标: 谷底 x 1/r = {inp['np_l'] * YI / inp['shares'] / r:.2f}; "
          f"floor (disclosed only, not max()'d): PB 1.0 = {inp['bps']:.2f}")
    print(f"candidate band (A17, FY27 single-house {inp['eps_fy27_single']:g}, g1 {g1_cand:+.2%} on M/H): "
          f"L'={L:.2f} M'={m_cand:.2f} H'={h_cand:.2f} A'={(L + m_cand) / 2:.2f} B'={(m_cand + h_cand) / 2:.2f}"
          f" (disclosed, not judged); per-share EPS at A'/B' {(L + m_cand) / 2 / pe['M']:.4f}/{(m_cand + h_cand) / 2 / pe['M']:.4f}")
    print(f"V_opt={v_opt:.4f} (stake {inp['opt_stake']:g} x capex {inp['opt_capex']:g}亿 = {k_share:.3f}亿 earning IRR; "
          f"ΔNI {dni_opt:.4f}亿 x {pe['M']:.3f}x - K_remain {k_remain:.3f}亿 (= {inp['opt_stake']:g} x ({inp['opt_capex']:g} - spent {inp['opt_spent']:g})) "
          f"-> {v_at_t:.4f}/sh @{inp['t_opt']:g}, ÷{disc:.4f}); deduction {k_remain * YI / inp['shares'] / disc:.4f}/sh at FY{NUM_YEAR}; "
          f"g=0 contrast {v_g0:.4f}; full-K (old) {v_full_k:.4f}; capex spread {build.start}-{build.stop - 1} {v_spread:.4f}; V_opt/M {v_opt / M:.4f}")
    print("table3: " + " / ".join(f"{t} {b:.2f}+{p:g}x{v_opt:.2f}={o:.2f}" for t, b, p, o in zip("LMH", (L, M, H), P_TIERS, opt))
          + f"  A'={A_v:.2f} B'={B_v:.2f}")
    per_yi = YI / inp["shares"] * pe["M"]
    print(f"sensitivity: +1亿 net profit -> M anchor {per_yi:+.2f} CNY")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"ratios: L/M={L / M:.4f} H/M={H / M:.4f} (H-L)/2M={(H - L) / (2 * M):.4f} "
        f"| 分子比 L={rows[0][2] / rows[1][2]:.4f} H={rows[2][2] / rows[1][2]:.4f} "
        f"| 倍数比 L={pe['L'] / pe['M']:.4f} H={pe['H'] / pe['M']:.4f} | V_opt/M {v_opt / M:.4f}"
    )
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
