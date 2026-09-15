#!/usr/bin/env python3
"""0857.HK (PetroChina) valuation eval.

frameworks/0857.HK.md is the source of truth; this script re-derives
L/M/H / A/B / zone from its §3 Inputs table and exits 1 on mismatch.

formula_id: petrochina_hk_brent_axis_ep_beta_gordon_v1

Main ruler: whole-company PE on the H share, numerator FY2027 (the furthest
year with >= 2 houses and a range).  The numerator is NOT the consensus three
points: it is the shared Brent axis (_AXIS.brent-oil.md, 68 / 75 / 85) pushed
through the company's OWN measured E&P elasticity,

    beta = [(E&P OP 2026H1 x 2 - E&P OP FY2025) / (realised 2026H1 - realised FY2025)]
           x (1 - CIT) x (realised / Brent, FY2025)              = 3,680 RMB mn per US$1
    NI_x = NI_FY2025 + beta x (Brent_x - 68.2)

with the three downstream segments frozen at FY2025 (A5).  裁决顺序 ②-b is
checked mechanically: the FY2027 consensus mean must not exceed EPS_H, and if
it sits below EPS_M the framework has to carry the named-variable row (A6:
the consensus still embeds the pre-2026-09-08 Brent decks).

The multiple is GENERATED (valuation-rules「永续增长口径」):

    PE_x = (1 - g2_x / ROE_x) / (r - g2_x),   r = 10%

PetroChina pays out 54.7% and grows DPS, so it sits on the RETENTION branch.
Its M-tier ROE (11.1%) is within 3pp of r -- the pathological regime where a
reverse-solved g is not a reading -- so g2 comes from the payout policy
itself: (1 - payout) x ROE_M = +5.045%, shared by L and M.  The H tier at ROE
13.4% would generate 12.57x, above the realised 5y monthly TTM band top
12.29; rule ③ replaces that g with the band-edge reverse-solve at ROE_H
(+4.755%, "自身实测带反解"), which also gives the cyclical reverse shape
g_L >= g_M >= g_H.  The US-major cluster (XOM / CVX / COP, median 4.47%) is a
different regime (monotonic) and is printed as a cross-check only.

g's leverage is disclosed: the band is re-run at both ends of the g2
evidence interval and the zone must not move.

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.axes import AXIS_BRENT  # noqa: E402
from lib.gordon import (  # noqa: E402
    G_CAP, check_branch, check_g_cap, check_r, implied_g_retaining, payout, payout_gap,
    perpetual_pe, recovery_two_stage_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report,
)
from lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from lib.zones import cut_points, zone_of  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
FRAMEWORK = REPO / "frameworks" / "0857.HK.md"
FORMULA_ID = "petrochina_hk_brent_axis_ep_beta_gordon_v1"
TICKER = "0857.HK"

TIERS = ("l", "m", "h")
MN = 1e6                    # Inputs money fields are RMB million
G_TOL = 5e-5
MIN_R_MINUS_G = 0.02
CONS_DEV_MAX = 0.20         # ②-b: M within 20% of the consensus mean
NG_SECONDARY_GATE = 0.30    # A4: a segment >= 30% of segment OP would reopen the secondary-class question
SOG_RETENTION = 0.525       # (1 - SOG 30%) x (1 - CIT 25%) for the theoretical beta cross-check
USDCNY_CROSS = 7.0

REQUIRED = [
    "price", "price_a", "shares", "equity", "fx_hkdcny",
    "ni_fy25", "eps_fy25", "div_fy25", "dps_fy25",
    "brent_2025", "brent_l", "brent_m", "brent_h",
    "ep_op_fy25", "ep_op_h1_26", "real_2025", "real_h1_26", "cit", "crude_fy25",
    "r_perp", "g2_l", "g2_m", "g2_h", "g_evid_min", "g_evid_max", "g_peer_us",
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


def band_at(g_m: float, g_h_edge: float, eps: dict[str, float], roe: dict[str, float],
            r: float, fx: float) -> tuple[float, float, float]:
    """L/M/H in HKD for one shared g_M; H keeps its band-edge g unless g_M is lower (shape g_H <= g_M)."""
    g = {"l": g_m, "m": g_m, "h": min(g_h_edge, g_m)}
    return tuple(eps[t] * perpetual_pe(g[t], roe[t], r) / fx for t in TIERS)  # type: ignore[return-value]


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
    eps = {t: ni[t] * MN / inp["shares"] for t in TIERS}
    roe = {t: ni[t] / inp["equity"] for t in TIERS}
    errors += ladder("eps", eps["l"], eps["m"], eps["h"])
    if errors:
        return report(errors, "FAIL (axis / numerators)")

    # --- Step 2: g2 on the retention branch (A7), guardrail + H band-edge (A8) --
    payout_fy25 = inp["div_fy25"] / inp["ni_fy25"]
    g2_derived = min((1.0 - payout_fy25) * roe["m"], G_CAP)
    errors += check_r(r, "r_perp")
    for t in TIERS:
        errors += check_g_cap(inp[f"g2_{t}"], f"g2_{t}")
        if r - inp[f"g2_{t}"] < MIN_R_MINUS_G:
            errors.append(f"g2_{t} {inp[f'g2_{t}']:+.4f}: r-g < {MIN_R_MINUS_G} (裁决顺序 ①)")
    if abs(inp["g2_l"] - inp["g2_m"]) > G_TOL:
        errors.append(f"g2_l {inp['g2_l']} != g2_m {inp['g2_m']} (A3: axis L is a regime, carries the M g)")
    if inp["g2_m"] <= 0:
        errors.append(f"g2_m {inp['g2_m']:+.4f} <= 0 is the full-payout branch — PetroChina pays out {payout_fy25:.0%} (A7)")
    if abs(inp["g2_m"] - g2_derived) > G_TOL:
        errors.append(f"g2_m {inp['g2_m']} vs (1 - payout {payout_fy25:.4f}) x ROE_M {roe['m']:.4f} = {g2_derived:.5f} (A7)")
    errors += check_branch(inp["g2_m"], roe["m"], r, payout_fy25, "g2_m")
    if not (inp["g_evid_min"] - 1e-9 <= inp["g2_m"] <= inp["g_evid_max"] + 1e-9):
        errors.append(f"g2_m {inp['g2_m']} outside evidence interval [{inp['g_evid_min']}, {inp['g_evid_max']}] (A9)")
    if errors:
        return report(errors, "FAIL (growth 口径)")

    pe_h_raw = perpetual_pe(inp["g2_m"], roe["h"], r)
    if pe_h_raw > inp["pe_own_max"] + 1e-9:
        g_h_edge, ok_h = implied_g_retaining(inp["pe_own_max"], roe["h"], r)
        if not ok_h or not (0.0 <= g_h_edge <= min(G_CAP, inp["g2_m"])):
            errors.append(f"H band-edge reverse solve g {g_h_edge:+.4%} (conditioned={ok_h}) not usable — BLOCKED (裁决顺序 ③)")
        if abs(inp["g2_h"] - g_h_edge) > G_TOL:
            errors.append(f"g2_h {inp['g2_h']} != band-edge reverse solve {g_h_edge:.5f} at ROE_H {roe['h']:.2%} (A8)")
        h_note = f"H: g2_m {inp['g2_m']:+.3%} -> {pe_h_raw:.2f}x > band top {inp['pe_own_max']} -> band-edge g_H {g_h_edge:+.4%} (自身实测带反解)"
    else:
        g_h_edge = inp["g2_m"]
        if abs(inp["g2_h"] - inp["g2_m"]) > G_TOL:
            errors.append(f"g2_h {inp['g2_h']} must equal g2_m when H sits inside the band (A8)")
        h_note = f"H inside band at g2_m ({pe_h_raw:.2f}x)"
    if not (inp["g2_l"] >= inp["g2_m"] >= inp["g2_h"] - 1e-12):
        errors.append(f"g tiers not reversed/flat: {inp['g2_l']}/{inp['g2_m']}/{inp['g2_h']} (cyclical, 裁决顺序 ⑤)")
    pe = {t: perpetual_pe(inp[f"g2_{t}"], roe[t], r) for t in TIERS}
    for t in TIERS:
        if not (inp["pe_own_min"] - 1e-9 <= pe[t] <= inp["pe_own_max"] + 1e-9):
            errors.append(f"guardrail: generated PE_{t} {pe[t]:.3f} outside realised band [{inp['pe_own_min']}, {inp['pe_own_max']}] — STOP, do not force g")
    if errors:
        return report(errors, "FAIL (guardrail)")

    # --- Step 3: anchors, zone, ②-b, check layer ------------------------------
    L, M, H = band_at(inp["g2_m"], inp["g2_h"], eps, roe, r, fx)
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

    evid = {g: band_at(g, inp["g2_h"], eps, roe, r, fx) for g in (inp["g_evid_min"], inp["g_evid_max"])}
    for g, b in evid.items():
        if zone_of(inp["price"], *b) != zone:
            errors.append(f"zone flips to {zone_of(inp['price'], *b)} at g2={g:+.2%} inside the evidence interval — BLOCKED (A9)")

    flat_errs, flat_cny = flat_multiple_ladder((eps["l"], eps["m"], eps["h"]), pe["m"])
    errors += flat_errs
    flat = tuple(v / fx for v in flat_cny)

    for key in ("pe_own_med",):
        if abs(inp[key] - pe["m"]) < 1e-9:
            errors.append(f"{key} leaked into the multiple path — it is a comparison field")
    if abs(inp["g_peer_us"] - inp["g2_m"]) < 1e-9:
        errors.append("g_peer_us leaked into g2 — it is a different-regime cross-check (A7)")
    leaked = [k for k in NOT_FORMULA if k not in inp]
    if leaked:
        errors.append(f"reference rows missing from Inputs: {leaked}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, zone)

    # --- report ----------------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(f"axis _AXIS.brent-oil OK: Brent {brent['l']:g}/{brent['m']:g}/{brent['h']:g}; base {inp['brent_2025']} (realised/Brent rho {rho:.4f})")
    print(f"beta = OP slope {slope_op:,.0f}/$ realised x (1-CIT {inp['cit']:.0%}) x rho = {beta:,.0f} RMB mn per US$1 Brent "
          f"(theoretical cross {beta_theory:,.0f} = crude {inp['crude_fy25']:.0f} mmbbl x rho x {SOG_RETENTION} x {USDCNY_CROSS}); ΔEPS/$1 = {beta * MN / inp['shares']:.4f} CNY")
    print(f"{'档':<3}{'Brent':>7}{'NI(mn)':>10}{'EPS':>9}{'ROE':>8}{'g2':>9}{'派息率':>7}{'PE':>7}{'CNY':>8}{'HKD':>8}")
    for t, a in zip(TIERS, (L, M, H)):
        print(f"{t.upper():<3}{brent[t]:7.0f}{ni[t]:10,.0f}{eps[t]:9.4f}{roe[t]:8.2%}{inp[f'g2_{t}']:+9.3%}"
              f"{payout(inp[f'g2_{t}'], roe[t]):7.0%}{pe[t]:7.2f}{eps[t] * pe[t]:8.3f}{a:8.2f}")
    print(f"分支: 留存 (FY2025 派息率 {payout_fy25:.1%} = {inp['div_fy25']:,.0f} / {inp['ni_fy25']:,.0f}); "
          f"g2 = (1-payout) x ROE_M {roe['m']:.2%} = {g2_derived:+.3%} (cap {G_CAP:.0%}); 病态区 |ROE_M-r| = {abs(roe['m'] - r) * 100:.2f}pp")
    modelled, gap = payout_gap(inp["g2_m"], roe["m"], payout_fy25)
    print(f"check_branch ✓: 模型派息率 {modelled:.1%} vs 实付 {payout_fy25:.1%}, 差 {gap:+.1%}; 证据区间 [{inp['g_evid_min']:+.2%}, {inp['g_evid_max']:+.2%}]; "
          f"美国大型油企簇 {inp['g_peer_us']:+.2%} (单调区, 不同域, 交叉)")
    print(f"倍数生成: r={r:.0%}; {h_note}; 护栏 [{inp['pe_own_min']}, {inp['pe_own_max']}] ✓; "
          f"M 档带边反解 (留存分支): 上沿 {inp['pe_own_max']}x ↔ g {implied_g_retaining(inp['pe_own_max'], roe['m'], r)[0]:+.2%}, 10x ↔ 0")
    print(f"②-b: 共识 FY27 {inp['eps_cons_fy27_lo']}/{cons_mean}/{inp['eps_cons_fy27_hi']} vs EPS {eps['l']:.4f}/{eps['m']:.4f}/{eps['h']:.4f}; "
          f"均值 {'in [M,H]' if eps['m'] <= cons_mean <= eps['h'] else ('below M' if cons_mean < eps['m'] else 'above H')}, M dev {cons_dev:+.1%}, 均值 ↔ Brent {brent_cons:.1f} (A6 deck 年份)")
    print(f"分部校验层 (FY2025 OP): E&P {inp['seg_ep'] / seg_sum:.1%} / 炼化 {inp['seg_rc'] / seg_sum:.1%} / 销售 {inp['seg_mk'] / seg_sum:.1%} / 天然气 {ng_share:.1%}; "
          f"四分部 {seg_sum:,.0f} − 集团 {inp['op_group_fy25']:,.0f} = 总部与抵销 {seg_sum - inp['op_group_fy25']:,.0f}; 次类门槛 {NG_SECONDARY_GATE:.0%} 未触发")
    d = decompose((L, M, H), (pe["l"], pe["m"], pe["h"]))
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.3f} H/M={H / M:.3f} (H-L)/2M={(H - L) / (2 * M):.1%} | 分子比 L={d['num_lm']:.3f} H={d['num_hm']:.3f} | 倍数比 L={d['pe_lm']:.3f} H={d['pe_hm']:.3f}")
    print(f"flat-multiple @PE_M={pe['m']:.2f}: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f} — 带宽 {(flat[2] - flat[0]) / (2 * flat[1]):.1%}")
    pe_px = inp["price"] * fx / eps["m"]
    g_px, ok_px = implied_g_retaining(pe_px, roe["m"], r)
    print(f"price(H)={inp['price']} zone={zone} | 现价 = {pe_px:.2f}x M 档 EPS: 留存分支 g {g_px:+.1%} (conditioned={ok_px}, 病态区不是读数), 全派息读法 r={1 / pe_px:.1%} (A10); "
          f"TP 均值 {inp['tp_cons_h']} = {inp['tp_cons_h'] * fx / eps['m']:.2f}x ↔ r {1 / (inp['tp_cons_h'] * fx / eps['m']):.1%}; H/TP {H / inp['tp_cons_h']:.2f} M/TP {M / inp['tp_cons_h']:.2f}")
    for g, b in evid.items():
        print(f"证据区间 g2={g:+.2%}: {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    for g in (inp["g2_m"] - 0.01, min(G_CAP, inp["g2_m"] + 0.01), 0.0):
        b = band_at(g, inp["g2_h"], eps, roe, r, fx)
        print(f"敏感性 g2 {g:+.2%}: {'/'.join(f'{x:.2f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    ni_t = {t: inp["ni_fy25"] + beta_theory * (brent[t] - inp["brent_2025"]) for t in TIERS}
    b_t = tuple(ni_t[t] * MN / inp["shares"] * perpetual_pe(inp[f"g2_{t}"], ni_t[t] / inp["equity"], r) / fx for t in TIERS)
    print(f"敏感性 β 理论交叉 {beta_theory:,.0f}: {'/'.join(f'{x:.2f}' for x in b_t)} zone={zone_of(inp['price'], *b_t)}; 每 US$1 Brent ≈ M {beta * MN / inp['shares'] * pe['m'] / fx:+.2f} HKD")
    zg = tuple(eps[t] * 10.0 / fx for t in TIERS)
    d0 = inp["dps_fy25"] / fx
    ddm = d0 * (1 + inp["g2_m"]) / (r - inp["g2_m"])
    print(f"交叉尺: 零增长 10x {zg[0]:.2f}/{zg[1]:.2f}/{zg[2]:.2f} (zone {zone_of(inp['price'], *zg)}); DDM D0 {d0:.4f} HKD -> {ddm:.2f} (现价隐含股息增长 {(inp['price'] * r - d0) / (inp['price'] + d0):+.2%}); "
          f"FCF 收益率 {inp['fcf_fy25'] * MN / (inp['price'] * fx * inp['shares']):.1%}; own 中位 {inp['pe_own_med']}x flat -> {'/'.join(f'{eps[t] * inp['pe_own_med'] / fx:.2f}' for t in TIERS)}")
    g1 = (inp["eps_fy2022"] / inp["eps_trough_fy2020"]) ** 0.5 - 1.0
    pe_rec = recovery_two_stage_pe(g1, 2, inp["g2_m"], roe["m"], r)
    print(f"谷底坐标 (A3): 回归段 2020->2022 g1 {g1:.1%} n=2 -> {pe_rec:.1f}x on FY2020 EPS {inp['eps_trough_fy2020']} = {inp['eps_trough_fy2020'] * pe_rec / fx:.2f} HKD (坐标, 不作锚); "
          f"谷底 x 1/r = {inp['eps_trough_fy2020'] / r / fx:.2f} HKD (deep_discount 压力坐标)")
    print(f"属性 D: 2026H1 归母 {inp['ni_h1_26']:,.0f} x2 = {2 * inp['ni_h1_26']:,.0f} ↔ 本尺 Brent {inp['brent_2025'] + (2 * inp['ni_h1_26'] - inp['ni_fy25']) / beta:.1f}")
    la, ma, ha = L * fx, M * fx, H * fx
    print(f"A股对照(CNY): L={la:.2f} M={ma:.2f} H={ha:.2f} | price_a={inp['price_a']} zone_a={zone_of(inp['price_a'], la, ma, ha)} | H/A = {inp['price'] * fx / inp['price_a']:.3f}")

    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
