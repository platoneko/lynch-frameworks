#!/usr/bin/env python3
"""WOLF.US (Wolfspeed) valuation eval — asset-PB bottom + court-EV recovery option.

frameworks/WOLF.US.md is the source of truth; this script recomputes
bottom L/M/H / A/B / zone / V_opt / 表3 and exits 1 on mismatch.

formula_id: wolf_asset_pb_fd_court_vopt_v3

Bottom = PB 0.55/0.80/1.00 × FULLY DILUTED book.  Post-Chapter-11 the three
converts are deep in the money, so the book that stands behind the diluted
share count is fresh-start equity + convert principal (the debt that vanishes
on conversion) + warrant proceeds, over `shares_fd` (A1/A11).  Using basic
shares is the single largest error available on this name.

There is no earnings numerator anywhere (consensus EPS negative through
FY28E), so neither Gordon nor EV/EBIT can generate a multiple, and an EV/Sales
ruler would hide an unrealised margin recovery inside the multiple (A3,
retired).  Revenue recovery is therefore the success path and lives in
V_opt: the ceiling is the court-approved fresh-start EV high, bridged to a
per-share value with today's net cash (A12); 表3 = base_k + p_k × V_opt with
P_K an eval constant, never an Input (A2e-7a).

Run:  python3 eval/WOLF.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    outputs_section,
    parse_inputs,
    report,
)
from eval.lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "WOLF.US.md"
FORMULA_ID = "wolf_asset_pb_fd_court_vopt_v3"
TOL = 0.05  # outputs rounded to 2 decimals
MM = 1e6  # inputs are in $M
TIERS = ("l", "m", "h")
# 表3 per-tier credit (A13): 拍值, no external anchor. Never an Input, never the base.
P_K = (0.0, 0.25, 1.0)

REQUIRED = [
    "price", "shares_fd", "cash", "debt", "conv_principal", "warrant_proceeds", "debt_total",
    "equity_book", "pb_l", "pb_m", "pb_h",
    "ev_court_l", "ev_court_m", "ev_court_h", "eq_court_bridge",
    "rev_l", "rev_m", "rev_h", "rev_fy26",
    "close_own_min",
]


def stated_v_opt(md: str) -> float | None:
    import re
    m = re.search(r"V_\{opt\}\D{0,20}\*\*([0-9.]+)\*\*", outputs_section(md))
    return float(m.group(1)) if m else None


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} not found in framework", file=sys.stderr)
        return 1

    i = parse_inputs(md)
    errors = check_missing(i, REQUIRED)
    if errors:
        return report(errors)

    # A1 counts converted shares, so A4 must exclude the debt those shares
    # replace and A11 must add it back to book. Both legs have to reconcile.
    if i["debt"] >= i["debt_total"] - 1e-9:
        errors.append(
            f"debt={i['debt']} is the full principal ({i['debt_total']}); shares_fd already "
            "prices the converts, so debt must be the non-convertible balance only (A1/A4)"
        )
    if abs(i["debt"] + i["conv_principal"] - i["debt_total"]) > 0.1:
        errors.append(f"debt({i['debt']}) + conv_principal({i['conv_principal']}) != debt_total({i['debt_total']})")
    if not (i["pb_l"] < i["pb_m"] < i["pb_h"]):
        errors.append(f"pb order violated: {i['pb_l']}/{i['pb_m']}/{i['pb_h']}")
    leaked = [k for k in i if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields in Inputs (A2e-7a): {leaked}")

    # ---- Step 1: bottom card — fully diluted book × PB tiers (A11) ----
    book_fd = i["equity_book"] + i["conv_principal"] + i["warrant_proceeds"]
    bps_fd = book_fd * MM / i["shares_fd"]
    L, M, H = (i[f"pb_{t}"] * bps_fd for t in TIERS)
    A, B = cut_points(L, M, H)
    zone = zone_of(i["price"], L, M, H)

    # ---- Step 2: option ceiling — court EV high bridged with today's net cash (A12)
    net_debt = i["debt"] - i["cash"] - i["warrant_proceeds"]
    court = {t: (i[f"ev_court_{t}"] - net_debt) * MM / i["shares_fd"] for t in TIERS}
    v_top = court["h"]
    v_opt = max(0.0, v_top - H)
    adj = [x + p * v_opt for x, p in zip((L, M, H), P_K)]
    adj_a, adj_b = cut_points(*adj)
    adj_zone = zone_of(i["price"], *adj)
    # The court's own emergence bridge, put on the same FD footing (A12 known weakness).
    bridge_fd = (i["eq_court_bridge"] + i["conv_principal"] + i["warrant_proceeds"]) * MM / i["shares_fd"]

    # ---- Step 3: cross-checks (never anchors) ----
    evs = {t: i[f"ev_court_{t}"] / i["rev_fy26"] for t in TIERS}
    old = {t: (i[f"rev_{t}"] * evs[t] - net_debt) * MM / i["shares_fd"] for t in TIERS}
    basic = i.get("shares_basic")

    print(f"formula_id={FORMULA_ID}")
    print(f"book_fd  {i['equity_book']:.1f} + conv {i['conv_principal']:.1f} + warrants {i['warrant_proceeds']:.1f} = {book_fd:.1f} $M"
          f"  / shares_fd {i['shares_fd']:.0f} -> BPS_fd {bps_fd:.3f}  PB={i['pb_l']:g}/{i['pb_m']:g}/{i['pb_h']:g}")
    print(f"base L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}  V_opt/M={v_opt / M:.1%}")
    print(f"decompose  L/M = num 1.000 x pb {i['pb_l'] / i['pb_m']:.3f} | H/M = num 1.000 x pb {i['pb_h'] / i['pb_m']:.3f}"
          f"  (asset ruler; flat ladder == base)")
    print(f"own band: post-emergence min close {i['close_own_min']:g} = FD PB {i['close_own_min'] / bps_fd:.2f}x; "
          f"price/BPS_fd {i['price'] / bps_fd:.2f}x")
    print(f"option     net_debt {net_debt:.1f}; court EV {i['ev_court_l']:.0f}/{i['ev_court_m']:.0f}/{i['ev_court_h']:.0f} "
          f"-> per FD share {court['l']:.2f}/{court['m']:.2f}/{court['h']:.2f}; ceiling = high {v_top:.2f} -> V_opt {v_opt:.2f}")
    print(f"表3  p_k={P_K[0]:.2f}/{P_K[1]:.2f}/{P_K[2]:.2f}  L'/M'/H' = {adj[0]:.2f}/{adj[1]:.2f}/{adj[2]:.2f}  "
          f"A'={adj_a:.2f} B'={adj_b:.2f}  zone+V = {adj_zone}")
    print(f"     市价隐含 p = {(i['price'] - H) / v_opt:.2f}; P/(H+V) = {i['price'] / adj[2] - 1:+.1%}")
    print(f"  sens anchor -> court mid / low: V_opt {max(0.0, court['m'] - H):.2f} / {max(0.0, court['l'] - H):.2f}; "
          f"court bridge equity {i['eq_court_bridge']:.1f} -> FD {bridge_fd:.2f}: V_opt {max(0.0, bridge_fd - H):.2f}")
    print(f"  cross retired EV/S ruler ({evs['l']:.3f}/{evs['m']:.3f}/{evs['h']:.3f}x on rev {i['rev_l']:.0f}/{i['rev_m']:.0f}/{i['rev_h']:.0f}): "
          f"{old['l']:.2f}/{old['m']:.2f}/{old['h']:.2f}")
    if basic:
        print(f"  cross basic-share error: BPS {i['equity_book'] * MM / basic:.2f}, court high {(i['ev_court_h'] - net_debt) * MM / basic:.2f}")
    print(f"表2  price {i['price']} -> zone = {zone}   P/H {i['price'] / H:.2f}x")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone, TOL)
    errors += ladder("base", L, M, H)
    if v_opt < 0:
        errors.append(f"V_opt must be >= 0, got {v_opt:.2f}")
    said_v = stated_v_opt(md)
    if said_v is None:
        errors.append("stated V_opt not found in Outputs")
    elif abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    if abs(adj[0] - L) > 1e-9:
        errors.append(f"p leaked into the base: 表3 L row {adj[0]:.4f} != base L {L:.4f}")
    if v_opt > 0 and "表3" not in outputs_section(md):
        errors.append("V_opt > 0 but Outputs has no 表3")
    if abs(v_top - i["price"]) < 1e-9:
        errors.append("option ceiling equals the current price: the anchor must be the court EV, not a price input (A12)")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
