#!/usr/bin/env python3
"""601899.SH (Zijin Mining) valuation eval — recompute anchors from frameworks/601899.SH.md.

frameworks/601899.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: zijin_fed_path_metal_ladder_gp_pe_v3

Scenario axis is the Fed rate path: L = hiking, M = on hold, H = cutting
without recession.  Gold maps monotonically to real rates; copper does not,
so the two legs are anchored on different kinds of evidence (see A17/A18).

Main ruler: consolidated annualised sales volume x (gold leg + copper leg +
silver leg) + a flat residual block -> group gross profit -> resource levy,
fixed opex, investment income -> attributable net profit -> cycle PE 12.
No discounting (current capacity x today's multiple, both sides same period).
L is additionally floored at pb_floor x bps (the asset floor exists today, so
it is not discounted).

RMB scenario prices are always derived from LME x FX x realization; the
framework must not hand-write them.  Silver rides the gold ladder.

Two guards beyond the anchor comparison:
  * M regression guard — the on-hold scenario MUST reproduce the annualised
    1H2026 reported P&L, because "rates unchanged" is by definition the
    current regime.
  * shared-ladder guard — the USD gold/copper ladder MUST match
    frameworks/603993.SH.md cell by cell.  The two tickers price the same
    metals; keeping that in a comment instead of a test is how they drifted.

Run:  python3 eval/601899.SH.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "601899.SH.md"
PEER = Path(__file__).resolve().parent.parent / "frameworks" / "603993.SH.md"
FORMULA_ID = "zijin_fed_path_metal_ladder_gp_pe_v3"
TOL = 0.05  # anchors stated to 2 decimals
YI = 1e8  # 亿, for reporting
OZ_TO_G = 31.1035

# The shared USD ladder: our field -> the peer framework's field.
SHARED_LADDER = {
    "lme_cu_l": "p_cu_l",
    "lme_cu_m": "p_cu_m",
    "lme_cu_h": "p_cu_h",
    "lme_au_l": "lme_au_l",
    "lme_au_m": "lme_au_m",
    "lme_au_h": "lme_au_h",
}

# 1H2026 interim report, annualised (x2). The M scenario must land here.
H1_2026_X2 = {
    "gp": (194_178_458_630 - 120_881_455_727) * 2,
    "pretax": 63_489_448_069 * 2,
    "net_income": (63_489_448_069 - 13_676_755_053) * 2,
    "parent": 39_169_807_243 * 2,
}
IDENTITY_TOL = 0.01  # 1% — inputs are rounded for readability

# 1H2026 realized RMB prices backed out of the interim sales tables; the
# derived M prices must reproduce them, which is what welds LME x FX x
# realization to the filing.
M_PRICE_REF = {"p_au": ("price_au_m", 1006.5), "p_cu": ("price_cu_m", 84466.0)}
M_PRICE_TOL = 0.005  # 0.5%

REQUIRED = [
    "price", "shares", "bps",
    "fx_usd_cny", "realization_au", "realization_cu",
    "lme_au_l", "lme_au_m", "lme_au_h", "vol_au_g", "cost_au",
    "lme_cu_l", "lme_cu_m", "lme_cu_h", "vol_cu_t", "cost_cu",
    "vol_ag_g", "price_ag_m", "cost_ag", "gp_rest",
    "rev_other_mine", "levy_rate", "opex_fixed", "inv_income",
    "tax_rate", "nci_share",
    "pe_mid", "pe_lo", "pe_hi", "pb_floor",
]


def parse_inputs(md: str) -> dict[str, float]:
    """Parse §3 Inputs table: | field | value | ... |"""
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


def prices(inp: dict[str, float], tag: str) -> tuple[float, float, float]:
    """Scenario RMB prices, derived — never read from the table."""
    p_au = inp[f"lme_au_{tag}"] / OZ_TO_G * inp["fx_usd_cny"] * inp["realization_au"]
    p_cu = inp[f"lme_cu_{tag}"] * inp["fx_usd_cny"] * inp["realization_cu"]
    p_ag = inp["price_ag_m"] * inp[f"lme_au_{tag}"] / inp["lme_au_m"]
    return p_au, p_cu, p_ag


def scenario(inp: dict[str, float], tag: str) -> dict[str, float]:
    """One rate-path scenario -> gross profit bridge -> attributable EPS."""
    p_au, p_cu, p_ag = prices(inp, tag)
    gp_au = inp["vol_au_g"] * (p_au - inp["cost_au"])
    gp_cu = inp["vol_cu_t"] * (p_cu - inp["cost_cu"])
    gp_ag = inp["vol_ag_g"] * (p_ag - inp["cost_ag"])
    gp = gp_au + gp_cu + gp_ag + inp["gp_rest"]

    # rev_other_mine already carries silver revenue at the M level and is held
    # flat, so silver's scenario delta rides the margin leg only (<0.6亿/档).
    mine_rev = inp["vol_au_g"] * p_au + inp["vol_cu_t"] * p_cu + inp["rev_other_mine"]
    levy = mine_rev * inp["levy_rate"]

    pretax = gp - levy - inp["opex_fixed"] + inp["inv_income"]
    net = pretax * (1.0 - inp["tax_rate"])
    parent = net * (1.0 - inp["nci_share"])
    return {
        "p_au": p_au, "p_cu": p_cu, "p_ag": p_ag,
        "gp_au": gp_au, "gp_cu": gp_cu, "gp_ag": gp_ag, "gp": gp,
        "levy": levy, "pretax": pretax, "net_income": net, "parent": parent,
        "eps": parent / inp["shares"],
    }


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

    # --- Step 1: sanity of the ladder itself --------------------------------
    errors: list[str] = []
    for metal, keys in (("gold", ("lme_au_l", "lme_au_m", "lme_au_h")),
                        ("copper", ("lme_cu_l", "lme_cu_m", "lme_cu_h"))):
        lo, mid, hi = (inp[k] for k in keys)
        if not (lo < mid < hi):
            errors.append(f"{metal} USD ladder violated: {lo}/{mid}/{hi}")
    if not (inp["pe_lo"] < inp["pe_mid"] < inp["pe_hi"]):
        errors.append(f"pe band violated: {inp['pe_lo']}/{inp['pe_mid']}/{inp['pe_hi']}")
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    # --- Step 2: shared-ladder guard vs 603993.SH ---------------------------
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
        errors.append("silver unit cost exceeds M price — check 口径")
    if S["l"]["p_au"] <= inp["cost_au"] or S["l"]["p_cu"] <= inp["cost_cu"]:
        errors.append("unit cost exceeds L-scenario price — check 口径")

    # --- Step 3a: M-scenario derived prices must match the filing -----------
    for key, (label, ref) in M_PRICE_REF.items():
        got = S["m"][key]
        if abs(got / ref - 1.0) > M_PRICE_TOL:
            errors.append(f"{label} derived {got:.2f} vs filing-implied {ref}")

    # --- Step 3b: M regression guard — must reproduce annualised 1H2026 -----
    for key, ref in H1_2026_X2.items():
        got = S["m"][key]
        if abs(got / ref - 1.0) > IDENTITY_TOL:
            errors.append(
                f"M-scenario {key} {got / YI:.1f}亿 vs 1H26x2 {ref / YI:.1f}亿 "
                f"({got / ref - 1:+.2%} > {IDENTITY_TOL:.0%})"
            )
    if errors:
        print("FAIL (M guard):", "; ".join(errors), file=sys.stderr)
        return 1

    # --- Step 4: anchors ----------------------------------------------------
    floor = inp["pb_floor"] * inp["bps"]  # asset floor exists today -> not discounted
    L = max(S["l"]["eps"] * inp["pe_mid"], floor)
    M = S["m"]["eps"] * inp["pe_mid"]
    H = S["h"]["eps"] * inp["pe_mid"]
    A = (L + M) / 2
    B = (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1

    # --- Step 5: compare against the stated Outputs -------------------------
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

    # --- report -------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print("shared ladder OK vs 603993.SH: cu " + "/".join(
        f"{inp[k]:g}" for k in ("lme_cu_l", "lme_cu_m", "lme_cu_h")
    ) + " $/t, au " + "/".join(
        f"{inp[k]:g}" for k in ("lme_au_l", "lme_au_m", "lme_au_h")
    ) + " $/oz")
    print(
        f"{'档':<3}{'金元/克':>9}{'铜元/吨':>10}{'金腿':>9}{'铜腿':>9}{'银腿':>8}"
        f"{'毛利':>10}{'税金附加':>10}{'利润总额':>11}{'归母':>10}{'EPS':>8}"
    )
    for t in ("l", "m", "h"):
        s = S[t]
        print(
            f"{t.upper():<3}{s['p_au']:9.1f}{s['p_cu']:10.0f}{s['gp_au'] / YI:9.1f}"
            f"{s['gp_cu'] / YI:9.1f}{s['gp_ag'] / YI:8.1f}{s['gp'] / YI:10.1f}"
            f"{s['levy'] / YI:10.1f}{s['pretax'] / YI:11.1f}{s['parent'] / YI:10.1f}{s['eps']:8.4f}"
        )
    print(f"M guard OK: M 档归母 {S['m']['parent'] / YI:.1f}亿 ≈ 1H26×2 {H1_2026_X2['parent'] / YI:.1f}亿")
    print(f"pe_mid={inp['pe_mid']:g} (band {inp['pe_lo']:g}-{inp['pe_hi']:g})  floor(pb*bps)={floor:.2f}")
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
