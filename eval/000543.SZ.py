#!/usr/bin/env python3
"""000543.SZ (Anhui Wenergy) valuation eval.

frameworks/000543.SZ.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading — the digest and the app zone on live quotes.

formula_id: wanneng_coal_axis_midcycle_pe_v5

Main ruler: whole-company PE on a MID-CYCLE EPS, flat 1/r on every tier with r
the basket r the framework names (篮 4 龙头制造 10%, `parse_baskets` +
`check_r`) and g2 = 0 (retention-bucket reading: ROE_M ~ r so growth capex has
~zero NPV; the Gordon multiple at ROE_M ~ r and the DDM are printed as crosses
only).  The numerators come from the coal axis
(`_AXIS.coal-price.md`, generator side: L = axis H 965 / M 830 / H = axis L
703) through the income-statement bridge the v5 draft validated:

    EPS = { tariff/1.13 x sales + resid(+capacity uplift) - uf(coal) x gen
            - nf x gen + gp_other - opex + misc } x (1 - tax) x par / shares
          + J(tariff, coal) / shares                     (神皖 49% associate)

    uf(coal) = uf_a + uf_b x coal            (axis §4a, 皖能 fit n=5)
    J        = assoc_a + assoc_b x tariff + assoc_c x coal   (FY2023-25 exact)

The thesis the tiers encode is the coal-move vs tariff-lag WAVE, not the coal
level: Anhui's annual market tariff is signed on the prior year's coal, so a
falling coal year is a fat year (FY2024 0.91 / FY2025 0.95) and a rising coal
year is a squeeze (2026H1 0.36).  Hence

  * L = the 2026E squeeze year taken as steady state: H1 realised + the bridge
    for H2 at the 2026-09 spot platform and the FY2025 tariff, with the 2026
    capacity tariff (165 CNY/kW-yr, 发改价格〔2023〕1501号) that every tier
    carries.  It loses to the PB floor (own-year PB low x BPS), which is what
    the framework reports (skill A2e-1: scenario_L and floor both stated).
  * M = the mid-cycle EPS: five cross-cycle readings (one lag-wave average,
    the bridge steady state at the caught-up tariff 437 / 430, the post-reform
    realised mean with and without 2026E) averaged; their min/max is the
    evidence interval, re-priced and printed at both ends.
  * H = the bridge at axis M coal 830 + the up-signed 2027 tariff 440 +
    capacity 165 — the fat-lag world, not a coal-703 world (that is `stretched`).

Guards (any failure exits 1): axis mount (rungs, base series, uf tiers vs axis
§4a), bridge reproduces FY2023/24/25 within +-20%, associate fit re-solved,
tariff-lag fit reproduces tariff_m, capacity uplift and squeeze re-derived,
E_H and the five-reading mid-cycle re-derived, r == its basket's value and
pe_m == 1/r, g2 and the policy g at or below g_cap(r) (`capped_payout_pe` must
equal `perpetual_pe` on the retention branch),
floor logic, ladder, and the 纠正对账门 table (valuation-rules 2026-09-15).
The E_M evidence interval and the axis M window are re-priced and printed.

Run:  python3 frameworks/eval/000543.SZ.py
"""

from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_COAL, check_coal_mount, load_coal_series  # noqa: E402
from lib.gordon import (  # noqa: E402
    BASKET_R, capped_payout_pe, check_branch, check_g_cap, check_r, g_cap, payout_gap, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "000543.SZ.md"
FORMULA_ID = "wanneng_coal_axis_midcycle_pe_v5"
TIERS = ("l", "m", "h")
YI = 1e8
VAT = 1.13

FLOOR_RECHECK_RATIO = 0.30   # A2e-1: below this the earnings ruler has failed at L
BRIDGE_TOL = 0.20            # axis 4c-1: realised-year reproduction
RECON_TOL = 0.20             # 纠正对账门: a coordinate "agrees" within this
EPS_TOL = 0.005              # stated tier EPS vs re-derived (2-dp inputs)
# Rejected rulers, kept as reconciliation coordinates (对账 ①).
M_V3_TTM, M_V4_FROZEN = 8.50, 3.78

REQUIRED = [
    "shares", "bps", "equity", "r_perp", "g2", "pe_m",
    "eps_l", "eps_m", "eps_h", "eps_m_lo", "eps_m_hi",
    "eps_h1_26", "eps_h2_26_bridge", "eps_ttm", "eps_fy26e",
    "eps_fy25", "eps_fy24", "eps_fy23", "eps_fy22",
    "coal_l", "coal_m", "coal_h", "coal_m_lo", "coal_m_hi", "coal_h2_26", "coal_fy2026e",
    "coal_fy2019", "coal_fy2020", "coal_fy2021", "coal_fy2022", "coal_fy2023", "coal_fy2024", "coal_fy2025",
    "uf_a", "uf_b",
    "tariff_fy22", "tariff_fy23", "tariff_fy24", "tariff_fy25", "tariff_fy26_impl",
    "tariff_m", "tariff_h", "tariff_bench", "tariff_cap", "k_tariff",
    "sales_fy23", "sales_fy24", "sales_fy25", "gen_fy23", "gen_fy24", "gen_fy25",
    "assoc_fy23", "assoc_fy24", "assoc_fy25", "assoc_a", "assoc_b", "assoc_c",
    "resid_m", "nf_kwh", "gp_other", "opex_m", "misc_m", "tax_op", "par_op",
    "cap_tariff_2025", "cap_tariff_2026", "cap_gw_coal", "eps_cap_uplift",
    "dps_fy25", "ni_fy25", "payout_fy25", "g2_policy",
    "pb_lo", "floor_l", "scenario_l",
    "pe_own_min", "pe_own_max", "pe_ownyear_l", "pe_ownyear_m", "pe_ownyear_h",
    "pe_same_n", "px_same_lo", "px_same_hi", "px_same_med", "pe_same_med",
    "peer_zjn_px", "peer_zjn_dps", "peer_hd_px", "peer_hd_dps",
]


# --- the bridge --------------------------------------------------------------
def uf(inp: dict[str, float], coal: float) -> float:
    """Unit fuel cost CNY/kWh from the axis §4a line (皖能 fit)."""
    return inp["uf_a"] + inp["uf_b"] * coal


def assoc_fit(inp: dict[str, float], tariff: float, coal: float) -> float:
    """神皖 49% associate income, 亿元, from the FY2023-25 exact fit."""
    return inp["assoc_a"] + inp["assoc_b"] * tariff + inp["assoc_c"] * coal


def cap_uplift_yi(inp: dict[str, float], cap_std: float) -> float:
    """Pretax capacity-tariff uplift over the FY2025 standard, 亿元: the FY2025
    residual already carries the 100 CNY/kW-yr standard, so only the delta is
    added (GW x CNY/kW x 1e6 / 1e8)."""
    return (cap_std - inp["cap_tariff_2025"]) * inp["cap_gw_coal"] * 1e-2


def bridge_eps(
    inp: dict[str, float], coal: float, tariff: float, cap_std: float,
    sales: float, gen: float, assoc_yi: float, frac: float = 1.0,
) -> float:
    """EPS from the income-statement bridge (亿元 -> CNY/share); `frac` scales
    the period (0.5 = a half year, structure parameters halved with it)."""
    shares_yi = inp["shares"] / YI
    power_rev = tariff / VAT * sales * frac / 1000 + (inp["resid_m"] + cap_uplift_yi(inp, cap_std)) * frac
    fuel = uf(inp, coal) * gen * frac
    pbt_op = power_rev - fuel - inp["nf_kwh"] * gen * frac + (inp["gp_other"] - inp["opex_m"] + inp["misc_m"]) * frac
    parent = pbt_op * (1.0 - inp["tax_op"]) * inp["par_op"] + assoc_yi * frac
    return parent / shares_yi


def world_eps(inp: dict[str, float], coal: float, tariff: float, cap_std: float, frac: float = 1.0) -> float:
    """A tier world: the bridge on FY2025 volumes with the associate fit."""
    return bridge_eps(inp, coal, tariff, cap_std, inp["sales_fy25"], inp["gen_fy25"],
                      assoc_fit(inp, tariff, coal), frac)


def midcycle_readings(inp: dict[str, float], coal_m: float, cap_std: float, eps_squeeze: float) -> dict[str, float]:
    """The five cross-cycle readings whose mean is E_M (A / B x2 / C x2)."""
    uplift = cap_uplift_yi(inp, cap_std) * (1.0 - inp["tax_op"]) * inp["par_op"] / (inp["shares"] / YI)
    fat = ((inp["eps_fy24"] + uplift) + (inp["eps_fy25"] + uplift)) / 2.0
    realised = [inp["eps_fy22"], inp["eps_fy23"], inp["eps_fy24"], inp["eps_fy25"]]
    return {
        "A 一个滞后波（肥年 FY24/25 归一到 165 + 挤压年 2026E，等权）": (fat + eps_squeeze) / 2.0,
        "B 桥稳态 煤 830 + 电价追平 437 + 容量 165": world_eps(inp, coal_m, inp["tariff_m"], cap_std),
        "B' 桥稳态 电价 430（2026 隐含）": world_eps(inp, coal_m, inp["tariff_fy26_impl"], cap_std),
        "C 改革后实测均值 FY2022–25": statistics.mean(realised),
        "C' 同上含 2026E": (sum(realised) + eps_squeeze) / 5.0,
    }


def ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """(intercept, slope) least squares."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return my - slope * mx, slope


def solve3(rows: list[tuple[float, float, float]], rhs: list[float]) -> tuple[float, float, float]:
    """Cramer's rule for the 3x3 associate fit (a + b x tariff + c x coal)."""
    def det(m: list[tuple[float, float, float]]) -> float:
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    d = det(rows)
    cols = []
    for j in range(3):
        m = [tuple(rhs[i] if k == j else rows[i][k] for k in range(3)) for i in range(3)]
        cols.append(det(m) / d)
    return cols[0], cols[1], cols[2]


def axis_uf_tiers(ticker: str = "000543.SZ") -> tuple[float, float, float]:
    """The mount's own coordinate rungs the axis §4a table states for it
    (`**0.2292 / 0.2537 / 0.2799**`), to be matched within +-0.0005."""
    for line in AXIS_COAL.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"| **`{ticker}`**"):
            m = re.search(r"\*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*", line)
            if m:
                return float(m.group(1)), float(m.group(2)), float(m.group(3))
    raise ValueError(f"axis §4a row for {ticker} not found")


def anchors_of(inp: dict[str, float], eps_l: float, eps_m: float, eps_h: float) -> tuple[float, float, float]:
    """L = max(scenario, PB floor) (A2e-1 floor allowed, both reported); M/H flat at pe_m."""
    floor = inp["pb_lo"] * inp["bps"]
    return max(eps_l * inp["pe_m"], floor), eps_m * inp["pe_m"], eps_h * inp["pe_m"]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errors += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    if errors:
        return report(errors, "FAIL (basket)")
    r = inp["r_perp"]
    shares_yi = inp["shares"] / YI
    eps = {t: inp[f"eps_{t}"] for t in TIERS}
    print(f"formula_id={FORMULA_ID}")

    # --- Step 1: axis mount (generator side) and the numerator ladder --------
    errors += check_coal_mount((inp["coal_l"], inp["coal_m"], inp["coal_h"]), "generator")
    series = load_coal_series()
    for year, want in series.items():
        got = inp.get(f"coal_fy{year}")
        if got is None or abs(got - want) > 0.5:
            errors.append(f"coal_fy{year}: stated {got} vs axis base series {want:g} (axis 4c-2)")
    uf_axis = axis_uf_tiers()
    uf_own = tuple(uf(inp, inp[f"coal_{t}"]) for t in ("h", "m", "l"))  # axis order 703 / 830 / 965
    for tier, got, want in zip(("703", "830", "965"), uf_own, uf_axis):
        if abs(got - want) > 0.0005:
            errors.append(f"uf({tier}) {got:.4f} vs axis §4a {want:.4f} (axis 4c-2, ±0.0005)")
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    if not (inp["coal_l"] > inp["coal_m"] > inp["coal_h"]):
        errors.append("coal ladder must fall as earnings rise (generator reads the axis mirrored)")
    if errors:
        return report(errors, "FAIL (axis mount / ladders)")
    print(f"轴挂载 ✓ 电厂侧 coal L/M/H = {inp['coal_l']:g}/{inp['coal_m']:g}/{inp['coal_h']:g} (= 轴 H/M/L); "
          f"基准序列 FY2019–25 {'/'.join(f'{series[y]:g}' for y in sorted(series))} ✓; "
          f"uf 轴线 {inp['uf_a']} + {inp['uf_b']:.2e}·x → 703/830/965 = {'/'.join(f'{u:.4f}' for u in uf_own)} 对轴 §4a ✓")

    # --- Step 2: the bridge must reproduce the realised years (axis 4c-1) ----
    years = {
        "FY2023": (inp["coal_fy2023"], inp["tariff_fy23"], inp["sales_fy23"], inp["gen_fy23"], inp["assoc_fy23"], inp["eps_fy23"]),
        "FY2024": (inp["coal_fy2024"], inp["tariff_fy24"], inp["sales_fy24"], inp["gen_fy24"], inp["assoc_fy24"], inp["eps_fy24"]),
        "FY2025": (inp["coal_fy2025"], inp["tariff_fy25"], inp["sales_fy25"], inp["gen_fy25"], inp["assoc_fy25"], inp["eps_fy25"]),
    }
    print(f"桥复现（轴 4c-1，档位桥口径：该年煤价 / 电价 / 电量 / 联营 + 中枢结构参数；容量按 FY2025 标准 {inp['cap_tariff_2025']:g}）：")
    passed = 0
    for name, (coal, tariff, sales, gen, assoc_yi, actual) in years.items():
        e = bridge_eps(inp, coal, tariff, inp["cap_tariff_2025"], sales, gen, assoc_yi)
        err = e / actual - 1.0
        ok = abs(err) <= BRIDGE_TOL
        passed += ok
        print(f"  {name} 煤 {coal:g} 电价 {tariff} 上网 {sales} 发电 {gen} 联营 {assoc_yi}: 桥 {e:.4f} vs 实 {actual} 误差 {err:+.1%} {'✓' if ok else '✗'}")
        if not ok:
            errors.append(f"bridge {name}: {e:.4f} vs {actual} ({err:+.1%}) outside ±{BRIDGE_TOL:.0%} — 桥错, BLOCKED (axis 4c-1)")
    if passed < 2:
        errors.append(f"bridge reproduces only {passed} realised year(s); axis 4c-1 needs >= 2")
    # The associate fit is the exact solution through the three realised points.
    a, b, c = solve3([(1.0, y[1], y[0]) for y in years.values()], [y[4] for y in years.values()])
    if abs(a - inp["assoc_a"]) > 0.05 or abs(b - inp["assoc_b"]) > 0.0005 or abs(c - inp["assoc_c"]) > 0.0005:
        errors.append(f"assoc fit re-solved {a:.2f} / {b:.4f} / {c:.4f} vs stated {inp['assoc_a']} / {inp['assoc_b']} / {inp['assoc_c']}")
    print(f"  联营 J = {a:.2f} + {b:.4f}·电价 + {c:.4f}·煤价（FY2023–25 三点精确解）✓")
    # Tariff second layer: lag-linkage fit (coal_{t-1} -> tariff_t) and the cap.
    pairs = [(inp["coal_fy2021"], inp["tariff_fy22"]), (inp["coal_fy2022"], inp["tariff_fy23"]),
             (inp["coal_fy2023"], inp["tariff_fy24"]), (inp["coal_fy2024"], inp["tariff_fy25"]),
             (inp["coal_fy2025"], inp["tariff_fy26_impl"])]
    t0, t1 = ols([p[0] for p in pairs], [p[1] for p in pairs])
    tariff_m_fit = t0 + t1 * inp["coal_m"]
    if abs(inp["tariff_m"] - tariff_m_fit) > 1.0:
        errors.append(f"tariff_m {inp['tariff_m']} vs lag fit at coal {inp['coal_m']:g}: {tariff_m_fit:.1f}")
    # H tariff = the 2027 contract signed on 2026's coal: the post-spike slope
    # (FY2024-26 pairs, no capped year) applied from the FY2026 base.
    _, t1_3 = ols([p[0] for p in pairs[2:]], [p[1] for p in pairs[2:]])
    tariff_h_lag = inp["tariff_fy26_impl"] + t1_3 * (inp["coal_fy2026e"] - inp["coal_fy2025"])
    tariff_mean_post = statistics.mean([inp["tariff_fy23"], inp["tariff_fy24"], inp["tariff_fy25"], inp["tariff_fy26_impl"]])
    if abs(inp["tariff_h"] - tariff_h_lag) > 1.0:
        errors.append(f"tariff_h {inp['tariff_h']} vs 2027-on-2026-coal lag {tariff_h_lag:.1f}")
    if abs(inp["tariff_cap"] - 1.2 * inp["tariff_bench"]) > 0.5:
        errors.append(f"tariff_cap {inp['tariff_cap']} != 1.2 x benchmark {inp['tariff_bench']}")
    print(f"  电价滞后联动：tariff_t = {t0:.1f} + {t1:.4f}·coal_(t−1)（五对 FY2022–26，含两个顶格年 ≤ cap {inp['tariff_cap']:g} = 1.2 × 基准 {inp['tariff_bench']}）→ 830 处 {tariff_m_fit:.1f} = tariff_m {inp['tariff_m']:g} ✓; "
          f"2027 对 2026 年均煤 {inp['coal_fy2026e']:g} 上签 = {inp['tariff_fy26_impl']:g} + 三对（FY2024–26）斜率 {t1_3:.4f} × {inp['coal_fy2026e'] - inp['coal_fy2025']:g} = {tariff_h_lag:.1f} = tariff_h {inp['tariff_h']:g} ✓（FY2023–26 四年均值 {tariff_mean_post:.1f} 互证；含顶格年的 FY2022–25 均值 {statistics.mean([inp['tariff_fy22'], inp['tariff_fy23'], inp['tariff_fy24'], inp['tariff_fy25']]):.1f} 只作上沿参照）")
    # Per-unit sensitivities of the bridge at the mid-cycle world.
    base = world_eps(inp, inp["coal_m"], inp["tariff_fy25"], inp["cap_tariff_2025"])
    k_tariff = world_eps(inp, inp["coal_m"], inp["tariff_fy25"] + 1.0, inp["cap_tariff_2025"]) - base
    k_coal10 = world_eps(inp, inp["coal_m"] + 10.0, inp["tariff_fy25"], inp["cap_tariff_2025"]) - base
    if abs(k_tariff - inp["k_tariff"]) > 0.0005:
        errors.append(f"k_tariff {inp['k_tariff']} vs bridge {k_tariff:.4f} per 元/MWh")
    uplift_eps = cap_uplift_yi(inp, inp["cap_tariff_2026"]) * (1.0 - inp["tax_op"]) * inp["par_op"] / shares_yi
    if abs(uplift_eps - inp["eps_cap_uplift"]) > EPS_TOL:
        errors.append(f"eps_cap_uplift {inp['eps_cap_uplift']} vs ({inp['cap_tariff_2026']:g}−{inp['cap_tariff_2025']:g}) × {inp['cap_gw_coal']:g} GW → {uplift_eps:.4f}")
    print(f"  桥敏感度（煤 830 / 电价 424.8 / 容量 100 处，E = {base:.4f}）：电价 +10 元/MWh {10 * k_tariff:+.4f}（含联营）、煤 +10 元/吨 {k_coal10:+.4f}；"
          f"容量电价 {inp['cap_tariff_2025']:g}→{inp['cap_tariff_2026']:g} 元/kW·年 × {inp['cap_gw_coal']:g} GW = {cap_uplift_yi(inp, inp['cap_tariff_2026']):.2f} 亿税前 → EPS {uplift_eps:+.4f}（每档都带）")
    if errors:
        return report(errors, "FAIL (bridge)")

    # --- Step 3: tier numerators from the lag wave -----------------------------
    h2 = world_eps(inp, inp["coal_h2_26"], inp["tariff_fy25"], inp["cap_tariff_2026"], frac=0.5)
    squeeze = inp["eps_h1_26"] + h2
    if abs(h2 - inp["eps_h2_26_bridge"]) > EPS_TOL:
        errors.append(f"eps_h2_26_bridge {inp['eps_h2_26_bridge']} vs bridge H2 {h2:.4f}")
    if abs(squeeze - eps["l"]) > EPS_TOL:
        errors.append(f"eps_l {eps['l']} vs 2026E squeeze {inp['eps_h1_26']} + {h2:.4f} = {squeeze:.4f}")
    e_h = world_eps(inp, inp["coal_m"], inp["tariff_h"], inp["cap_tariff_2026"])
    if abs(e_h - eps["h"]) > 0.01:
        errors.append(f"eps_h {eps['h']} vs bridge at coal {inp['coal_m']:g} / tariff {inp['tariff_h']:g} / cap {inp['cap_tariff_2026']:g}: {e_h:.4f}")
    reads = midcycle_readings(inp, inp["coal_m"], inp["cap_tariff_2026"], squeeze)
    e_m = statistics.mean(reads.values())
    lo, hi = min(reads.values()), max(reads.values())
    if abs(e_m - eps["m"]) > EPS_TOL:
        errors.append(f"eps_m {eps['m']} vs mean of the five readings {e_m:.4f}")
    if abs(lo - inp["eps_m_lo"]) > EPS_TOL or abs(hi - inp["eps_m_hi"]) > EPS_TOL:
        errors.append(f"evidence interval [{inp['eps_m_lo']}, {inp['eps_m_hi']}] vs readings [{lo:.4f}, {hi:.4f}]")
    if not (inp["eps_m_lo"] <= eps["m"] <= inp["eps_m_hi"]):
        errors.append(f"eps_m {eps['m']} outside [{inp['eps_m_lo']}, {inp['eps_m_hi']}]")
    print(f"L 挤压年 2026E：H1 实测 {inp['eps_h1_26']} + H2 桥（煤 {inp['coal_h2_26']:g} / 电价 {inp['tariff_fy25']} / 容量 {inp['cap_tariff_2026']:g}，半年）{h2:.4f} = {squeeze:.4f} → eps_l {eps['l']} ✓"
          f"（Q3 单季桥 ≈ {world_eps(inp, inp['coal_h2_26'], inp['tariff_fy25'], inp['cap_tariff_2026'], frac=0.25):.3f}；电价 {inp['tariff_fy26_impl']:g} → H2 {world_eps(inp, inp['coal_h2_26'], inp['tariff_fy26_impl'], inp['cap_tariff_2026'], frac=0.5):.4f}）")
    print("M 中枢 = 五个跨周期读数的均值：")
    for k, v in reads.items():
        print(f"  {v:.4f}  {k}")
    print(f"  mean {e_m:.4f} → eps_m {eps['m']} ✓; 证据区间 [{lo:.4f}, {hi:.4f}] → [{inp['eps_m_lo']}, {inp['eps_m_hi']}] ✓")
    print(f"H 肥年世界：桥（煤 {inp['coal_m']:g} / 电价 {inp['tariff_h']:g} / 容量 {inp['cap_tariff_2026']:g}）= {e_h:.4f} → eps_h {eps['h']} ✓")
    print(f"周期位置（轴 4c-4）：当期 ÷ 中枢 — TTM {inp['eps_ttm'] / eps['m']:.2f} · FY2025 {inp['eps_fy25'] / eps['m']:.2f} · FY26E {inp['eps_fy26e'] / eps['m']:.2f} · 2026E {squeeze / eps['m']:.2f}；"
          f"煤价：2026H1 772 / YTD ~796 = L–M 之间，现货 962–989 = 轴 H 状态 = 本票 L 世界")
    if errors:
        return report(errors, "FAIL (numerators)")

    # --- Step 4: the multiple — flat 1/r; Gordon and DDM are crosses ---------
    roe_m = eps["m"] * inp["shares"] / (inp["equity"] * YI)
    payout_fy25 = inp["dps_fy25"] * inp["shares"] / (inp["ni_fy25"] * YI)
    g_policy = (1.0 - payout_fy25) * roe_m
    errors += check_g_cap(inp["g2"], r, "g2")
    if abs(inp["g2"]) > 1e-9:
        errors.append(f"g2 {inp['g2']} != 0 — the main ruler is flat 1/r (growth capex NPV ~ 0, A17)")
    if abs(inp["pe_m"] - 1.0 / (r - inp["g2"])) > 1e-9:
        errors.append(f"pe_m {inp['pe_m']} != 1/(r − g2) {1 / (r - inp['g2']):.2f} — the main ruler is flat E/r")
    if abs(payout_fy25 - inp["payout_fy25"]) > 0.005:
        errors.append(f"payout_fy25 {inp['payout_fy25']} vs DPS x shares / NI = {payout_fy25:.4f}")
    if abs(g_policy - inp["g2_policy"]) > 0.0005:
        errors.append(f"g2_policy {inp['g2_policy']} vs (1 − {payout_fy25:.3f}) × ROE_M {roe_m:.4f} = {g_policy:.4f}")
    errors += check_g_cap(inp["g2_policy"], r, "g2_policy")
    errors += check_branch(inp["g2_policy"], roe_m, r, payout_fy25, "g2_policy")
    pe_gordon = perpetual_pe(inp["g2_policy"], roe_m, r)
    if abs(capped_payout_pe(g_policy, roe_m, r, payout_fy25) - perpetual_pe(g_policy, roe_m, r)) > 1e-9:
        errors.append("capped_payout_pe != perpetual_pe — policy g crossed the cap, the dividend ruler would apply")
    d_m = payout_fy25 * eps["m"]
    ddm_m = d_m * (1.0 + inp["g2_policy"]) / (r - inp["g2_policy"])
    modelled, gap = payout_gap(inp["g2_policy"], roe_m, payout_fy25)
    regime = "病态区" if abs(roe_m - r) < 0.03 else ("峰形区" if roe_m < r else "单调区")
    print(f"倍数：主尺 flat {inp['pe_m']:g}× = 1/r，r = {r:.1%} 篮 {baskets['r_perp']} {BASKET_R[baskets['r_perp']][0]}，g2 = {inp['g2']:g}（增长 capex NPV ≈ 0，留存不加不减）；ROE_M = {eps['m']} × {shares_yi:.2f} ÷ {inp['equity']} = {roe_m:.2%}（|ROE − r| = {abs(roe_m - r):.2%} → {regime}）")
    print(f"  交叉 Gordon：派息率 {payout_fy25:.1%}（DPS {inp['dps_fy25']} × 股本 ÷ 归母 {inp['ni_fy25']} 亿）→ 政策 g = {g_policy:.2%} < cap {g_cap(r):.0%}（capped_payout_pe ≡ perpetual_pe ✓）→ {pe_gordon:.2f}× → M {eps['m'] * pe_gordon:.2f}；"
          f"check_branch ✓ 模型派息率 {modelled:.1%} vs 实付 {payout_fy25:.1%}（差 {gap:+.1%}）")
    print(f"  交叉 DDM：D_M = {payout_fy25:.3f} × {eps['m']} = {d_m:.3f} × (1+g) ÷ (r−g) = {ddm_m:.2f}；病态区 g∈[0,6%] 的 Gordon 只从 {perpetual_pe(0.0, roe_m, r):.2f}× 走到 {perpetual_pe(g_cap(r), roe_m, r):.2f}×——两把交叉尺都贴 10×，倍数由 r 钉死，结论建立在中枢分子上")
    if errors:
        return report(errors, "FAIL (multiple)")

    # --- Step 5: anchors, floor, interval re-pricing -------------------------
    floor = inp["pb_lo"] * inp["bps"]
    scenario_l = eps["l"] * inp["pe_m"]
    if abs(floor - inp["floor_l"]) > 0.01 or abs(scenario_l - inp["scenario_l"]) > 0.05:
        errors.append(f"floor {floor:.2f} / scenario_L {scenario_l:.2f} vs stated {inp['floor_l']} / {inp['scenario_l']}")
    L, M, H = anchors_of(inp, eps["l"], eps["m"], eps["h"])
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}")
        return report(errors, "FAIL (ladder)")
    if scenario_l / M <= FLOOR_RECHECK_RATIO:
        errors.append(f"scenario_L/M = {scenario_l / M:.3f} <= {FLOOR_RECHECK_RATIO} — earnings ruler failed at L, A2e-1 回问")
    A, B = cut_points(L, M, H)
    winner = "地板胜出" if floor > scenario_l else "情景胜出"
    print(f"地板（A2e-1）：scenario_L = {eps['l']} × {inp['pe_m']:g} = {scenario_l:.2f} vs PB 地板 {inp['pb_lo']} × BPS {inp['bps']} = {floor:.2f} → {winner}，L = {L:.2f}；scenario_L/M = {scenario_l / M:.2f} > {FLOOR_RECHECK_RATIO} ✓（不触发回问）")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    # The E_M evidence interval and the axis M window (axis 4c-5), re-priced
    # and printed (disclosure — the doc states no zone to hold them to).
    for tag, em in (("eps_m_lo", inp["eps_m_lo"]), ("eps_m_hi", inp["eps_m_hi"])):
        b = anchors_of(inp, eps["l"], em, eps["h"])
        a_, b_ = cut_points(*b)
        print(f"  区间 E_M = {em}（{tag}）: {'/'.join(f'{x:.2f}' for x in b)} A={a_:.2f} B={b_:.2f}")
    for cm in (inp["coal_m_lo"], inp["coal_m_hi"]):
        em = statistics.mean(midcycle_readings(inp, cm, inp["cap_tariff_2026"], squeeze).values())
        eh = world_eps(inp, cm, inp["tariff_h"], inp["cap_tariff_2026"])
        b = anchors_of(inp, eps["l"], em, eh)
        a_, b_ = cut_points(*b)
        print(f"  区间 轴 M 窗口 煤 {cm:g}: E_M {em:.4f} E_H {eh:.4f} → {'/'.join(f'{x:.2f}' for x in b)} A={a_:.2f} B={b_:.2f}")
    # Sensitivities (printed, not asserted): tariff, capacity, TTM as numerator.
    for t in (inp["tariff_fy26_impl"], inp["tariff_m"], inp["tariff_h"]):
        em = world_eps(inp, inp["coal_m"], t, inp["cap_tariff_2026"])
        m_t = em * inp["pe_m"]
        print(f"  敏感性 中枢单取桥稳态 电价 {t:g}: E_M {em:.4f} → M {m_t:.2f}（H {H:.2f} 不动）"
              + (" M=H 塌" if m_t >= H - 1e-9 else ""))
    sq100 = inp["eps_h1_26"] + world_eps(inp, inp["coal_h2_26"], inp["tariff_fy25"], inp["cap_tariff_2025"], frac=0.5)
    em100 = statistics.mean(midcycle_readings(inp, inp["coal_m"], inp["cap_tariff_2025"], sq100).values())
    eh100 = world_eps(inp, inp["coal_m"], inp["tariff_h"], inp["cap_tariff_2025"])
    b100 = anchors_of(inp, sq100, em100, eh100)
    print(f"  敏感性 容量电价停在 {inp['cap_tariff_2025']:g}（政策已锁 165，仅对照）: E {sq100:.4f}/{em100:.4f}/{eh100:.4f} → {'/'.join(f'{x:.2f}' for x in b100)}")
    m_ttm = inp["eps_ttm"] * inp["pe_m"]
    print(f"  敏感性 TTM {inp['eps_ttm']} 作分子（v3 口径, flat 10×）: M {m_ttm:.2f}（TTM ÷ 中枢 {inp['eps_ttm'] / eps['m']:.2f}，且 FY2026 滚动到 ~{squeeze:.2f}）")
    # Basket-r disclosures (printed, not asserted): g2 ±1pp, r ±50bp and the
    # alternative baskets the framework rejected (A17).
    for tag, rr, gg in (("g2 +1pp", r, 0.01), ("g2 −1pp", r, -0.01), ("r −50bp", r - 0.005, 0.0), ("r +50bp", r + 0.005, 0.0),
                        ("篮 2 7.5%", 0.075, 0.0), ("篮 6 13%", 0.13, 0.0)):
        pe_x = 1.0 / (rr - gg)
        b = (max(eps["l"] * pe_x, floor), eps["m"] * pe_x, eps["h"] * pe_x)
        print(f"  敏感区 {tag}: PE {pe_x:.2f}× → {'/'.join(f'{x:.2f}' for x in b)}")
    flat_errs, flat = flat_multiple_ladder((eps["l"], eps["m"], eps["h"]), inp["pe_m"])
    errors += flat_errs
    print(f"flat-multiple @{inp['pe_m']:g}×: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}（L 地板前 {scenario_l:.2f}）— 带宽 {(flat[2] - flat[0]) / (2 * flat[1]):.0%}")
    if errors:
        return report(errors, "FAIL (flat ladder)")

    # --- Step 6: 纠正对账门 (valuation-rules 2026-09-15) ---------------------
    g_zjn = (inp["peer_zjn_px"] * r - inp["peer_zjn_dps"]) / (inp["peer_zjn_px"] + inp["peer_zjn_dps"])
    g_hd = (inp["peer_hd_px"] * r - inp["peer_hd_dps"]) / (inp["peer_hd_px"] + inp["peer_hd_dps"])
    g_peer = statistics.median([g_zjn, g_hd])
    peer_d0 = inp["dps_fy25"] * (1.0 + g_peer) / (r - g_peer)
    peer_dm = d_m * (1.0 + g_peer) / (r - g_peer)
    rows = [
        ("① 上一版 M（v3，TTM 作中枢）", M_V3_TTM, True),
        ("①' v4 M（冻结电价的桥，已废，只报不计）", M_V4_FROZEN, False),
        ("② E_M / r", eps["m"] / r, True),
        (f"③ 股息尺 D_M {d_m:.3f} × (1+g) ÷ (r−g)，g = 政策 {inp['g2_policy']:.2%}", ddm_m, True),
        (f"④ 同等盈利月份实付价中位（可见 TTM ∈ 中枢 ±12%，n = {inp['pe_same_n']:g}，价 {inp['px_same_lo']}–{inp['px_same_hi']}，PE 中位 {inp['pe_same_med']}×）", inp["px_same_med"], True),
        (f"⑤ 同业同尺同日：浙能 / 华电 D0 尺反解 g_d {g_zjn:.2%} / {g_hd:.2%} 中位 {g_peer:.2%} → 皖能 D0 {inp['dps_fy25']}", peer_d0, True),
        (f"⑤' 同上配中枢股息 D_M {d_m:.3f}（跨口径：同业 g_d 从当期股息反解，只报不计）", peer_dm, False),
    ]
    print(f"纠正对账门：新 M {M:.2f} vs v3 {M_V3_TTM}（{M / M_V3_TTM - 1:+.0%}）· v4 {M_V4_FROZEN}（{M / M_V4_FROZEN - 1:+.0%}）")
    outside = counted = 0
    for label, v, counts in rows:
        dev = M / v - 1.0
        print(f"  {label:<96} {v:6.2f}  M/坐标 {M / v:5.2f} ({dev:+.0%}) {'外' if abs(dev) > RECON_TOL else '内'}{'' if counts else '  [不计]'}")
        if counts:
            counted += 1
            outside += abs(dev) > RECON_TOL
    m_pb = M / inp["bps"]
    print(f"  ⑥ 资产口径（单边）：M ÷ BPS = {m_pb:.2f}× vs 自身实测 PB 低沿 {inp['pb_lo']} → {'内（M 在市场印过的 PB 之上）' if m_pb >= inp['pb_lo'] else '外'}")
    if m_pb < inp["pb_lo"]:
        errors.append(f"M/BPS {m_pb:.2f} below the own PB low {inp['pb_lo']} — 尺错 signal")
    if outside == counted:
        errors.append(f"new M outside every reconciliation coordinate by >{RECON_TOL:.0%} — BLOCKED")
    if abs(inp["pe_same_med"] - inp["pe_m"]) / inp["pe_m"] > RECON_TOL:
        errors.append(f"pe_same_med {inp['pe_same_med']} vs pe_m {inp['pe_m']}: the market paid a different multiple on ≈ mid-cycle earnings")
    band = {"中枢": eps["m"], "TTM": inp["eps_ttm"], "FY26E": inp["eps_fy26e"]}
    print(f"  对账门 {'通过' if outside < counted else '不过'}：{counted - outside}/{counted} 个独立坐标在 ±{RECON_TOL:.0%} 内；"
          f"中性带 [{A:.2f}, {B:.2f}) = " + " · ".join(f"{k} {A / v:.1f}–{B / v:.1f}×" for k, v in band.items()))
    if B / inp["eps_ttm"] <= 7.0:
        errors.append(f"neutral band tops out at {B / inp['eps_ttm']:.1f}× TTM on a 40%-payout utility — 荒诞信号 (valuation-rules「纠正对账门」)")
    if errors:
        return report(errors, "FAIL (对账门)")

    # --- Step 7: coordinates outside the band and the stated outputs ----------
    d = decompose((L, M, H), (inp["pe_m"],) * 3)
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.1%} | 分子比 L/M={eps['l'] / eps['m']:.3f}（地板前）/ H/M={d['num_hm']:.3f} | 倍数比 1.000 / 1.000（flat）")
    print(f"坐标 · own-year PE 实测点：FY2022 尖峰年 {inp['pe_ownyear_l']}× → 年均价 {inp['eps_fy22'] * inp['pe_ownyear_l']:.2f}（旧 regime，deep_discount 内）· 四年中位 {inp['pe_ownyear_m']}× · FY2025 肥年 {inp['pe_ownyear_h']}× → 年均价 {inp['eps_fy25'] * inp['pe_ownyear_h']:.2f}（neutral 内）；"
          f"5 年月频 TTM PE 带 [{inp['pe_own_min']}, {inp['pe_own_max']}] 含 {inp['pe_m']:g}× ✓")
    perm = world_eps(inp, inp["coal_m"], inp["tariff_fy25"], inp["cap_tariff_2025"])
    spike_new = inp["eps_fy22"] + inp["cap_tariff_2026"] * inp["cap_gw_coal"] * 1e-2 * (1.0 - inp["tax_op"]) * inp["par_op"] / shares_yi
    print(f"坐标 · deep_discount（< {L:.2f}）：挤压永续化（电价不再联动 + 容量剔除，煤 830 / 电价 {inp['tariff_fy25']} / 容量 {inp['cap_tariff_2025']:g}）{perm:.4f} → {perm * inp['pe_m']:.2f}；"
          f"谷底 × 1/r = {inp['eps_fy22'] / r:.2f}；2022 式尖峰在新 regime（FY2022 {inp['eps_fy22']} + 165 容量全额 {spike_new - inp['eps_fy22']:.2f}）= {spike_new:.2f} → {spike_new * inp['pe_m']:.2f}（仍在 L 之上）")
    bull = world_eps(inp, inp["coal_h"], inp["tariff_h"], inp["cap_tariff_2026"])
    print(f"坐标 · stretched（> {H:.2f}）：牛顶世界 煤 {inp['coal_h']:g} + 电价 {inp['tariff_h']:g} + 容量 165 = {bull:.4f} → {bull * inp['pe_m']:.2f}；FY2025 式肥年 + 165 = {inp['eps_fy25'] + uplift_eps:.4f} → {(inp['eps_fy25'] + uplift_eps) * inp['pe_m']:.2f}；"
          f"股息率 @L {inp['dps_fy25'] / L:.2%}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
