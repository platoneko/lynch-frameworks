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
profit to parent -> x a Gordon-generated PE.

Multiples are generated, not sampled (valuation-rules「永续增长口径」): per tier
ROE_x = NP_x / equity, PE_x = perpetual_pe(g2, ROE_x, r_perp) with ONE flat
g2 (A2e-5 cyclical default).  g2 = the gold+copper producer cross-section
value (tier 1, 2.76%) × the M-tier gross-profit weight of the copper + gold
legs; the cobalt / other-mining / IXM / elimination blocks have no cluster and
carry 0.  The axis 永续 g2 row is referenced verbatim (`axis_g2_aucu`) and
superseded by tier 1.  The tier-to-tier multiple spread is the ROE term only.

L tier (valuation-rules「谷底档」): the axis L world (copper 9,431 = 2025H1
platform, gold 3,942) is a regime, not the company's realised trough, so it is
priced as a low steady state.  `recovery_two_stage_pe` on the company's own
measured path (FY2019 18.57 亿 → FY2021 51.06 亿, n = 2) is printed as a
coordinate — it overshoots M with the measured CAGR and collapses into M with
the model's L→M magnitude — and is not the anchor.  The ticker's own 5-year
PE band is only a guardrail: a generated multiple outside it fails the run.

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
from lib.gordon import check_g_cap, check_r, perpetual_pe, recovery_two_stage_pe  # noqa: E402
from lib.tiers import report as tier_report  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "603993.SH.md"
PEER = Path(__file__).resolve().parent.parent / "frameworks" / "601899.SH.md"
FORMULA_ID = "cmoc_fed_path_cu_au_ladder_gp_bridge_pe_v2_gordon_v2"
MIN_R_MINUS_G = 0.02
# A23: the company's own realised trough→recovery path (Longbridge annual parent NI,
# FY2019 18.57 亿 → FY2021 51.06 亿, the last copper cycle trough).
RECOVERY_MEASURED = {"FY2019→FY2021": (18.57, 51.06, 2)}
TOL = 0.05  # anchors are stated to 2 decimals
YI = 1e8  # 亿

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
    "g2_aucu",
    "g2",
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


def parse_inputs(md: str) -> dict[str, float]:
    """Parse §3 Inputs table: | field | value | meaning | as-of |."""
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
        if key in ("字段名",) or raw in ("取值",) or set(key) <= set("- :"):
            continue
        if raw in ("待补", "", "—"):
            continue
        try:
            out[key] = float(raw.replace(",", ""))
        except ValueError:
            continue
    return out


def zone_of(price: float, L: float, M: float, H: float) -> str:
    A = (L + M) / 2
    B = (M + H) / 2
    if price < L:
        return "deep_discount"
    if price < A:
        return "conservative"
    if price < B:
        return "neutral"
    if price <= H:
        return "optimistic"
    return "stretched"


def first_float(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


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

    errors: list[str] = []

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
    # Gordon inputs: r on a tier, every g under the cap, r − g off the pole, and
    # the axis row referenced verbatim (superseded by tier 1, A22).
    errors += check_r(inp["r_perp"], "r_perp")
    for k in ("g2", "g2_aucu", "axis_g2_aucu"):
        errors += check_g_cap(inp[k], k)
    if inp["r_perp"] - inp["g2"] < MIN_R_MINUS_G:
        errors.append(f"r − g2 = {inp['r_perp'] - inp['g2']:.4f} < {MIN_R_MINUS_G} (pole)")
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
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

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
        print("FAIL (shared ladder):", "; ".join(errors), file=sys.stderr)
        return 1

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

    def scenario(price_usd_t: float, lme_au: float, gp_co: float, g2: float):
        gp_cu = copper_leg(price_usd_t)
        price_au_oz, gp_au = gold_leg(lme_au)
        gp = gp_cu + gp_au + gp_co + inp["gp_other"] + inp["gp_ixm"] + inp["gp_misc"]
        pretax = gp - inp["opex"]
        np_parent = pretax * (1.0 - inp["tax_rate"]) * (1.0 - inp["mi_rate"])
        eps = np_parent * YI / inp["shares"]
        roe = np_parent / inp["equity"]
        pe = perpetual_pe(g2, roe, inp["r_perp"])
        return gp_cu, gp_au, price_au_oz, gp, pretax, np_parent, eps, eps * pe, roe, pe

    sc_l = scenario(inp["p_cu_l"], inp["lme_au_l"], inp["gp_co_l"], inp["g2"])
    sc_m = scenario(inp["p_cu_m"], inp["lme_au_m"], inp["gp_co_m"], inp["g2"])
    sc_h = scenario(inp["p_cu_h"], inp["lme_au_h"], inp["gp_co_h"], inp["g2"])
    pe_l, pe_m, pe_h = sc_l[9], sc_m[9], sc_h[9]

    # One flat g2 = tier-1 cluster value × the M-tier gross-profit weight of the
    # copper + gold legs (the legs that ride the axis); every other block has no
    # cluster and is frozen across tiers, so it carries 0.
    w_axis = (sc_m[0] + sc_m[1]) / sc_m[3]
    g2_blend = w_axis * inp["g2_aucu"]
    if abs(inp["g2"] - g2_blend) > 1e-4:
        errors.append(f"g2={inp['g2']} vs blended tier-1 g2 {g2_blend:.5f} (w_axis {w_axis:.4f})")

    # Guardrail (裁决顺序 ③): every generated multiple inside the ticker's own
    # realised band.  A failure is BLOCKED, never fixed by twisting g or r.
    for tag, pe in (("L", pe_l), ("M", pe_m), ("H", pe_h)):
        if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
            errors.append(
                f"guardrail: PE_{tag}={pe:.2f} outside own band [{inp['pe_own_min']}, {inp['pe_own_max']}] — BLOCKED, do not twist g"
            )

    # Baseline closure: M must reproduce the filed net profit to parent.
    if abs(sc_m[5] - BASE_NP_PARENT_YI) > BASE_NP_TOL_YI:
        errors.append(
            f"baseline closure broken: M net profit {sc_m[5]:.4f}亿 vs filed "
            f"{BASE_NP_PARENT_YI}亿 (2026H1 x 2)"
        )

    L, M, H = sc_l[7], sc_m[7], sc_h[7]
    A = (L + M) / 2
    B = (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}")

    # A2e-2c flat-multiple ladder: with every tier at pe_m the order must survive,
    # i.e. the ladder has to live in the numerator, not in the counter-cyclical band.
    flat = [sc[6] * pe_m for sc in (sc_l, sc_m, sc_h)]
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken at PE_M={pe_m:.2f}: {flat}")
    # No probability field may sit in Inputs (A2e-7a); the copper alias p_cu_* is the axis's, not a p_k.
    for k in inp:
        if k.startswith("p_") and not k.startswith("p_cu_"):
            errors.append(f"probability-style input {k} in Inputs")

    # --- compare against the stated Outputs ----------------------------------
    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    stated = {
        "L": first_float(r"L = \*\*([0-9.]+)\*\*", out_sec),
        "M": first_float(r"M = \*\*([0-9.]+)\*\*", out_sec),
        "H": first_float(r"H = \*\*([0-9.]+)\*\*", out_sec),
        "A": first_float(r"A = \*\*([0-9.]+)\*\*", out_sec),
        "B": first_float(r"B = \*\*([0-9.]+)\*\*", out_sec),
    }
    for k, v in {"L": L, "M": M, "H": H, "A": A, "B": B}.items():
        s = stated.get(k)
        if s is None:
            errors.append(f"stated {k} not found in Outputs")
        elif abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")

    zm = re.search(r"zone = \*\*`([a-z_]+)`\*\*", out_sec)
    stated_zone = zm.group(1) if zm else None
    if stated_zone != zone:
        errors.append(f"zone: stated {stated_zone} vs recomputed {zone}")

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print("shared ladder OK vs _AXIS.fed-path-gold-copper (+ peer 601899.SH): cu " + "/".join(
        f"{inp[k]:g}" for k in ("p_cu_l", "p_cu_m", "p_cu_h")
    ) + " $/t, au " + "/".join(
        f"{inp[k]:g}" for k in ("lme_au_l", "lme_au_m", "lme_au_h")
    ) + " $/oz")
    for tag, sc, p, au in (
        ("L", sc_l, inp["p_cu_l"], inp["lme_au_l"]),
        ("M", sc_m, inp["p_cu_m"], inp["lme_au_m"]),
        ("H", sc_h, inp["p_cu_h"], inp["lme_au_h"]),
    ):
        print(
            f"{tag}: cu={p:>9.2f}$/t au={au:>7.0f}$/oz  gp_cu={sc[0]:7.2f}  gp_au={sc[1]:6.2f}  "
            f"gp={sc[3]:7.2f}  pretax={sc[4]:7.2f}  np={sc[5]:7.2f}亿  eps={sc[6]:.4f}  "
            f"roe={sc[8]:.4f}  pe={sc[9]:.4f}  anchor={sc[7]:.4f}"
        )
    per_kusd = (
        inp["vol_cu"] * 1000.0 * inp["realization_cu"] * inp["fx_usd_cny"] * (1.0 - inp["royalty_cu"]) / YI
    )
    print(
        f"sensitivity: +$1000/t copper -> pretax {per_kusd:.2f}亿, "
        f"eps {per_kusd * (1 - inp['tax_rate']) * (1 - inp['mi_rate']) * YI / inp['shares']:.4f}"
    )
    print(
        f"gordon: r={inp['r_perp']:g} g2={inp['g2']:g} flat (= tier-1 {inp['g2_aucu']:g} × axis-leg weight {w_axis:.4f}; "
        f"axis row {g2_axis:g} referenced, superseded) "
        f"roe={sc_l[8]:.3f}/{sc_m[8]:.3f}/{sc_h[8]:.3f} -> pe={pe_l:.2f}/{pe_m:.2f}/{pe_h:.2f} inside own band "
        f"[{inp['pe_own_min']}, {inp['pe_own_max']}] (spread = ROE term only)"
    )
    for dg in (-0.01, 0.01):
        pe_alt = perpetual_pe(inp["g2"] + dg, sc_m[8], inp["r_perp"])
        print(f"  g2 {dg:+.0%} -> PE_M {pe_alt:.2f}, M {sc_m[6] * pe_alt:.2f}")
    # A23 谷底档 coordinates: (i) the measured trough→recovery CAGR on the L numerator;
    # (ii) the measured n with the model's own L→M magnitude.  Printed, not anchors.
    for label, (np0, np1, n) in RECOVERY_MEASURED.items():
        g1_meas = (np1 / np0) ** (1.0 / n) - 1.0
        pe_i = recovery_two_stage_pe(g1_meas, n, inp["g2"], sc_m[8], inp["r_perp"])
        g1_lm = (sc_m[6] / sc_l[6]) ** (1.0 / n) - 1.0
        pe_ii = recovery_two_stage_pe(g1_lm, n, inp["g2"], sc_m[8], inp["r_perp"])
        print(
            f"谷底档坐标（A23）{label} n={n}: (i) measured CAGR {g1_meas:.1%} -> {pe_i:.1f}x -> {sc_l[6] * pe_i:.2f} "
            f"(vs M {sc_m[7]:.2f}: {'overshoot' if sc_l[6] * pe_i > sc_m[7] else 'below M'}); "
            f"(ii) L→M magnitude g1 {g1_lm:.1%} -> {pe_ii:.2f}x -> {sc_l[6] * pe_ii:.2f} (L/M {sc_l[6] * pe_ii / sc_m[7]:.3f}, collapsed)"
        )
    print(f"谷底 x 1/r = {sc_l[6] / inp['r_perp']:.2f}  (deep_discount pressure coordinate)")
    print(f"co_gp={inp['gp_co_l']}/{inp['gp_co_m']}/{inp['gp_co_h']}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"flat-multiple ladder @ PE_M {pe_m:.2f}: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    for line in tier_report((L, M, H), (pe_l, pe_m, pe_h), (sc_l[6], sc_m[6], sc_h[6])):
        print(line)
    print(
        f"L/M {L / M:.3f} = num {sc_l[6] / sc_m[6]:.3f} x pe {pe_l / pe_m:.3f} | "
        f"H/M {H / M:.3f} = num {sc_h[6] / sc_m[6]:.3f} x pe {pe_h / pe_m:.3f} | "
        f"width {(H - L) / (2 * M):.3f}"
    )
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
