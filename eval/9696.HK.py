#!/usr/bin/env python3
"""9696.HK (Tianqi Lithium H) valuation eval.

frameworks/9696.HK.md is the source of truth.
formula_id: tianqi_li2co3_twoleg_volplan_pe10_v2
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import check_li2co3_mount  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "9696.HK.md"
FORMULA_ID = "tianqi_li2co3_twoleg_volplan_pe10_v2"
TOL = 0.05
YI = 1e8

REQUIRED = [
    "price", "shares", "bps",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "realization_conc", "realization_chem",
    "cost_conc", "cost_chem",
    "vol_conc_plan", "vol_chem_plan",
    "r_disc", "n_disc",
    "conv_ratio", "fx_hkd_per_cny",
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
    disc = (1.0 + inp["r_disc"]) ** (-inp["n_disc"])
    gp = disc * (
        inp["vol_conc_plan"] * (li * inp["realization_conc"] - inp["cost_conc"])
        + inp["vol_chem_plan"] * (li * inp["realization_chem"] - inp["cost_chem"])
    )
    parent = gp * inp["conv_ratio"]
    eps_hkd = parent / inp["shares"] * inp["fx_hkd_per_cny"]
    return {"gp": gp, "parent": parent, "eps_hkd": eps_hkd}


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
    errors += check_li2co3_mount(
        (inp["li2co3_l"], inp["li2co3_m"], inp["li2co3_h"])
    )
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    S = {t: scenario(inp, t) for t in ("l", "m", "h")}
    floor = inp["pb_floor"] * inp["bps"]
    L = max(S["l"]["eps_hkd"] * inp["pe_mid"], floor)
    M = S["m"]["eps_hkd"] * inp["pe_mid"]
    H = S["h"]["eps_hkd"] * inp["pe_mid"]
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

    zm = re.search(r"zone = \*\*`([a-z_]+)`\*\*", out_sec)
    stated_zone = zm.group(1) if zm else None
    if stated_zone != zone:
        errors.append(f"zone: stated {stated_zone} vs recomputed {zone}")

    print(f"formula_id={FORMULA_ID}")
    print(
        "li2co3 OK: "
        + "/".join(f"{inp[k]:g}" for k in ("li2co3_l", "li2co3_m", "li2co3_h"))
    )
    print(
        f"{'档':<3}{'毛利亿':>8}{'归母亿':>8}{'EPS_HKD':>10}{'锚点':>8}"
    )
    for t in ("l", "m", "h"):
        s = S[t]
        print(
            f"{t.upper():<3}{s['gp']/YI:8.1f}{s['parent']/YI:8.1f}"
            f"{s['eps_hkd']:10.3f}{s['eps_hkd']*inp['pe_mid']:8.2f}"
        )
    print(f"floor={floor:.2f}  disc={(1+inp['r_disc'])**(-inp['n_disc']):.4f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
