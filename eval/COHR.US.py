#!/usr/bin/env python3
"""COHR.US (Coherent Corp.) valuation eval — recompute anchors from frameworks/COHR.US.md.

frameworks/COHR.US.md is the source of truth; this script re-parses its §3 Inputs,
recomputes L/M/H / A/B / zone and exits 1 on mismatch.

formula_id: cohr_sotp_dcc_industrial_pe_fy28_disc_v1

Main ruler: two-leg SOTP on FY2028 (fiscal year ending 2028-06-30).
Each leg = segment revenue x segment-profit margin, less a revenue-pro-rata share
of corporate + SBC, taxed at the normalized non-GAAP rate, per diluted share,
times a leg PE.  The Datacenter & Communications leg carries the whole multiple
band (15/22/30); Industrial gets one fixed cyclical multiple across scenarios.
The sum is discounted from 2027-06-30 (where a forward PE on FY2028 earnings
sits) back to today, then net debt per share is added.

Sanity checks beyond the L<M<H / Outputs reconciliation:
  - scenario monotonicity on revenue, margins and PE
  - pe_dcc_h hard cap (sell-side ceiling for the AI-optical group)
  - m_dcc_h hard cap (segment margin has never exceeded ~25%)
  - the M-scenario bottom-up economic EPS must land within +/-20% of the
    FY2028 street consensus non-GAAP EPS (the A2d cross-constraint, mechanised:
    it blocks silently inflating the mid scenario)

Run:  python3 eval/COHR.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "COHR.US.md"
FORMULA_ID = "cohr_sotp_dcc_industrial_pe_fy28_disc_v1"
TOL = 0.05  # outputs rounded to 2 decimals

PE_DCC_HARD_CAP = 35.0  # Citi's 35x FY2028E on LITE is the sector ceiling; COHR must sit below
MGN_DCC_HARD_CAP = 0.35  # DC&C segment-profit margin: 19.0/24.1/25.2% FY24-26
CONSENSUS_BAND = 0.20  # |bottom-up M economic EPS / street FY28 non-GAAP EPS - 1|


def parse_inputs(md: str) -> dict[str, float]:
    """Parse §3 Inputs table: | field | value | meaning | as-of |"""
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
        if key in ("字段名", "--------", "---") or raw in ("取值",):
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


def first_float(pattern: str, md: str) -> float | None:
    m = re.search(pattern, md)
    return float(m.group(1)) if m else None


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    required = [
        "price",
        "shares_diluted",
        "rev_dcc_l",
        "rev_dcc_m",
        "rev_dcc_h",
        "rev_ind",
        "m_dcc_l",
        "m_dcc_m",
        "m_dcc_h",
        "m_ind_l",
        "m_ind_m",
        "m_ind_h",
        "corp_pct",
        "tax_rate",
        "pe_dcc_l",
        "pe_dcc_m",
        "pe_dcc_h",
        "pe_ind",
        "r_disc",
        "t_disc",
        "net_debt_ps",
        "eps_cons_fy28",
    ]
    missing = [k for k in required if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1

    # --- Step 0: sanity guards on the inputs themselves -------------------
    guards: list[str] = []
    if not (inp["pe_dcc_l"] < inp["pe_dcc_m"] < inp["pe_dcc_h"]):
        guards.append(
            f"pe_dcc order violated: {inp['pe_dcc_l']}/{inp['pe_dcc_m']}/{inp['pe_dcc_h']}"
        )
    if inp["pe_dcc_h"] > PE_DCC_HARD_CAP + 1e-9:
        guards.append(f"pe_dcc_h={inp['pe_dcc_h']} exceeds hard cap {PE_DCC_HARD_CAP}")
    if not (inp["m_dcc_l"] < inp["m_dcc_m"] < inp["m_dcc_h"]):
        guards.append("m_dcc order violated")
    if inp["m_dcc_h"] > MGN_DCC_HARD_CAP + 1e-9:
        guards.append(f"m_dcc_h={inp['m_dcc_h']} exceeds hard cap {MGN_DCC_HARD_CAP}")
    if not (inp["m_ind_l"] < inp["m_ind_m"] < inp["m_ind_h"]):
        guards.append("m_ind order violated")
    if not (inp["rev_dcc_l"] < inp["rev_dcc_m"] < inp["rev_dcc_h"]):
        guards.append("rev_dcc order violated")
    if not (0.0 < inp["tax_rate"] <= 0.35):
        guards.append(f"tax_rate={inp['tax_rate']} outside (0, 0.35]")
    if inp["net_debt_ps"] > 0:
        guards.append(f"net_debt_ps={inp['net_debt_ps']} must be <= 0 (net debt, not net cash)")
    if guards:
        print("FAIL:", "; ".join(guards), file=sys.stderr)
        return 1

    # --- Step 1: per-scenario two-leg SOTP --------------------------------
    def scenario(
        rev_dcc: float, m_dcc: float, m_ind: float, pe_dcc: float
    ) -> tuple[float, float, float, float]:
        """(DC&C value/sh, Industrial value/sh, economic EPS, undiscounted sum/sh)."""
        rev_ind = inp["rev_ind"]
        rev_tot = rev_dcc + rev_ind
        corp = inp["corp_pct"] * rev_tot  # corporate + SBC, allocated pro-rata by revenue
        ebit_dcc = rev_dcc * m_dcc - corp * rev_dcc / rev_tot
        ebit_ind = rev_ind * m_ind - corp * rev_ind / rev_tot
        after_tax = 1.0 - inp["tax_rate"]
        eps_dcc = ebit_dcc * after_tax * 1e6 / inp["shares_diluted"]  # inputs in $M
        eps_ind = ebit_ind * after_tax * 1e6 / inp["shares_diluted"]
        v_dcc = eps_dcc * pe_dcc
        v_ind = eps_ind * inp["pe_ind"]
        return v_dcc, v_ind, eps_dcc + eps_ind, v_dcc + v_ind

    v_dcc_l, v_ind_l, eps_l, sum_l = scenario(
        inp["rev_dcc_l"], inp["m_dcc_l"], inp["m_ind_l"], inp["pe_dcc_l"]
    )
    v_dcc_m, v_ind_m, eps_m, sum_m = scenario(
        inp["rev_dcc_m"], inp["m_dcc_m"], inp["m_ind_m"], inp["pe_dcc_m"]
    )
    v_dcc_h, v_ind_h, eps_h, sum_h = scenario(
        inp["rev_dcc_h"], inp["m_dcc_h"], inp["m_ind_h"], inp["pe_dcc_h"]
    )

    # --- Step 2: A2d cross-constraint, mechanised -------------------------
    dev = eps_m / inp["eps_cons_fy28"] - 1.0
    if abs(dev) > CONSENSUS_BAND:
        print(
            f"FAIL: M-scenario economic EPS {eps_m:.2f} deviates {dev:+.1%} from"
            f" street FY2028 non-GAAP consensus {inp['eps_cons_fy28']}"
            f" (band +/-{CONSENSUS_BAND:.0%})",
            file=sys.stderr,
        )
        return 1

    # --- Step 3: discount to today, then close with net debt --------------
    disc = (1.0 + inp["r_disc"]) ** (-inp["t_disc"])
    L = sum_l * disc + inp["net_debt_ps"]
    M = sum_m * disc + inp["net_debt_ps"]
    H = sum_h * disc + inp["net_debt_ps"]
    A = (L + M) / 2
    B = (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1

    # --- Step 4: reconcile against the stated Outputs ---------------------
    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    stated = {
        "L": first_float(r"L = \*\*([0-9.]+)\*\*", out_sec),
        "M": first_float(r"M = \*\*([0-9.]+)\*\*", out_sec),
        "H": first_float(r"H = \*\*([0-9.]+)\*\*", out_sec),
        "A": first_float(r"A = \*\*([0-9.]+)\*\*", out_sec),
        "B": first_float(r"B = \*\*([0-9.]+)\*\*", out_sec),
    }
    recomputed = {"L": L, "M": M, "H": H, "A": A, "B": B}
    errors: list[str] = []
    for k, v in recomputed.items():
        s = stated.get(k)
        if s is None:
            errors.append(f"stated {k} not found")
        elif abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")

    zm = re.search(r"zone = \*\*`([a-z_]+)`\*\*", out_sec)
    stated_zone = zm.group(1) if zm else None
    if stated_zone != zone:
        errors.append(f"zone: stated {stated_zone} vs recomputed {zone}")

    print(f"formula_id={FORMULA_ID}")
    print(
        f"econ EPS FY28  L/M/H = {eps_l:.2f}/{eps_m:.2f}/{eps_h:.2f}"
        f"   (street non-GAAP {inp['eps_cons_fy28']}, M dev {dev:+.1%})"
    )
    print(f"DC&C  $/sh     L/M/H = {v_dcc_l:.2f}/{v_dcc_m:.2f}/{v_dcc_h:.2f}  pe={inp['pe_dcc_l']}/{inp['pe_dcc_m']}/{inp['pe_dcc_h']}")
    print(f"Indus $/sh     L/M/H = {v_ind_l:.2f}/{v_ind_m:.2f}/{v_ind_h:.2f}  pe={inp['pe_ind']}")
    print(f"sum undisc     L/M/H = {sum_l:.2f}/{sum_m:.2f}/{sum_h:.2f}  disc={disc:.4f}  net_debt_ps={inp['net_debt_ps']}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"implied PE on street FY28 EPS: L={L / inp['eps_cons_fy28']:.1f}x"
        f" M={M / inp['eps_cons_fy28']:.1f}x H={H / inp['eps_cons_fy28']:.1f}x"
        f" price={inp['price'] / inp['eps_cons_fy28']:.1f}x"
    )
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
