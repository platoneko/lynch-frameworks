#!/usr/bin/env python3
"""NVDA.US (NVIDIA) valuation eval — recompute anchors from frameworks/NVDA.US.md.

frameworks/NVDA.US.md is the source of truth; this script re-derives
L/M/H / A/B / zone from the §3 Inputs table and exits 1 on any mismatch.

formula_id: nvda_fy28_scenario_rev_gm_gordon_v2

Main ruler: one whole-company FY2028 bridge run at three *named* scenarios --
    eps_i = (rev_i * gm_i - opex_fy28) * (1 - tax_rate) / shares_fy28
    ROE_i = eps_i / BPS_open_FY28_i      (E_{n+1} / B_n, A24)
    anchor_i = eps_i * perpetual_pe(g2, ROE_i, r_perp)
The multiple is generated, not borrowed: one perpetual g2 shared by all three
tiers (peer cross-section reverse-solve, capped at g_cap(r)), tier ROE on the
FY2028 OPENING book: the FY27Q2 equity rolled over the 2H FY27 earnings not
yet booked at the growth-required retention b1 = g2/ROE (closed form
BPS = BPS0 / (1 - g2·N/eps); valuation-rules 裁决表 ② as of 62c72a2).  With ROE far above r the payout is ~1 and the three multiples
differ by well under a turn, so the tiers are still told apart by the numerator
alone (A2e-2c; the cyclical secondary's flat policy survives mechanically).
Revenue for all three comes from the same analyst range:
L = its low ($416.4B, a digestion year with gross margin reset to 65%),
M = its mean ($673.5B), H = its high ($778.5B). The company's own +70% guide
($699.0B) is a coordinate inside the band, not the H numerator -- it is
explicitly supply-limited, so it caps capacity rather than demand (A3).
Numerator basis is the company's own non-GAAP (includes SBC, excludes equity
investment gains) -- GAAP EPS must NOT be used, see A10.

Numerator year (valuation-rules 裁决顺序 ②, A20): FY2028 is the furthest year
with a >=2-house consensus (52-house EPS range, 56-house revenue range); FY2029
is single-house, so there is no transition year and no g1.  Guardrail (③, A19):
every generated multiple must sit inside the ticker's own realised next-FY PE
band (`pe_own_min/max`, normal-earnings segment); the band-edge Δg printed
below is the shift of g2 that would take the M-tier multiple to either edge --
evidence of what the market has paid for, not an input.

V_opt (A14): the China data-center reopening priced as k=1 × the H20 quarterly
run-rate the company actually booked in Q1 FY26 ($4.6B, 8-K Ex.99), at the
M-tier gross margin and Gordon multiple.  Probabilities live only in table 3.

Sanity checks beyond the anchor comparison:
  * scenario ordering  rev_l < rev_m <= rev_h, gm_l < gm_m <= gm_h,
    and the resulting eps_l < eps_m < eps_h
  * r basket: the Inputs source cell of r_perp names 篮 N and r equals that
    basket's value (valuation-rules.md「§r 篮子」) / g2 <= g_cap(r) / r - g2 >= 2%
  * guardrail: every generated multiple inside the ticker's own realised band
  * flat-multiple ladder (A2e-2c): the tiers must still order correctly with the
    multiple held flat, i.e. the numerator alone separates them
  * two-sided consensus bridge (A17): recomputing FY2027 with the same formula
    must land within 15% of the FY2027 consensus EPS, and the M-scenario EPS
    within 15% of the FY2028 consensus EPS -- this is what stops a dirty
    numerator from silently drifting into the anchors
  * L < M < H; stated V_opt and p_L/p_M/p_H present and consistent

Run:  python3 eval/NVDA.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import check_cowos_mount  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    check_g_cap,
    check_r,
    g_cap,
    implied_g,
    perpetual_pe,
)
from eval.lib.inputs import parse_baskets  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402
from eval.lib.tiers import flat_multiple_ladder, report as tier_report  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "NVDA.US.md"
FORMULA_ID = "nvda_fy28_scenario_rev_gm_gordon_v2"
LISTING_CCY = "USD"
TOL = 0.05  # outputs are stated to 2 decimals
MIN_R_MINUS_G = 0.02  # AGENTS.md: below this the multiple sits at the pole
BRIDGE_TOL = 0.15  # A17: max allowed deviation from consensus EPS
B = 1e9

REQUIRED = [
    "price",
    "shares_fy28",
    "tax_rate",
    "opex_fy28",
    "rev_l",
    "rev_m",
    "rev_h",
    "gm_l",
    "gm_m",
    "gm_h",
    "equity",
    "r_perp",
    "g2",
    "g2_cand",
    "pe_own_min",
    "pe_own_max",
    "rev_fy27",
    "gm_fy27",
    "opex_fy27",
    "opex_fy26",
    "shares_fy27",
    "eps_fy27_cons",
    "eps_fy28_cons",
    "cowos_quota_l",
    "cowos_quota_m",
    "cowos_quota_h",
    "dc_share_rev",
    "hyper_share_dc",
    "china_dc_rev_unit",
    "v_opt_units",
    "eps_1h_fy27",
    "payout_3y",
]

_ANCHORS = re.compile(
    r"^- 底牌 L = \*\*([0-9.]+)\*\* · M = \*\*([0-9.]+)\*\* · H = \*\*([0-9.]+)\*\*"
    r" · 切点 A = \*\*([0-9.]+)\*\* · B = \*\*([0-9.]+)\*\*",
    re.MULTILINE,
)
_ZONE = re.compile(r"zone = \*\*`([a-z_]+)`\*\*")
_V_OPT = re.compile(r"V_\{opt\}\\\)\s*=\s*\*\*([0-9.]+)\*\*")
_P_TIERS = re.compile(
    r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*[≈=]\s*\*{0,2}\s*"
    r"([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)"
)


def parse_inputs(md: str) -> dict[str, float]:
    """Parse the §3 Inputs table: | field | value | meaning | as-of |."""
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
        if key.startswith("-") or key == "字段名" or raw in ("取值", "待补", "", "—"):
            continue
        try:
            out[key] = float(raw.replace(",", ""))
        except ValueError:
            continue
    return out


def zone_of(price: float, L: float, M: float, H: float) -> str:
    a, b = (L + M) / 2, (M + H) / 2
    if price < L:
        return "deep_discount"
    if price < a:
        return "conservative"
    if price < b:
        return "neutral"
    if price <= H:
        return "optimistic"
    return "stretched"


def eps_of(rev: float, gm: float, opex: float, tax: float, shares: float) -> float:
    """Non-GAAP EPS bridge: revenue -> gross profit -> operating income -> per share."""
    return (rev * gm - opex) * (1.0 - tax) / shares


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

    # --- Step 1: scenario ordering (a scenario ladder must actually be a ladder) ---
    if not (inp["rev_l"] < inp["rev_m"] <= inp["rev_h"]):
        errors.append(
            f"revenue order: {inp['rev_l']:.3e}/{inp['rev_m']:.3e}/{inp['rev_h']:.3e}"
        )
    if not (inp["gm_l"] < inp["gm_m"] <= inp["gm_h"]):
        errors.append(f"gm order: {inp['gm_l']}/{inp['gm_m']}/{inp['gm_h']}")
    # Perpetual-growth 口径: one basket r for the whole-company leg (A23), one
    # g2 capped at that r, not at the pole.
    r, g2 = inp["r_perp"], inp["g2"]
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(g2, r, "g2")
    errors += check_g_cap(inp["g2_cand"], r, "g2_cand")
    if r - g2 <= 0:
        errors.append("perpetuity diverges: g2 >= r")
    elif r - g2 < MIN_R_MINUS_G:
        errors.append(f"r - g2 = {r - g2:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    if r - inp["g2_cand"] < MIN_R_MINUS_G:
        errors.append(f"r - g2_cand = {r - inp['g2_cand']:.2%} < {MIN_R_MINUS_G:.0%}")

    # --- Step 2: the FY2028 bridge, run three times ---
    tax, shares, opex = inp["tax_rate"], inp["shares_fy28"], inp["opex_fy28"]
    eps_l = eps_of(inp["rev_l"], inp["gm_l"], opex, tax, shares)
    eps_m = eps_of(inp["rev_m"], inp["gm_m"], opex, tax, shares)
    eps_h = eps_of(inp["rev_h"], inp["gm_h"], opex, tax, shares)
    if not (eps_l < eps_m < eps_h):
        errors.append(f"eps order: {eps_l:.3f}/{eps_m:.3f}/{eps_h:.3f}")

    # --- Step 2b: multiples generated from g2 and tier ROE (AGENTS.md 永续增长口径) ---
    # ROE = E_{n+1} / B_n: FY2028 EPS over the FY2028 OPENING book (= end of
    # FY2027), not today's FY27Q2 book (valuation-rules 裁决表 ② as of 62c72a2,
    # 2026-09-21; A24).  The FY27Q2 book is rolled over the 2H FY27 earnings not
    # yet booked (FY27 consensus minus 1H FY27 actual, non-GAAP) at the
    # GROWTH-REQUIRED retention b1 = g/ROE -- not the actual payout complement.
    # No g1 window here (FY29 has no consensus, A20), so every tier rolls at g2.
    # With ROE = eps / BPS and BPS = BPS0 + b1·N the fixed point is closed-form:
    # BPS = BPS0 / (1 - g2·N/eps).  Actual retention beyond b1 is the B bucket,
    # printed as a disclosure, not put into the book.
    unbooked = (inp["eps_fy27_cons"] - inp["eps_1h_fy27"]) * inp["shares_fy27"] / shares
    bps_q2 = inp["equity"] / shares
    bps_open = {}
    roe_t = {}
    b1 = {}
    for t, e in (("l", eps_l), ("m", eps_m), ("h", eps_h)):
        bps_open[t] = bps_q2 / (1.0 - g2 * unbooked / e)
        roe_t[t] = e / bps_open[t]
        b1[t] = g2 / roe_t[t]
        if not (0.0 < b1[t] < 1.0):
            errors.append(f"{t.upper()} growth-required retention b1 = {b1[t]:.3f} outside (0,1)")
    roe_l, roe_m, roe_h = roe_t["l"], roe_t["m"], roe_t["h"]
    ret_actual = 1.0 - inp["payout_3y"]
    excess_cash = {t: (ret_actual - b1[t]) * unbooked for t in b1}  # disclosure only
    pe_l, pe_m, pe_h = (perpetual_pe(g2, roe, r) for roe in (roe_l, roe_m, roe_h))
    # Guardrail (裁决顺序 ③, A19): inside the ticker's own realised next-FY PE band.
    for label, pe in (("L", pe_l), ("M", pe_m), ("H", pe_h)):
        if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
            errors.append(
                f"{label} generated PE {pe:.2f}x outside own realised band "
                f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]"
            )

    # Band-edge g (③ 带即证据): the g2 that would put the M-tier multiple on each
    # edge of the own band.  Reported, never used.
    def g_at(target: float) -> float:
        lo, hi = -0.30, r - 1e-4
        for _ in range(200):
            mid = (lo + hi) / 2
            if perpetual_pe(mid, roe_m, r) < target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    band_edge_g = (g_at(inp["pe_own_min"]), g_at(inp["pe_own_max"]))

    L = eps_l * pe_l
    M = eps_m * pe_m
    H = eps_h * pe_h
    A = (L + M) / 2
    Bcut = (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}/{M:.2f}/{H:.2f}")

    # --- Step 3: A17 two-sided consensus bridge (guards against a dirty numerator) ---
    eps_fy27 = eps_of(
        inp["rev_fy27"], inp["gm_fy27"], inp["opex_fy27"], tax, inp["shares_fy27"]
    )
    dev27 = eps_fy27 / inp["eps_fy27_cons"] - 1.0
    dev28 = eps_m / inp["eps_fy28_cons"] - 1.0
    if abs(dev27) > BRIDGE_TOL:
        errors.append(f"FY27 bridge deviates {dev27:+.1%} (> {BRIDGE_TOL:.0%})")
    if abs(dev28) > BRIDGE_TOL:
        errors.append(f"FY28 M bridge deviates {dev28:+.1%} (> {BRIDGE_TOL:.0%})")

    # --- Step 3b: opex ramp guard -------------------------------------------
    # The consensus bridge alone leaves opex_fy28 free over roughly $0-108B,
    # and opex_fy28 is the one input with no first-party disclosure behind it.
    # Tie it to the realised FY26->FY27 ramp: opex must grow with a business
    # whose revenue grows ~60%, but not faster than it did last year.
    g27 = inp["opex_fy27"] / inp["opex_fy26"] - 1.0
    g28 = inp["opex_fy28"] / inp["opex_fy27"] - 1.0
    if not (inp["opex_fy26"] < inp["opex_fy27"] < inp["opex_fy28"]):
        errors.append(
            f"opex must rise FY26<FY27<FY28: "
            f"{inp['opex_fy26']:.3e}/{inp['opex_fy27']:.3e}/{inp['opex_fy28']:.3e}"
        )
    elif g28 > g27:
        errors.append(
            f"opex_fy28 ramp {g28:+.1%} exceeds realised FY26->FY27 ramp {g27:+.1%} "
            f"— an accelerating opex ramp needs its own assumption (A7)"
        )

    # --- Step 3b2: tier construction guards (A2e-2c / A2e-5) ----------------
    # The three tiers must be told apart by their numerators; if holding the
    # multiple flat collapses a tier into its neighbour, the multiple was doing
    # the separating -- and a higher multiple on higher earnings is the cycle-
    # peak error this framework exists to avoid.
    ladder_errors, _ = flat_multiple_ladder((eps_l, eps_m, eps_h), pe_m)
    errors.extend(ladder_errors)
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")

    # --- Step 3c: shared-axis guard vs _AXIS.cowos-capacity.md --------------
    # The quotas do not enter the anchors; they are what the anchors *mean*.
    # Reading them from the axis file is what stops NVDA and AVGO from both
    # assuming they lose share (their L/H map to opposite states, axis §3).
    errors.extend(
        check_cowos_mount(
            "NVDA", inp["cowos_quota_l"], inp["cowos_quota_m"], inp["cowos_quota_h"]
        )
    )

    # --- Step 4: diagnostics that must never feed back into the anchors ---
    weight_m = (inp["price"] - L) / (M - L)
    implied_peak_pe = L / eps_m
    g_mkt, g_mkt_ok = implied_g(inp["price"] / eps_m, roe_m, r)

    # On-axis revenue scales with the quota; ACIE is the residual. Printing the
    # implied ACIE move keeps L's weakest input (A4 ②) visible on every run.
    non_dc = inp["rev_m"] * (1.0 - inp["dc_share_rev"])
    on_axis_m = inp["rev_m"] * inp["dc_share_rev"] * inp["hyper_share_dc"]
    split: dict[str, tuple[float, float]] = {}
    for label, rev, quota in (
        ("L", inp["rev_l"], inp["cowos_quota_l"]),
        ("M", inp["rev_m"], inp["cowos_quota_m"]),
        ("H", inp["rev_h"], inp["cowos_quota_h"]),
    ):
        on_axis = on_axis_m * quota / inp["cowos_quota_m"]
        split[label] = (on_axis, rev - non_dc - on_axis)
    acie_m = split["M"][1]

    # --- Step 4b: option ceiling (A14) -- probabilities only in table 3 ---
    v_opt = (
        inp["v_opt_units"] * inp["china_dc_rev_unit"] * inp["gm_m"] * (1.0 - tax) / shares * pe_m
    )

    # --- Step 5: compare against the stated Outputs block ---
    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    am, zm = _ANCHORS.search(out_sec), _ZONE.search(out_sec)
    if not am:
        errors.append("stated 底牌 L/M/H · 切点 A/B line not found in ### Outputs")
    if not zm:
        errors.append("stated zone not found in ### Outputs")

    if am:
        stated = dict(zip(("L", "M", "H", "A", "B"), [float(x) for x in am.groups()]))
        for k, v in {"L": L, "M": M, "H": H, "A": A, "B": Bcut}.items():
            if abs(stated[k] - v) > TOL:
                errors.append(f"{k}: stated {stated[k]} vs recomputed {v:.4f}")
    if zm and zm.group(1) != zone:
        errors.append(f"zone: stated {zm.group(1)} vs recomputed {zone}")
    vm = _V_OPT.search(out_sec)
    if vm is None or abs(float(vm.group(1)) - v_opt) > TOL:
        errors.append(f"V_opt: stated {vm.group(1) if vm else None} vs recomputed {v_opt:.4f}")
    pm = _P_TIERS.search(out_sec)
    p_tiers = tuple(float(x) for x in pm.groups()) if pm else None
    if p_tiers is None:
        errors.append("p_L/p_M/p_H not stated in ### Outputs")
    elif p_tiers[0] != 0.0:
        errors.append(f"table 3 L row must equal the base L (p_L=0), got p_L={p_tiers[0]}")

    print(f"formula_id={FORMULA_ID}")
    print(
        f"rev($B)={inp['rev_l'] / B:.1f}/{inp['rev_m'] / B:.1f}/{inp['rev_h'] / B:.1f}"
        f"  gm={inp['gm_l']:.3f}/{inp['gm_m']:.3f}/{inp['gm_h']:.3f}"
        f"  opex={opex / B:.1f}  tax={tax:.0%}  shares={shares / B:.2f}B"
    )
    print(f"eps={eps_l:.3f}/{eps_m:.3f}/{eps_h:.3f}  ROE={roe_l:.3f}/{roe_m:.3f}/{roe_h:.3f}"
          f"  pe(g2={g2:g}, r={r:g} 篮 {baskets.get('r_perp')})={pe_l:.2f}/{pe_m:.2f}/{pe_h:.2f}  band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]")
    print(
        f"bridge: FY27 eps {eps_fy27:.3f} vs cons {inp['eps_fy27_cons']} ({dev27:+.1%})"
        f" | FY28-M {eps_m:.3f} vs cons {inp['eps_fy28_cons']} ({dev28:+.1%})"
    )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={Bcut:.2f}")
    print(
        f"ROE basis: BPS_open_FY28 = {bps_open['l']:.2f}/{bps_open['m']:.2f}/{bps_open['h']:.2f} USD/sh "
        f"(FY27Q2 book {bps_q2:.2f} rolled over 2H FY27 unbooked {unbooked:.2f}/sh at b1 = g2/ROE = "
        f"{b1['l']:.3f}/{b1['m']:.3f}/{b1['h']:.3f}); FY27Q2-book basis would read ROE "
        f"{eps_l * shares / inp['equity']:.1%}/{eps_m * shares / inp['equity']:.1%}/{eps_h * shares / inp['equity']:.1%}"
    )
    print(
        f"B bucket (modelled-as-distributed, actually retained): actual retention {ret_actual:.1%} − b1 → "
        f"{excess_cash['l']:.2f}/{excess_cash['m']:.2f}/{excess_cash['h']:.2f} USD/sh over 2H FY27 "
        f"(disclosure only; not a leg, not in BPS)"
    )
    cap_hit = band_edge_g[1] > g_cap(r) + 1e-9
    print(
        f"own band [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] band-edge g @ M ROE: "
        f"lower {band_edge_g[0]:+.4f} (Δ {band_edge_g[0] - g2:+.4f}) / upper {band_edge_g[1]:+.4f} "
        f"(Δ {band_edge_g[1] - g2:+.4f}){f' — above the {g_cap(r):.0%} cap, unreachable under ①' if cap_hit else ''}"
    )
    print(
        f"V_opt={v_opt:.2f} (units {inp['v_opt_units']:g} x China DC unit ${inp['china_dc_rev_unit'] / B:.1f}B/yr "
        f"x gm_m {inp['gm_m']:.3f} x (1-tax) / shares x PE_M {pe_m:.2f})  V_opt/M {v_opt / M:.3f}"
    )
    if p_tiers:
        opt = tuple(a + p * v_opt for a, p in zip((L, M, H), p_tiers))
        a2, b2 = (opt[0] + opt[1]) / 2, (opt[1] + opt[2]) / 2
        print(f"zone+V band: {opt[0]:.2f}/{opt[1]:.2f}/{opt[2]:.2f}  A'={a2:.2f} B'={b2:.2f}  "
              f"zone+V={zone_of(inp['price'], *opt)}")
    print(f"price={inp['price']} zone={zone}")
    print(
        f"implied weight on FY28 consensus = {weight_m:.1%}"
        f" | L implied peak PE = {implied_peak_pe:.2f}x"
        f" | market-implied g (P / eps_M = {inp['price'] / eps_m:.1f}x) = {g_mkt:.4f}"
        f" ({'well' if g_mkt_ok else 'ill'}-conditioned, reference only)"
    )
    for line in tier_report((L, M, H), (pe_l, pe_m, pe_h), (eps_l, eps_m, eps_h)):
        print(line)
    print("axis _AXIS.cowos-capacity (α/β/γ -> L/M/H), $B on-axis / ACIE:")
    for label in ("L", "M", "H"):
        on_axis, acie = split[label]
        print(
            f"  {label}: quota {inp[f'cowos_quota_{label.lower()}'] / 1e4:>5.1f}万片"
            f"  on-axis {on_axis / B:>5.1f}  ACIE {acie / B:>5.1f}"
            f"  ({acie / acie_m - 1.0:+.1%} vs M)"
        )

    # A22 candidate band: same formula, only g2 -> g2_cand (peak-normalized).
    g2c = inp["g2_cand"]
    pe_c = tuple(perpetual_pe(g2c, roe, r) for roe in (roe_l, roe_m, roe_h))
    cand = (eps_l * pe_c[0], eps_m * pe_c[1], eps_h * pe_c[2])
    if not (cand[0] < cand[1] < cand[2]):
        errors.append(f"candidate band not a ladder: {cand}")
    stated_cand = load_framework(FRAMEWORK).candidate
    if stated_cand is None:
        errors.append("候选带 line missing from Outputs (A22)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), stated_cand, cand):
            if abs(said - got) > TOL:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")
    print(
        f"候选带（g2={g2c:g} 峰值后归一；不进底牌/zone 判定）: "
        f"L′/M′/H′={cand[0]:.2f}/{cand[1]:.2f}/{cand[2]:.2f}  "
        f"pe={pe_c[0]:.2f}/{pe_c[1]:.2f}/{pe_c[2]:.2f}  "
        f"候选 zone={zone_of(inp['price'], *cand)}"
    )
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): r_perp is the only
    # priced r; Δr_f moves it 1:1 in each tier's Gordon multiple while the FY28 EPS
    # bridge, tier ROE and g2 stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        return tuple(e * perpetual_pe(g2, roe, r + dr) for e, roe in ((eps_l, roe_l), (eps_m, roe_m), (eps_h, roe_h)))

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf, inp["price"])
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    # Only a clean run writes, so a FAIL never feeds the daily digest.
    write_rf_readings("NVDA.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
