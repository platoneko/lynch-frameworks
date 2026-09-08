#!/usr/bin/env python3
"""AEHR.US (Aehr Test Systems) valuation eval — recompute anchors from frameworks/AEHR.US.md.

frameworks/AEHR.US.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on any mismatch.

formula_id: aehr_dual_core_opt_rev_margin_pe_disc_v3

Main ruler: dual-driver steady-state revenue off FY2027 guidance.
L/M use t_steady (FY2029); H alone uses t_steady_h (FY2030).
L = guidance low x trough ratio (whole-company, no leg split).
M/H = core + optical legs, each compounded at its own g_*, then summed;
shared GM / opex / PE. H locks ~24.5% opex ratio via absolute opex_h.
L is floored at pb_floor x tangible BPS (asset floor exists today — NOT discounted).

Run:  python3 eval/AEHR.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "AEHR.US.md"
FORMULA_ID = "aehr_dual_core_opt_rev_margin_pe_disc_v3"
TOL = 0.05  # outputs rounded to 2 decimals
MILLION = 1e6  # money inputs are in $M, share counts are absolute

# --- sanity envelopes (A6 / A8) -------------------------------------------
PE_HARD_CAP = 32.0  # A8: peer forward-PE ceiling (TER 30.6), never raise to fit price
GM_RANGE = (0.30, 0.55)  # A6: observed FY2023-FY2026 gross margin band 35.3%-50.4%
TAX_RANGE = (0.0, 0.50)

REQUIRED = [
    "price",
    "shares_now",
    "shares_t",
    "tangible_book",
    "net_cash",
    "guide_low",
    "guide_mid",
    "guide_high",
    "trough_ratio",
    "opt_share",
    "g_core_m",
    "g_opt_m",
    "g_core_h",
    "g_opt_h",
    "gm_l",
    "gm_m",
    "gm_h",
    "opex_l",
    "opex_m",
    "opex_h",
    "tax",
    "pe_l",
    "pe_m",
    "pe_h",
    "r_disc",
    "year_now",
    "t_steady",
    "t_steady_h",
    "pb_floor",
]


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
        if key in ("字段名", "--------", "---") or raw == "取值":
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


def check_inputs(inp: dict[str, float]) -> list[str]:
    """Sanity guards that must hold before the anchors mean anything."""
    errs: list[str] = []

    if inp["pe_h"] > PE_HARD_CAP + 1e-9:
        errs.append(f"pe_h={inp['pe_h']} exceeds hard cap {PE_HARD_CAP} (A8)")
    if not (inp["pe_l"] < inp["pe_m"] < inp["pe_h"]):
        errs.append(f"pe order: {inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']}")
    if not (inp["gm_l"] < inp["gm_m"] < inp["gm_h"]):
        errs.append(f"gm order: {inp['gm_l']}/{inp['gm_m']}/{inp['gm_h']}")
    for k in ("gm_l", "gm_m", "gm_h"):
        if not (GM_RANGE[0] <= inp[k] <= GM_RANGE[1]):
            errs.append(f"{k}={inp[k]} outside observed GM band {GM_RANGE} (A6)")
    if not (inp["opex_l"] < inp["opex_m"] < inp["opex_h"]):
        errs.append(f"opex order: {inp['opex_l']}/{inp['opex_m']}/{inp['opex_h']}")
    if not (inp["guide_low"] < inp["guide_mid"] < inp["guide_high"]):
        errs.append("guidance band must be low < mid < high")
    if not (0.0 < inp["trough_ratio"] < 1.0):
        errs.append(f"trough_ratio={inp['trough_ratio']} must be a drawdown in (0,1) (A5)")
    if not (0.0 < inp["opt_share"] < 1.0):
        errs.append(f"opt_share={inp['opt_share']} must be in (0,1) (A14)")
    if not (0.0 <= inp["g_core_m"] < inp["g_core_h"]):
        errs.append(
            f"core growth: g_core_m={inp['g_core_m']} must be >=0 and < g_core_h={inp['g_core_h']}"
        )
    if not (0.0 <= inp["g_opt_m"] < inp["g_opt_h"]):
        errs.append(
            f"opt growth: g_opt_m={inp['g_opt_m']} must be >=0 and < g_opt_h={inp['g_opt_h']}"
        )
    if inp["g_opt_m"] < inp["g_core_m"]:
        errs.append(
            f"g_opt_m={inp['g_opt_m']} < g_core_m={inp['g_core_m']} — optical mid should be faster (A14)"
        )
    if not (TAX_RANGE[0] <= inp["tax"] <= TAX_RANGE[1]):
        errs.append(f"tax={inp['tax']} outside {TAX_RANGE}")
    if inp["t_steady"] <= inp["year_now"]:
        errs.append("t_steady must be later than year_now")
    if inp["t_steady_h"] < inp["t_steady"]:
        errs.append(
            f"t_steady_h={inp['t_steady_h']} must be >= t_steady={inp['t_steady']} (A4)"
        )
    return errs


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

    guard_errors = check_inputs(inp)
    if guard_errors:
        print("FAIL: " + "; ".join(guard_errors), file=sys.stderr)
        return 1

    # Steps 1-4 — L trough; M/H dual-driver legs.
    years_lm = inp["t_steady"] - inp["year_now"]
    years_h = inp["t_steady_h"] - inp["year_now"]
    ramp_lm = years_lm - 1.0
    ramp_h = years_h - 1.0
    share_opt = inp["opt_share"]
    share_core = 1.0 - share_opt

    rev_l = inp["guide_low"] * inp["trough_ratio"]
    rev_core_m = inp["guide_mid"] * share_core * (1.0 + inp["g_core_m"]) ** ramp_lm
    rev_opt_m = inp["guide_mid"] * share_opt * (1.0 + inp["g_opt_m"]) ** ramp_lm
    rev_m = rev_core_m + rev_opt_m
    rev_core_h = inp["guide_high"] * share_core * (1.0 + inp["g_core_h"]) ** ramp_h
    rev_opt_h = inp["guide_high"] * share_opt * (1.0 + inp["g_opt_h"]) ** ramp_h
    rev_h = rev_core_h + rev_opt_h

    # Steps 5-7 — margin bridge, then EV multiple plus net cash, per share.
    def scenario(rev: float, gm: float, opex: float, pe: float):
        gp = rev * gm
        ebit = gp - opex
        nopat = max(ebit, 0.0) * (1.0 - inp["tax"])
        equity_t = pe * nopat + inp["net_cash"]  # $M
        return gp, ebit, nopat, equity_t, equity_t * MILLION / inp["shares_t"]

    gp_l, ebit_l, nopat_l, eq_l, v_l = scenario(rev_l, inp["gm_l"], inp["opex_l"], inp["pe_l"])
    gp_m, ebit_m, nopat_m, eq_m, v_m = scenario(rev_m, inp["gm_m"], inp["opex_m"], inp["pe_m"])
    gp_h, ebit_h, nopat_h, eq_h, v_h = scenario(rev_h, inp["gm_h"], inp["opex_h"], inp["pe_h"])

    # Steps 8-10 — discount earnings legs; asset floor exists today.
    disc_lm = (1.0 + inp["r_disc"]) ** (-years_lm)
    disc_h = (1.0 + inp["r_disc"]) ** (-years_h)
    tbvps = inp["tangible_book"] * MILLION / inp["shares_now"]
    floor = inp["pb_floor"] * tbvps
    L = max(v_l * disc_lm, floor)
    M = v_m * disc_lm
    H = v_h * disc_h
    A = (L + M) / 2
    B = (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
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

    # The floor wins in L, so trough inputs need the 中间量 L-row check.
    earn_l = v_l * disc_lm
    l_row = re.search(
        r"^\|\s*L\s*\|\s*([0-9.]+)\s*\|[^|]*\|\s*([0-9.]+)\s*\|[^|]*\|\s*\*?\*?(−?-?[0-9.]+)",
        md,
        re.MULTILINE,
    )
    if not l_row:
        errors.append("§3 中间量 L 行未找到（L 档输入否则无任何校验）")
    else:
        for label, got, want in (
            ("Rev", float(l_row.group(1)), rev_l),
            ("GP", float(l_row.group(2)), gp_l),
            ("EBIT", float(l_row.group(3).replace("−", "-")), ebit_l),
        ):
            if abs(got - want) > 0.05:
                errors.append(f"中间量 L/{label}: stated {got} vs recomputed {want:.2f}")
    if earn_l >= floor:
        errors.append(
            f"L 盈利腿 {earn_l:.2f} 已不低于资产地板 {floor:.2f} —— A10 的 L 档口径叙述必须改写"
        )

    # H opex should stay near the locked 24.5% ratio (A7).
    opex_ratio_h = inp["opex_h"] / rev_h if rev_h else 0.0
    if abs(opex_ratio_h - 0.245) > 0.005:
        errors.append(f"opex_h/rev_h={opex_ratio_h:.3%} vs locked 24.5% (A7)")

    zone_nums: set[float] = set()
    for line in out_sec.splitlines():
        if line.startswith("| `"):
            zone_nums.update(float(x) for x in re.findall(r"([0-9]+\.[0-9]+)", line))
    for name, val in (("L", L), ("A", A), ("B", B), ("H", H)):
        if not any(abs(val - z) <= TOL for z in zone_nums):
            errors.append(f"zone 表缺少边界 {name}={val:.2f}")
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
        f"rev($M)={rev_l:.2f}/{rev_m:.2f}/{rev_h:.2f}"
        f"  (M core={rev_core_m:.2f}+opt={rev_opt_m:.2f}"
        f"  H core={rev_core_h:.2f}+opt={rev_opt_h:.2f})"
    )
    print(
        f"ebit={ebit_l:.2f}/{ebit_m:.2f}/{ebit_h:.2f}"
        f"  nopat={nopat_l:.2f}/{nopat_m:.2f}/{nopat_h:.2f}"
    )
    print(
        f"ebit_margin={ebit_l / rev_l:.1%}/{ebit_m / rev_m:.1%}/{ebit_h / rev_h:.1%}"
        f"  opex_ratio={inp['opex_l'] / rev_l:.1%}/{inp['opex_m'] / rev_m:.1%}/{opex_ratio_h:.1%}"
    )
    print(
        f"V@T={v_l:.2f}/{v_m:.2f}/{v_h:.2f}"
        f"  disc_LM={disc_lm:.5f} ({years_lm:.0f}y)"
        f"  disc_H={disc_h:.5f} ({years_h:.0f}y @ {inp['r_disc']:.0%})"
    )
    print(f"pe={inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']}  tbvps={tbvps:.3f} floor(pb*tbvps)={floor:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
