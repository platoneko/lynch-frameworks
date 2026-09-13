#!/usr/bin/env python3
"""1772.HK (Ganfeng Lithium H) valuation eval.

frameworks/1772.HK.md is the source of truth.
formula_id: ganfeng_li2co3_twopoint_batt_pe10_v2

Ganfeng does not disclose lithium sales volumes or its self-supplied feed
share, so the lithium leg (salts + mining + JV share, all inside the reported
segment results) is not built bottom-up.  Its pre-tax profit is a straight
line through two of the company's own realised half-years -- 2025H1 at the
cycle trough and 2026H1 on the 2026 platform -- read at the shared Li2CO3 axis
rungs.  The line carries 2026H1 volume; the shared axis is a 2027-28 price
deck, so the lithium leg is scaled by the sell-side 2027E/2026E sales ratio
and discounted one year -- the same "2027 volume x delta" construction as
9696.HK and 000792.SZ.  The battery leg is its annualised segment result
(current, undiscounted) and also supplies the first V_opt component,
solid-state (k=1 x today's battery leg, A2e-7c).  The second component is the
2028+ volume growth (Mt Marion upgrade, Goulamina / Cauchari phase 2): no
per-project unit economics, so it is valued as k=1 x the company's own
2026->2027 step (vol_2027e - vol_2026e) read on the two-point line at the axis
M rung, discounted two years (A12).  Per-tier credits for both components are
hard-coded here and never enter Inputs (A2e-7a); a value-weighted blend is
also stated in the doc for the daily digest, which only reads one p triple.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import check_li2co3_mount  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "1772.HK.md"
FORMULA_ID = "ganfeng_li2co3_twopoint_batt_pe10_v2"
TOL = 0.05

# Per-tier option credits (A9): solid-state is a judgement call, the 2028 step
# is anchored on Dongwu's 2028E/2027E (+12.5% / one 17.4% step ~ 0.72).
P_SS = {"l": 0.0, "m": 0.25, "h": 1.0}
P_VOL = {"l": 0.0, "m": 0.7, "h": 1.0}

REQUIRED = [
    "price", "shares", "bps", "fx_hkd_per_cny",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "cal_p0", "cal_li_pretax_0", "cal_p1", "cal_li_pretax_1",
    "vol_2026e", "vol_2027e", "r_disc", "n_disc",
    "batt_pretax", "net_finance",
    "tax_rate", "nci_share",
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


def parent_from_pretax(pretax: float, inp: dict[str, float]) -> float:
    return pretax * (1.0 - inp["tax_rate"]) * (1.0 - inp["nci_share"])


def per_share_hkd(parent_yi: float, inp: dict[str, float]) -> float:
    """亿 CNY → HKD per share (shares in millions)."""
    return parent_yi * 100.0 / inp["shares"] * inp["fx_hkd_per_cny"]


def vol_scale(inp: dict[str, float]) -> float:
    """2027E/2026E sales ratio, discounted back one year (A11)."""
    disc = (1.0 + inp["r_disc"]) ** (-inp["n_disc"])
    return inp["vol_2027e"] / inp["vol_2026e"] * disc


def li_2026(inp: dict[str, float], li2co3: float) -> float:
    """Lithium-leg pre-tax at 2026H1 volume structure, 亿 CNY (the raw two-point line)."""
    slope = (inp["cal_li_pretax_1"] - inp["cal_li_pretax_0"]) / (
        inp["cal_p1"] - inp["cal_p0"]
    )
    return inp["cal_li_pretax_0"] + (li2co3 - inp["cal_p0"]) * slope


def v_opt_vol(inp: dict[str, float], li2co3: float) -> float:
    """One more 2026->2027-sized volume step at the given rung, 2028 run-rate (A12)."""
    step = (inp["vol_2027e"] - inp["vol_2026e"]) / inp["vol_2026e"]
    disc2 = (1.0 + inp["r_disc"]) ** (-2 * inp["n_disc"])
    pretax = li_2026(inp, li2co3) * step * disc2
    return per_share_hkd(parent_from_pretax(pretax, inp), inp) * inp["pe_mid"]


def scenario(inp: dict[str, float], tag: str) -> dict[str, float]:
    li = li_2026(inp, inp[f"li2co3_{tag}"]) * vol_scale(inp)
    pretax = li + inp["batt_pretax"] - inp["net_finance"]
    parent = parent_from_pretax(pretax, inp)
    eps = per_share_hkd(parent, inp)
    return {"li": li, "pretax": pretax, "parent": parent, "eps": eps}


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
    if not (inp["cal_p0"] < inp["cal_p1"] and inp["cal_li_pretax_0"] < inp["cal_li_pretax_1"]):
        errors.append("calibration points must be ordered (trough below platform)")
    if not inp["vol_2027e"] > inp["vol_2026e"]:
        errors.append("2027E volume must exceed 2026E (the scale is a growth factor)")
    errors += check_li2co3_mount(
        (inp["li2co3_l"], inp["li2co3_m"], inp["li2co3_h"])
    )
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    S = {t: scenario(inp, t) for t in ("l", "m", "h")}
    floor = inp["pb_floor"] * inp["bps"]
    scenario_L = S["l"]["eps"] * inp["pe_mid"]
    L = max(scenario_L, floor)
    M = S["m"]["eps"] * inp["pe_mid"]
    H = S["h"]["eps"] * inp["pe_mid"]
    A, B = (L + M) / 2, (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    # Option components: solid-state (k=1 x today's battery leg) and one more
    # 2026->2027 volume step at the axis M rung (A12).  Both at the same multiple.
    v_ss = per_share_hkd(parent_from_pretax(inp["batt_pretax"], inp), inp) * inp["pe_mid"]
    v_vol = v_opt_vol(inp, inp["li2co3_m"])
    v_opt = v_ss + v_vol

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1

    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    for k, v in {"L": L, "M": M, "H": H, "A": A, "B": B}.items():
        s = first_float(rf"\b{k} = \*\*([0-9.]+)\*\*", out_sec)
        if s is None:
            errors.append(f"stated {k} not found")
        elif abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")
    s = first_float(r"`scenario_L` = \*\*([0-9.]+)\*\*", out_sec)
    if s is None or abs(s - scenario_L) > TOL:
        errors.append(f"scenario_L: stated {s} vs recomputed {scenario_L:.4f}")
    vm = re.search(
        r"V_\{opt\}\\\) = \*\*([0-9.]+)\*\*（固态 \*\*([0-9.]+)\*\* \+ 2028 量增 \*\*([0-9.]+)\*\*）",
        out_sec,
    )
    if vm is None:
        errors.append("stated V_opt line (total + two components) not found")
    else:
        for label, stated, want in (
            ("V_opt", float(vm.group(1)), v_opt),
            ("V_opt^ss", float(vm.group(2)), v_ss),
            ("V_opt^vol", float(vm.group(3)), v_vol),
        ):
            if abs(stated - want) > TOL:
                errors.append(f"{label}: stated {stated} vs recomputed {want:.4f}")

    # zone+V table: the two per-tier credit triples are hard-coded above; the
    # doc must restate them verbatim and the corrected band must reproduce.
    for name, table, rx in (
        ("p^ss", P_SS, r"p\^\{ss\}_\{L/M/H\}\\\) = \*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*"),
        ("p^vol", P_VOL, r"p\^\{vol\}_\{L/M/H\}\\\) = \*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*"),
    ):
        pm = re.search(rx, out_sec)
        if pm is None:
            errors.append(f"{name} triple not stated")
            continue
        for k, got in zip("lmh", pm.groups()):
            if abs(float(got) - table[k]) > 1e-9:
                errors.append(f"{name}_{k}: stated {got} vs eval constant {table[k]}")
    base = {"L": L, "M": M, "H": H}
    adj = {k: base[k] + P_SS[t] * v_ss + P_VOL[t] * v_vol for k, t in zip("LMH", "lmh")}
    for k, v in adj.items():
        s = first_float(rf"{k}′ = \*\*([0-9.]+)\*\*", out_sec)
        if s is None or abs(s - v) > TOL:
            errors.append(f"{k}′ (zone+V): stated {s} vs recomputed {v:.4f}")
    # The daily digest reads a single p triple applied to the total: the stated
    # blend must land on the same corrected band.
    pm = re.search(
        r"p_L/p_M/p_H\\\) = \*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*", out_sec
    )
    if pm is None:
        errors.append("blended p_L/p_M/p_H (digest) not stated")
    else:
        for k, t, got in zip("LMH", "lmh", pm.groups()):
            blended = base[k] + float(got) * v_opt
            if abs(blended - adj[k]) > TOL:
                errors.append(
                    f"blended p_{t}={got} gives {k}′={blended:.4f}, components give {adj[k]:.4f}"
                )

    zm = re.search(r"底牌 zone = \*\*`([a-z_]+)`\*\*", out_sec)
    stated_zone = zm.group(1) if zm else None
    if stated_zone != zone:
        errors.append(f"zone: stated {stated_zone} vs recomputed {zone}")

    slope = (inp["cal_li_pretax_1"] - inp["cal_li_pretax_0"]) / (inp["cal_p1"] - inp["cal_p0"])
    print(f"formula_id={FORMULA_ID}")
    print(
        "li2co3 OK: "
        + "/".join(f"{inp[k]:g}" for k in ("li2co3_l", "li2co3_m", "li2co3_h"))
        + f"  slope={slope*1e4:.2f} 亿/万元"
        + f"  vol_scale={inp['vol_2027e']:g}/{inp['vol_2026e']:g} x disc = {vol_scale(inp):.4f}"
    )
    print(f"{'档':<3}{'锂腿税前':>9}{'税前':>8}{'归母':>8}{'EPS_HKD':>9}{'锚点':>8}")
    for t in ("l", "m", "h"):
        s_ = S[t]
        print(
            f"{t.upper():<3}{s_['li']:9.1f}{s_['pretax']:8.1f}{s_['parent']:8.1f}"
            f"{s_['eps']:9.3f}{s_['eps']*inp['pe_mid']:8.2f}"
        )
    winner = "floor" if floor > scenario_L else "scenario_L"
    print(f"floor={floor:.2f}  scenario_L={scenario_L:.2f}  winner={winner}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  "
          f"V_opt={v_opt:.2f} = ss {v_ss:.2f} + vol {v_vol:.2f} "
          f"(one step {(inp['vol_2027e'] - inp['vol_2026e']) / inp['vol_2026e']:.1%} @axis M, δ²)")
    print("zone+V: " + "  ".join(
        f"{k}′={adj[k]:.2f}(p_ss={P_SS[t]:g},p_vol={P_VOL[t]:g})" for k, t in zip("LMH", "lmh")
    ) + f"  A′={(adj['L'] + adj['M']) / 2:.2f} B′={(adj['M'] + adj['H']) / 2:.2f}"
        f"  vol step @L/H rung = {v_opt_vol(inp, inp['li2co3_l']):.2f}/{v_opt_vol(inp, inp['li2co3_h']):.2f}")
    print(
        f"L/M={L/M:.2f} H/M={H/M:.2f} (H-L)/2M={(H-L)/2/M:.2%} V_opt/M={v_opt/M:.1%} "
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
