#!/usr/bin/env python3
"""GLW.US (Corning) valuation eval — recompute anchors from frameworks/GLW.US.md.

frameworks/GLW.US.md is the source of truth; this script re-derives
L/M/H / A/B / zone from the §3 Inputs table and exits 1 on mismatch.

formula_id: glw_sotp_core_segment_pe_v3

Main ruler: FY2028 segment SOTP. Earning legs use ni_*_q×4×g_* × forward PE
with pe_oc_h < 30; loss legs use sales×4×g × P/S; plus prepaid locked profit
× probability (p_h=1); minus closing items. Whole-company H/eps_fy28 must be < 30.

Run:  python3 eval/GLW.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "GLW.US.md"
FORMULA_ID = "glw_sotp_core_segment_pe_v3"
TOL = 0.05
PE_OC_HARD_CAP = 30.0  # strict: pe_oc_h must be < this
MM = 1e6

PE_LEGS = ("oc", "gi", "au")
PS_LEGS = ("so", "ls")


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
        if key in ("字段名", "--------", "---") or raw in ("取值",):
            continue
        if raw in ("待补", "", "—"):
            continue
        try:
            out[key] = float(raw.replace(",", "").replace("&lt;", ""))
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
    required = (
        [
            "price",
            "shares_diluted",
            "eps_fy28",
            "corp_pretax_q",
            "tax_core",
            "nci_q",
            "pe_corp",
            "net_debt",
            "pension",
            "contract_liab",
            "pp_margin",
            "p_pp_l",
            "p_pp_m",
            "p_pp_h",
        ]
        + [f"ni_{leg}_q" for leg in PE_LEGS]
        + [f"g_{leg}" for leg in PE_LEGS]
        + [f"pe_{leg}_{k}" for leg in PE_LEGS for k in "lmh"]
        + [f"sales_{leg}_q" for leg in PS_LEGS]
        + [f"g_{leg}" for leg in PS_LEGS]
        + [f"ps_{leg}_{k}" for leg in PS_LEGS for k in "lmh"]
    )
    missing = [k for k in required if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1

    for leg in PE_LEGS:
        band = [inp[f"pe_{leg}_{k}"] for k in "lmh"]
        if not (band[0] < band[1] < band[2]):
            print(f"FAIL: pe_{leg} band not increasing: {band}", file=sys.stderr)
            return 1
    for leg in PS_LEGS:
        band = [inp[f"ps_{leg}_{k}"] for k in "lmh"]
        if not (band[0] < band[1] < band[2]):
            print(f"FAIL: ps_{leg} band not increasing: {band}", file=sys.stderr)
            return 1

    if inp["pe_oc_h"] >= PE_OC_HARD_CAP - 1e-12:
        print(
            f"FAIL: pe_oc_h={inp['pe_oc_h']} must be < {PE_OC_HARD_CAP} (FY28 constraint)",
            file=sys.stderr,
        )
        return 1

    ni_fy28 = {leg: inp[f"ni_{leg}_q"] * 4 * inp[f"g_{leg}"] for leg in PE_LEGS}
    sales_fy28 = {leg: inp[f"sales_{leg}_q"] * 4 * inp[f"g_{leg}"] for leg in PS_LEGS}

    corp_cap = inp["corp_pretax_q"] * 4 * (1 - inp["tax_core"]) * inp["pe_corp"]
    nci_cap = inp["nci_q"] * 4 * inp["pe_corp"]
    adj = -corp_cap - nci_cap - inp["net_debt"] - inp["pension"]

    p_l, p_m, p_h = inp["p_pp_l"], inp["p_pp_m"], inp["p_pp_h"]
    if not (0 <= p_l < p_m < p_h):
        print(f"FAIL: p_pp band not increasing: {[p_l, p_m, p_h]}", file=sys.stderr)
        return 1
    if abs(p_h - 1.0) > 1e-9:
        print(f"FAIL: p_pp_h must be 1.0, got {p_h}", file=sys.stderr)
        return 1
    if not (0 < inp["pp_margin"] < 1):
        print(f"FAIL: pp_margin out of range: {inp['pp_margin']}", file=sys.stderr)
        return 1
    pp_locked_ni = inp["contract_liab"] * inp["pp_margin"]
    pp_add = {"l": pp_locked_ni * p_l, "m": pp_locked_ni * p_m, "h": pp_locked_ni * p_h}

    def anchor(k: str) -> tuple[dict[str, float], float]:
        legs = {leg: ni_fy28[leg] * inp[f"pe_{leg}_{k}"] for leg in PE_LEGS}
        legs.update({leg: sales_fy28[leg] * inp[f"ps_{leg}_{k}"] for leg in PS_LEGS})
        legs["pp"] = pp_add[k]
        total = sum(legs.values()) + adj
        return legs, total * MM / inp["shares_diluted"]

    legs_l, L = anchor("l")
    legs_m, M = anchor("m")
    legs_h, H = anchor("h")
    A = (L + M) / 2
    B = (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1

    fy28_pe_h = H / inp["eps_fy28"]
    if fy28_pe_h >= PE_OC_HARD_CAP - 1e-12:
        print(
            f"FAIL: H/eps_fy28={fy28_pe_h:.2f} must be < {PE_OC_HARD_CAP}",
            file=sys.stderr,
        )
        return 1

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
    print("FY28 NI/sales $M: " + " ".join(f"{k}={v:,.0f}" for k, v in {**ni_fy28, **sales_fy28}.items()))
    print("legs $M  L: " + " ".join(f"{k}={v:,.0f}" for k, v in legs_l.items()))
    print("legs $M  M: " + " ".join(f"{k}={v:,.0f}" for k, v in legs_m.items()))
    print("legs $M  H: " + " ".join(f"{k}={v:,.0f}" for k, v in legs_h.items()))
    print(
        f"adj={adj:,.1f}M = {adj * MM / inp['shares_diluted']:.2f}/sh; "
        f"prepaid={pp_locked_ni:,.1f}M x p → "
        f"{pp_add['l'] * MM / inp['shares_diluted']:.2f}/"
        f"{pp_add['m'] * MM / inp['shares_diluted']:.2f}/"
        f"{pp_add['h'] * MM / inp['shares_diluted']:.2f}/sh"
    )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"FY28 PE L/M/H={L / inp['eps_fy28']:.2f}/"
        f"{M / inp['eps_fy28']:.2f}/{fy28_pe_h:.2f}x "
        f"(cap <{PE_OC_HARD_CAP:g})"
    )

    others_m = sum(v for k, v in legs_m.items() if k != "oc")
    implied_pe_oc = (inp["price"] * inp["shares_diluted"] / MM - adj - others_m) / ni_fy28["oc"]
    print(
        f"price={inp['price']} zone={zone}  "
        f"price/eps_fy28={inp['price'] / inp['eps_fy28']:.2f}x  "
        f"implied pe_oc FY28 (others+pp at M)={implied_pe_oc:.1f}x"
    )

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
