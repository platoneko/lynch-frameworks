#!/usr/bin/env python3
"""601899.SH (Zijin Mining) valuation eval — recompute anchors from frameworks/601899.SH.md.

frameworks/601899.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: zijin_fed_li_dual_axis_gp_pe_v4

Two orthogonal axes:
  * Fed rate path → gold / copper USD ladder (_AXIS.fed-path-gold-copper)
  * Lithium supply regime → battery-grade Li2CO3 CNY (_AXIS.lithium-carbonate)

Gold/copper/silver use current consolidated sales (no discount). Lithium uses
2028 planned volume (30 万 t LCE) discounted n_disc_li years at r_disc_li.
Residual block excludes lithium. Cycle PE 12 flat; L floored at pb_floor × bps.

M regression (rewritten): gold+copper+silver+non-li residual reproduce the
1H2026 annualised bridge; lithium is PV(30 万 t × axis-M realization), so
group M parent is above 1H2026×2 by the lithium volume uplift.

Run:  python3 eval/601899.SH.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import check_au_cu_mount, check_li2co3_mount  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "601899.SH.md"
PEER = Path(__file__).resolve().parent.parent / "frameworks" / "603993.SH.md"
FORMULA_ID = "zijin_fed_li_dual_axis_gp_pe_v4"
TOL = 0.05
YI = 1e8
OZ_TO_G = 31.1035

SHARED_LADDER = {
    "lme_cu_l": "p_cu_l",
    "lme_cu_m": "p_cu_m",
    "lme_cu_h": "p_cu_h",
    "lme_au_l": "lme_au_l",
    "lme_au_m": "lme_au_m",
    "lme_au_h": "lme_au_h",
}

# 1H2026×2 for the non-lithium bridge check (see M guard below).
H1_2026_X2 = {
    "gp": (194_178_458_630 - 120_881_455_727) * 2,
    "pretax": 63_489_448_069 * 2,
    "net_income": (63_489_448_069 - 13_676_755_053) * 2,
    "parent": 39_169_807_243 * 2,
}
IDENTITY_TOL = 0.01

M_PRICE_REF = {"p_au": ("price_au_m", 1006.5), "p_cu": ("price_cu_m", 84466.0)}
M_PRICE_TOL = 0.005

# 1H2026 lithium: revenue from product table; GP from business-map 3.4% share.
LI_REV_H1 = (28.80 + 10.98) * 1e8
LI_GP_H1 = 732.97e8 * 0.034
LI_VOL_H1 = 4.4e4
LI_ASP_H1 = LI_REV_H1 / LI_VOL_H1
LI_COST_H1 = (LI_REV_H1 - LI_GP_H1) / LI_VOL_H1

REQUIRED = [
    "price", "shares", "bps",
    "fx_usd_cny", "realization_au", "realization_cu",
    "lme_au_l", "lme_au_m", "lme_au_h", "vol_au_g", "cost_au",
    "lme_cu_l", "lme_cu_m", "lme_cu_h", "vol_cu_t", "cost_cu",
    "vol_ag_g", "price_ag_m", "cost_ag",
    "li2co3_l", "li2co3_m", "li2co3_h", "realization_li",
    "vol_li_t", "cost_li", "r_disc_li", "n_disc_li",
    "gp_rest", "rev_other_mine", "levy_rate", "opex_fixed", "inv_income",
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


def prices(inp: dict[str, float], tag: str) -> tuple[float, float, float, float]:
    p_au = inp[f"lme_au_{tag}"] / OZ_TO_G * inp["fx_usd_cny"] * inp["realization_au"]
    p_cu = inp[f"lme_cu_{tag}"] * inp["fx_usd_cny"] * inp["realization_cu"]
    p_ag = inp["price_ag_m"] * inp[f"lme_au_{tag}"] / inp["lme_au_m"]
    p_li = inp[f"li2co3_{tag}"] * inp["realization_li"]
    return p_au, p_cu, p_ag, p_li


def scenario(inp: dict[str, float], tag: str) -> dict[str, float]:
    p_au, p_cu, p_ag, p_li = prices(inp, tag)
    disc = (1.0 + inp["r_disc_li"]) ** (-inp["n_disc_li"])

    gp_au = inp["vol_au_g"] * (p_au - inp["cost_au"])
    gp_cu = inp["vol_cu_t"] * (p_cu - inp["cost_cu"])
    gp_ag = inp["vol_ag_g"] * (p_ag - inp["cost_ag"])
    gp_li = inp["vol_li_t"] * (p_li - inp["cost_li"]) * disc
    rev_li = inp["vol_li_t"] * p_li * disc

    gp = gp_au + gp_cu + gp_ag + inp["gp_rest"] + gp_li
    mine_rev = (
        inp["vol_au_g"] * p_au
        + inp["vol_cu_t"] * p_cu
        + inp["rev_other_mine"]
        + rev_li
    )
    levy = mine_rev * inp["levy_rate"]
    pretax = gp - levy - inp["opex_fixed"] + inp["inv_income"]
    net = pretax * (1.0 - inp["tax_rate"])
    parent = net * (1.0 - inp["nci_share"])
    return {
        "p_au": p_au, "p_cu": p_cu, "p_ag": p_ag, "p_li": p_li,
        "gp_au": gp_au, "gp_cu": gp_cu, "gp_ag": gp_ag, "gp_li": gp_li,
        "gp": gp, "levy": levy, "pretax": pretax, "net_income": net,
        "parent": parent, "eps": parent / inp["shares"], "disc": disc,
    }


def lithium_parent_standalone(asp: float, vol: float, inp: dict[str, float]) -> float:
    """Marginal parent from a lithium volume×ASP block (levy on li rev only)."""
    gp = (asp - inp["cost_li"]) * vol
    rev = asp * vol
    pbt = gp - inp["levy_rate"] * rev
    return pbt * (1.0 - inp["tax_rate"]) * (1.0 - inp["nci_share"])


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
    for metal, keys in (
        ("gold", ("lme_au_l", "lme_au_m", "lme_au_h")),
        ("copper", ("lme_cu_l", "lme_cu_m", "lme_cu_h")),
        ("li2co3", ("li2co3_l", "li2co3_m", "li2co3_h")),
    ):
        lo, mid, hi = (inp[k] for k in keys)
        if not (lo < mid < hi):
            errors.append(f"{metal} ladder violated: {lo}/{mid}/{hi}")
    if not (inp["pe_lo"] < inp["pe_mid"] < inp["pe_hi"]):
        errors.append(f"pe band violated: {inp['pe_lo']}/{inp['pe_mid']}/{inp['pe_hi']}")
    if inp["r_disc_li"] <= 0 or inp["n_disc_li"] < 0:
        errors.append("lithium discount inputs invalid")
    if abs(inp["cost_li"] - LI_COST_H1) / LI_COST_H1 > 0.01:
        errors.append(f"cost_li {inp['cost_li']:.2f} vs H1-implied {LI_COST_H1:.2f}")
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    errors += check_au_cu_mount(
        (inp["lme_au_l"], inp["lme_au_m"], inp["lme_au_h"]),
        (inp["lme_cu_l"], inp["lme_cu_m"], inp["lme_cu_h"]),
    )
    errors += check_li2co3_mount(
        (inp["li2co3_l"], inp["li2co3_m"], inp["li2co3_h"]),
    )
    peer = parse_inputs(PEER.read_text(encoding="utf-8"))
    for ours, theirs in SHARED_LADDER.items():
        if theirs not in peer:
            errors.append(f"peer 603993.SH missing {theirs}")
        elif abs(inp[ours] - peer[theirs]) > 1e-6:
            errors.append(
                f"shared ladder drift: {ours}={inp[ours]} vs 603993.{theirs}={peer[theirs]}"
            )
    if errors:
        print("FAIL (shared ladder):", "; ".join(errors), file=sys.stderr)
        return 1

    S = {t: scenario(inp, t) for t in ("l", "m", "h")}

    if inp["price_ag_m"] <= inp["cost_ag"]:
        errors.append("silver unit cost exceeds M price")
    if S["l"]["p_au"] <= inp["cost_au"] or S["l"]["p_cu"] <= inp["cost_cu"]:
        errors.append("unit cost exceeds L-scenario Au/Cu price")
    if S["l"]["p_li"] <= inp["cost_li"]:
        errors.append("unit cost exceeds L-scenario lithium price")

    for key, (label, ref) in M_PRICE_REF.items():
        got = S["m"][key]
        if abs(got / ref - 1.0) > M_PRICE_TOL:
            errors.append(f"{label} derived {got:.2f} vs filing-implied {ref}")

    # Lithium realization was calibrated as H1 ASP / old axis M (150,000); the
    # axis M now sits on the 2027 consensus deck, so p_li_m = H1 ASP × M/150k
    # rather than the H1 ASP itself.  The M regression below still pins M.
    li_m_ref = LI_ASP_H1 * inp["li2co3_m"] / 150_000
    if abs(S["m"]["p_li"] / li_m_ref - 1.0) > M_PRICE_TOL:
        errors.append(
            f"price_li_m derived {S['m']['p_li']:.2f} vs H1 ASP × M/150k {li_m_ref:.2f}"
        )

    # M regression (rewritten): non-li 1H26×2 + lithium PV uplift.
    li_old = lithium_parent_standalone(LI_ASP_H1, LI_VOL_H1 * 2, inp)
    li_new = lithium_parent_standalone(S["m"]["p_li"], inp["vol_li_t"], inp) * S["m"]["disc"]
    expected_m_parent = H1_2026_X2["parent"] - li_old + li_new
    got_m = S["m"]["parent"]
    if abs(got_m / expected_m_parent - 1.0) > IDENTITY_TOL:
        errors.append(
            f"M-scenario parent {got_m / YI:.1f}亿 vs expected "
            f"{expected_m_parent / YI:.1f}亿 (H1×2 − old li + PV li) "
            f"({got_m / expected_m_parent - 1:+.2%})"
        )
    if errors:
        print("FAIL (M guard):", "; ".join(errors), file=sys.stderr)
        return 1

    floor = inp["pb_floor"] * inp["bps"]
    L = max(S["l"]["eps"] * inp["pe_mid"], floor)
    M = S["m"]["eps"] * inp["pe_mid"]
    H = S["h"]["eps"] * inp["pe_mid"]
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
    for k, v in {"L": L, "M": M, "H": H, "A": A, "B": B}.items():
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
        "shared Au/Cu OK vs _AXIS.fed-path-gold-copper (+ peer 603993.SH); "
        "Li2CO3 OK vs _AXIS.lithium-carbonate: "
        + "/".join(f"{inp[k]:g}" for k in ("li2co3_l", "li2co3_m", "li2co3_h"))
        + " 元/t"
    )
    print(
        f"{'档':<3}{'金元/克':>9}{'铜元/吨':>10}{'锂元/吨':>10}"
        f"{'金腿':>8}{'铜腿':>8}{'银腿':>7}{'锂腿':>8}"
        f"{'毛利':>9}{'归母':>9}{'EPS':>8}"
    )
    for t in ("l", "m", "h"):
        s = S[t]
        print(
            f"{t.upper():<3}{s['p_au']:9.1f}{s['p_cu']:10.0f}{s['p_li']:10.0f}"
            f"{s['gp_au'] / YI:8.1f}{s['gp_cu'] / YI:8.1f}{s['gp_ag'] / YI:7.1f}"
            f"{s['gp_li'] / YI:8.1f}{s['gp'] / YI:9.1f}{s['parent'] / YI:9.1f}{s['eps']:8.4f}"
        )
    print(
        f"M guard OK: parent {S['m']['parent'] / YI:.1f}亿 = "
        f"H1×2 {H1_2026_X2['parent'] / YI:.1f} − old-li {li_old / YI:.1f} "
        f"+ PV-li {li_new / YI:.1f}"
    )
    print(
        f"pe_mid={inp['pe_mid']:g}  floor={floor:.2f}  "
        f"li disc={(1 + inp['r_disc_li']) ** (-inp['n_disc_li']):.4f} "
        f"({inp['n_disc_li']:g}y @{inp['r_disc_li']:.0%})"
    )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"price={inp['price']} zone={zone}")
    print(
        "PE sensitivity: "
        + " | ".join(
            f"pe={pe:g} -> {zone_of(inp['price'], max(S['l']['eps'] * pe, floor), S['m']['eps'] * pe, S['h']['eps'] * pe)}"
            for pe in (inp["pe_lo"], inp["pe_mid"], inp["pe_hi"])
        )
    )

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
