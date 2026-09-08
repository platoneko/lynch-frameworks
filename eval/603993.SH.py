#!/usr/bin/env python3
"""603993.SH (CMOC) valuation eval — recompute anchors from frameworks/603993.SH.md.

frameworks/603993.SH.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on any mismatch.

formula_id: cmoc_fed_path_cu_au_ladder_gp_bridge_pe_v2

Scenario axis is the Fed rate path: L = hiking, M = on hold, H = cutting
without recession (see A19).  The recession-cut case moves gold and copper in
opposite directions and is deliberately NOT an anchor.

Main ruler: the 2026 interim segment gross-profit table is the audited base.
The copper leg is shifted by (annualised copper sales volume x LME price delta
x realisation x FX x (1 - DRC royalty)); the gold leg rides the shared gold
ladder; the cobalt leg is a quota-driven gross-profit level given per scenario;
the other-mining / IXM-trading / elimination / opex blocks are held flat across
all three scenarios.  Gross profit -> pretax -> x(1-tax)x(1-minority) -> net
profit to parent -> x counter-cyclical PE.

Gross-profit style inputs are in 亿 CNY and already annualised (2026H1 x 2).

Beyond the anchor comparison, the shared-ladder guard checks the USD gold and
copper ladders cell by cell against frameworks/601899.SH.md — the two tickers
price the same metals, and keeping that in a comment is how they drifted.

Run:  python3 eval/603993.SH.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "603993.SH.md"
PEER = Path(__file__).resolve().parent.parent / "frameworks" / "601899.SH.md"
FORMULA_ID = "cmoc_fed_path_cu_au_ladder_gp_bridge_pe_v2"
TOL = 0.05  # anchors are stated to 2 decimals
YI = 1e8  # 亿

# The shared USD ladder: our field -> the peer framework's field.
SHARED_LADDER = {
    "p_cu_l": "lme_cu_l",
    "p_cu_m": "lme_cu_m",
    "p_cu_h": "lme_cu_h",
    "lme_au_l": "lme_au_l",
    "lme_au_m": "lme_au_m",
    "lme_au_h": "lme_au_h",
}

# Audited baseline: 2026 interim net profit to parent x 2 (161.52187亿 x 2).
# The M scenario re-uses the base copper price, so its recomputed net profit
# must land back on this number — that is what welds the bridge to the filing.
BASE_NP_PARENT_YI = 323.0437
BASE_NP_TOL_YI = 0.5

REQUIRED = [
    "price",
    "shares",
    "fx_usd_cny",
    "vol_cu",
    "p_cu_base",
    "p_cu_l",
    "p_cu_m",
    "p_cu_h",
    "lme_au_l",
    "lme_au_m",
    "lme_au_h",
    "vol_au_oz",
    "cost_au_oz",
    "price_au_m_oz",
    "realization_cu",
    "royalty_cu",
    "gp_cu_base",
    "gp_co_l",
    "gp_co_m",
    "gp_co_h",
    "gp_other",
    "gp_ixm",
    "gp_misc",
    "opex",
    "tax_rate",
    "mi_rate",
    "pe_l",
    "pe_m",
    "pe_h",
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
        if key in ("字段名",) or raw in ("取值",) or set(key) <= set("- :"):
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


def first_float(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


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

    # --- sanity guards (see §3 校验步骤) -------------------------------------
    if not (inp["p_cu_l"] < inp["p_cu_m"] < inp["p_cu_h"]):
        errors.append(
            f"copper price order violated: {inp['p_cu_l']}/{inp['p_cu_m']}/{inp['p_cu_h']}"
        )
    if not (inp["lme_au_l"] < inp["lme_au_m"] < inp["lme_au_h"]):
        errors.append(
            f"gold price order violated: {inp['lme_au_l']}/{inp['lme_au_m']}/{inp['lme_au_h']}"
        )
    if inp["price_au_m_oz"] <= inp["cost_au_oz"]:
        errors.append("gold unit cost exceeds M price — check 口径")
    if not (inp["gp_co_l"] < inp["gp_co_m"] < inp["gp_co_h"]):
        errors.append(
            f"cobalt leg order violated: {inp['gp_co_l']}/{inp['gp_co_m']}/{inp['gp_co_h']}"
        )
    # Counter-cyclical PE is a hard rule: a rising PE across rising price
    # scenarios would multiply the price optimism a second time.
    if not (inp["pe_l"] > inp["pe_m"] > inp["pe_h"]):
        errors.append(
            f"PE band must be counter-cyclical (pe_l>pe_m>pe_h): "
            f"{inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']}"
        )
    for k in ("tax_rate", "mi_rate", "royalty_cu"):
        if not (0.0 <= inp[k] < 1.0):
            errors.append(f"{k}={inp[k]} outside [0,1)")
    if not (0.80 <= inp["realization_cu"] <= 1.05):
        errors.append(f"realization_cu={inp['realization_cu']} implausible")
    if abs(inp["p_cu_m"] - inp["p_cu_base"]) > 1e-6:
        errors.append("p_cu_m must equal p_cu_base (M is the audited baseline)")
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    # --- shared-ladder guard vs 601899.SH ------------------------------------
    peer = parse_inputs(PEER.read_text(encoding="utf-8"))
    for ours, theirs in SHARED_LADDER.items():
        if theirs not in peer:
            errors.append(f"peer 601899.SH missing {theirs}")
        elif abs(inp[ours] - peer[theirs]) > 1e-6:
            errors.append(
                f"shared ladder drift: {ours}={inp[ours]} vs 601899.{theirs}={peer[theirs]}"
            )
    if errors:
        print("FAIL (shared ladder):", "; ".join(errors), file=sys.stderr)
        return 1

    # --- the ruler -----------------------------------------------------------
    def copper_leg(price_usd_t: float) -> float:
        """Annualised copper gross profit, 亿 CNY."""
        delta = (
            inp["vol_cu"]
            * (price_usd_t - inp["p_cu_base"])
            * inp["realization_cu"]
            * inp["fx_usd_cny"]
            * (1.0 - inp["royalty_cu"])
        )
        return inp["gp_cu_base"] + delta / YI

    def gold_leg(lme_au_usd_oz: float) -> tuple[float, float]:
        """Annualised gold gross profit, 亿 CNY, riding the shared gold ladder."""
        price_oz = inp["price_au_m_oz"] * lme_au_usd_oz / inp["lme_au_m"]
        return price_oz, inp["vol_au_oz"] * (price_oz - inp["cost_au_oz"]) / YI

    def scenario(price_usd_t: float, lme_au: float, gp_co: float, pe: float):
        gp_cu = copper_leg(price_usd_t)
        price_au_oz, gp_au = gold_leg(lme_au)
        gp = gp_cu + gp_au + gp_co + inp["gp_other"] + inp["gp_ixm"] + inp["gp_misc"]
        pretax = gp - inp["opex"]
        np_parent = pretax * (1.0 - inp["tax_rate"]) * (1.0 - inp["mi_rate"])
        eps = np_parent * YI / inp["shares"]
        return gp_cu, gp_au, price_au_oz, gp, pretax, np_parent, eps, eps * pe

    sc_l = scenario(inp["p_cu_l"], inp["lme_au_l"], inp["gp_co_l"], inp["pe_l"])
    sc_m = scenario(inp["p_cu_m"], inp["lme_au_m"], inp["gp_co_m"], inp["pe_m"])
    sc_h = scenario(inp["p_cu_h"], inp["lme_au_h"], inp["gp_co_h"], inp["pe_h"])

    # Baseline closure: M must reproduce the filed net profit to parent.
    if abs(sc_m[5] - BASE_NP_PARENT_YI) > BASE_NP_TOL_YI:
        errors.append(
            f"baseline closure broken: M net profit {sc_m[5]:.4f}亿 vs filed "
            f"{BASE_NP_PARENT_YI}亿 (2026H1 x 2)"
        )

    L, M, H = sc_l[7], sc_m[7], sc_h[7]
    A = (L + M) / 2
    B = (M + H) / 2
    zone = zone_of(inp["price"], L, M, H)

    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.4f}, {M:.4f}, {H:.4f}")

    # --- compare against the stated Outputs ----------------------------------
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
            errors.append(f"stated {k} not found in Outputs")
        elif abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")

    zm = re.search(r"zone = \*\*`([a-z_]+)`\*\*", out_sec)
    stated_zone = zm.group(1) if zm else None
    if stated_zone != zone:
        errors.append(f"zone: stated {stated_zone} vs recomputed {zone}")

    # --- report --------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print("shared ladder OK vs 601899.SH: cu " + "/".join(
        f"{inp[k]:g}" for k in ("p_cu_l", "p_cu_m", "p_cu_h")
    ) + " $/t, au " + "/".join(
        f"{inp[k]:g}" for k in ("lme_au_l", "lme_au_m", "lme_au_h")
    ) + " $/oz")
    for tag, sc, p, au in (
        ("L", sc_l, inp["p_cu_l"], inp["lme_au_l"]),
        ("M", sc_m, inp["p_cu_m"], inp["lme_au_m"]),
        ("H", sc_h, inp["p_cu_h"], inp["lme_au_h"]),
    ):
        print(
            f"{tag}: cu={p:>9.2f}$/t au={au:>7.0f}$/oz  gp_cu={sc[0]:7.2f}  gp_au={sc[1]:6.2f}  "
            f"gp={sc[3]:7.2f}  pretax={sc[4]:7.2f}  np={sc[5]:7.2f}亿  eps={sc[6]:.4f}  anchor={sc[7]:.4f}"
        )
    per_kusd = (
        inp["vol_cu"] * 1000.0 * inp["realization_cu"] * inp["fx_usd_cny"] * (1.0 - inp["royalty_cu"]) / YI
    )
    print(
        f"sensitivity: +$1000/t copper -> pretax {per_kusd:.2f}亿, "
        f"eps {per_kusd * (1 - inp['tax_rate']) * (1 - inp['mi_rate']) * YI / inp['shares']:.4f}"
    )
    print(f"pe={inp['pe_l']}/{inp['pe_m']}/{inp['pe_h']}  co_gp={inp['gp_co_l']}/{inp['gp_co_m']}/{inp['gp_co_h']}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
