#!/usr/bin/env python3
"""000792.SZ (Salt Lake) valuation eval.

frameworks/000792.SZ.md is the source of truth.
formula_id: saltlake_li_axis_kcl_ladder_pe_v2

Lithium volume is the commissioned nameplate (9.8 万吨/年) discounted one year,
so the 2027-28 price deck of the shared axis meets a 2027 run-rate volume --
the same construction as 9696.HK.  Potash stays on the annualised H1 volume
without discounting (current capacity).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import check_li2co3_mount  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "000792.SZ.md"
FORMULA_ID = "saltlake_li_axis_kcl_ladder_pe_v2"
TOL = 0.05
YI = 1e8

REQUIRED = [
    "price", "shares", "bps",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "realization_li", "vol_li_plan", "vol_li_h1", "cost_li",
    "r_disc", "n_disc",
    "kcl_price_l", "kcl_price_m", "kcl_price_h",
    "vol_k", "cost_k",
    "conv_ratio",
    "pe_mid", "pe_lo", "pe_hi", "pb_floor",
]


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
        if key in ("字段名", "--------", "---") or raw == "取值":
            continue
        if "待补" in raw:
            continue
        try:
            out[key] = float(raw.replace(",", ""))
        except ValueError:
            continue
    return out


def zone_of(price: float, L: float, M: float, H: float) -> str:
    A, B = (L + M) / 2, (M + H) / 2
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


def scenario(inp: dict[str, float], tag: str) -> dict[str, float]:
    li = inp[f"li2co3_{tag}"]
    kcl = inp[f"kcl_price_{tag}"]
    disc = (1.0 + inp["r_disc"]) ** (-inp["n_disc"])
    gp_li = disc * inp["vol_li_plan"] * (li * inp["realization_li"] - inp["cost_li"])
    gp_k = inp["vol_k"] * (kcl - inp["cost_k"])
    gp = gp_li + gp_k
    parent = gp * inp["conv_ratio"]
    eps = parent / inp["shares"]
    return {
        "gp_li": gp_li,
        "gp_k": gp_k,
        "gp": gp,
        "parent": parent,
        "eps": eps,
        "px": eps * inp["pe_mid"],
    }


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    missing = [k for k in REQUIRED if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1

    errors: list[str] = []
    if not (inp["li2co3_l"] < inp["li2co3_m"] < inp["li2co3_h"]):
        errors.append("li2co3 ladder violated")
    if not (inp["kcl_price_l"] < inp["kcl_price_m"] < inp["kcl_price_h"]):
        errors.append("kcl ladder violated")
    if not (inp["pe_lo"] == inp["pe_mid"] == inp["pe_hi"]):
        errors.append("PE must be flat")
    errors += check_li2co3_mount(
        (inp["li2co3_l"], inp["li2co3_m"], inp["li2co3_h"])
    )
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    S = {t: scenario(inp, t) for t in ("l", "m", "h")}
    floor = inp["pb_floor"] * inp["bps"]
    L = max(S["l"]["px"], floor)
    M = S["m"]["px"]
    H = S["h"]["px"]
    A, B = (L + M) / 2, (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        print(f"FAIL: L<M<H violated ({L:.2f}/{M:.2f}/{H:.2f})", file=sys.stderr)
        return 1

    doc_L = first_float(r"L = \*\*([0-9.]+)\*\*", md)
    doc_M = first_float(r"M = \*\*([0-9.]+)\*\*", md)
    doc_H = first_float(r"H = \*\*([0-9.]+)\*\*", md)
    for label, got, want in (("L", L, doc_L), ("M", M, doc_M), ("H", H, doc_H)):
        if want is None:
            print(f"FAIL: doc {label} missing", file=sys.stderr)
            return 1
        if abs(got - want) > TOL:
            print(
                f"FAIL: {label} mismatch calc={got:.2f} doc={want:.2f}",
                file=sys.stderr,
            )
            return 1

    print(f"formula_id={FORMULA_ID}")
    print(
        "li2co3 OK vs _AXIS.lithium-carbonate: "
        + "/".join(f"{inp[k]:g}" for k in ("li2co3_l", "li2co3_m", "li2co3_h"))
    )
    print(
        f"kcl ladder: {inp['kcl_price_l']:g}/{inp['kcl_price_m']:g}/{inp['kcl_price_h']:g}"
    )
    print(f"L/M/H = {L:.2f}/{M:.2f}/{H:.2f}  A/B = {A:.2f}/{B:.2f}")
    print(f"floor={floor:.2f} scenario_L={S['l']['px']:.2f} winner=scenario_L")
    print(
        f"li vol={inp['vol_li_plan']:g} x disc={(1 + inp['r_disc']) ** (-inp['n_disc']):.4f} "
        f"(H1 sales x2 = {inp['vol_li_h1']:g}, not in formula)"
    )
    print(
        f"M parent={S['m']['parent']/YI:.2f}亿 "
        f"(li GP {S['m']['gp_li']/YI:.2f} + k GP {S['m']['gp_k']/YI:.2f})"
    )
    print(
        f"L/M={L/M:.2f} H/M={H/M:.2f} (H-L)/2M={(H-L)/(2*M):.2%} V_opt/M=0"
    )
    print(f"price={inp['price']:g} → zone={zone}")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
