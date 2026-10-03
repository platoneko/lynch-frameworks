#!/usr/bin/env python3
"""WOLF.US (Wolfspeed) valuation eval — asset-PB bottom + full-capacity recovery option.

frameworks/WOLF.US.md is the source of truth; this script recomputes
bottom L/M/H / A/B / V_opt / 表3 and exits 1 on mismatch.  The doc carries no
current price (AGENTS.md「现价 — 禁写契约」): which zone a quote falls in is
derived live by the daily digest and the app, so nothing here reads a price.

formula_id: wolf_asset_pb_fd_sic_axis_vopt_v5

Bottom = PB 0.55/0.80/1.00 × FULLY DILUTED book.  Post-Chapter-11 the three
converts are deep in the money, so the book that stands behind the diluted
share count is fresh-start equity + convert principal (the debt that vanishes
on conversion) + warrant proceeds, over `shares_fd` (A1/A11).  Using basic
shares is the single largest error available on this name.

There is no earnings numerator anywhere (consensus EPS negative through
FY28E), so neither Gordon nor EV/EBIT can generate a multiple (A6), and an
EV/Sales ruler would hide an unrealised margin recovery inside the multiple
(A3, retired).  Revenue recovery is the success path and lives in V_opt, on the
peer-ruler axis `_AXIS.sic` (frameworks/axes/sic.md; A12): count = the named
Mohawk Valley full-capacity revenue (rev_named); unit economics MUST be
full-capacity (m_full = EBIT margin from the public-data cost split, range
m_full_lo..m_full_hi; the mid-ramp FY2028E consensus margin is printed as the
error it used to be); unlevered NOPAT over operating capital only (FD book +
FD net debt — identical to equity + all debt principal − cash, so the convert
treatment does not move it), Gordon at the axis g2 (capped) and the basket r,
valued in t_opt, discounted, plus FD net cash.  V_opt = max(0, V^G_H − H).
The court EV is a borrowed price and stays a cross coordinate.

Basket r (A14): 篮 4 常规经营 10% after the 2026-10-03 narrowing of 篮 7 (top
customer 27%, top two 38%, US company; devices have no quoted price).  r never
enters the bottom card.  Shared axis rows (g2_sic_src, t_align) must equal
frameworks/axes/sic.md.

Run:  python3 frameworks/eval/WOLF.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import check_g_cap, check_r, g_cap, perpetual_pe  # noqa: E402
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    outputs_section,
    parse_baskets,
    parse_inputs,
    report,
)
from eval.lib.zones import cut_points  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "WOLF.US.md"
AXIS = REPO_ROOT / "frameworks" / "axes" / "sic.md"
SHARED = ("g2_sic_src", "t_align")  # rows that must equal _AXIS.sic
FORMULA_ID = "wolf_asset_pb_fd_sic_axis_vopt_v5"
TOL = 0.05  # outputs rounded to 2 decimals
MM = 1e6  # inputs are in $M
TIERS = ("l", "m", "h")
# 表3 per-tier credit (A13, _AXIS.sic): 拍值, no external anchor. Never an Input, never the base.
P_K = (0.0, 0.25, 1.0)

REQUIRED = [
    "shares_fd", "cash", "debt", "conv_principal", "warrant_proceeds", "debt_total",
    "equity_book", "pb_l", "pb_m", "pb_h", "r_perp",
    "ev_court_l", "ev_court_m", "ev_court_h", "eq_court_bridge",
    "rev_l", "rev_m", "rev_h", "rev_fy26",
    "close_own_min", "shares_basic",
    "rev_named", "rev_installed", "m_full", "m_full_lo", "m_full_hi", "m_plan29", "tax_opt",
    "eps_fy28e", "rev_fy28e", "lease_liab", "g2_sic_src", "t_align", "t_opt", "year_now",
]


def stated_v_opt(md: str) -> float | None:
    m = re.search(r"V_\{opt\}\D{0,20}\*\*([0-9.]+)\*\*", outputs_section(md))
    return float(m.group(1)) if m else None


def stated_table3(md: str) -> tuple[float, ...] | None:
    m = re.search(r"表3[^\n]*?L′ = \*\*([0-9.]+)\*\*[^\n]*?M′ = \*\*([0-9.]+)\*\*[^\n]*?H′ = \*\*([0-9.]+)\*\*",
                  outputs_section(md))
    return tuple(float(x) for x in m.groups()) if m else None


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
    if not (i["m_full_lo"] <= i["m_full"] <= i["m_full_hi"]):
        errors.append(f"m_full {i['m_full']} outside its stated range [{i['m_full_lo']}, {i['m_full_hi']}] (A12)")
    leaked = [k for k in i if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields in Inputs (A2e-7a): {leaked}")
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp source cell names no 篮 N (A14)")
    errors += check_r(i["r_perp"], "r_perp", baskets.get("r_perp"))
    r = i["r_perp"]
    g2 = min(i["g2_sic_src"], g_cap(r))
    errors += check_g_cap(g2, r, "g2 (_AXIS.sic)")
    if abs(i["t_opt"] - (i["t_align"] + 2)) > 1e-9:
        errors.append(f"t_opt {i['t_opt']} != t_align + 2 ({i['t_align'] + 2}): no named full-capacity year (A5)")

    # ---- Peer-ruler axis (_AXIS.sic): shared rows must match the axis file ----
    if AXIS.is_file():
        axis = parse_inputs(AXIS.read_text(encoding="utf-8"))
        for k in SHARED:
            if k not in axis or abs(axis[k] - i[k]) > 1e-9:
                errors.append(f"{k} {i[k]:g} != _AXIS.sic {axis.get(k)} — the peer ruler drifted")
    else:
        errors.append("frameworks/axes/sic.md missing — peer ruler unchecked")

    # ---- Step 1: bottom card — fully diluted book × PB tiers (A11) ----
    book_fd = i["equity_book"] + i["conv_principal"] + i["warrant_proceeds"]
    bps_fd = book_fd * MM / i["shares_fd"]
    L, M, H = (i[f"pb_{t}"] * bps_fd for t in TIERS)
    A, B = cut_points(L, M, H)

    # ---- Step 2: option — full-capacity world on the own ruler (A12) ----
    net_debt = i["debt"] - i["cash"] - i["warrant_proceeds"]
    cap_op = book_fd + net_debt  # = equity + all debt principal − cash; convert-neutral

    def success(margin: float, rev: float | None = None, rr: float | None = None, g: float | None = None,
                cap: float | None = None, nd: float | None = None) -> dict[str, float]:
        rr = r if rr is None else rr
        g = g2 if g is None else g
        rev = i["rev_named"] if rev is None else rev
        cap = cap_op if cap is None else cap
        nd = net_debt if nd is None else nd
        nopat = rev * margin * (1.0 - i["tax_opt"])
        roe = nopat / cap
        pe = perpetual_pe(g, roe, rr) if roe > 0 else 0.0
        disc = (1.0 + rr) ** (-(i["t_opt"] - i["year_now"]))
        v = (pe * max(0.0, nopat) * disc - nd) * MM / i["shares_fd"]
        return {"nopat": nopat, "roe": roe, "pe": pe, "disc": disc, "op": pe * max(0.0, nopat), "v": v}

    post = success(i["m_full"])
    v_top = post["v"]
    v_opt = max(0.0, v_top - H)
    adj = [x + p * v_opt for x, p in zip((L, M, H), P_K)]
    adj_a, adj_b = cut_points(*adj)
    m_align = i["eps_fy28e"] * i["shares_basic"] / MM / i["rev_fy28e"]
    rev_scale = i["rev_installed"] / i["rev_named"]
    sens = {
        "margin hi (plan slope 2,000)": success(i["m_full_hi"]),
        "plan FY29 ratios": success(i["m_plan29"]),
        "margin lo (today price, full util)": success(i["m_full_lo"]),
        "FY28E cons margin (mid-ramp)": success(m_align),
        "installed capacity 1,100": success(i["m_full"], rev=i["rev_installed"]),
        "capital scaled x 2000/1100": success(i["m_full"], cap=cap_op / rev_scale),
        "leases as debt": success(i["m_full"], cap=cap_op + i["lease_liab"], nd=net_debt + i["lease_liab"]),
        "g2 -1pp": success(i["m_full"], g=g2 - 0.01),
        "g2 0": success(i["m_full"], g=0.0),
        "old 篮 7 r 15%": success(i["m_full"], rr=0.15),
    }
    court = {t: (i[f"ev_court_{t}"] - net_debt) * MM / i["shares_fd"] for t in TIERS}
    bridge_fd = (i["eq_court_bridge"] + i["conv_principal"] + i["warrant_proceeds"]) * MM / i["shares_fd"]
    evs = {t: i[f"ev_court_{t}"] / i["rev_fy26"] for t in TIERS}
    old = {t: (i[f"rev_{t}"] * evs[t] - net_debt) * MM / i["shares_fd"] for t in TIERS}
    basic = i["shares_basic"]

    print(f"formula_id={FORMULA_ID}")
    print(f"book_fd  {i['equity_book']:.1f} + conv {i['conv_principal']:.1f} + warrants {i['warrant_proceeds']:.1f} = {book_fd:.1f} $M"
          f"  / shares_fd {i['shares_fd']:.0f} -> BPS_fd {bps_fd:.3f}  PB={i['pb_l']:g}/{i['pb_m']:g}/{i['pb_h']:g}")
    print(f"base L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}  V_opt/M={v_opt / M:.1%}")
    print(f"decompose  L/M = num 1.000 x pb {i['pb_l'] / i['pb_m']:.3f} | H/M = num 1.000 x pb {i['pb_h'] / i['pb_m']:.3f}"
          f"  (asset ruler; flat ladder == base)")
    print(f"own band: post-emergence min close {i['close_own_min']:g} = FD PB {i['close_own_min'] / bps_fd:.2f}x")
    print(f"option     {i['rev_named']:.0f} $M x EBIT margin {i['m_full']:.3f} x (1 - {i['tax_opt']:g}) = NOPAT {post['nopat']:.1f}; "
          f"op capital {book_fd:.1f} + net debt {net_debt:.1f} = {cap_op:.1f} -> ROE {post['roe']:.2%}")
    print(f"           g2 {g2:.2%} (axis src {i['g2_sic_src']:.4f}) r {r:g} -> PE {post['pe']:.2f}x (payout {1 - g2 / post['roe']:.0%}); "
          f"op value {post['op']:.1f} x disc {post['disc']:.3f} (t_opt {i['t_opt']:g}) + FD net cash {-net_debt:.1f} "
          f"-> V^G_H {v_top:.2f} vs H {H:.2f} -> V_opt {v_opt:.2f}")
    print(f"           ROE = r at EBIT margin {r * cap_op / (i['rev_named'] * (1 - i['tax_opt'])):.1%}; "
          f"FY28E cons margin {m_align:+.1%} (EPS {i['eps_fy28e']} x basic {basic / MM:.1f}M / rev {i['rev_fy28e']:.1f})")
    print(f"表3  p_k={P_K[0]:.2f}/{P_K[1]:.2f}/{P_K[2]:.2f}  L'/M'/H' = {adj[0]:.2f}/{adj[1]:.2f}/{adj[2]:.2f}  "
          f"A'={adj_a:.2f} B'={adj_b:.2f}")
    for name, s in sens.items():
        print(f"  sens {name:36s}: NOPAT {s['nopat']:7.1f} ROE {s['roe']:6.1%} PE {s['pe']:5.2f} V^G_H {s['v']:.2f} (V_opt {max(0.0, s['v'] - H):.2f})")
    print(f"  cross court EV {i['ev_court_l']:.0f}/{i['ev_court_m']:.0f}/{i['ev_court_h']:.0f} -> per FD share "
          f"{court['l']:.2f}/{court['m']:.2f}/{court['h']:.2f} (borrowed price, not a ceiling); "
          f"court bridge equity {i['eq_court_bridge']:.1f} -> FD {bridge_fd:.2f}")
    print(f"  cross retired EV/S ruler ({evs['l']:.3f}/{evs['m']:.3f}/{evs['h']:.3f}x on rev {i['rev_l']:.0f}/{i['rev_m']:.0f}/{i['rev_h']:.0f}): "
          f"{old['l']:.2f}/{old['m']:.2f}/{old['h']:.2f}")
    print(f"  cross basic-share error: BPS {i['equity_book'] * MM / basic:.2f}, court high {(i['ev_court_h'] - net_debt) * MM / basic:.2f}")
    print(f"  r_perp {r:g} (篮 {baskets.get('r_perp')}), option only (bottom card has no r); 篮 4 floor 1/r x E = 0.00 (E < 0), L stays {L:.2f}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    if i["t_opt"] <= i["year_now"]:
        errors.append(f"t_opt {i['t_opt']} must be after year_now {i['year_now']}")
    errors += ladder("base", L, M, H)
    said_v = stated_v_opt(md)
    if said_v is None:
        errors.append("stated V_opt not found in Outputs")
    elif abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    if abs(adj[0] - L) > 1e-9:
        errors.append(f"p leaked into the base: 表3 L row {adj[0]:.4f} != base L {L:.4f}")
    if v_opt > 0:
        said_t3 = stated_table3(md)
        if said_t3 is None:
            errors.append("V_opt > 0 but Outputs has no 表3 line (L′ / M′ / H′)")
        elif any(abs(a - b) > TOL for a, b in zip(said_t3, adj)):
            errors.append(f"表3: stated {said_t3} vs recomputed {tuple(round(x, 2) for x in adj)}")
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
