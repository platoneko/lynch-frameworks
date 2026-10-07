#!/usr/bin/env python3
"""0857.HK (PetroChina) valuation eval.

frameworks/0857.HK.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The
framework carries no current price (AGENTS.md「现价 — 禁写契约」): this
script neither reads a price nor derives or checks a zone -- the daily
digest derives the zone from live quotes.

formula_id: petrochina_hk_brent_axis_owner_earnings_leg_sum_v3

Main ruler: a four-leg SUM on the H share (valuation-rules「归篮触发分腿」:
the segments sit in different baskets, so the legs are priced separately and
added, never on a blended r).  Numerator year FY2027 (the furthest year with
>= 2 houses and a range).  The numerator is the shared Brent axis
(_AXIS.brent-oil.md, 68 / 75 / 85) pushed through the company's OWN measured
E&P elasticity, measured half-year against the same half-year (A2):

    beta = [(E&P OP 2026H1 - E&P OP 2025H1) x 2 / (realised 2026H1 - realised 2025H1)]
           x (1 - CIT) x (realised / Brent, FY2025)            = 1,817 RMB mn per US$1
    NI_x = NI_FY2025 + beta x (Brent_x - 68.2)

The v2 two-point slope (2026H1 x 2 against FY2025) read the H2 seasonality --
Q4 impairments and year-end costs, H2/H1 E&P OP 0.74 / 0.74 / 0.59 in
2023-25 -- as oil elasticity and doubled beta; it is printed as a cross-check
only.  The eight-year segment regression (2018-25) is the second cross.

Legs: FY2025 NI split by FY2025 segment OP share; beta and the maintenance
capex above D&A (11,000) both land on the E&P leg; the three downstream legs
are frozen at FY2025 (A5: 2018-25 shows refining moves WITH oil, not against
it, and gas is the only leg that leans the other way).

    E&P      (1 - b) / (r_perp - g2)   篮 6 13%, b and g2 from named growth capex (A7)
    gas      1 / r_ng                  篮 6 13% (import-cost spread, Kunlun city gas < 1/10)
    refining 1 / r_rc                  篮 6 13%
    marketing 1 / r_mk                 篮 4 10%

The realised 5y monthly PE band is a guardrail on the EFFECTIVE multiple
(anchor / E_owner): out-of-band is DISCLOSED (裁决顺序 ③), not forced back.

Run:  python3 frameworks/eval/0857.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_BRENT  # noqa: E402
from lib.gordon import (  # noqa: E402
    FULL_PAYOUT, basket_r, check_g_cap, check_r, recovery_two_stage_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.tiers import decompose  # noqa: E402
from lib.zones import cut_points, zone_of  # noqa: E402

# rf_report / bands_io import eval.lib.*, so the repo root must be importable too.
sys.path.append(str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FRAMEWORK = REPO / "frameworks" / "0857.HK.md"
FORMULA_ID = "petrochina_hk_brent_axis_owner_earnings_leg_sum_v3"
TICKER = "0857.HK"
LISTING_CCY = "HKD"

TIERS = ("l", "m", "h")
MN = 1e6                    # Inputs money fields are RMB million
G_TOL = 5e-4                # g2 stated to 0.01pp
B_TOL = 5e-3                # b_growth stated to 0.1pp
MIN_R_MINUS_G = 0.02
CONS_DEV_MAX = 0.20         # ②-b: M within 20% of the consensus mean
GATE_OUT = 0.20             # 纠正对账门: new M outside every coordinate by > 20% -> BLOCKED
SOG_RETENTION = 0.525       # (1 - SOG 30%) x (1 - CIT 25%) for the theoretical beta cross-check
USDCNY_CROSS = 7.0
MAINT_ALL = 59000.0         # A9: the whole capex-above-D&A gap read as maintenance (RMB mn)

LEGS = ("r_perp", "r_ng", "r_rc", "r_mk")   # E&P / gas / refining / marketing
SEGS = ("seg_ep", "seg_ng", "seg_rc", "seg_mk")

REQUIRED = [
    "shares", "equity", "fx_hkdcny",
    "ni_fy25", "eps_fy25", "div_fy25", "dps_fy25",
    "brent_2025", "brent_l", "brent_m", "brent_h",
    "ep_op_fy25", "ep_op_h1_26", "ep_op_h1_25", "real_2025", "real_h1_26", "real_h1_25", "cit",
    "crude_fy25", "ep_slope_reg_lo", "ep_slope_reg_hi",
    *LEGS, "capex_maint_excess", "capex_growth", "roe_proj", "b_growth", "net_debt",
    "g2_l", "g2_m", "g2_h", "g_peer_us",
    "pe_own_min", "pe_own_max", "pe_own_med",
    "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi", "tp_cons_h",
    *SEGS, "op_group_fy25",
    "ni_h1_26", "fcf_fy25", "eps_trough_fy2020", "eps_fy2022",
    "px_same_p25", "px_same_med", "px_same_p75", "pb_own_med", "pb_own_min",
]
# Reference rows: present in Inputs, never in an anchor path (校验步骤 11).
NOT_FORMULA = (
    "crude_fy25", "ep_slope_reg_lo", "ep_slope_reg_hi", "pe_own_med", "g_peer_us",
    "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi", "tp_cons_h",
    "ni_h1_26", "fcf_fy25", "eps_trough_fy2020", "eps_fy2022",
    "px_same_p25", "px_same_med", "px_same_p75", "pb_own_med", "pb_own_min",
)

# _AXIS.brent-oil.md §1 rung rows: | **L** | regime | **68** | sources | as-of |
_AXIS_ROW = re.compile(r"^\|\s*\*\*([LMH])\*\*\s*\|")
# _AXIS.brent-oil.md §3 transmission rows: | L | 68 | 0857 NI | 0857 EPS | 0857 ROE | 0883 ... |
_TRANS_ROW = re.compile(r"^\|\s*([LMH])\s*\|\s*\d+\s*\|")


def load_brent_rungs(path: Path = AXIS_BRENT) -> dict[str, float]:
    """{tier: Brent US$/bbl} from the axis §1 table (column 2, 0-based)."""
    rungs: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _AXIS_ROW.match(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        try:
            rungs[m.group(1)] = float(cells[2].strip("* ").replace(",", ""))
        except ValueError:
            continue
    missing = {"L", "M", "H"} - rungs.keys()
    if missing:
        raise ValueError(f"{path.name}: rungs missing {sorted(missing)}")
    if not (rungs["L"] < rungs["M"] < rungs["H"]):
        raise ValueError(f"{path.name}: rungs not ordered {rungs}")
    return rungs


def load_axis_transmission(path: Path = AXIS_BRENT) -> dict[str, tuple[float, float, float]]:
    """{tier: (NI mn, EPS, ROE)} for this ticker from the axis §3 table (columns 2-4)."""
    out: dict[str, tuple[float, float, float]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _TRANS_ROW.match(line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 5:
            continue
        num = lambda s: float(s.replace(",", "").replace("%", ""))  # noqa: E731
        out[m.group(1)] = (num(cells[2]), num(cells[3]), num(cells[4]) / 100.0)
    return out


def check_brent_mount(stated: tuple[float, float, float]) -> list[str]:
    """The mount restates the axis rungs exactly, and the axis declares the mount."""
    if not AXIS_BRENT.exists():
        return [f"axis file missing: {AXIS_BRENT.name}"]
    rungs = load_brent_rungs()
    errors = [
        f"{tier} Brent rung: stated {got:g} vs axis {rungs[tier]:g}"
        for tier, got in zip(("L", "M", "H"), stated)
        if abs(got - rungs[tier]) > 1e-9
    ]
    if TICKER not in AXIS_BRENT.read_text(encoding="utf-8"):
        errors.append(f"{TICKER} is not declared on {AXIS_BRENT.name} — a mount has to exist on both sides")
    return errors


def ep_pe(b_growth: float, r: float, g: float) -> float:
    """E&P leg: retention-adjusted perpetuity, retention named by growth capex (A7)."""
    if r - g <= 0:
        raise ValueError(f"perpetuity diverges: g={g} >= r={r}")
    return (1.0 - b_growth) / (r - g)


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    leaked_p = [k for k in inp if k.startswith("p_")]
    if leaked_p:
        errors.append(f"probability fields in Inputs {leaked_p} (A2e-7a)")
    fx, shares = inp["fx_hkdcny"], inp["shares"]
    r_leg = {leg: inp[leg] for leg in LEGS}

    # --- Step 1: axis mount, beta (half against half), numerator ladder ---------
    brent = {"l": inp["brent_l"], "m": inp["brent_m"], "h": inp["brent_h"]}
    errors += check_brent_mount((brent["l"], brent["m"], brent["h"]))
    rho = inp["real_2025"] / inp["brent_2025"]
    slope_op = 2.0 * (inp["ep_op_h1_26"] - inp["ep_op_h1_25"]) / (inp["real_h1_26"] - inp["real_h1_25"])
    beta = slope_op * (1.0 - inp["cit"]) * rho
    slope_v2 = (2.0 * inp["ep_op_h1_26"] - inp["ep_op_fy25"]) / (inp["real_h1_26"] - inp["real_2025"])
    beta_v2 = slope_v2 * (1.0 - inp["cit"]) * rho
    beta_theory = inp["crude_fy25"] * rho * SOG_RETENTION * USDCNY_CROSS
    beta_reg = tuple(s * (1.0 - inp["cit"]) * rho for s in (inp["ep_slope_reg_lo"], inp["ep_slope_reg_hi"]))
    if not (inp["ep_slope_reg_lo"] * 0.8 <= slope_op <= inp["ep_slope_reg_hi"] * 1.2):
        errors.append(f"E&P slope {slope_op:,.0f}/$ outside the 2018-25 regression "
                      f"[{inp['ep_slope_reg_lo']:,.0f}, {inp['ep_slope_reg_hi']:,.0f}] ±20% (A2)")
    ni = {t: inp["ni_fy25"] + beta * (brent[t] - inp["brent_2025"]) for t in TIERS}
    eps = {t: ni[t] * MN / shares for t in TIERS}                                   # reported-NI EPS (②-b, ROE)
    e_owner = {t: (ni[t] - inp["capex_maint_excess"]) * MN / shares for t in TIERS}
    roe = {t: ni[t] / inp["equity"] for t in TIERS}                                # disclosed only
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    errors += ladder("e_owner", e_owner["l"], e_owner["m"], e_owner["h"])

    trans = load_axis_transmission()
    for t, tier in zip(TIERS, ("L", "M", "H")):
        if tier not in trans:
            errors.append(f"axis §3: no {TICKER} transmission row {tier}")
            continue
        a_ni, a_eps, a_roe = trans[tier]
        if abs(a_ni - ni[t]) > 1.0 or abs(a_eps - eps[t]) > 5e-4 or abs(a_roe - roe[t]) > 5e-4:
            errors.append(f"axis §3 {tier}: {a_ni:,.0f} / {a_eps:.4f} / {a_roe:.2%} vs computed "
                          f"{ni[t]:,.0f} / {eps[t]:.4f} / {roe[t]:.2%}")
    if errors:
        return report(errors, "FAIL (axis / numerators)")

    # --- Step 2: baskets, g2 from named growth capex (A7), cap ----------------
    baskets = parse_baskets(md)
    for leg in LEGS:
        if leg not in baskets:
            errors.append(f"{leg}: no 篮 N in its Inputs source cell (valuation-rules.md「§r 篮子」)")
        errors += check_r(inp[leg], leg, baskets.get(leg))
    r_ep = r_leg["r_perp"]
    for t in TIERS:
        errors += check_g_cap(inp[f"g2_{t}"], r_ep, f"g2_{t}")
        if r_ep - inp[f"g2_{t}"] < MIN_R_MINUS_G:
            errors.append(f"g2_{t} {inp[f'g2_{t}']:+.4f}: r-g < {MIN_R_MINUS_G} (裁决顺序 ①)")
    if not (abs(inp["g2_l"] - inp["g2_m"]) <= G_TOL and abs(inp["g2_h"] - inp["g2_m"]) <= G_TOL):
        errors.append(f"g2 tiers must be flat: {inp['g2_l']}/{inp['g2_m']}/{inp['g2_h']} (A7: growth is carried by named capex)")
    e_owner_m_mn = ni["m"] - inp["capex_maint_excess"]
    g2_derived = inp["capex_growth"] * inp["roe_proj"] / e_owner_m_mn
    b_derived = inp["capex_growth"] / e_owner_m_mn
    if inp["g2_m"] <= 0:
        errors.append(f"g2_m {inp['g2_m']:+.4f} <= 0 is the full-payout branch — PetroChina retains (A7)")
    if abs(inp["g2_m"] - g2_derived) > G_TOL:
        errors.append(f"g2_m {inp['g2_m']} vs capex_growth x roe_proj / E_owner_M = {g2_derived:.5f} (A7)")
    if abs(inp["b_growth"] - b_derived) > B_TOL:
        errors.append(f"b_growth {inp['b_growth']} vs capex_growth / E_owner_M = {b_derived:.4f} (A7)")
    payout_fy25 = inp["div_fy25"] / inp["ni_fy25"]
    if payout_fy25 >= FULL_PAYOUT:
        errors.append(f"payout {payout_fy25:.0%} >= {FULL_PAYOUT:.0%}: nothing retained to fund g2 > 0 (A7 分支)")
    if errors:
        return report(errors, "FAIL (baskets / growth 口径)")

    # --- Step 3: leg sum -----------------------------------------------------
    seg_sum = sum(inp[k] for k in SEGS)
    if abs(inp["seg_ep"] - inp["ep_op_fy25"]) > 1e-6:
        errors.append("seg_ep must equal ep_op_fy25 (same filed number)")
    share = {k: inp[k] / seg_sum for k in SEGS}
    per_share = lambda v: v * MN / shares / fx  # noqa: E731

    def legs_at(t: str, r: dict[str, float], g: float, b: float, beta_x: float = beta,
                maint: float = inp["capex_maint_excess"]) -> tuple[float, float, float, float]:
        base = inp["ni_fy25"]
        ep_ni = base * share["seg_ep"] + beta_x * (brent[t] - inp["brent_2025"]) - maint
        return (per_share(ep_ni) * ep_pe(b, r["r_perp"], g),
                per_share(base * share["seg_ng"]) / r["r_ng"],
                per_share(base * share["seg_rc"]) / r["r_rc"],
                per_share(base * share["seg_mk"]) / r["r_mk"])

    def band(r: dict[str, float] = r_leg, g: float = inp["g2_m"], b: float = inp["b_growth"], **kw) -> tuple[float, float, float]:
        return tuple(sum(legs_at(t, r, g, b, **kw)) for t in TIERS)  # type: ignore[return-value]

    legs = {t: legs_at(t, r_leg, inp["g2_m"], inp["b_growth"]) for t in TIERS}
    L, M, H = (sum(legs[t]) for t in TIERS)
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}"])
    A, B = cut_points(L, M, H)
    pe_eff = {t: a * fx / e_owner[t] for t, a in zip(TIERS, (L, M, H))}
    pe_e = ep_pe(inp["b_growth"], r_ep, inp["g2_m"])

    # --- Step 4: guardrail ③ on the effective multiple, ②-b ------------------
    in_band = all(inp["pe_own_min"] - 1e-9 <= pe_eff[t] <= inp["pe_own_max"] + 1e-9 for t in TIERS)
    band_note = (f"③ 不触发: 有效 PE {'/'.join(f'{pe_eff[t]:.2f}' for t in TIERS)} ∈ [{inp['pe_own_min']}, {inp['pe_own_max']}]" if in_band
                 else f"③ 出带: 有效 PE {'/'.join(f'{pe_eff[t]:.2f}' for t in TIERS)} outside [{inp['pe_own_min']}, {inp['pe_own_max']}] — disclosed, not forced")
    cons_mean = inp["eps_cons_fy27_mean"]
    cons_dev = eps["m"] / cons_mean - 1.0
    if cons_mean > eps["h"]:
        errors.append(f"②-b: consensus FY27 mean {cons_mean} above EPS_H {eps['h']:.4f} — H must become the market-baseline world")
    if abs(cons_dev) > CONS_DEV_MAX:
        errors.append(f"②-b: M deviates {cons_dev:+.1%} from consensus FY27 mean (> {CONS_DEV_MAX:.0%}) — switch numerators to the consensus three points")
    if cons_mean < eps["m"] and "②-b" not in md:
        errors.append("②-b: consensus FY27 mean below EPS_M with no named-variable row in the framework (A6)")
    brent_cons = inp["brent_2025"] + (cons_mean * shares / MN - inp["ni_fy25"]) / beta

    # --- Step 5: 纠正对账门 coordinates (M moved > 25% from v2 10.51) ----------
    zero_g = band(g=0.0, b=0.0)
    r_vw = sum(v * r_leg[leg] for v, leg in zip(legs["m"], LEGS)) / M
    d1 = payout_fy25 * eps["m"] / fx * (1.0 + inp["g2_m"])
    ddm = d1 / (r_vw - inp["g2_m"])
    bps_hkd = inp["equity"] * MN / shares / fx
    coords = {
        "② E_M/r (逐腿 g 0)": zero_g[1],
        "③ D_M/(r̄−g)": ddm,
        "④ 同等盈利月份中位": inp["px_same_med"],
        "⑥ BPS × 5 年 PB 中位": bps_hkd * inp["pb_own_med"],
    }
    if all(abs(M / v - 1.0) > GATE_OUT for v in coords.values()):
        errors.append(f"纠正对账门: M {M:.2f} outside every coordinate by > {GATE_OUT:.0%} — BLOCKED")

    for k in NOT_FORMULA:
        if k not in inp:
            errors.append(f"reference row missing from Inputs: {k}")
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # --- report ----------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"axis _AXIS.brent-oil OK: Brent {brent['l']:g}/{brent['m']:g}/{brent['h']:g}; base {inp['brent_2025']} (realised/Brent rho {rho:.4f}); axis §3 transmission rows match")
    print(f"beta = E&P OP slope (半年同比 ×2) {slope_op:,.0f}/$ x (1-CIT) x rho = {beta:,.0f} RMB mn per US$1 Brent; ΔEPS/$1 = {beta * MN / shares:.4f} CNY | "
          f"2018-25 回归 {inp['ep_slope_reg_lo']:,.0f}–{inp['ep_slope_reg_hi']:,.0f}/$ → β {beta_reg[0]:,.0f}–{beta_reg[1]:,.0f}; "
          f"v2 两点法 {slope_v2:,.0f}/$ → β {beta_v2:,.0f} (已废); 理论交叉 {beta_theory:,.0f} (未扣特别收益金)")
    print("篮子: " + "; ".join(f"{leg} 篮 {baskets[leg]} {basket_r(baskets[leg]):.0%}" for leg in LEGS) + f" | 价值加权 r̄ {r_vw:.2%} (只披露)")
    print(f"{'档':<3}{'Brent':>7}{'NI(mn)':>10}{'EPS':>9}{'E_owner':>9}{'ROE':>8}{'E&P':>7}{'气':>7}{'炼化':>7}{'销售':>7}{'HKD':>8}{'有效PE':>8}")
    for t, a in zip(TIERS, (L, M, H)):
        ep, ng, rc, mk = legs[t]
        print(f"{t.upper():<3}{brent[t]:7.0f}{ni[t]:10,.0f}{eps[t]:9.4f}{e_owner[t]:9.4f}{roe[t]:8.2%}{ep:7.2f}{ng:7.2f}{rc:7.2f}{mk:7.2f}{a:8.2f}{pe_eff[t]:8.2f}")
    print(f"E&P 腿: PE = (1 − b_g)/(r − g2) = (1 − {inp['b_growth']:.3f})/({r_ep:.2f} − {inp['g2_m']:.4f}) = {pe_e:.3f}x flat; "
          f"g2 = 增长 capex {inp['capex_growth']:,.0f} x 项目 ROE {inp['roe_proj']:.0%} / E_owner_M {e_owner_m_mn:,.0f} = {g2_derived:+.3%} "
          f"(cap {min(0.06, r_ep - 0.04):.0%}); b_g = {b_derived:.1%}; 项目 ROE < r → 留存毁值 (g 0 b 0 的 1/r {1 / r_ep:.2f}x)")
    print(f"分支: 留存 (FY2025 派息率 {payout_fy25:.1%}); 模型派息 1 − b_g = {1 - inp['b_growth']:.1%}, 差 {1 - inp['b_growth'] - payout_fy25:+.1%} = 财务性留存 (只披露); "
          f"美国大型油企簇 {inp['g_peer_us']:+.2%} (交叉)")
    print(f"护栏: {band_note}")
    print(f"②-b: 共识 FY27 {inp['eps_cons_fy27_lo']}/{cons_mean}/{inp['eps_cons_fy27_hi']} vs 归母 EPS {eps['l']:.4f}/{eps['m']:.4f}/{eps['h']:.4f}; "
          f"均值 {'in [M,H]' if eps['m'] <= cons_mean <= eps['h'] else ('below M' if cons_mean < eps['m'] else 'above H')}, M dev {cons_dev:+.1%}, 均值 ↔ Brent {brent_cons:.1f}")
    print(f"分部 (FY2025 OP): E&P {share['seg_ep']:.1%} / 天然气 {share['seg_ng']:.1%} / 炼化 {share['seg_rc']:.1%} / 销售 {share['seg_mk']:.1%}; "
          f"四分部 {seg_sum:,.0f} − 集团 {inp['op_group_fy25']:,.0f} = 总部与抵销 {seg_sum - inp['op_group_fy25']:,.0f} (按份额摊入各腿)")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    d = decompose((L, M, H), (pe_eff["l"], pe_eff["m"], pe_eff["h"]))
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.1%} | 分子比 L={d['num_lm']:.3f} H={d['num_hm']:.3f} | 有效倍数比 L={d['pe_lm']:.3f} H={d['pe_hm']:.3f}")
    print("纠正对账门 (v2 M 10.51 → " + f"{M:.2f}, {M / 10.51 - 1:+.0%}): "
          + "; ".join(f"{k} {v:.2f} ({M / v - 1:+.0%})" for k, v in coords.items())
          + f"; ④ IQR {inp['px_same_p25']}–{inp['px_same_p75']}; ⑤ 同业同尺 待补")
    a_cny, b_cny = A * fx, B * fx
    print(f"中性带 PE 读数: TTM(FY25 EPS {inp['eps_fy25']}) {a_cny / inp['eps_fy25']:.1f}–{b_cny / inp['eps_fy25']:.1f}x · "
          f"中枢 EPS {eps['m']:.3f} {a_cny / eps['m']:.1f}–{b_cny / eps['m']:.1f}x · FY26E {inp['eps_cons_fy26_mean']} {a_cny / inp['eps_cons_fy26_mean']:.1f}–{b_cny / inp['eps_cons_fy26_mean']:.1f}x")
    for label, kw in (
        ("天然气 篮 4 10%", dict(r={**r_leg, "r_ng": 0.10})),
        ("g2 −1pp", dict(g=inp["g2_m"] - 0.01)),
        ("g2 +1pp", dict(g=inp["g2_m"] + 0.01)),
        ("g 0 b 0 (逐腿 1/r)", dict(g=0.0, b=0.0)),
        ("E&P 篮 7 15%", dict(r={**r_leg, "r_perp": 0.15})),
        ("全腿 篮 4 10%", dict(r={leg: 0.10 for leg in LEGS})),
        (f"β 回归下沿 {beta_reg[0]:,.0f}", dict(beta_x=beta_reg[0])),
        (f"β 回归上沿 {beta_reg[1]:,.0f}", dict(beta_x=beta_reg[1])),
        (f"β v2 两点法 {beta_v2:,.0f} (已废)", dict(beta_x=beta_v2)),
        ("维持 capex 0 (全增长)", dict(maint=0.0)),
        (f"维持 capex {MAINT_ALL:,.0f} (全维持)", dict(maint=MAINT_ALL)),
    ):
        print(f"敏感性 {label}: {'/'.join(f'{x:.2f}' for x in band(**kw))}")
    print(f"每 US$1 Brent ≈ {per_share(beta) * pe_e:+.3f} HKD (E&P 腿)")
    tp = inp["tp_cons_h"]
    print(f"卖方 TP 均值 {tp} HKD 落 {zone_of(tp, L, M, H)}; H/TP {H / tp:.2f} M/TP {M / tp:.2f} (交叉, 不反解)")
    print(f"净负债 (只披露): {inp['net_debt']:,.0f} mn = {per_share(inp['net_debt']):.2f} HKD/股 ({per_share(inp['net_debt']) / M:.1%} of M)")
    print(f"地板 (只披露): BPS {bps_hkd:.2f} HKD; 锚点 PB {L / bps_hkd:.2f}/{M / bps_hkd:.2f}/{H / bps_hkd:.2f}; "
          f"BPS × PB 5 年最低 {inp['pb_own_min']} = {bps_hkd * inp['pb_own_min']:.2f}")
    print(f"交叉尺: own 中位 {inp['pe_own_med']}x × E_owner → {'/'.join(f'{e_owner[t] * inp['pe_own_med'] / fx:.2f}' for t in TIERS)}; "
          f"P/FCF 10x → {per_share(inp['fcf_fy25']) * 10:.2f}")
    g1 = (inp["eps_fy2022"] / inp["eps_trough_fy2020"]) ** 0.5 - 1.0
    pe_rec = recovery_two_stage_pe(g1, 2, inp["g2_m"], roe["m"], r_ep)
    print(f"谷底坐标: 回归段 2020->2022 g1 {g1:.1%} n=2 -> {pe_rec:.1f}x on FY2020 EPS = {inp['eps_trough_fy2020'] * pe_rec / fx:.2f} HKD; "
          f"谷底 x 1/r = {inp['eps_trough_fy2020'] / r_ep / fx:.2f} HKD (deep_discount 压力坐标)")
    print(f"属性 D: 2026H1 归母 {inp['ni_h1_26']:,.0f} x2 = {2 * inp['ni_h1_26']:,.0f} ↔ 本尺 Brent {inp['brent_2025'] + (2 * inp['ni_h1_26'] - inp['ni_fy25']) / beta:.1f}")
    print(f"A股对照(CNY): L={L * fx:.2f} M={M * fx:.2f} H={H * fx:.2f} A={A * fx:.2f} B={B * fx:.2f}")

    # r_f readings (_AXIS.rates): Δr_f moves every leg's r 1:1; Brent rungs,
    # E_owner, b_growth and g2 stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        return band(r={leg: v + dr for leg, v in r_leg.items()})

    rf = rf_block(LISTING_CCY, dict(r_leg), band_rf)
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    # Only a clean run feeds the daily digest.
    if not errors:
        write_rf_readings(TICKER, rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
