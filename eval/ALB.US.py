#!/usr/bin/env python3
"""ALB.US (Albemarle) valuation eval.

frameworks/ALB.US.md is the source of truth.
formula_id: alb_li2co3_grid_interp_spec_pe10_v1

The Energy Storage leg is not modelled bottom-up: Albemarle publishes a
FY2026E "outlook considerations" grid (adj. EBITDA at ~$10 / ~$20 / ~$30 per kg
LCE) that already carries its contract book (~40% of salts on LTAs), the
Windfield equity income and CORFO royalties.  The eval maps the shared Li2CO3
axis (CNY/t incl. VAT) onto $/kg and interpolates that grid piecewise-linearly.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import check_li2co3_mount  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "ALB.US.md"
FORMULA_ID = "alb_li2co3_grid_interp_spec_pe10_v1"
TOL = 0.05

REQUIRED = [
    "price", "shares_diluted", "bps",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "vat", "fx_usd_cny",
    "grid_p1", "grid_p2", "grid_p3",
    "grid_es1", "grid_es2", "grid_es3",
    "spec_ebitda", "da", "interest", "tax_rate", "nci",
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


def es_ebitda(p_usd_kg: float, inp: dict[str, float]) -> float:
    """Piecewise-linear read of the company grid; no extrapolation beyond $30."""
    p1, p2, p3 = inp["grid_p1"], inp["grid_p2"], inp["grid_p3"]
    e1, e2, e3 = inp["grid_es1"], inp["grid_es2"], inp["grid_es3"]
    if p_usd_kg <= p2:
        return e1 + (p_usd_kg - p1) * (e2 - e1) / (p2 - p1)
    return e2 + (p_usd_kg - p2) * (e3 - e2) / (p3 - p2)


def scenario(inp: dict[str, float], tag: str) -> dict[str, float]:
    p = inp[f"li2co3_{tag}"] / inp["vat"] / inp["fx_usd_cny"] / 1000.0
    es = es_ebitda(p, inp)
    ebitda = es + inp["spec_ebitda"]
    ebt = ebitda - inp["da"] - inp["interest"]
    ni = ebt * (1.0 - inp["tax_rate"]) - inp["nci"]
    eps = ni * 1000.0 / inp["shares_diluted"]
    return {"p": p, "es": es, "ebitda": ebitda, "ebt": ebt, "ni": ni, "eps": eps}


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
    if not (inp["pe_lo"] == inp["pe_mid"] == inp["pe_hi"]):
        errors.append("PE must be flat")
    if not (inp["grid_p1"] < inp["grid_p2"] < inp["grid_p3"]
            and inp["grid_es1"] < inp["grid_es2"] < inp["grid_es3"]):
        errors.append("company grid must be monotonic")
    errors += check_li2co3_mount(
        (inp["li2co3_l"], inp["li2co3_m"], inp["li2co3_h"])
    )
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    S = {t: scenario(inp, t) for t in ("l", "m", "h")}
    for t in ("l", "m", "h"):
        if not (inp["grid_p1"] <= S[t]["p"] <= inp["grid_p3"]):
            errors.append(f"{t.upper()} $/kg {S[t]['p']:.2f} outside company grid")
    floor = inp["pb_floor"] * inp["bps"]
    scenario_L = S["l"]["eps"] * inp["pe_mid"]
    L = max(scenario_L, floor)
    M = S["m"]["eps"] * inp["pe_mid"]
    H = S["h"]["eps"] * inp["pe_mid"]
    A, B = (L + M) / 2, (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1

    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    for k, v in {"L": L, "M": M, "H": H, "A": A, "B": B}.items():
        s = first_float(rf"{k} = \*\*([0-9.]+)\*\*", out_sec)
        if s is None:
            errors.append(f"stated {k} not found")
        elif abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")
    s = first_float(r"`scenario_L` = \*\*([0-9.]+)\*\*", out_sec)
    if s is None or abs(s - scenario_L) > TOL:
        errors.append(f"scenario_L: stated {s} vs recomputed {scenario_L:.4f}")

    zm = re.search(r"zone = \*\*`([a-z_]+)`\*\*", out_sec)
    stated_zone = zm.group(1) if zm else None
    if stated_zone != zone:
        errors.append(f"zone: stated {stated_zone} vs recomputed {zone}")

    print(f"formula_id={FORMULA_ID}")
    print(
        "li2co3 OK: "
        + "/".join(f"{inp[k]:g}" for k in ("li2co3_l", "li2co3_m", "li2co3_h"))
    )
    print(f"{'档':<3}{'$/kg':>7}{'ES EBITDA':>11}{'EBITDA':>8}{'EBT':>7}{'NI':>7}{'EPS':>7}{'锚点':>8}")
    for t in ("l", "m", "h"):
        s_ = S[t]
        print(
            f"{t.upper():<3}{s_['p']:7.2f}{s_['es']:11.3f}{s_['ebitda']:8.3f}"
            f"{s_['ebt']:7.3f}{s_['ni']:7.3f}{s_['eps']:7.2f}{s_['eps']*inp['pe_mid']:8.2f}"
        )
    winner = "floor" if floor > scenario_L else "scenario_L"
    print(f"floor={floor:.2f}  scenario_L={scenario_L:.2f}  winner={winner}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"L/M={L/M:.2f} H/M={H/M:.2f} (H-L)/2M={(H-L)/2/M:.2%} "
        f"numerator L/M={S['l']['eps']/S['m']['eps']:.2f} H/M={S['h']['eps']/S['m']['eps']:.2f}"
    )
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
