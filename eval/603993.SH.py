#!/usr/bin/env python3
"""603993.SH (CMOC) valuation eval — recompute anchors from frameworks/603993.SH.md.

frameworks/603993.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on any mismatch.

formula_id: cmoc_fed_path_cu_au_ladder_gp_bridge_pe_v2_gordon_v2

Scenario axis is the Fed rate path: L = hiking, M = on hold, H = cutting
without recession (see A19).  The recession-cut case moves gold and copper in
opposite directions and is deliberately NOT an anchor.

Main ruler: the 2026 interim segment gross-profit table is the audited base.
The copper leg is shifted by (annualised copper sales volume x LME price delta
x realisation x FX x (1 - DRC royalty)); the gold leg rides the shared gold
ladder; the cobalt leg is a quota-driven gross-profit level given per scenario;
the other-mining / IXM-trading / elimination / opex blocks are held flat across
all three scenarios.  Gross profit -> pretax -> x(1-tax)x(1-minority) -> net
profit to parent.

Multiples are generated per leg, not sampled (valuation-rules「永续增长口径」
「§r 篮子」, A24 / A26): net profit is split across four legs by each tier's
gross-profit share (copper + gold / cobalt quota / Mo-W-Nb-P incl. eliminations
/ IXM trading), and every leg carries its own basket r and its own flat g —
copper + gold on 篮 4 (10%) with the §13 commodity-leg g2 (inflation 2.5%),
cobalt and Mo-W-Nb-P on 篮 6 (13%) at g 0, IXM on 篮 5 (11%) at g 0.  All legs
share the company tier ROE (ROE_x = NP_x / equity), so the tier-to-tier spread
of the copper + gold multiple is the ROE term only.  The axis 永续 g2 row is
referenced verbatim (`axis_g2_aucu`) and superseded by the §13 tier default.

L tier (valuation-rules「谷底档」): the axis L world (copper 9,431 = 2025H1
platform, gold 3,942) is a regime, not the company's realised trough, so it is
priced as a low steady state.  `recovery_two_stage_pe` on the company's own
measured path (FY2019 18.57 亿 → FY2021 51.06 亿, n = 2) is printed as a
coordinate on the copper + gold ruler — it overshoots M with the measured CAGR
and collapses into M with the model's L→M magnitude — and is not the anchor.
The ticker's own 5-year PE band is only a guardrail: a copper + gold leg
multiple or a blended equivalent PE (anchor / EPS) outside it fails the run.

Gross-profit style inputs are in 亿 CNY and already annualised (2026H1 x 2).

Beyond the anchor comparison, the shared-ladder guard checks the USD gold and
copper ladders cell by cell against frameworks/axes/fed-path-gold-copper.md (logical id `_AXIS.fed-path-gold-copper`)
(and, as a dual check, the peer mount 601899.SH).

Run:  python3 eval/603993.SH.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import AXIS_AU_CU, check_au_cu_mount  # noqa: E402
from lib.gordon import basket_r, check_g_cap, check_r, perpetual_pe, recovery_two_stage_pe  # noqa: E402
from lib.inputs import check_against_stated, check_missing, parse_baskets, parse_inputs, report  # noqa: E402
from lib.tiers import report as tier_report  # noqa: E402
from lib.zones import zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "603993.SH.md"
PEER = Path(__file__).resolve().parent.parent / "frameworks" / "601899.SH.md"
FORMULA_ID = "cmoc_fed_path_cu_au_ladder_gp_bridge_pe_v2_gordon_v2"
MIN_R_MINUS_G = 0.02
# A23: the company's own realised trough→recovery path (Longbridge annual parent NI,
# FY2019 18.57 亿 → FY2021 51.06 亿, the last copper cycle trough).
RECOVERY_MEASURED = {"FY2019→FY2021": (18.57, 51.06, 2)}
TOL = 0.05  # anchors are stated to 2 decimals
YI = 1e8  # 亿

# Legs (A24): label -> (r row, g row).  Order is the Outputs 表1 order.
LEGS = {
    "铜金": ("r_perp", "g2_aucu"),
    "钴": ("r_co", "g2_co"),
    "钼钨铌磷": ("r_other", "g2_other"),
    "IXM": ("r_ixm", "g2_ixm"),
}

# Peer field aliases (dual check after the axis mount).
SHARED_LADDER = {
    "p_cu_l": "lme_cu_l",
    "p_cu_m": "lme_cu_m",
    "p_cu_h": "lme_cu_h",
    "lme_au_l": "lme_au_l",
    "lme_au_m": "lme_au_m",
    "lme_au_h": "lme_au_h",
}

# Audited baseline: 2026 interim net profit to parent x 2 (161.52187亿 x 2).
# The M scenario re-uses the base copper price, so its recomputed net profit
# must land back on this number — that is what welds the bridge to the filing.
BASE_NP_PARENT_YI = 323.0437
BASE_NP_TOL_YI = 0.5

REQUIRED = [
    "price",
    "shares",
    "fx_usd_cny",
    "vol_cu",
    "p_cu_base",
    "p_cu_l",
    "p_cu_m",
    "p_cu_h",
    "lme_au_l",
    "lme_au_m",
    "lme_au_h",
    "vol_au_oz",
    "cost_au_oz",
    "price_au_m_oz",
    "realization_cu",
    "royalty_cu",
    "gp_cu_base",
    "gp_co_l",
    "gp_co_m",
    "gp_co_h",
    "gp_other",
    "gp_ixm",
    "gp_misc",
    "opex",
    "tax_rate",
    "mi_rate",
    "equity",
    "r_perp",
    "r_co",
    "r_other",
    "r_ixm",
    "g2_aucu",
    "g2_co",
    "g2_other",
    "g2_ixm",
    "axis_g2_aucu",
    "pe_own_min",
    "pe_own_max",
]

# Axis §1「永续 g2（2026-09-14）」row: the M-tier g every mounted ticker reads.
_AXIS_G2_ROW = re.compile(r"^\|\s*\*\*永续 g2（[0-9-]+）\*\*\s*\|\s*\*\*([0-9.]+)%\*\*", re.MULTILINE)


def axis_g2(path=AXIS_AU_CU) -> float:
    m = _AXIS_G2_ROW.search(path.read_text(encoding="utf-8"))
    if not m:
        raise ValueError(f"{path.name}: no 永续 g2 row")
    return float(m.group(1)) / 100.0


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r = {leg: inp[rrow] for leg, (rrow, _) in LEGS.items()}
    g = {leg: inp[grow] for leg, (_, grow) in LEGS.items()}

    # --- Step 1: baskets — each leg's r must be the basket its row names -------
    baskets = parse_baskets(md)
    for leg, (rrow, _) in LEGS.items():
        if rrow not in baskets:
            errors.append(f"{rrow}: Inputs source cell names no 篮 N (AGENTS.md「篮子声明」)")
        errors += check_r(r[leg], rrow, baskets.get(rrow))
    if errors:
        return report(errors, "FAIL (baskets)")

    # --- sanity guards (see §3 校验步骤) -------------------------------------
    if not (inp["p_cu_l"] < inp["p_cu_m"] < inp["p_cu_h"]):
        errors.append(
            f"copper price order violated: {inp['p_cu_l']}/{inp['p_cu_m']}/{inp['p_cu_h']}"
        )
    if not (inp["lme_au_l"] < inp["lme_au_m"] < inp["lme_au_h"]):
        errors.append(
            f"gold price order violated: {inp['lme_au_l']}/{inp['lme_au_m']}/{inp['lme_au_h']}"
        )
    if inp["price_au_m_oz"] <= inp["cost_au_oz"]:
        errors.append("gold unit cost exceeds M price — check 口径")
    if not (inp["gp_co_l"] < inp["gp_co_m"] < inp["gp_co_h"]):
        errors.append(
            f"cobalt leg order violated: {inp['gp_co_l']}/{inp['gp_co_m']}/{inp['gp_co_h']}"
        )
    # Gordon inputs: every leg's g under its own basket's cap; commodity / fee legs
    # never below 0; the copper + gold leg off the pole; the axis row referenced
    # verbatim (superseded by the §13 tier default, A22).
    for leg, (_, grow) in LEGS.items():
        errors += check_g_cap(g[leg], r[leg], grow)
        if g[leg] < 0:
            errors.append(f"{grow}={g[leg]} < 0 — commodity / fee-type leg g floors at 0 (valuation-rules §13)")
    errors += check_g_cap(inp["axis_g2_aucu"], r["铜金"], "axis_g2_aucu")
    if r["铜金"] - g["铜金"] < MIN_R_MINUS_G:
        errors.append(f"r_perp − g2_aucu = {r['铜金'] - g['铜金']:.4f} < {MIN_R_MINUS_G} (pole)")
    g2_axis = axis_g2()
    if abs(inp["axis_g2_aucu"] - g2_axis) > 1e-9:
        errors.append(f"axis_g2_aucu={inp['axis_g2_aucu']} vs axis 永续 g2 {g2_axis}")
    if inp["equity"] <= 0:
        errors.append("equity must be positive")
    for k in ("tax_rate", "mi_rate", "royalty_cu"):
        if not (0.0 <= inp[k] < 1.0):
            errors.append(f"{k}={inp[k]} outside [0,1)")
    if not (0.80 <= inp["realization_cu"] <= 1.05):
        errors.append(f"realization_cu={inp['realization_cu']} implausible")
    if abs(inp["p_cu_m"] - inp["p_cu_base"]) > 1e-6:
        errors.append("p_cu_m must equal p_cu_base (M is the audited baseline)")
    if errors:
        return report(errors)

    # --- shared-ladder guard vs axis (+ peer dual check) ---------------------
    errors += check_au_cu_mount(
        (inp["lme_au_l"], inp["lme_au_m"], inp["lme_au_h"]),
        (inp["p_cu_l"], inp["p_cu_m"], inp["p_cu_h"]),
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
        return report(errors, "FAIL (shared ladder)")

    # --- the ruler -----------------------------------------------------------
    def copper_leg(price_usd_t: float) -> float:
        """Annualised copper gross profit, 亿 CNY."""
        delta = (
            inp["vol_cu"]
            * (price_usd_t - inp["p_cu_base"])
            * inp["realization_cu"]
            * inp["fx_usd_cny"]
            * (1.0 - inp["royalty_cu"])
        )
        return inp["gp_cu_base"] + delta / YI

    def gold_leg(lme_au_usd_oz: float) -> tuple[float, float]:
        """Annualised gold gross profit, 亿 CNY, riding the shared gold ladder."""
        price_oz = inp["price_au_m_oz"] * lme_au_usd_oz / inp["lme_au_m"]
        return price_oz, inp["vol_au_oz"] * (price_oz - inp["cost_au_oz"]) / YI

    def scenario(price_usd_t: float, lme_au: float, gp_co: float, r=r, g=g, np_override=None) -> dict:
        """One tier: the gross-profit bridge, then the four-leg Gordon sum (A24)."""
        gp_cu = copper_leg(price_usd_t)
        price_au_oz, gp_au = gold_leg(lme_au)
        legs = {
            "铜金": gp_cu + gp_au,
            "钴": gp_co,
            "钼钨铌磷": inp["gp_other"] + inp["gp_misc"],
            "IXM": inp["gp_ixm"],
        }
        gp = sum(legs.values())
        pretax = gp - inp["opex"]
        np_parent = pretax * (1.0 - inp["tax_rate"]) * (1.0 - inp["mi_rate"])
        if np_override is not None:
            np_parent = np_override(pretax)
        eps = np_parent * YI / inp["shares"]
        roe = np_parent / inp["equity"]
        pes = {leg: perpetual_pe(g[leg], roe, r[leg]) for leg in legs}
        weights = {leg: v / gp for leg, v in legs.items()}
        per_leg = {leg: eps * weights[leg] * pes[leg] for leg in legs}
        return {
            "gp_cu": gp_cu, "gp_au": gp_au, "price_au_oz": price_au_oz, "gp": gp,
            "pretax": pretax, "np": np_parent, "eps": eps, "roe": roe,
            "pes": pes, "weights": weights, "per_leg": per_leg,
            "anchor": sum(per_leg.values()),
        }

    sc = {
        "L": scenario(inp["p_cu_l"], inp["lme_au_l"], inp["gp_co_l"]),
        "M": scenario(inp["p_cu_m"], inp["lme_au_m"], inp["gp_co_m"]),
        "H": scenario(inp["p_cu_h"], inp["lme_au_h"], inp["gp_co_h"]),
    }
    sc_l, sc_m, sc_h = sc["L"], sc["M"], sc["H"]
    # The copper + gold leg is the only leg whose multiple moves with ROE (g > 0);
    # its tier ladder and the blended equivalent PE are what the guardrail reads.
    pe_l, pe_m, pe_h = (sc[t]["pes"]["铜金"] for t in ("L", "M", "H"))
    eq_pe = {t: sc[t]["anchor"] / sc[t]["eps"] for t in ("L", "M", "H")}

    # Guardrail (裁决顺序 ③): copper + gold leg multiples and the blended
    # equivalent PE inside the ticker's own realised band.  A failure is BLOCKED,
    # never fixed by twisting g or r (A25).
    for tag, pe in (("L", pe_l), ("M", pe_m), ("H", pe_h)):
        if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
            errors.append(
                f"guardrail: 铜金 PE_{tag}={pe:.2f} outside own band [{inp['pe_own_min']}, {inp['pe_own_max']}] — BLOCKED, do not twist g"
            )
    for tag, pe in eq_pe.items():
        if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
            errors.append(
                f"guardrail: blended PE_{tag}={pe:.2f} outside own band [{inp['pe_own_min']}, {inp['pe_own_max']}] — BLOCKED"
            )

    # Baseline closure: M must reproduce the filed net profit to parent.
    if abs(sc_m["np"] - BASE_NP_PARENT_YI) > BASE_NP_TOL_YI:
        errors.append(
            f"baseline closure broken: M net profit {sc_m['np']:.4f}亿 vs filed "
            f"{BASE_NP_PARENT_YI}亿 (2026H1 x 2)"
        )

    L, M, H = sc_l["anchor"], sc_m["anchor"], sc_h["anchor"]
    A = (L + M) / 2
    B = (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}")

    # A2e-2c flat-multiple ladder: with every tier at the copper + gold PE_M the
    # order must survive, i.e. the ladder has to live in the numerator.
    flat = [sc[t]["eps"] * pe_m for t in ("L", "M", "H")]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken at PE_M={pe_m:.2f}: {flat}")
    # No probability field may sit in Inputs (A2e-7a); the copper alias p_cu_* is the axis's, not a p_k.
    for k in inp:
        if k.startswith("p_") and not k.startswith("p_cu_"):
            errors.append(f"probability-style input {k} in Inputs")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print("baskets: " + " · ".join(
        f"{leg} {rrow} 篮 {baskets[rrow]} {basket_r(baskets[rrow]):.0%} g {g[leg]:.1%}"
        for leg, (rrow, _) in LEGS.items()
    ))
    print("shared ladder OK vs _AXIS.fed-path-gold-copper (+ peer 601899.SH): cu " + "/".join(
        f"{inp[k]:g}" for k in ("p_cu_l", "p_cu_m", "p_cu_h")
    ) + " $/t, au " + "/".join(
        f"{inp[k]:g}" for k in ("lme_au_l", "lme_au_m", "lme_au_h")
    ) + " $/oz")
    for tag, p, au in (("L", inp["p_cu_l"], inp["lme_au_l"]), ("M", inp["p_cu_m"], inp["lme_au_m"]), ("H", inp["p_cu_h"], inp["lme_au_h"])):
        s = sc[tag]
        print(
            f"{tag}: cu={p:>9.2f}$/t au={au:>7.0f}$/oz  gp_cu={s['gp_cu']:7.2f}  gp_au={s['gp_au']:6.2f}  "
            f"gp={s['gp']:7.2f}  pretax={s['pretax']:7.2f}  np={s['np']:7.2f}亿  eps={s['eps']:.4f}  "
            f"roe={s['roe']:.4f}  anchor={s['anchor']:.4f}"
        )
        print("    legs: " + "  ".join(
            f"{leg} w={s['weights'][leg]:.3f} pe={s['pes'][leg]:.2f} ->{s['per_leg'][leg]:.2f}" for leg in LEGS
        ) + f"  | blended pe={eq_pe[tag]:.2f}")
    per_kusd = (
        inp["vol_cu"] * 1000.0 * inp["realization_cu"] * inp["fx_usd_cny"] * (1.0 - inp["royalty_cu"]) / YI
    )
    d_anchor = scenario(inp["p_cu_m"] + 1000.0, inp["lme_au_m"], inp["gp_co_m"])["anchor"] - M
    print(
        f"sensitivity: +$1000/t copper -> pretax {per_kusd:.2f}亿, "
        f"eps {per_kusd * (1 - inp['tax_rate']) * (1 - inp['mi_rate']) * YI / inp['shares']:.4f}, M anchor {d_anchor:+.2f}"
    )
    print(
        f"gordon 铜金: r={r['铜金']:g} g2={g['铜金']:g} flat (§13 tier; axis row {g2_axis:g} referenced, superseded) "
        f"roe={sc_l['roe']:.3f}/{sc_m['roe']:.3f}/{sc_h['roe']:.3f} -> pe={pe_l:.2f}/{pe_m:.2f}/{pe_h:.2f}; "
        f"blended pe={eq_pe['L']:.2f}/{eq_pe['M']:.2f}/{eq_pe['H']:.2f} inside own band "
        f"[{inp['pe_own_min']}, {inp['pe_own_max']}] (spread = ROE term only)"
    )
    for dg in (-0.01, 0.01):
        g_alt = {**g, "铜金": g["铜金"] + dg}
        alt = [scenario(inp[f"p_cu_{t}"], inp[f"lme_au_{t}"], inp[f"gp_co_{t}"], g=g_alt)["anchor"] for t in ("l", "m", "h")]
        print(f"  g2_aucu {dg:+.0%} -> {alt[0]:.2f}/{alt[1]:.2f}/{alt[2]:.2f} zone {zone_of(inp['price'], *alt)}")
    # A26 basket alternatives (disclosure): 铜金 on 篮 5 (country add-on) / 篮 6.
    for label, rb in (("铜金 篮 5 11%", 0.11), ("铜金 篮 6 13%", 0.13)):
        r_alt = {**r, "铜金": rb}
        alt = [scenario(inp[f"p_cu_{t}"], inp[f"lme_au_{t}"], inp[f"gp_co_{t}"], r=r_alt)["anchor"] for t in ("l", "m", "h")]
        print(f"  {label} -> {alt[0]:.2f}/{alt[1]:.2f}/{alt[2]:.2f} zone {zone_of(inp['price'], *alt)}")
    # Implied r (δ): parallel shift of all four basket r's that prices the M tier at P.
    lo, hi = -0.08, 0.15
    for _ in range(100):
        mid = (lo + hi) / 2
        m_alt = scenario(inp["p_cu_m"], inp["lme_au_m"], inp["gp_co_m"], r={k: v + mid for k, v in r.items()})["anchor"]
        lo, hi = (mid, hi) if m_alt > inp["price"] else (lo, mid)
    delta = (lo + hi) / 2
    print("implied r(P) δ=" + f"{delta:+.2%}: " + " / ".join(f"{leg} {r[leg] + delta:.1%}" for leg in LEGS))
    # A23 谷底档 coordinates on the copper + gold ruler: (i) the measured
    # trough→recovery CAGR on the L numerator; (ii) the measured n with the
    # model's own L→M magnitude.  Printed, not anchors.
    for label, (np0, np1, n) in RECOVERY_MEASURED.items():
        g1_meas = (np1 / np0) ** (1.0 / n) - 1.0
        pe_i = recovery_two_stage_pe(g1_meas, n, g["铜金"], sc_m["roe"], r["铜金"])
        g1_lm = (sc_m["eps"] / sc_l["eps"]) ** (1.0 / n) - 1.0
        pe_ii = recovery_two_stage_pe(g1_lm, n, g["铜金"], sc_m["roe"], r["铜金"])
        print(
            f"谷底档坐标（A23）{label} n={n}: (i) measured CAGR {g1_meas:.1%} -> {pe_i:.1f}x -> {sc_l['eps'] * pe_i:.2f} "
            f"(vs M {M:.2f}: {'overshoot' if sc_l['eps'] * pe_i > M else 'below M'}); "
            f"(ii) L→M magnitude g1 {g1_lm:.1%} -> {pe_ii:.2f}x -> {sc_l['eps'] * pe_ii:.2f} (L/M {sc_l['eps'] * pe_ii / M:.3f}, collapsed)"
        )
    print(f"谷底 x 1/r = {sc_l['eps'] / r['铜金']:.2f}  (deep_discount pressure coordinate)")
    print(f"co_gp={inp['gp_co_l']}/{inp['gp_co_m']}/{inp['gp_co_h']}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat-multiple ladder @ 铜金 PE_M {pe_m:.2f}: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    for line in tier_report((L, M, H), (pe_l, pe_m, pe_h), (sc_l["eps"], sc_m["eps"], sc_h["eps"])):
        print(line)
    print(
        f"L/M {L / M:.3f} = num {sc_l['eps'] / sc_m['eps']:.3f} x pe {(L / M) / (sc_l['eps'] / sc_m['eps']):.3f} | "
        f"H/M {H / M:.3f} = num {sc_h['eps'] / sc_m['eps']:.3f} x pe {(H / M) / (sc_h['eps'] / sc_m['eps']):.3f} | "
        f"width {(H - L) / (2 * M):.3f}"
    )
    print(f"price={inp['price']} zone={zone}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
