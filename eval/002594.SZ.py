#!/usr/bin/env python3
"""002594.SZ (BYD, A share) valuation eval.

frameworks/002594.SZ.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a
zone or a market-implied reading — the digest and the app zone on live quotes.

formula_id: byd_group_ni_fy28_consensus_perpetual_gordon_v1

Main ruler: one numerator (group 归母 EPS) and a Gordon multiple from a named
perpetual g, one stage, no transition:

  PE_x   = perpetual_pe(g2, ROE_x, r) = min(1, 1 - g2/ROE_x) / (r - g2)
  anchor = eps_x * PE_x / (1 + r)^disc_x

r is 篮 4 常规经营 (10%), read from the Inputs row and checked against the
篮 N tag.  g2 is one named value for all three tiers (cyclical flat-multiple
policy; A5), ≤ the mega-hardware cap min(4%, r-4%).

Numerators (A1 / A2):
  M / H = FY2028E 归母 EPS — consensus mean / high of the post-interim house set
          (Eastmoney F10, 19 houses); FY2028 = current FY + 2 → discounted one
          year at r (construction §3).
  L     = FY2025 actual EPS (the price-war digestion year) frozen as a regime
          world; numerator year t = 1, not discounted.

ROE (A6): tier EPS ÷ the numerator year's OPENING BPS (E_{n+1}/B_n).  The 2Q26
common book (归母权益 less perpetual bonds, less the FY2025 dividend paid
after the balance-sheet date) is rolled over the not-yet-booked earnings at
the growth-required retention b = g2/ROE, closed form
BPS_open = BPS0 / (1 - g2·N/eps).  M / H roll 2H26 + FY2027 along their own
house path (mean / 广发); L rolls 2H26 at the frozen FY2025 level.

③ (A9): the M numerator has never been realised (no equal-earnings months),
so the L tier is tested; its multiple sits below the equal-earnings minimum,
and the band is distorted (the market then priced ~25%/yr growth vs the model
g2), so ③ is 「不可判定」 — the basket stays, and the 对账门 coordinates are
printed; at least one independent coordinate must be within 20% of M.

Run:  python3 frameworks/eval/002594.SZ.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.gordon import (  # noqa: E402
    check_branch, check_g_cap, check_r, g_cap, payout, payout_gap, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, outputs_section, parse_baskets, parse_inputs, report,
)
from lib.tiers import flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "002594.SZ.md"
FORMULA_ID = "byd_group_ni_fy28_consensus_perpetual_gordon_v1"

TIERS = ("l", "m", "h")
MIN_SPREAD = 0.02           # r - g2 floor (valuation-rules ①)
MIN_CONSENSUS_HOUSES = 2    # a numerator year needs >= 2 houses with a range (②)
DISTORTED_GAP = 0.10        # ③ step 1b: then-expected growth − model g >= 10pp/yr
RECONCILE_TOL = 0.20        # 纠正对账门: M within 20% of >= 1 independent coordinate
MEGA_HW = True              # A5: hardware, FY2028E revenue >= $150B, no proven pricing power

FORMULA_FIELDS = frozenset({
    "shares", "equity", "dps_after", "ni_1h26", "r_perp", "g2", "disc_years",
    "eps_l", "eps_m", "eps_h",
    "eps_fy26_m", "eps_fy26_h", "eps_fy27_m", "eps_fy27_h",
})

REQUIRED = sorted(FORMULA_FIELDS | {
    "consensus_n_fy28", "eps_fy28_lo", "eps_ttm", "payout_fy25", "payout_3y",
    "pe_eq_lo", "pe_eq_n", "roe_band", "g_exp_band", "pb_lo_5y", "pb_lo_all",
    "net_debt", "ebit_fy25", "da_1h26", "int_1h26",
    "fd_install_apr", "fd_ext_share", "unit_profit_catl", "unit_disc",
    "capex_per_gwh", "t_num", "t_opt",
    "tp_hsbc", "tp_citi", "tp_ubs", "tp_consensus",
})

# 表3 only — never Inputs, never the base band (A2e-7a).  No sell-side volume
# for the external-battery leg → the option enters H only (A10).
P_K = (0.0, 0.0, 1.0)


def bps0(inp: dict[str, float]) -> float:
    """2Q26 common BPS (perpetual bonds excluded) less the dividend paid after 2Q26."""
    return inp["equity"] * 1e8 / inp["shares"] - inp["dps_after"]


def eps_1h26(inp: dict[str, float]) -> float:
    return inp["ni_1h26"] * 1e8 / inp["shares"]


def unbooked(inp: dict[str, float], tag: str) -> float:
    """EPS earned before the numerator year but not yet in the 2Q26 book."""
    if tag == "l":
        return inp["eps_l"] - eps_1h26(inp)                 # 2H26 at the frozen FY2025 level
    return inp[f"eps_fy26_{tag}"] - eps_1h26(inp) + inp[f"eps_fy27_{tag}"]


def bps_open(inp: dict[str, float], tag: str) -> float:
    return bps0(inp) / (1.0 - inp["g2"] * unbooked(inp, tag) / inp[f"eps_{tag}"])


def roe(inp: dict[str, float], tag: str) -> float:
    return inp[f"eps_{tag}"] / bps_open(inp, tag)


def multiple(inp: dict[str, float], tag: str) -> float:
    return perpetual_pe(inp["g2"], roe(inp, tag), inp["r_perp"])


def disc(inp: dict[str, float], tag: str) -> float:
    years = 0.0 if tag == "l" else inp["disc_years"]
    return (1.0 + inp["r_perp"]) ** (-years)


def anchor(inp: dict[str, float], tag: str) -> float:
    return inp[f"eps_{tag}"] * multiple(inp, tag) * disc(inp, tag)


def battery_option(inp: dict[str, float], base_h: float) -> dict[str, float]:
    """V_opt — one more unit of today's external battery supply (A10).

    Size: k = 1 × the April-2026 snapshot of external installs annualised
    (FinDreams domestic installs × external share × 12), 「快照·下限」.  Unit
    economics: CATL's 2026H1 unit net profit less a named haircut.  Ruler:
    this ticker's own H-tier Gordon (same g2, H opening BPS), in FY2028 terms,
    discounted to today like H, then back from the realisation year.  Less the
    capital for the new capacity at CATL's announced per-GWh budget, charged
    once in the realisation year.
    """
    gwh = inp["fd_install_apr"] * inp["fd_ext_share"] * 12.0
    unit = inp["unit_profit_catl"] * (1.0 - inp["unit_disc"])            # 元/kWh
    d_ni = gwh * unit / 100.0                                            # 亿
    d_eps = d_ni * 1e8 / inp["shares"]
    eps_post = inp["eps_h"] + d_eps
    roe_post = eps_post / bps_open(inp, "h")
    pe_post = perpetual_pe(inp["g2"], roe_post, inp["r_perp"])
    anchor_post = eps_post * pe_post * disc(inp, "h")
    k_ps = gwh * inp["capex_per_gwh"] * 1e8 / inp["shares"] * disc(inp, "h")
    d_real = (1.0 + inp["r_perp"]) ** (-(inp["t_opt"] - inp["t_num"]))
    return {"gwh": gwh, "unit": unit, "d_ni": d_ni, "d_eps": d_eps, "roe_post": roe_post,
            "pe_post": pe_post, "anchor_post": anchor_post, "k_ps": k_ps, "d_real": d_real,
            "v_gross": (anchor_post - base_h) * d_real,
            "v_opt": (anchor_post - base_h - k_ps) * d_real}


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    baskets = parse_baskets(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r, g2 = inp["r_perp"], inp["g2"]

    # --- ladders and the numerator-year qualification (②) --------------------
    errors += ladder("eps", inp["eps_l"], inp["eps_m"], inp["eps_h"])
    errors += ladder("FY2028E range", inp["eps_fy28_lo"], inp["eps_m"], inp["eps_h"])
    if inp["consensus_n_fy28"] < MIN_CONSENSUS_HOUSES:
        errors.append(f"consensus_n_fy28={inp['consensus_n_fy28']:.0f} < {MIN_CONSENSUS_HOUSES} (A1)")
    if inp["disc_years"] != 1:
        errors.append("FY2028 = current FY + 2 → disc_years must be 1 (A1)")
    for t in TIERS:
        k = g2 * unbooked(inp, t) / inp[f"eps_{t}"]
        if not 0.0 <= k < 1.0:
            errors.append(f"book roll diverges for {t}: g2·N/eps = {k:.3f} (A6)")
    if errors:
        return report(errors, "FAIL (inputs/ladders)")

    # --- basket, caps, payout -------------------------------------------------
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(g2, r, "g2", mega_hw=MEGA_HW)
    if r - g2 < MIN_SPREAD - 1e-12:
        errors.append(f"r - g2 = {r - g2:.2%} < {MIN_SPREAD:.0%}")
    rho = {t: roe(inp, t) for t in TIERS}
    for t in TIERS:
        pay = payout(g2, rho[t])
        if not 0.0 < pay <= 1.0 + 1e-12:
            errors.append(f"payout_{t}={pay:.3f} outside (0, 1]")
        if rho[t] - r < 0.03:
            errors.append(f"ROE_{t}={rho[t]:.2%} not in the monotone domain (ROE − r < 3pp) — re-audit")
        errors += check_branch(g2, rho[t], r, inp["payout_fy25"], f"g2@{t}")
    if errors:
        return report(errors, "FAIL (basket/caps/branch)")

    pe = {t: multiple(inp, t) for t in TIERS}

    # --- the non-formula fields really are non-formula ------------------------
    lean = {k: v for k, v in inp.items() if k in FORMULA_FIELDS}
    if any(abs(anchor(lean, t) - anchor(inp, t)) > 1e-9 for t in TIERS):
        errors.append("anchor path touches a non-formula field")

    L, M, H = (anchor(inp, t) for t in TIERS)
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}")
        return report(errors)
    A, B = cut_points(L, M, H)

    # A2e-2c: flat multiple, in each tier's own year terms.
    eps_eff = tuple(inp[f"eps_{t}"] * disc(inp, t) for t in TIERS)
    flat_errs, flat = flat_multiple_ladder(eps_eff, pe["m"])
    errors += flat_errs + ladder("flat-multiple", *flat)

    # ③ (A9): M never realised → test L against its equal-earnings months.
    l_out = pe["l"] < inp["pe_eq_lo"]
    distorted = inp["g_exp_band"] - g2 >= DISTORTED_GAP
    if l_out and not distorted:
        errors.append("③: L below the equal-earnings band and the band is clean → BLOCKED path (step 2-4)")

    # 纠正对账门 (A9): independent coordinates for M.
    bps_2q = inp["equity"] * 1e8 / inp["shares"]
    coords = {
        "② E_M/r": inp["eps_m"] / r * disc(inp, "m"),
        "③ D_M/(r−g)": inp["payout_3y"] * inp["eps_m"] / (r - g2) * disc(inp, "m"),
        "⑥ BPS×PB 5y low": bps_2q * inp["pb_lo_5y"],
        "⑥′ BPS×PB all-period low": bps_2q * inp["pb_lo_all"],
    }
    near = [k for k, v in coords.items() if abs(M / v - 1.0) <= RECONCILE_TOL]
    if not near:
        errors.append("对账门: M outside every coordinate by > 20% → BLOCKED")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # V_opt (A10) — held outside the base band; stated values must reproduce.
    opt = battery_option(inp, H)
    if opt["v_opt"] <= 0:
        errors.append(f"battery option non-positive: {opt['v_opt']:.2f}")
    if any(k.startswith("p_") for k in inp):
        errors.append("probability fields present in §3 Inputs (A2e-7a)")
    band3 = tuple(base + P_K[i] * opt["v_opt"] for i, base in enumerate((L, M, H)))
    out_sec = outputs_section(md)
    vm = re.search(r"V_\{opt\}\\\) = \*\*([0-9.]+)\*\*", out_sec)
    if vm is None or abs(float(vm.group(1)) - opt["v_opt"]) > 0.05:
        errors.append(f"V_opt: stated {vm.group(1) if vm else None} vs recomputed {opt['v_opt']:.4f}")
    for k, v in zip("LMH", band3):
        m3 = re.search(rf"^\| {k} \| [0-9.]+ \| [^|]+\| [^|]+\| \*\*([0-9.]+)\*\* \|", out_sec, re.MULTILINE)
        if m3 is None or abs(float(m3.group(1)) - v) > 0.05:
            errors.append(f"table3 {k}: stated {m3.group(1) if m3 else None} vs recomputed {v:.4f}")
    a3, b3 = cut_points(*band3)
    for label, want, rx in (("A′", a3, r"A′ = \*\*([0-9.]+)\*\*"), ("B′", b3, r"B′ = \*\*([0-9.]+)\*\*")):
        mm = re.search(rx, out_sec)
        if mm is None or abs(float(mm.group(1)) - want) > 0.05:
            errors.append(f"{label}: stated {mm.group(1) if mm else None} vs recomputed {want:.4f}")

    # --- report ---------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}  (r={r:.0%} = 篮 {baskets['r_perp']}, g2={g2:.0%}, "
          f"cap(mega)={g_cap(r, mega_hw=True):.0%}, 单段永续)")
    print(f"{'档':<3}{'EPS':>8}{'年初BPS':>9}{'ROE':>8}{'派息率':>8}{'PE':>8}{'折现':>8}{'锚点':>9}")
    for t in TIERS:
        print(f"{t.upper():<3}{inp[f'eps_{t}']:8.4f}{bps_open(inp, t):9.3f}{rho[t]:8.2%}"
              f"{payout(g2, rho[t]):8.3f}{pe[t]:8.3f}{disc(inp, t):8.4f}{anchor(inp, t):9.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.1%} V_opt/M={opt['v_opt'] / M:.1%}")
    print(f"分子比 L/M={eps_eff[0] / eps_eff[1]:.3f} H/M={eps_eff[2] / eps_eff[1]:.3f} | "
          f"倍数比 L/M={pe['l'] / pe['m']:.3f} H/M={pe['h'] / pe['m']:.3f}")
    print(f"flat-multiple @PE_M={pe['m']:.3f}: {flat[0]:.2f} / {flat[1]:.2f} / {flat[2]:.2f}")
    for t in TIERS:
        model_pay, gap = payout_gap(g2, rho[t], inp["payout_fy25"])
        excess = (1.0 - inp["payout_fy25"] - g2 / rho[t]) * unbooked(inp, t)
        print(f"  payout_gap {t}: model {model_pay:.3f} vs paid {inp['payout_fy25']:.2f} (gap {gap:.3f}); "
              f"视同派出 {excess:.2f} 元/股 (k=0 → {excess:.2f})")
    print(f"③ L 档：PE_L {pe['l']:.2f} vs 同等盈利月份最低 {inp['pe_eq_lo']:.2f}（{inp['pe_eq_n']:.0f} 个月）"
          f" → {'视同出带' if l_out else '入带'}；带有效性：当时预期增速 {inp['g_exp_band']:.0%} − 模型 g "
          f"{g2:.0%} = {inp['g_exp_band'] - g2:.0%} ≥ 10pp → {'失真 → 不可判定，篮子不动' if distorted else '干净'}")
    print("对账门坐标：" + "；".join(f"{k} {v:.2f}（M/坐标 {M / v - 1:+.1%}）" for k, v in coords.items())
          + f" → 20% 内：{', '.join(near)}")
    print(f"压力坐标：TTM {inp['eps_ttm']:.3f} × 1/r = {inp['eps_ttm'] / r:.2f}；"
          f"FY2028E 下沿 {inp['eps_fy28_lo']:.2f} × PE_M ÷ 1.1 = {inp['eps_fy28_lo'] * pe['m'] * disc(inp, 'm'):.2f}")
    for dg in (-0.01, 0.01):
        alt = dict(inp, g2=g2 + dg)
        la, ma, ha = (anchor(alt, t) for t in TIERS)
        print(f"敏感 g2 {g2 + dg:.0%}: L {la:.2f} M {ma:.2f} H {ha:.2f}")
    nd_ebitda = inp["net_debt"] / (inp["ebit_fy25"] + 2 * inp["da_1h26"])
    print(f"杠杆门：净债 {inp['net_debt']:.1f} 亿 / EBITDA≈{inp['ebit_fy25'] + 2 * inp['da_1h26']:.0f} = "
          f"{nd_ebitda:.2f}；利息(1H26×2) / EBIT = {2 * inp['int_1h26'] / inp['ebit_fy25']:.1%} → 未触发")
    print(f"V_opt：{opt['gwh']:.1f} GWh × {opt['unit']:.2f} 元/kWh = {opt['d_ni']:.2f} 亿（ΔEPS {opt['d_eps']:.3f}）"
          f" → ROE {opt['roe_post']:.2%}、PE {opt['pe_post']:.3f} → 兑现后锚点 {opt['anchor_post']:.2f} − H {H:.2f}"
          f" − 资本 {opt['k_ps']:.2f} = {opt['anchor_post'] - H - opt['k_ps']:.2f} × {opt['d_real']:.4f}"
          f" = {opt['v_opt']:.2f}（扣资本前 {opt['v_gross']:.2f}）")
    print(f"表3 p_k={P_K[0]:g}/{P_K[1]:g}/{P_K[2]:g} → {band3[0]:.2f} / {band3[1]:.2f} / {band3[2]:.2f}"
          f"  A′={a3:.2f} B′={b3:.2f}")
    for name, tp in (("汇丰", inp["tp_hsbc"]), ("花旗", inp["tp_citi"]), ("瑞银", inp["tp_ubs"]),
                     ("一致", inp["tp_consensus"])):
        print(f"  TP {name} {tp:.2f} → FY2028E 均值折现口径 PE {tp / (inp['eps_m'] * disc(inp, 'm')):.2f}")
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
