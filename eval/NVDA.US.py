#!/usr/bin/env python3
"""NVDA.US (NVIDIA) valuation eval — recompute anchors from frameworks/NVDA.US.md.

frameworks/NVDA.US.md is the source of truth; this script re-derives
L/M/H / A/B / zone from the §3 Inputs table and exits 1 on any mismatch.

formula_id: nvda_fy28_scenario_rev_gm_pe_v1

Main ruler: one whole-company FY2028 bridge run at three *named* scenarios --
    eps_i = (rev_i * gm_i - opex_fy28) * (1 - tax_rate) / shares_fy28
    anchor_i = eps_i * pe_i
All three tiers use ONE flat 20x multiple; they are told apart by the numerator
alone (A2e-2b/2c). Revenue for all three comes from the same analyst range:
L = its low ($416.4B, a digestion year with gross margin reset to 65%),
M = its mean ($673.5B), H = its high ($778.5B). The company's own +70% guide
($699.0B) is a coordinate inside the band, not the H numerator -- it is
explicitly supply-limited, so it caps capacity rather than demand (A3).
Numerator basis is the company's own non-GAAP (includes SBC, excludes equity
investment gains) -- GAAP EPS must NOT be used, see A10.

Sanity checks beyond the anchor comparison:
  * scenario ordering  rev_l < rev_m <= rev_h, gm_l < gm_m <= gm_h,
    pe_l <= pe_m <= pe_h, and the resulting eps_l < eps_m < eps_h
  * pe hard cap (no anchor may use a multiple above the street's widest)
  * flat-multiple ladder (A2e-2c): the tiers must still order correctly with the
    multiple held flat, i.e. the numerator alone separates them
  * two-sided consensus bridge (A17): recomputing FY2027 with the same formula
    must land within 15% of the FY2027 consensus EPS, and the M-scenario EPS
    within 15% of the FY2028 consensus EPS -- this is what stops a dirty
    numerator from silently drifting into the anchors
  * L < M < H

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
from eval.lib.tiers import flat_multiple_ladder, report as tier_report  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "NVDA.US.md"
FORMULA_ID = "nvda_fy28_scenario_rev_gm_pe_v1"
TOL = 0.05  # outputs are stated to 2 decimals
PE_HARD_CAP = 30.0  # widest multiple anyone on the street applies (GS, normalized)
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
    "pe_l",
    "pe_m",
    "pe_h",
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
]

_ANCHORS = re.compile(
    r"^- L = \*\*([0-9.]+)\*\* · M = \*\*([0-9.]+)\*\* · H = \*\*([0-9.]+)\*\*\s*$",
    re.MULTILINE,
)
_CUTS = re.compile(
    r"^- 切点 A = \*\*([0-9.]+)\*\* · B = \*\*([0-9.]+)\*\*\s*$",
    re.MULTILINE,
)
_ZONE = re.compile(r"zone = \*\*`([a-z_]+)`\*\*")


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
    if not (inp["pe_l"] <= inp["pe_m"] <= inp["pe_h"]):
        errors.append(f"pe order: {inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']}")
    if inp["pe_h"] > PE_HARD_CAP + 1e-9:
        errors.append(f"pe_h={inp['pe_h']} exceeds hard cap {PE_HARD_CAP}")

    # --- Step 2: the FY2028 bridge, run three times ---
    tax, shares, opex = inp["tax_rate"], inp["shares_fy28"], inp["opex_fy28"]
    eps_l = eps_of(inp["rev_l"], inp["gm_l"], opex, tax, shares)
    eps_m = eps_of(inp["rev_m"], inp["gm_m"], opex, tax, shares)
    eps_h = eps_of(inp["rev_h"], inp["gm_h"], opex, tax, shares)
    if not (eps_l < eps_m < eps_h):
        errors.append(f"eps order: {eps_l:.3f}/{eps_m:.3f}/{eps_h:.3f}")

    L = eps_l * inp["pe_l"]
    M = eps_m * inp["pe_m"]
    H = eps_h * inp["pe_h"]
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
    ladder_errors, _ = flat_multiple_ladder(
        (eps_l, eps_m, eps_h), inp["pe_m"]
    )
    errors.extend(ladder_errors)

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

    # --- Step 5: compare against the stated Outputs block ---
    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    am, cm, zm = _ANCHORS.search(out_sec), _CUTS.search(out_sec), _ZONE.search(out_sec)
    if not am:
        errors.append("stated L/M/H line not found in ### Outputs")
    if not cm:
        errors.append("stated 切点 A/B line not found in ### Outputs")
    if not zm:
        errors.append("stated zone not found in ### Outputs")

    if am and cm:
        stated = dict(
            zip(
                ("L", "M", "H", "A", "B"),
                [float(x) for x in am.groups()] + [float(x) for x in cm.groups()],
            )
        )
        for k, v in {"L": L, "M": M, "H": H, "A": A, "B": Bcut}.items():
            if abs(stated[k] - v) > TOL:
                errors.append(f"{k}: stated {stated[k]} vs recomputed {v:.4f}")
    if zm and zm.group(1) != zone:
        errors.append(f"zone: stated {zm.group(1)} vs recomputed {zone}")

    print(f"formula_id={FORMULA_ID}")
    print(
        f"rev($B)={inp['rev_l'] / B:.1f}/{inp['rev_m'] / B:.1f}/{inp['rev_h'] / B:.1f}"
        f"  gm={inp['gm_l']:.3f}/{inp['gm_m']:.3f}/{inp['gm_h']:.3f}"
        f"  opex={opex / B:.1f}  tax={tax:.0%}  shares={shares / B:.2f}B"
    )
    print(f"eps={eps_l:.3f}/{eps_m:.3f}/{eps_h:.3f}  pe={inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']}")
    print(
        f"bridge: FY27 eps {eps_fy27:.3f} vs cons {inp['eps_fy27_cons']} ({dev27:+.1%})"
        f" | FY28-M {eps_m:.3f} vs cons {inp['eps_fy28_cons']} ({dev28:+.1%})"
    )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={Bcut:.2f}")
    print(f"price={inp['price']} zone={zone}")
    print(
        f"implied weight on FY28 consensus = {weight_m:.1%}"
        f" | L implied peak PE = {implied_peak_pe:.2f}x"
    )
    for line in tier_report(
        (L, M, H),
        (inp["pe_l"], inp["pe_m"], inp["pe_h"]),
        (eps_l, eps_m, eps_h),
    ):
        print(line)
    print("axis _AXIS.cowos-capacity (α/β/γ -> L/M/H), $B on-axis / ACIE:")
    for label in ("L", "M", "H"):
        on_axis, acie = split[label]
        print(
            f"  {label}: quota {inp[f'cowos_quota_{label.lower()}'] / 1e4:>5.1f}万片"
            f"  on-axis {on_axis / B:>5.1f}  ACIE {acie / B:>5.1f}"
            f"  ({acie / acie_m - 1.0:+.1%} vs M)"
        )

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
