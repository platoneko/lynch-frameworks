#!/usr/bin/env python3
"""2631.HK (SICC) valuation eval — asset-PB bottom + full-capacity success option.

frameworks/2631.HK.md is the source of truth; this script recomputes
bottom L/M/H / A/B / V_opt / 表3 and exits 1 on mismatch.  The doc carries no
current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied p — the digest and the app zone on live quotes.

formula_id (bottom): sicc_asset_pb_bottom_v1
formula_id (option): sicc_fullcap_sic_axis_vopt_v5

Bottom = PB 0.55/0.80/1.00 × BPS (no ASP repair), BPS = equity × fx / shares.
Option (vopt_v5, peer-ruler axis `_AXIS.sic`, frameworks/axes/sic.md): count =
SICC's own named full capacity (cap_kpcs) × own measured ASP (asp_h); unit
economics MUST be full-capacity (m_full — the scale-matched sell-side point,
cross-checked by the cost split; the ramp-year consensus m_align is printed as
the error it used to be); ROE on operating capital only (equity − net cash +
the named expansion capex still to be spent), the rest of net cash added back
undiscounted; Gordon at the axis g2 (capped at G_cap) and basket r, valued in
t_opt and discounted.  V_opt = max(0, V^G_H − H); 表3 = base_k + p_k × V_opt.
The IPO price is a borrowed price — cross coordinate only.

r is the basket rate (A14): 篮 4 常规经营 10% after the 2026-10-03 narrowing of
篮 7 (no customer ≥50% / top-two ≥70%, no high country risk; no quoted price,
so not 篮 6).  `check_r` requires the value to match the tag.  Shared axis rows
(g2_sic_src, t_align) must equal frameworks/axes/sic.md.

Earnings-ruler reference (A2e-1 asset_play row): consensus NP × Gordon (g=0),
printed and required to sit below L.

Run:  python3 frameworks/eval/2631.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.gordon import check_g_cap, check_r, g_cap, perpetual_pe, two_stage_pe  # noqa: E402
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

FRAMEWORK = REPO_ROOT / "frameworks" / "2631.HK.md"
AXIS = REPO_ROOT / "frameworks" / "axes" / "sic.md"
SHARED = ("g2_sic_src", "t_align")  # rows that must equal _AXIS.sic
FORMULA_IDS = (
    "sicc_asset_pb_bottom_v1",
    "sicc_fullcap_sic_axis_vopt_v5",
)
# 表3 per-tier credit (A12, _AXIS.sic): 拍值, no external anchor. Never an Input, never the base.
P_K = (0.0, 0.25, 1.0)
KPCS = 1e4
YI = 1e8
TOL = 0.05

REQUIRED = [
    "shares", "fx_cny_hkd", "equity_cny",
    "pb_l", "pb_m", "pb_h",
    "ipo_price_hkd", "close_own_min", "close_own_median",
    "cap_kpcs", "vol_unit_kpcs", "rev_basis_up", "rev_basis_now", "asp_h",
    "m_full", "m_full_lo", "m_full_hi", "m_align", "m_h",
    "net_cash_cny", "net_cash_free_cny", "capex_named_hkd",
    "g2_sic_src", "t_align", "r_perp", "r_disc", "year_now", "t_opt",
    "np26e_cny", "np27e_cny", "np28e_cny",
    "pb_own_min", "pb_own_max",
]


def stated_v_opt(md: str) -> float | None:
    m = re.search(r"V_\{opt\}\D{0,20}\*\*([0-9.]+)\*\*", outputs_section(md))
    return float(m.group(1)) if m else None


def stated_table3(md: str) -> tuple[float, ...] | None:
    """The `- 表3：L′ = **x** · M′ = **y** · H′ = **z**` line in Outputs."""
    m = re.search(r"表3[^\n]*?L′ = \*\*([0-9.]+)\*\*[^\n]*?M′ = \*\*([0-9.]+)\*\*[^\n]*?H′ = \*\*([0-9.]+)\*\*",
                  outputs_section(md))
    return tuple(float(x) for x in m.groups()) if m else None


def success(inp: dict[str, float], *, margin: float | None = None, kpcs: float | None = None,
            net_cash: float | None = None, capex: bool = True, basis: float | None = None,
            t_opt: float | None = None, g2: float | None = None, r: float | None = None) -> dict[str, float]:
    """Full-capacity world on the own ruler (A4 / A6 / A11): operating-capital ROE, axis g2, basket r."""
    r = inp["r_perp"] if r is None else r
    g2 = min(inp["g2_sic_src"], g_cap(r)) if g2 is None else g2
    rev = (inp["cap_kpcs"] if kpcs is None else kpcs) * KPCS * inp["asp_h"] * (inp["rev_basis_up"] if basis is None else basis) / YI
    np_h = rev * (inp["m_full"] if margin is None else margin)
    nc = inp["net_cash_cny"] if net_cash is None else net_cash
    k = inp["capex_named_hkd"] / inp["fx_cny_hkd"] if capex else 0.0
    cap_op = inp["equity_cny"] - nc + k
    roe = np_h / cap_op
    pe = perpetual_pe(g2, roe, r) if roe > 0 else 0.0
    years = (inp["t_opt"] if t_opt is None else t_opt) - inp["year_now"]
    disc = (1.0 + r) ** (-years)
    op_value = pe * max(0.0, np_h) * disc
    v = (op_value + nc - k) * YI * inp["fx_cny_hkd"] / inp["shares"]
    return {"rev": rev, "np": np_h, "cap_op": cap_op, "roe": roe, "pe": pe, "g2": g2, "disc": disc,
            "op_undisc": pe * max(0.0, np_h), "addback": nc - k, "v": v}


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    errors: list[str] = []
    for fid in FORMULA_IDS:
        if fid not in md:
            errors.append(f"formula_id {fid} missing from framework")

    inp = parse_inputs(md)
    errors += check_missing(inp, REQUIRED)
    if errors and any(e.startswith("missing") or "formula_id" in e for e in errors):
        return report(errors)

    # r must be the basket value named in the Inputs source cell (A14); r_disc
    # carries no basket tag and only has to be a basket-table value.
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N in the Inputs source cell (A14)")
    errors += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    errors += check_r(inp["r_disc"], "r_disc", baskets.get("r_disc"))
    if abs(inp["r_disc"] - inp["r_perp"]) > 1e-9:
        errors.append(f"r_disc {inp['r_disc']} != r_perp {inp['r_perp']}: the discount year uses the same basket r (A2 / A14)")
    g2 = min(inp["g2_sic_src"], g_cap(inp["r_perp"]))
    errors += check_g_cap(g2, inp["r_perp"], "g2 (_AXIS.sic)")
    if not (inp["pb_l"] < inp["pb_m"] < inp["pb_h"]):
        errors.append(f"pb order violated: {inp['pb_l']}/{inp['pb_m']}/{inp['pb_h']}")
    if not (inp["m_full_lo"] <= inp["m_full"] <= inp["m_full_hi"]):
        errors.append(f"m_full {inp['m_full']} outside its stated range [{inp['m_full_lo']}, {inp['m_full_hi']}] (A4)")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields in Inputs (A2e-7a): {leaked}")

    # ---- Peer-ruler axis (_AXIS.sic): shared rows must match the axis file ----
    if AXIS.is_file():
        axis = parse_inputs(AXIS.read_text(encoding="utf-8"))
        for k in SHARED:
            if k not in axis or abs(axis[k] - inp[k]) > 1e-9:
                errors.append(f"{k} {inp[k]:g} != _AXIS.sic {axis.get(k)} — the peer ruler drifted")
    else:
        errors.append("frameworks/axes/sic.md missing — peer ruler unchecked")

    # --- bottom card: asset PB ------------------------------------------------
    bps = inp["equity_cny"] * YI * inp["fx_cny_hkd"] / inp["shares"]
    L = inp["pb_l"] * bps
    M = inp["pb_m"] * bps
    H = inp["pb_h"] * bps
    A, B = cut_points(L, M, H)

    # --- option: full-capacity world on the own ruler (A4 / A6 / A11) ---------
    post = success(inp)
    v_top = post["v"]
    v_opt = max(0.0, v_top - H)
    adj = [x + p * v_opt for x, p in zip((L, M, H), P_K)]
    adj_a, adj_b = cut_points(*adj)
    sens = {
        "margin lo (2028E cons top)": success(inp, margin=inp["m_full_lo"]),
        "margin hi (cost split top)": success(inp, margin=inp["m_full_hi"]),
        "margin 2028E cons mean": success(inp, margin=inp["m_align"]),
        "margin FY2024 measured": success(inp, margin=inp["m_h"]),
        "free cash only": success(inp, net_cash=inp["net_cash_free_cny"]),
        "no expansion capex": success(inp, capex=False),
        "other-business 1.066": success(inp, basis=inp["rev_basis_now"]),
        "t_opt = t_align + 2": success(inp, t_opt=inp["t_align"] + 2),
        "g2 -1pp": success(inp, g2=g2 - 0.01),
        "g2 0": success(inp, g2=0.0),
        "pre-ramp volume": success(inp, kpcs=inp["vol_unit_kpcs"]),
        "old 篮 7 r 15%": success(inp, r=0.15),
    }

    # --- earnings-ruler reference (A2e-1 asset_play row) ----------------------
    ref = {}
    for label, key, years in (("2026E", "np26e_cny", 0), ("2027E", "np27e_cny", 0), ("2028E", "np28e_cny", 2)):
        np_y = inp[key] * YI
        roe = np_y / (inp["equity_cny"] * YI)
        pe = perpetual_pe(0.0, roe, inp["r_perp"])
        disc = (1.0 + inp["r_disc"]) ** (-years)
        ref[label] = {"roe": roe, "pe": pe, "v": pe * np_y * inp["fx_cny_hkd"] / inp["shares"] * disc}
    g1 = inp["np28e_cny"] / inp["np27e_cny"] - 1.0
    roe27 = ref["2027E"]["roe"]
    two_stage = two_stage_pe(g1, 1, 0.0, roe27, inp["r_perp"])

    print(f"formula_id: {FORMULA_IDS[0]} + {FORMULA_IDS[1]}")
    print(f"bottom     BPS {bps:.3f} HKD (equity {inp['equity_cny']:.2f} 亿 CNY x fx {inp['fx_cny_hkd']})"
          f"  PB={inp['pb_l']:g}/{inp['pb_m']:g}/{inp['pb_h']:g}")
    print(f"base L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}  V_opt/M={v_opt / M:.1%}")
    print(f"decompose  L/M = num 1.000 x pb {inp['pb_l'] / inp['pb_m']:.3f} | H/M = num 1.000 x pb "
          f"{inp['pb_h'] / inp['pb_m']:.3f}  (asset ruler; flat ladder == base)")
    print(f"own PB band [{inp['pb_own_min']}, {inp['pb_own_max']}] (H-share realised) vs deck "
          f"{inp['pb_l']}-{inp['pb_h']}: deck entirely below the band")
    print(f"option     {inp['cap_kpcs']:g} 万片 x ASP {inp['asp_h']:g} x {inp['rev_basis_up']} = rev {post['rev']:.2f}亿 x margin "
          f"{inp['m_full']:.3f} = np {post['np']:.2f}亿; op capital {inp['equity_cny']:.2f} - net cash {inp['net_cash_cny']:.2f} "
          f"+ capex {inp['capex_named_hkd'] / inp['fx_cny_hkd']:.2f} = {post['cap_op']:.2f}亿 -> roe {post['roe']:.2%}")
    print(f"           g2 {post['g2']:.2%} (axis src {inp['g2_sic_src']:.4f}) r {inp['r_perp']:g} -> PE {post['pe']:.2f}x "
          f"(payout {1 - post['g2'] / post['roe']:.0%}); op value {post['op_undisc']:.1f}亿 x disc {post['disc']:.3f} "
          f"(t_opt {inp['t_opt']:g}) + add-back {post['addback']:.2f}亿 -> V^G_H {v_top:.2f} HKD vs H {H:.2f} -> V_opt {v_opt:.2f}")
    print(f"           ROE = r at margin {inp['r_perp'] * post['cap_op'] / post['rev']:.1%}")
    print(f"表3  p_k={P_K[0]:.2f}/{P_K[1]:.2f}/{P_K[2]:.2f}  L'/M'/H' = {adj[0]:.2f}/{adj[1]:.2f}/{adj[2]:.2f}  "
          f"A'={adj_a:.2f} B'={adj_b:.2f}")
    print(f"cross only: IPO price {inp['ipo_price_hkd']:.2f} HKD (borrowed price, not a ceiling); "
          f"own closes since IPO min {inp['close_own_min']:g} / median {inp['close_own_median']:g}")
    for name, s in sens.items():
        print(f"  sens {name:28s}: np {s['np']:.2f}亿 cap {s['cap_op']:.2f} roe {s['roe']:.2%} pe {s['pe']:.2f} "
              f"V^G_H {s['v']:.2f} (V_opt {max(0.0, s['v'] - H):.2f})")
    print("earnings ruler ref (consensus NP x Gordon g=0, ROE<r -> 1/r): "
          + " / ".join(f"{k} {x['v']:.2f} (roe {x['roe']:.1%})" for k, x in ref.items())
          + f"  | all < L {L:.2f}: {all(x['v'] < L for x in ref.values())}")
    print(f"two-stage lever (g1 {g1:+.1%} x1y on 2027E, roe {roe27:.1%}): stage-1 payout {1 - g1 / roe27:+.1f}, "
          f"multiple {two_stage:.2f} -> degenerate, unavailable")
    print(f"篮 {baskets.get('r_perp')} floor 1/r x E (disclosure, not max()-ed): "
          + " / ".join(f"{k} {x['v']:.2f}" for k, x in ref.items()) + f"  | L stays {L:.2f}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, tol=TOL)
    if inp["t_opt"] <= inp["year_now"]:
        errors.append(f"t_opt {inp['t_opt']} must be after year_now {inp['year_now']}")
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
    if not all(x["v"] < L for x in ref.values()):
        errors.append("earnings-ruler reference exceeds L: the asset ruler is no longer the upper bound — back to dialogue")
    if v_opt > 0:
        said_t3 = stated_table3(md)
        if said_t3 is None:
            errors.append("V_opt > 0 but Outputs has no 表3 line (L′ / M′ / H′)")
        elif any(abs(a - b) > TOL for a, b in zip(said_t3, adj)):
            errors.append(f"表3: stated {said_t3} vs recomputed {tuple(round(x, 2) for x in adj)}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
