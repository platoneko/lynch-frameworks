#!/usr/bin/env python3
"""159263.SZ (E Fund CNI Value 100 ETF) valuation eval.

formula_id: efund_cni_value100_sotp_lookthrough_v3

Snapshot SOTP: white-goods Gordon (FY2027E consensus three points) + CMB /
Yuntianhua / Chalco look-through + Industrial Bank PB-ROE leg + other
financials × k_bank + residual Gordon (TTM).

Branch (valuation-rules「反解分支」, 2026-09-15).  Both Gordon legs pin their
branch on the constituents' observed payout before any g is read:

  * white goods (格力 / 美的 / 海尔, earnings-weighted): FY2025 payout 57.7 /
    74.6 / 55.3% -> 61.7%, forward ROE 16-23% — every name in the MONOTONE
    regime (ROE >= r + 3pp), where the Gordon multiple has one branch only and
    a forward PE below 1/r is unreachable for a company that retains.  格力
    at 7.71x is therefore not a g reading (it says r ~ 13%) and is EXCLUDED
    from the cluster, not clipped; v2 fed its full-payout reading (-2.96%)
    into the median and got 0.2%.  美的 12.93x -> +3.39%, 海尔 10.07x -> +0.18%
    on the retention formula; median (n = 2) = +1.78%.  check_branch is
    sign-only here; the 29pp payout_gap is disclosed (book vs marginal ROE).
  * residual (54.5%, index ROE 10.8% ~ r, ILL-CONDITIONED regime): the multiple
    sits at 1/r whatever g is, so g comes from the payout policy only —
    look-through payout 51.3% (yield 5.0% x PE 10.26, the 08-14 official PE
    scaled by the index level, not the dividend-accruing ETF NAV) -> g2 =
    (1 - 0.513) x 10.8% = +5.26% on the M/H tiers (H = M: nothing to name
    above M in this regime), 10.82x; L keeps the named zero-growth world (10x).
    check_branch's magnitude test applies and passes (modelled payout ==
    observed).

Same-world gate: 格力 / 美的 / 海尔 FY26E -> FY27E all up; the residual's
covered names (华域 n=7->9, 电信 n=2->4) up — coverage thin: no official CNI
PE series exists (CNI / Longbridge expose none; the constituent look-through
only yields ratios, A6).  The zone must hold across both legs' evidence
intervals, jointly (校验步骤 6).
"""
from __future__ import annotations

import sys
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.etf_lookthrough import scale  # noqa: E402
from lib.gordon import (  # noqa: E402
    G_CAP, NEAR_FULL_PAYOUT, check_branch, check_g_cap, check_r, implied_g, implied_g_retaining,
    justified_pb, payout_gap, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, parse_inputs, report, stated_anchors,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "159263.SZ.md"
FORMULA_ID = "efund_cni_value100_sotp_lookthrough_v3"

# Look-through sleeves copy their L/M/H from another framework; a copy that
# drifts from its source is a stale input, so it is checked here (A2e-4).
LOOKTHROUGH = {"cmb": "600036.SH", "yth": "600096.SH", "alc": "601600.SH"}
WEIGHTS = ("w_white", "w_cmb", "w_xyb", "w_obank", "w_yth", "w_alc", "w_res")
WHITE = ("gree", "midea", "haier")
WHITE_FIELDS = ("w", "pe", "fpe", "roe", "dps25", "eps25", "fy26", "fy27")
BLOCKED_WHITE = ("gree",)  # forward PE below 1/r on a retaining, monotone-regime name (A5)
LEG_TOL = 0.005
G2_TOL = 0.0005
PE_TOL = 0.05
_ROE_MONOTONE = 0.03

REQUIRED = [
    "price", "fee_drag", "r_perp",
    "w_white", "pe_white_now", "roe_white", "g2_white", "payout_white",
    "g_evid_white_min", "g_evid_white_max",
    "eps_white_l", "eps_white_m", "eps_white_h",
    *(f"{n}_{f}" for n in WHITE for f in WHITE_FIELDS),
    "w_cmb", "px_cmb", "cmb_l", "cmb_m", "cmb_h",
    "w_xyb", "pb_xyb", "roe_xyb", "g2_bank", "k_bank_l", "k_bank_m", "k_bank_h",
    "w_obank",
    "w_yth", "px_yth", "yth_l", "yth_m", "yth_h",
    "w_alc", "px_alc", "alc_l", "alc_m", "alc_h",
    "w_res", "pe_res_now", "roe_idx", "idx_dy_lo", "idx_dy_hi", "payout_res",
    "g2_res_l", "g2_res_m", "g2_res_h", "g_evid_res_min", "g_evid_res_max",
    "pe_res_l", "pe_res_m", "pe_res_h", "eps_res_l", "eps_res_m", "eps_res_h",
]


def white_weights(inp: dict[str, float]) -> dict[str, float]:
    """Earnings share w_k / PE_k inside the white-goods sleeve, normalised."""
    raw = {n: inp[f"{n}_w"] / inp[f"{n}_pe"] for n in WHITE}
    total = sum(raw.values())
    return {n: v / total for n, v in raw.items()}


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)
    # A2e-7a: the base band carries no probability field.
    errors += [f"probability-looking input {k}" for k in inp if k.startswith("p_")]
    wsum = sum(inp[w] for w in WEIGHTS)
    if abs(wsum - 1.0) > 0.002:
        errors.append(f"weights sum {wsum:.4f} != 1")

    r = inp["r_perp"]
    errors += check_r(r, "r_perp")
    errors += check_g_cap(inp["g2_white"], "g2_white")
    errors += check_g_cap(inp["g2_bank"], "g2_bank")
    for tag in "lmh":
        errors += check_g_cap(inp[f"g2_res_{tag}"], f"g2_res_{tag}")
        pe_gen = perpetual_pe(inp[f"g2_res_{tag}"], inp["roe_idx"], r)
        if abs(pe_gen - inp[f"pe_res_{tag}"]) > PE_TOL:
            errors.append(
                f"pe_res_{tag}={inp[f'pe_res_{tag}']} != perpetual_pe(g={inp[f'g2_res_{tag}']}, "
                f"ROE={inp['roe_idx']}, r={r}) = {pe_gen:.2f}"
            )
    for key, ticker in LOOKTHROUGH.items():
        src = stated_anchors((FRAMEWORK.parent / f"{ticker}.md").read_text(encoding="utf-8"))
        for tier in "LMH":
            said, ref = inp[f"{key}_{tier.lower()}"], src[tier]
            if ref is None or abs(said - ref) > 0.01:
                errors.append(f"{key}_{tier.lower()}={said} != {ticker} stated {tier}={ref} — re-copy from source")
    if errors:
        return report(errors)

    # --- Step 1: white-goods branch, name by name (A5) -------------------------
    ew = white_weights(inp)
    pe_white_now = sum(inp[f"{n}_w"] for n in WHITE) / sum(inp[f"{n}_w"] / inp[f"{n}_pe"] for n in WHITE)
    if abs(pe_white_now - inp["pe_white_now"]) > PE_TOL:
        errors.append(f"pe_white_now {inp['pe_white_now']} != earnings-weighted harmonic {pe_white_now:.2f}")
    payout_white = sum(ew[n] * inp[f"{n}_dps25"] / inp[f"{n}_eps25"] for n in WHITE)
    roe_white = sum(ew[n] * inp[f"{n}_roe"] for n in WHITE)
    if abs(payout_white - inp["payout_white"]) > LEG_TOL:
        errors.append(f"payout_white {inp['payout_white']} != earnings-weighted FY2025 DPS/EPS {payout_white:.4f}")
    if abs(roe_white - inp["roe_white"]) > LEG_TOL:
        errors.append(f"roe_white {inp['roe_white']} != earnings-weighted ROE_M {roe_white:.4f}")
    cluster: dict[str, float] = {}
    blocked: dict[str, float] = {}
    for n in WHITE:
        roe = inp[f"{n}_roe"]
        if roe - r < _ROE_MONOTONE:
            errors.append(f"{n}: ROE {roe:.1%} left the monotone regime — the single-branch reading no longer applies, re-decide (A5)")
        if inp[f"{n}_dps25"] / inp[f"{n}_eps25"] >= NEAR_FULL_PAYOUT:
            errors.append(f"{n}: FY2025 payout {inp[f'{n}_dps25'] / inp[f'{n}_eps25']:.0%} >= {NEAR_FULL_PAYOUT:.0%} — no longer retains, re-decide the branch (A5)")
        # Same-world gate: the leg's own consensus must point up for a g > 0 source.
        if inp[f"{n}_fy27"] <= inp[f"{n}_fy26"]:
            errors.append(f"{n}: FY27E {inp[f'{n}_fy27']} <= FY26E {inp[f'{n}_fy26']} — consensus turned down, g2 > 0 fails the same-world gate (裁决顺序 ④)")
        g, ok = implied_g_retaining(inp[f"{n}_fpe"], roe, r)
        if inp[f"{n}_fpe"] < 1.0 / r or not ok:
            blocked[n] = g
        else:
            cluster[n] = g
    for n in BLOCKED_WHITE:
        if n in cluster:
            errors.append(f"{n} entered the white cluster (fpe {inp[f'{n}_fpe']}) — A5 excludes it as unreachable; re-decide in conversation")
    if len(cluster) < 2:
        errors.append(f"white cluster n={len(cluster)} < 2 after exclusions — source must fall back to own payout x ROE (A5)")
    else:
        g_med = median(cluster.values())
        if abs(g_med - inp["g2_white"]) > G2_TOL:
            errors.append(f"g2_white {inp['g2_white']} != cluster median {g_med:.4f} of {cluster}")
        if abs(min(cluster.values()) - inp["g_evid_white_min"]) > G2_TOL or abs(max(cluster.values()) - inp["g_evid_white_max"]) > G2_TOL:
            errors.append(f"g_evid_white_min/max {inp['g_evid_white_min']}/{inp['g_evid_white_max']} != cluster min/max {min(cluster.values()):.4f}/{max(cluster.values()):.4f}")
    if inp["g2_white"] <= 0:
        errors.append(f"g2_white {inp['g2_white']:+.4f} <= 0 is the full-payout branch — the leg pays out {inp['payout_white']:.0%} (A5)")
    errors += check_branch(inp["g2_white"], inp["roe_white"], r, inp["payout_white"], "g2_white")

    # --- Step 2: residual branch from the payout policy (A6) -------------------
    payout_res = (inp["idx_dy_lo"] + inp["idx_dy_hi"]) / 2 * inp["pe_res_now"]
    if abs(payout_res - inp["payout_res"]) > LEG_TOL:
        errors.append(f"payout_res {inp['payout_res']} != mid yield x index PE {payout_res:.4f}")
    g_res = (1.0 - inp["payout_res"]) * inp["roe_idx"]
    if abs(min(G_CAP, g_res) - inp["g2_res_m"]) > G2_TOL:
        errors.append(f"g2_res_m {inp['g2_res_m']} != (1 - payout_res {inp['payout_res']}) x ROE {inp['roe_idx']} = {g_res:.4f}")
    if inp["g2_res_h"] != inp["g2_res_m"]:
        errors.append(f"g2_res_h {inp['g2_res_h']} must equal g2_res_m {inp['g2_res_m']} — no H-side growth to name in the ill-conditioned regime (A6)")
    if inp["g2_res_l"] != 0.0:
        errors.append(f"g2_res_l {inp['g2_res_l']} must be exactly 0: the named zero-growth world (A6)")
    if abs(inp["roe_idx"] - r) >= _ROE_MONOTONE:
        errors.append(f"roe_idx {inp['roe_idx']:.1%} left the ill-conditioned band — A6's regime statement no longer holds, re-decide")
    errors += check_branch(inp["g2_res_m"], inp["roe_idx"], r, inp["payout_res"], "g2_res_m")
    evid_res = {
        "min": (1.0 - inp["idx_dy_hi"] * inp["pe_res_now"]) * inp["roe_idx"],
        "max": (1.0 - inp["idx_dy_lo"] * inp["pe_res_now"]) * inp["roe_idx"],
    }
    for k, g in evid_res.items():
        if abs(g - inp[f"g_evid_res_{k}"]) > G2_TOL:
            errors.append(f"g_evid_res_{k} {inp[f'g_evid_res_{k}']} != {g:.4f} from idx_dy_{'hi' if k == 'min' else 'lo'} x pe_res_now")
    if errors:
        return report(errors, "FAIL (branch)")

    # --- Step 3: anchors --------------------------------------------------------
    def pe_white(tag: str, g2: float) -> float:
        roe = inp["roe_white"] * inp[f"eps_white_{tag}"] / inp["eps_white_m"]
        return perpetual_pe(g2, roe, r)

    k_xyb = justified_pb(inp["g2_bank"], inp["roe_xyb"], r) / inp["pb_xyb"]

    def legs(tag: str, g2w: float, pe_res: dict[str, float], flat: bool = False) -> dict[str, float]:
        pw = pe_white("m" if flat else tag, g2w)
        pr = pe_res["m"] if flat else pe_res[tag]
        kb = inp[f"k_bank_{tag}"]
        return {
            "white": inp["w_white"] * inp[f"eps_white_{tag}"] * pw / inp["pe_white_now"],
            "cmb": inp["w_cmb"] * inp[f"cmb_{tag}"] / inp["px_cmb"],
            "xyb": inp["w_xyb"] * k_xyb * kb,
            "obank": inp["w_obank"] * kb,
            "yth": inp["w_yth"] * inp[f"yth_{tag}"] / inp["px_yth"],
            "alc": inp["w_alc"] * inp[f"alc_{tag}"] / inp["px_alc"],
            "res": inp["w_res"] * inp[f"eps_res_{tag}"] * pr / inp["pe_res_now"],
        }

    def anchor(tag: str, g2w: float, pe_res: dict[str, float], flat: bool = False) -> float:
        return scale(inp["price"], inp["fee_drag"], sum(legs(tag, g2w, pe_res, flat).values()))

    def res_pe(g_m: float) -> dict[str, float]:
        """Residual multiples for one M/H g: L stays the named zero-growth 1/r."""
        pm = perpetual_pe(g_m, inp["roe_idx"], r)
        return {"l": inp["pe_res_l"], "m": pm, "h": pm}

    def band(g2w: float, pe_res: dict[str, float]) -> tuple[float, float, float]:
        return tuple(anchor(t, g2w, pe_res) for t in "lmh")  # type: ignore[return-value]

    base_res = {t: inp[f"pe_res_{t}"] for t in "lmh"}
    computed = {"L": anchor("l", inp["g2_white"], base_res), "M": anchor("m", inp["g2_white"], base_res), "H": anchor("h", inp["g2_white"], base_res)}
    if not (computed["L"] < computed["M"] < computed["H"]):
        return report(["ladder collapsed"])
    # A2e-2c: every Gordon leg at its M-tier multiple; the ladder must survive on numerators.
    flat = tuple(anchor(t, inp["g2_white"], base_res, flat=True) for t in "lmh")
    if not (flat[0] < flat[1] < flat[2]):
        return report([f"flat-multiple ladder collapsed: {flat}"])
    A, B = cut_points(computed["L"], computed["M"], computed["H"])
    computed["A"], computed["B"] = A, B
    zone = zone_of(inp["price"], computed["L"], computed["M"], computed["H"])
    errors = check_against_stated(md, computed, zone, tol=0.01)
    # 校验步骤 6: the zone must hold across both legs' evidence intervals, jointly.
    evid_w = (inp["g_evid_white_min"], inp["g_evid_white_max"])
    evid_r = (inp["g_evid_res_min"], inp["g_evid_res_max"])
    evid_bands = {(gw, gr): band(gw, res_pe(gr)) for gw in (inp["g2_white"], *evid_w) for gr in (inp["g2_res_m"], *evid_r)}
    for (gw, gr), b in evid_bands.items():
        if zone_of(inp["price"], *b) != zone:
            errors.append(f"zone flips to {zone_of(inp['price'], *b)} at g2_white={gw:+.2%} x g2_res={gr:+.2%} inside the evidence intervals — BLOCKED (A5/A6)")
    if errors:
        return report(errors)

    # --- report -----------------------------------------------------------------
    L, M, H = computed["L"], computed["M"], computed["H"]
    nav = inp["price"] * inp["fee_drag"]
    print(f"formula_id={FORMULA_ID}")
    print("白电成份 (FY2025 DPS/EPS → 派息率; 09-11 收盘 ÷ FY27E → 前瞻 PE; 留存分支反解; FY26E→FY27E 方向):")
    for n in WHITE:
        pay = inp[f"{n}_dps25"] / inp[f"{n}_eps25"]
        g_ret, ok = implied_g_retaining(inp[f"{n}_fpe"], inp[f"{n}_roe"], r)
        g_full, _ = implied_g(inp[f"{n}_fpe"], inp[f"{n}_roe"], r)
        status = "BLOCKED 剔除 (< 10x 顶, 留存公司不可达)" if n in blocked else "入簇"
        print(f"  {n:<6} 权重 {ew[n]:.3f}  DPS {inp[f'{n}_dps25']:.4f}/EPS {inp[f'{n}_eps25']:.4f} = {pay:.1%}  ROE {inp[f'{n}_roe']:.1%} 单调区  "
              f"fPE {inp[f'{n}_fpe']:.2f}x → 留存分支 {g_ret:+.2%} (cond={ok}; 全派息读数 {g_full:+.2%})  "
              f"共识 {inp[f'{n}_fy26']:.3f}→{inp[f'{n}_fy27']:.3f} ({inp[f'{n}_fy27'] / inp[f'{n}_fy26'] - 1:+.1%})  {status}")
    modelled_w, gap_w = payout_gap(inp["g2_white"], inp["roe_white"], inp["payout_white"])
    print(f"白电腿: 派息率 {inp['payout_white']:.1%} (< {NEAR_FULL_PAYOUT:.0%} 留存) · ROE_M {inp['roe_white']:.1%} (单调区 ≥ r+3pp) · 簇 n={len(cluster)} 中位 g2 {inp['g2_white']:+.2%} "
          f"(证据区间 [{inp['g_evid_white_min']:+.2%}, {inp['g_evid_white_max']:+.2%}]) → PE {pe_white('l', inp['g2_white']):.2f}/{pe_white('m', inp['g2_white']):.2f}/{pe_white('h', inp['g2_white']):.2f} vs 现 {inp['pe_white_now']}x; "
          f"check_branch ✓ (符号) · payout_gap: 模型派息率 {modelled_w:.1%} vs 实付 {inp['payout_white']:.1%} 差 {gap_w:+.1%} (账面 ROE ≠ 边际 ROE, 只披露); "
          f"自身派息政策 × ROE = {(1 - inp['payout_white']) * inp['roe_white']:+.2%} > cap → 只进 stretched")
    modelled_r, gap_r = payout_gap(inp["g2_res_m"], inp["roe_idx"], inp["payout_res"])
    print(f"残余腿: 透视派息率 {inp['payout_res']:.1%} (股息率 {inp['idx_dy_lo']:.1%}–{inp['idx_dy_hi']:.1%} 中值 × PE {inp['pe_res_now']}) · ROE {inp['roe_idx']:.1%} 病态区 |ROE−r| {abs(inp['roe_idx'] - r):.1%} · "
          f"g2 M/H = (1−{inp['payout_res']:.3f}) × {inp['roe_idx']:.3f} = {g_res:+.2%} → PE {inp['pe_res_l']}/{inp['pe_res_m']}/{inp['pe_res_h']}; L 档具名零增长; "
          f"check_branch ✓ 模型派息率 {modelled_r:.1%} vs 实付 {inp['payout_res']:.1%} 差 {gap_r:+.1%}; 证据区间 [{inp['g_evid_res_min']:+.2%}, {inp['g_evid_res_max']:+.2%}]")
    print(f"  PE(g) 在 ROE {inp['roe_idx']:.1%} 下: g 0/2/3/4/5/6% → " + "/".join(f"{perpetual_pe(g, inp['roe_idx'], r):.2f}" for g in (0, .02, .03, .04, .05, .06))
          + f"x — 贴 1/r, 结论对 g 不敏感; 指数 {inp['pe_res_now']}x 留存分支反解 {implied_g_retaining(inp['pe_res_now'], inp['roe_idx'], r)[0]:+.2%} (cond={implied_g_retaining(inp['pe_res_now'], inp['roe_idx'], r)[1]}) 只作交叉")
    print(f"兴业 fair PB {justified_pb(inp['g2_bank'], inp['roe_xyb'], r):.3f} / {inp['pb_xyb']} = k {k_xyb:.3f}")
    for tag in "lmh":
        d = legs(tag, inp["g2_white"], base_res)
        print(f"{tag.upper()}: " + "  ".join(f"{k} {v * nav:.4f}" for k, v in d.items()) + f"  = {computed[tag.upper()]:.4f}")
    print(f"flat-multiple ladder @ M-tier multiples: {flat[0]:.4f}/{flat[1]:.4f}/{flat[2]:.4f}")
    print(
        f"L/M {L / M:.3f} (white leg: num {inp['eps_white_l'] / inp['eps_white_m']:.3f} x pe "
        f"{pe_white('l', inp['g2_white']) / pe_white('m', inp['g2_white']):.3f}; res leg: num {inp['eps_res_l']:.2f} x pe "
        f"{inp['pe_res_l'] / inp['pe_res_m']:.3f}) | H/M {H / M:.3f} (white: num "
        f"{inp['eps_white_h'] / inp['eps_white_m']:.3f} x pe {pe_white('h', inp['g2_white']) / pe_white('m', inp['g2_white']):.3f}; "
        f"res: num {inp['eps_res_h']:.2f} x pe {inp['pe_res_h'] / inp['pe_res_m']:.3f}) | "
        f"width {(H - L) / (2 * M):.3f} | V_opt/M 0.000 | all-at-market ref {nav:.4f}"
    )
    m_legs = legs("m", inp["g2_white"], base_res)
    # Each leg's all-at-market value is w_k x NAV x fee, so the excess is (leg - w_k) x nav.
    print("M 高出全市价对照带: " + "  ".join(f"{k} {(v - inp[f'w_{k}']) * nav:+.4f}" for k, v in m_legs.items()))
    for (gw, gr), b in evid_bands.items():
        if (gw, gr) == (inp["g2_white"], inp["g2_res_m"]):
            continue
        print(f"证据区间 白电 {gw:+.2%} × 残余 {gr:+.2%}: {'/'.join(f'{x:.4f}' for x in b)} A={cut_points(*b)[0]:.4f} zone={zone_of(inp['price'], *b)}")
    for dg in (-0.01, 0.01):
        b = band(max(0.0, inp["g2_white"] + dg), base_res)
        print(f"敏感性 g2_white {dg:+.0%} ({max(0.0, inp['g2_white'] + dg):+.2%}): {'/'.join(f'{x:.4f}' for x in b)} zone={zone_of(inp['price'], *b)}")
        g = min(G_CAP, inp["g2_res_m"] + dg)
        b = band(inp["g2_white"], res_pe(g))
        print(f"敏感性 g2_res_m {dg:+.0%} ({g:+.2%}, PE {perpetual_pe(g, inp['roe_idx'], r):.2f}): {'/'.join(f'{x:.4f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    b = band(0.002, base_res)
    print(f"对照 v2 白电 g 0.2% (格力入簇): {'/'.join(f'{x:.4f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    b = band(inp["g2_white"], {"l": 10.0, "m": 10.2, "h": 10.3})
    print(f"对照 v2 残余 0/2/3% (10.0/10.2/10.3x): {'/'.join(f'{x:.4f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    b = band(inp["g2_white"], {t: inp["pe_res_m"] for t in "lmh"})
    print(f"对照 残余三档 flat {inp['pe_res_m']}x: {'/'.join(f'{x:.4f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    g_pol = min(G_CAP, (1 - inp["payout_white"]) * inp["roe_white"])
    b = band(g_pol, base_res)
    print(f"对照 白电自身派息政策 × ROE ({g_pol:+.2%} 截顶, PE {pe_white('m', g_pol):.2f}x): {'/'.join(f'{x:.4f}' for x in b)} zone={zone_of(inp['price'], *b)} (stretched 解释)")
    white_gree = inp["w_white"] * inp["eps_white_m"] * inp["gree_fpe"] / inp["pe_white_now"] * nav
    print(f"对照 白电全腿按格力 {inp['gree_fpe']}x: 白电腿 M {white_gree:.4f} ({white_gree - m_legs['white'] * nav:+.4f})")
    print(f"对照 残余分子取 E1 = TTM × (1+g2): 残余腿 M {m_legs['res'] * nav * (1 + inp['g2_res_m']):.4f} ({m_legs['res'] * nav * inp['g2_res_m']:+.4f})")
    print(f"对照 兴业冻结市价: M {M - (m_legs['xyb'] - inp['w_xyb']) * nav:.4f}; 白电分子改 TTM: M {M - (m_legs['white'] - m_legs['white'] / inp['eps_white_m']) * nav:.4f}; "
          f"压力坐标 (兴业冻结 + 残余八折): L {L - (legs('l', inp['g2_white'], base_res)['xyb'] - inp['w_xyb'] * inp['k_bank_l']) * nav - legs('l', inp['g2_white'], base_res)['res'] / inp['eps_res_l'] * 0.1 * nav:.4f}")
    print(f"OK  L={L:.4f} M={M:.4f} H={H:.4f} A={A:.4f} B={B:.4f}  zone={zone}  price={inp['price']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
