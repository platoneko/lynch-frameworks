#!/usr/bin/env python3
"""0857.HK (PetroChina) valuation eval.

frameworks/0857.HK.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: petrochina_hk_brent_axis_owner_earnings_flat_pe_v2

Main ruler: whole-company OWNER-EARNINGS PE on the H share, numerator FY2027
(the furthest year with >= 2 houses and a range).  The numerator is NOT the
consensus three points: it is the shared Brent axis (_AXIS.brent-oil.md,
68 / 75 / 85) pushed through the company's OWN measured E&P elasticity,

    beta = [(E&P OP 2026H1 x 2 - E&P OP FY2025) / (realised 2026H1 - realised FY2025)]
           x (1 - CIT) x (realised / Brent, FY2025)              = 3,680 RMB mn per US$1
    NI_x      = NI_FY2025 + beta x (Brent_x - 68.2)
    E_owner_x = (NI_x - maintenance capex above D&A 11,000) / shares     (A7, §4.0 bucket 1)

with the three downstream segments frozen at FY2025 (A5).  裁决顺序 ②-b is
checked mechanically on the reported-NI ladder: the FY2027 consensus mean must
not exceed EPS_H, and if it sits below EPS_M the framework has to carry the
named-variable row (A6).

The multiple is a flat retention-adjusted perpetuity, NOT a per-tier Gordon on
book ROE (M-tier ROE 11.1% sits within 3pp of r -- the pathological regime
where g barely moves the multiple and a reverse-solved g is not a reading):

    g2 = growth capex 48,000 x project ROE 9% / E_owner_M  = 2.5%  (= volume growth, §4.0 bucket 2)
    b  = growth capex / E_owner_M                           = 28%
    PE = (1 - b) / (r - g2) = 0.72 / 0.075                  = 9.6x, all three tiers

r is the E&P leg's basket (篮 4, 10%); the other legs (gas 篮 4, refining 篮 6,
marketing 篮 4) only enter the leg-sum cross-check (表1′).  Net debt is disclosed
per share, never subtracted (§4.0 bucket 3).  The realised 5y monthly PE band is
a guardrail: an out-of-band multiple is DISCLOSED (裁决顺序 ③), not forced back.

g's leverage is disclosed (敏感区): +1pp of g2 flips the zone to deep_discount.

The shared axis is parsed here rather than through eval/lib/axes.py: that
module is not part of this ticker's task.  Same row shape as the other
commodity axes (| **L** | regime | **68** | ...), so a future
`load_brent_rungs` in lib/axes.py is a drop-in.

Run:  python3 eval/0857.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_BRENT  # noqa: E402
from lib.gordon import (  # noqa: E402
    FULL_PAYOUT, basket_r, check_g_cap, check_r, implied_g_retaining, recovery_two_stage_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points, zone_of  # noqa: E402

# rf_report / bands_io import eval.lib.*, so the repo root must be importable too.
sys.path.append(str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FRAMEWORK = REPO / "frameworks" / "0857.HK.md"
FORMULA_ID = "petrochina_hk_brent_axis_owner_earnings_flat_pe_v2"
TICKER = "0857.HK"
LISTING_CCY = "HKD"

TIERS = ("l", "m", "h")
MN = 1e6                    # Inputs money fields are RMB million
G_TOL = 5e-4                # g2 is stated to 0.1pp (2.5%); the derivation lands on 2.52%
B_TOL = 5e-3                # b_growth stated to 1pp (28%)
MIN_R_MINUS_G = 0.02
CONS_DEV_MAX = 0.20         # ②-b: M within 20% of the consensus mean
NG_SECONDARY_GATE = 0.30    # A4: a segment >= 30% of segment OP would reopen the secondary-class question
LEG_SUM_TOL = 0.02          # 表1′: leg-sum cross-check within 2% of the deck
SOG_RETENTION = 0.525       # (1 - SOG 30%) x (1 - CIT 25%) for the theoretical beta cross-check
USDCNY_CROSS = 7.0
MAINT_ALL = 59000.0         # A9: the whole capex-above-D&A gap read as maintenance (RMB mn)

LEGS = ("r_perp", "r_ng", "r_rc", "r_mk")   # E&P / gas / refining / marketing

REQUIRED = [
    "price", "price_a", "shares", "equity", "fx_hkdcny",
    "ni_fy25", "eps_fy25", "div_fy25", "dps_fy25",
    "brent_2025", "brent_l", "brent_m", "brent_h",
    "ep_op_fy25", "ep_op_h1_26", "real_2025", "real_h1_26", "cit", "crude_fy25",
    *LEGS, "capex_maint_excess", "capex_growth", "roe_proj", "b_growth", "net_debt",
    "g2_l", "g2_m", "g2_h", "g_peer_us",
    "pe_own_min", "pe_own_max", "pe_own_med",
    "eps_cons_fy26_mean", "eps_cons_fy27_lo", "eps_cons_fy27_mean", "eps_cons_fy27_hi", "tp_cons_h",
    "seg_ep", "seg_rc", "seg_mk", "seg_ng", "op_group_fy25",
    "ni_h1_26", "fcf_fy25", "eps_trough_fy2020", "eps_fy2022",
]
# Reference rows: present in Inputs, never in an anchor path (校验步骤 11).
NOT_FORMULA = (
    "crude_fy25", "pe_own_med", "g_peer_us", "eps_cons_fy26_mean", "eps_cons_fy27_lo",
    "eps_cons_fy27_mean", "eps_cons_fy27_hi", "tp_cons_h", "ni_h1_26", "fcf_fy25",
    "eps_trough_fy2020", "eps_fy2022",
)

# _AXIS.brent-oil.md §1 rung rows: | **L** | regime | **68** | sources | as-of |
_AXIS_ROW = re.compile(r"^\|\s*\*\*([LMH])\*\*\s*\|")


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


def flat_pe(b_growth: float, r: float, g: float) -> float:
    """Retention-adjusted perpetuity with the retention named by capex, not by g/ROE (A7)."""
    if r - g <= 0:
        raise ValueError(f"perpetuity diverges: g={g} >= r={r}")
    return (1.0 - b_growth) / (r - g)


def band_at(e_owner: dict[str, float], pe: float, fx: float) -> tuple[float, float, float]:
    """L/M/H in HKD for one flat multiple on the owner-earnings ladder."""
    return tuple(e_owner[t] * pe / fx for t in TIERS)  # type: ignore[return-value]


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
    r, fx = inp["r_perp"], inp["fx_hkdcny"]

    # --- Step 1: axis mount and the numerator ladder --------------------------
    brent = {"l": inp["brent_l"], "m": inp["brent_m"], "h": inp["brent_h"]}
    errors += check_brent_mount((brent["l"], brent["m"], brent["h"]))
    rho = inp["real_2025"] / inp["brent_2025"]
    slope_op = (2.0 * inp["ep_op_h1_26"] - inp["ep_op_fy25"]) / (inp["real_h1_26"] - inp["real_2025"])
    beta = slope_op * (1.0 - inp["cit"]) * rho
    beta_theory = inp["crude_fy25"] * rho * SOG_RETENTION * USDCNY_CROSS
    ni = {t: inp["ni_fy25"] + beta * (brent[t] - inp["brent_2025"]) for t in TIERS}
    eps = {t: ni[t] * MN / inp["shares"] for t in TIERS}                            # reported-NI EPS (②-b, ROE)
    e_owner = {t: (ni[t] - inp["capex_maint_excess"]) * MN / inp["shares"] for t in TIERS}
    roe = {t: ni[t] / inp["equity"] for t in TIERS}                                # disclosed only (A7)
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    errors += ladder("e_owner", e_owner["l"], e_owner["m"], e_owner["h"])
    if errors:
        return report(errors, "FAIL (axis / numerators)")

    # --- Step 2: baskets, g2 from named growth capex (A7), cap ----------------
    baskets = parse_baskets(md)
    for leg in LEGS:
        if leg not in baskets:
            errors.append(f"{leg}: no 篮 N in its Inputs source cell (valuation-rules.md「§r 篮子」)")
        errors += check_r(inp[leg], leg, baskets.get(leg))
    for t in TIERS:
        errors += check_g_cap(inp[f"g2_{t}"], r, f"g2_{t}")
        if r - inp[f"g2_{t}"] < MIN_R_MINUS_G:
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

    # --- Step 3: flat multiple, guardrail (③ disclosed), anchors, zone -------
    pe = flat_pe(inp["b_growth"], r, inp["g2_m"])
    in_band = inp["pe_own_min"] - 1e-9 <= pe <= inp["pe_own_max"] + 1e-9
    band_note = (f"③ 不触发: {pe:.2f}x ∈ [{inp['pe_own_min']}, {inp['pe_own_max']}]" if in_band
                 else f"③ 出带: {pe:.2f}x outside [{inp['pe_own_min']}, {inp['pe_own_max']}] — disclosed, not forced")
    L, M, H = band_at(e_owner, pe, fx)
    if not (L < M < H):
        return report(errors + [f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}"])
    A, B = cut_points(L, M, H)
    zone = zone_of(inp["price"], L, M, H)

    cons_mean = inp["eps_cons_fy27_mean"]
    cons_dev = eps["m"] / cons_mean - 1.0
    if cons_mean > eps["h"]:
        errors.append(f"②-b: consensus FY27 mean {cons_mean} above EPS_H {eps['h']:.4f} — H must become the market-baseline world")
    if abs(cons_dev) > CONS_DEV_MAX:
        errors.append(f"②-b: M deviates {cons_dev:+.1%} from consensus FY27 mean (> {CONS_DEV_MAX:.0%}) — switch numerators to the consensus three points")
    if cons_mean < eps["m"] and "②-b" not in md:
        errors.append("②-b: consensus FY27 mean below EPS_M with no named-variable row in the framework (A6)")
    brent_cons = inp["brent_2025"] + (cons_mean * inp["shares"] / MN - inp["ni_fy25"]) / beta

    seg_sum = inp["seg_ep"] + inp["seg_rc"] + inp["seg_mk"] + inp["seg_ng"]
    if abs(inp["seg_ep"] - inp["ep_op_fy25"]) > 1e-6:
        errors.append("seg_ep must equal ep_op_fy25 (same filed number)")
    ng_share = inp["seg_ng"] / seg_sum
    if ng_share >= NG_SECONDARY_GATE:
        errors.append(f"natural gas is {ng_share:.1%} of segment OP (>= {NG_SECONDARY_GATE:.0%}) — reopen the secondary-class question (A4)")

    # 表1′ leg sum: FY2025 NI split by segment OP share, beta and the maintenance
    # deduction both on the E&P leg, each leg on its own basket r (g 0 = 1/r).
    def leg_sum(t: str) -> tuple[float, float, float, float]:
        base = inp["ni_fy25"]
        ep = base * inp["seg_ep"] / seg_sum + (ni[t] - base) - inp["capex_maint_excess"]
        ng, rc, mk = (base * inp[k] / seg_sum for k in ("seg_ng", "seg_rc", "seg_mk"))
        per_share = lambda v: v * MN / inp["shares"] / fx  # noqa: E731
        return (per_share(ep) * pe, per_share(ng) / inp["r_ng"], per_share(rc) / inp["r_rc"], per_share(mk) / inp["r_mk"])
    legs = {t: leg_sum(t) for t in TIERS}
    for t, a in zip(TIERS, (L, M, H)):
        if abs(sum(legs[t]) / a - 1.0) > LEG_SUM_TOL:
            errors.append(f"leg-sum {t.upper()} {sum(legs[t]):.2f} deviates > {LEG_SUM_TOL:.0%} from deck {a:.2f} (表1′)")

    flat_errs, flat_cny = flat_multiple_ladder((e_owner["l"], e_owner["m"], e_owner["h"]), pe)
    errors += flat_errs
    flat = tuple(v / fx for v in flat_cny)

    if abs(inp["pe_own_med"] - pe) < 1e-9:
        errors.append("pe_own_med leaked into the multiple path — it is a comparison field")
    if abs(inp["g_peer_us"] - inp["g2_m"]) < 1e-9:
        errors.append("g_peer_us leaked into g2 — it is a different-regime cross-check")
    leaked = [k for k in NOT_FORMULA if k not in inp]
    if leaked:
        errors.append(f"reference rows missing from Inputs: {leaked}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report ----------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"axis _AXIS.brent-oil OK: Brent {brent['l']:g}/{brent['m']:g}/{brent['h']:g}; base {inp['brent_2025']} (realised/Brent rho {rho:.4f})")
    print(f"beta = OP slope {slope_op:,.0f}/$ realised x (1-CIT {inp['cit']:.0%}) x rho = {beta:,.0f} RMB mn per US$1 Brent "
          f"(theoretical cross {beta_theory:,.0f} = crude {inp['crude_fy25']:.0f} mmbbl x rho x {SOG_RETENTION} x {USDCNY_CROSS}); ΔEPS/$1 = {beta * MN / inp['shares']:.4f} CNY")
    print("篮子: " + "; ".join(f"{leg} 篮 {baskets[leg]} {basket_r(baskets[leg]):.0%}" for leg in LEGS) + " (底牌用 r_perp, 其余腿只进分腿加总)")
    print(f"{'档':<3}{'Brent':>7}{'NI(mn)':>10}{'EPS':>9}{'E_owner':>9}{'ROE':>8}{'g2':>8}{'b_g':>6}{'PE':>7}{'CNY':>8}{'HKD':>8}")
    for t, a in zip(TIERS, (L, M, H)):
        print(f"{t.upper():<3}{brent[t]:7.0f}{ni[t]:10,.0f}{eps[t]:9.4f}{e_owner[t]:9.4f}{roe[t]:8.2%}{inp[f'g2_{t}']:+8.2%}"
              f"{inp['b_growth']:6.0%}{pe:7.2f}{e_owner[t] * pe:8.3f}{a:8.2f}")
    print(f"所有者盈利: NI − 维持 capex 超出 D&A {inp['capex_maint_excess']:,.0f} mn (三档同扣); "
          f"g2 = 增长 capex {inp['capex_growth']:,.0f} x 项目 ROE {inp['roe_proj']:.0%} / E_owner_M {e_owner_m_mn:,.0f} = {g2_derived:+.3%} (cap {min(0.06, r - 0.04):.0%}); "
          f"b_g = {b_derived:.1%}; PE = (1 − b_g)/(r − g2) = {pe:.3f}x flat; 病态区 |ROE_M − r| = {abs(roe['m'] - r) * 100:.2f}pp (ROE 只披露)")
    print(f"分支: 留存 (FY2025 派息率 {payout_fy25:.1%} = {inp['div_fy25']:,.0f} / {inp['ni_fy25']:,.0f}); "
          f"模型派息 1 − b_g = {1 - inp['b_growth']:.0%}, 差 {1 - inp['b_growth'] - payout_fy25:+.1%} = 财务性留存 (第三桶, 只披露); "
          f"美国大型油企簇 {inp['g_peer_us']:+.2%} (单调区, 不同域, 交叉)")
    print(f"护栏: {band_note}")
    print(f"②-b: 共识 FY27 {inp['eps_cons_fy27_lo']}/{cons_mean}/{inp['eps_cons_fy27_hi']} vs 归母 EPS {eps['l']:.4f}/{eps['m']:.4f}/{eps['h']:.4f}; "
          f"均值 {'in [M,H]' if eps['m'] <= cons_mean <= eps['h'] else ('below M' if cons_mean < eps['m'] else 'above H')}, M dev {cons_dev:+.1%}, 均值 ↔ Brent {brent_cons:.1f} (A6 deck 年份)")
    print(f"分部校验层 (FY2025 OP): E&P {inp['seg_ep'] / seg_sum:.1%} / 炼化 {inp['seg_rc'] / seg_sum:.1%} / 销售 {inp['seg_mk'] / seg_sum:.1%} / 天然气 {ng_share:.1%}; "
          f"四分部 {seg_sum:,.0f} − 集团 {inp['op_group_fy25']:,.0f} = 总部与抵销 {seg_sum - inp['op_group_fy25']:,.0f}; 次类门槛 {NG_SECONDARY_GATE:.0%} 未触发")
    for t, a in zip(TIERS, (L, M, H)):
        ep, ng, rc, mk = legs[t]
        print(f"分腿加总 {t.upper()}: E&P {ep:.2f} + 天然气 {ng:.2f} + 炼化 {rc:.2f} + 销售 {mk:.2f} = {sum(legs[t]):.2f} (vs 底牌 {a:.2f}, {sum(legs[t]) / a - 1:+.1%})")
    d = decompose((L, M, H), (pe, pe, pe))
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.1%} | 分子比 L={d['num_lm']:.3f} H={d['num_hm']:.3f} | 倍数比 L={d['pe_lm']:.3f} H={d['pe_hm']:.3f}")
    print(f"flat-multiple @PE={pe:.2f}: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f} — 带宽 {(flat[2] - flat[0]) / (2 * flat[1]):.1%}")
    pe_px = inp["price"] * fx / e_owner["m"]
    r_px = (1.0 - inp["b_growth"]) / pe_px + inp["g2_m"]
    pe_a = inp["price_a"] / e_owner["m"]
    r_a = (1.0 - inp["b_growth"]) / pe_a + inp["g2_m"]
    pe_tp = inp["tp_cons_h"] * fx / e_owner["m"]
    g_px, ok_px = implied_g_retaining(inp["price"] * fx / eps["m"], roe["m"], r)
    print(f"price(H)={inp['price']} zone={zone} | 现价 = {pe_px:.2f}x E_owner_M → 隐含 r(P) {r_px:.1%} (篮 {baskets['r_perp']} {r:.0%} {r_px - r:+.1%}pp); "
          f"A 股 {inp['price_a']} = {pe_a:.2f}x → {r_a:.1%}, H 折价 ≈ {r_px - r_a:+.1%}pp; "
          f"TP 均值 {inp['tp_cons_h']} = {pe_tp:.2f}x ↔ r {(1 - inp['b_growth']) / pe_tp + inp['g2_m']:.1%} (zone {zone_of(inp['tp_cons_h'], L, M, H)}); H/TP {H / inp['tp_cons_h']:.2f} M/TP {M / inp['tp_cons_h']:.2f}; "
          f"留存×账面 ROE 反解 g {g_px:+.1%} (conditioned={ok_px}, 病态区不是读数)")
    print(f"净负债 (只披露): {inp['net_debt']:,.0f} mn = {inp['net_debt'] * MN / inp['shares']:.2f} CNY = {inp['net_debt'] * MN / inp['shares'] / fx:.2f} HKD/股 "
          f"({inp['net_debt'] * MN / inp['shares'] / fx / inp['price']:.1%} 市值)")
    bps = inp["equity"] * MN / inp["shares"]
    print(f"地板 (只披露): BPS {bps:.2f} CNY = {bps / fx:.2f} HKD; 现价 PB {inp['price'] * fx / bps:.2f}; 锚点 PB {'/'.join(f'{e_owner[t] * pe / bps:.2f}' for t in TIERS)}")
    for label, g in (("g2 −1pp", inp["g2_m"] - 0.01), ("g2 +1pp (⚠敏感区)", inp["g2_m"] + 0.01)):
        b = band_at(e_owner, flat_pe(inp["b_growth"], r, g), fx)
        print(f"敏感区 {label} {g:+.2%}: PE {flat_pe(inp['b_growth'], r, g):.2f} → {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    zg = band_at(e_owner, 1.0 / r, fx)
    print(f"敏感性 g=0 全派息 1/r: {'/'.join(f'{x:.2f}' for x in zg)} zone={zone_of(inp['price'], *zg)}")
    for label, r_alt in (("篮 5 11%", 0.11), ("篮 6 13%", 0.13)):
        b = band_at(e_owner, flat_pe(inp["b_growth"], r_alt, inp["g2_m"]), fx)
        print(f"敏感性 r_perp {label}: {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    for label, maint in (("0 (全增长)", 0.0), (f"{MAINT_ALL:,.0f} (全维持)", MAINT_ALL)):
        eo = {t: (ni[t] - maint) * MN / inp["shares"] for t in TIERS}
        b = band_at(eo, pe, fx)
        print(f"敏感性 capex_maint_excess {label}: {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    eo_t = {t: (inp["ni_fy25"] + beta_theory * (brent[t] - inp["brent_2025"]) - inp["capex_maint_excess"]) * MN / inp["shares"] for t in TIERS}
    b_t = band_at(eo_t, pe, fx)
    print(f"敏感性 β 理论交叉 {beta_theory:,.0f}: {'/'.join(f'{x:.2f}' for x in b_t)} zone={zone_of(inp['price'], *b_t)}; 每 US$1 Brent ≈ {beta * MN / inp['shares'] * pe / fx:+.2f} HKD")
    med = band_at(e_owner, inp["pe_own_med"], fx)
    d0 = inp["dps_fy25"] / fx
    ddm = d0 * (1 + inp["g2_m"]) / (r - inp["g2_m"])
    print(f"交叉尺: own 中位 {inp['pe_own_med']}x flat → {'/'.join(f'{x:.2f}' for x in med)} (zone {zone_of(inp['price'], *med)}); "
          f"DDM D0 {d0:.4f} HKD → {ddm:.2f} (现价隐含股息增长 {(inp['price'] * r - d0) / (inp['price'] + d0):+.2%}); "
          f"FCF 收益率 {inp['fcf_fy25'] * MN / (inp['price'] * fx * inp['shares']):.1%}, P/FCF 10x → {inp['fcf_fy25'] * MN / inp['shares'] * 10 / fx:.2f}")
    g1 = (inp["eps_fy2022"] / inp["eps_trough_fy2020"]) ** 0.5 - 1.0
    pe_rec = recovery_two_stage_pe(g1, 2, inp["g2_m"], roe["m"], r)
    print(f"谷底坐标 (A3): 回归段 2020->2022 g1 {g1:.1%} n=2 -> {pe_rec:.1f}x on FY2020 EPS {inp['eps_trough_fy2020']} = {inp['eps_trough_fy2020'] * pe_rec / fx:.2f} HKD (坐标, 不作锚); "
          f"谷底 x 1/r = {inp['eps_trough_fy2020'] / r / fx:.2f} HKD (deep_discount 压力坐标)")
    print(f"属性 D: 2026H1 归母 {inp['ni_h1_26']:,.0f} x2 = {2 * inp['ni_h1_26']:,.0f} ↔ 本尺 Brent {inp['brent_2025'] + (2 * inp['ni_h1_26'] - inp['ni_fy25']) / beta:.1f}")
    la, ma, ha = L * fx, M * fx, H * fx
    print(f"A股对照(CNY): L={la:.2f} M={ma:.2f} H={ha:.2f} | price_a={inp['price_a']} zone_a={zone_of(inp['price_a'], la, ma, ha)} | H/A = {inp['price'] * fx / inp['price_a']:.3f}")
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_perp 1:1 in the flat multiple; the Brent rungs, E_owner, b_growth and g2
    # stay put.  r_ng / r_rc / r_mk only price the 表1′ leg-sum cross-check, not
    # L/M/H, so they are not shifted.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        return band_at(e_owner, flat_pe(inp["b_growth"], r + dr, inp["g2_m"]), fx)

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf, inp["price"])
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    # Only a clean run feeds the daily digest.
    if not errors:
        write_rf_readings(TICKER, rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
