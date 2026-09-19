#!/usr/bin/env python3
"""159263.SZ (E Fund CNI Value 100 ETF) valuation eval.

formula_id: etf_tr_trend_channel_v1  (主尺)
cross-check: efund_cni_value100_sotp_lookthrough_v3 at basket r  (对照尺)

Ruler (valuation-rules.md「§ETF 例外」): a passive basket has no fair value
apart from its NAV — price ≡ NAV, the fund retains and allocates nothing, and
the index PE / PB / ROE are snapshots of the current basket (quarterly
rebalance, ~104% turnover).  Only the total-return flow is continuous, so the
deck is the log-linear trend channel of the underlying TR index 480081:
M = trend (compound 中枢, slope = realised central return), L / H = residual
p10 / p90, mapped to the ETF price by k = price / index level.  The ETF
accumulates (cash DPS = 0, A1), so the TR series is used directly and no
rate-neutral cross-read is run.  No r enters the deck; the basket rows exist
so the index basket column is populated and the cross-check runs at basket r.

Cross-check (v1 look-through SOTP, kept as 对照尺 and E-side guardrail): white
goods Gordon (FY2027E consensus three points; g2 from the 美的 / 海尔 retention
branch, 格力 7.71x excluded as unreachable in the monotone regime, A5) + CMB /
Yuntianhua / Chalco look-through + Industrial Bank PB-ROE (篮 5, r 11%) + other
financials × k_bank + residual Gordon (index ROE 10.8% ~ r: ill-conditioned,
g2 from the payout policy, A6).  Its band is printed and compared with the
Outputs 对照 line; its zone is never the deck zone.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.etf import REGIME_GAP, SUBWINDOWS, channel, history, slope_since  # noqa: E402
from lib.etf_lookthrough import scale  # noqa: E402
from lib.gordon import (  # noqa: E402
    NEAR_FULL_PAYOUT, check_branch, check_g_cap, check_r, g_cap, implied_g, implied_g_retaining,
    justified_pb, payout_gap, perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, outputs_section, parse_baskets, parse_inputs, report,
    stated_anchors,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "159263.SZ.md"
FORMULA_ID = "etf_tr_trend_channel_v1"
SOTP_FORMULA_ID = "efund_cni_value100_sotp_lookthrough_v3"

# The ETF declares its own index (eval/lib/etf.py holds only fetch + maths).
# 480081 is the total-return twin of 980081 国证价值100; the ETF accrues its
# dividends (A1), so the channel runs on TR directly.  No regime break is
# declared: the 2019 / 2021 sub-window slopes are printed as sensitivity only.
INDEX_SRC, INDEX_CODE = "cni", "480081"
INDEX_LABEL = "980081 价值100 全收益（480081）"
# The framework's chan_* rows were read on this window end; later rows in the
# cache must not move the deck without a framework update.
CHANNEL_END = "2026-09-17"
CHAN_TOL = {"slope": 0.0015, "sigma": 0.0015, "z": 0.01, "idx": 1.0}

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
_STATED_SOTP = re.compile(r"对照（look-through SOTP[^）]*）\**：\*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*")
_SENS_LINE = re.compile(r"^- \*\*敏感区\*\*：(.*)$", re.MULTILINE)

REQUIRED = [
    "price", "fee_drag", "r_perp", "r_bank",
    "chan_slope", "chan_slope_2019", "chan_slope_2021", "chan_sigma", "chan_z",
    "chan_l_idx", "chan_m_idx", "chan_h_idx", "idx_cur",
    "r_lt_implied", "eps_pt_from_peak", "eps_pt_yoy", "beta_rate_prior",
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
    for fid in (FORMULA_ID, SOTP_FORMULA_ID):
        if fid not in md:
            print(f"FAIL: formula_id {fid} missing", file=sys.stderr)
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

    # Basket declaration: every r row names its basket and carries that basket's value.
    baskets = parse_baskets(md)
    for key in ("r_perp", "r_bank"):
        if key not in baskets:
            errors.append(f"{key}: no 篮 N in its Inputs source cell (valuation-rules.md「§r 篮子」)")
        errors += check_r(inp[key], key, baskets.get(key))
    r, r_bank = inp["r_perp"], inp["r_bank"]
    errors += check_g_cap(inp["g2_white"], r, "g2_white")
    errors += check_g_cap(inp["g2_bank"], r_bank, "g2_bank")
    for tag in "lmh":
        errors += check_g_cap(inp[f"g2_res_{tag}"], r, f"g2_res_{tag}")
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

    # --- Step 1: the deck — TR trend channel of the underlying index -----------
    s = history(INDEX_SRC, INDEX_CODE)
    s = s[s.index <= CHANNEL_END]
    ch = channel(s)
    sub = {w[:4]: slope_since(s, w) for w in SUBWINDOWS}
    got = {"chan_slope": ch["slope"], "chan_slope_2019": sub["2019"], "chan_slope_2021": sub["2021"],
           "chan_sigma": ch["sigma"], "chan_z": ch["z"],
           "chan_l_idx": ch["L"], "chan_m_idx": ch["M"], "chan_h_idx": ch["H"], "idx_cur": ch["cur"]}
    for key, val in got.items():
        tol = CHAN_TOL["idx"] if key.endswith("_idx") or key == "idx_cur" else CHAN_TOL[key.split("_")[1]]
        if abs(val - inp[key]) > tol:
            errors.append(f"{key} {inp[key]} != channel {val:.4f} ({INDEX_LABEL}, {ch['start']}..{ch['end']})")
    # Regime rule: a sub-window slope ≥ 5pp off the full window with a nameable
    # cause fits from the break; none is declared here, so a gap that wide is a
    # decision the eval cannot take.
    gap = max(abs(v - ch["slope"]) for v in sub.values())
    if gap >= REGIME_GAP:
        errors.append(f"sub-window slope gap {gap:.1%} >= {REGIME_GAP:.0%} — regime break candidate, re-decide the window in conversation")
    if errors:
        return report(errors, "FAIL (channel)")

    # --- Step 2: map index points to the ETF price; zone ------------------------
    k = inp["price"] / ch["cur"]  # price ≡ NAV tracks TR
    L, M, H = ch["L"] * k, ch["M"] * k, ch["H"] * k
    A, B = cut_points(L, M, H)
    computed = {"L": L, "M": M, "H": H, "A": A, "B": B}
    zone = zone_of(inp["price"], L, M, H)
    errors = check_against_stated(md, computed, zone, tol=0.01)
    # 敏感区: the window choice is the deck's only judgement input.  A sub-window
    # that flips the zone does not move the deck (gap < REGIME_GAP keeps the full
    # window) but the Outputs 敏感区 line must carry the ⚠ marker — and only then.
    win_bands = {}
    for w in SUBWINDOWS:
        cw = channel(s[s.index >= w])
        win_bands[w[:4]] = (cw["L"] * k, cw["M"] * k, cw["H"] * k)
    flips = [w for w, b in win_bands.items() if zone_of(inp["price"], *b) != zone]
    sens = _SENS_LINE.search(outputs_section(md))
    if not sens:
        errors.append("Outputs 敏感区 line not found")
    elif bool(flips) != ("⚠" in sens.group(1)):
        errors.append(f"敏感区 line {'lacks' if flips else 'carries'} ⚠ but sub-window zone flips = {flips or 'none'}")
    if errors:
        return report(errors)

    # --- Step 3: cross-check — look-through SOTP at basket r (A4–A6) -----------
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

    payout_res = (inp["idx_dy_lo"] + inp["idx_dy_hi"]) / 2 * inp["pe_res_now"]
    if abs(payout_res - inp["payout_res"]) > LEG_TOL:
        errors.append(f"payout_res {inp['payout_res']} != mid yield x index PE {payout_res:.4f}")
    g_res = (1.0 - inp["payout_res"]) * inp["roe_idx"]
    if abs(min(g_cap(r), g_res) - inp["g2_res_m"]) > G2_TOL:
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
    for key, g in evid_res.items():
        if abs(g - inp[f"g_evid_res_{key}"]) > G2_TOL:
            errors.append(f"g_evid_res_{key} {inp[f'g_evid_res_{key}']} != {g:.4f} from idx_dy_{'hi' if key == 'min' else 'lo'} x pe_res_now")
    if errors:
        return report(errors, "FAIL (cross-check branch)")

    def pe_white(tag: str, g2: float) -> float:
        roe = inp["roe_white"] * inp[f"eps_white_{tag}"] / inp["eps_white_m"]
        return perpetual_pe(g2, roe, r)

    k_xyb = justified_pb(inp["g2_bank"], inp["roe_xyb"], r_bank) / inp["pb_xyb"]

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
    sotp = band(inp["g2_white"], base_res)
    if not (sotp[0] < sotp[1] < sotp[2]):
        return report([f"cross-check ladder collapsed: {sotp}"])
    # A2e-2c: every Gordon leg at its M-tier multiple; the ladder must survive on numerators.
    flat = tuple(anchor(t, inp["g2_white"], base_res, flat=True) for t in "lmh")
    if not (flat[0] < flat[1] < flat[2]):
        return report([f"cross-check flat-multiple ladder collapsed: {flat}"])
    m_sotp = _STATED_SOTP.search(outputs_section(md))
    if not m_sotp:
        return report(["stated 对照（look-through SOTP…）：**L / M / H** line not found in Outputs"])
    for said, val, tier in zip(m_sotp.groups(), sotp, "LMH"):
        if abs(float(said) - val) > 0.01:
            errors.append(f"对照 SOTP {tier}: stated {said} vs recomputed {val:.4f}")
    if errors:
        return report(errors)

    # --- report -----------------------------------------------------------------
    nav = inp["price"] * inp["fee_drag"]
    print(f"formula_id={FORMULA_ID}  (对照 {SOTP_FORMULA_ID})")
    print(f"通道 {INDEX_LABEL} {ch['start']}..{ch['end']}: 斜率 {ch['slope']:+.1%} (2019 起 {sub['2019']:+.1%} / 2021 起 {sub['2021']:+.1%}, "
          f"最大差 {gap:.1%} < {REGIME_GAP:.0%} 不触发 regime) · σ {ch['sigma']:.1%} · z {ch['z']:+.2f} · 现值 {ch['cur']:.2f} vs M {ch['M']:.0f} ({ch['cur'] / ch['M'] - 1:+.1%})")
    print(f"折算 k = {inp['price']} / {ch['cur']:.2f} = {k:.4e}; 指数点 L/M/H {ch['L']:.0f}/{ch['M']:.0f}/{ch['H']:.0f} → {L:.4f}/{M:.4f}/{H:.4f}")
    for w, b in win_bands.items():
        print(f"敏感性 通道窗 {w} 起: {'/'.join(f'{x:.4f}' for x in b)} (M {b[1] / M - 1:+.1%}) zone={zone_of(inp['price'], *b)}")
    print(f"L/M {L / M:.3f} | H/M {H / M:.3f} | width {(H - L) / (2 * M):.3f} | V_opt/M 0.000 — 全部来自残差分位, 无分子 / 倍数分解")
    print(f"E 侧护栏 (只披露): 指数 PE {inp['pe_res_now']} / ROE {inp['roe_idx']:.1%} ⇒ 成分层隐含 r {inp['r_lt_implied']:.1%} (k=1) · 透视派息率 {inp['idx_dy_lo'] * inp['pe_res_now']:.1%}–{inp['idx_dy_hi'] * inp['pe_res_now']:.1%} · "
          f"EPS/点 同比 {inp['eps_pt_yoy']:+.1%}, 自峰 {inp['eps_pt_from_peak']:+.1%} · 利率轴 β 先验 {inp['beta_rate_prior']:+.0f} (待 _AXIS.rates.md) · look-through 篮子 r: r_perp 篮 {baskets['r_perp']} {r:.1%} / r_bank 篮 {baskets['r_bank']} {r_bank:.1%}")

    print(f"--- 对照尺 {SOTP_FORMULA_ID} @ 篮子 r (白电 / 残余 {r:.0%}, 兴业 {r_bank:.0%}) ---")
    print("白电成份 (FY2025 DPS/EPS → 派息率; 09-11 收盘 ÷ FY27E → 前瞻 PE; 留存分支反解; FY26E→FY27E 方向):")
    for n in WHITE:
        pay = inp[f"{n}_dps25"] / inp[f"{n}_eps25"]
        g_ret, ok = implied_g_retaining(inp[f"{n}_fpe"], inp[f"{n}_roe"], r)
        g_full, _ = implied_g(inp[f"{n}_fpe"], inp[f"{n}_roe"], r)
        status = "BLOCKED 剔除 (< 1/r 顶, 留存公司不可达)" if n in blocked else "入簇"
        print(f"  {n:<6} 权重 {ew[n]:.3f}  DPS {inp[f'{n}_dps25']:.4f}/EPS {inp[f'{n}_eps25']:.4f} = {pay:.1%}  ROE {inp[f'{n}_roe']:.1%} 单调区  "
              f"fPE {inp[f'{n}_fpe']:.2f}x → 留存分支 {g_ret:+.2%} (cond={ok}; 全派息读数 {g_full:+.2%})  "
              f"共识 {inp[f'{n}_fy26']:.3f}→{inp[f'{n}_fy27']:.3f} ({inp[f'{n}_fy27'] / inp[f'{n}_fy26'] - 1:+.1%})  {status}")
    modelled_w, gap_w = payout_gap(inp["g2_white"], inp["roe_white"], inp["payout_white"])
    print(f"白电腿: 派息率 {inp['payout_white']:.1%} (< {NEAR_FULL_PAYOUT:.0%} 留存) · ROE_M {inp['roe_white']:.1%} (单调区 ≥ r+3pp) · 簇 n={len(cluster)} 中位 g2 {inp['g2_white']:+.2%} "
          f"(证据区间 [{inp['g_evid_white_min']:+.2%}, {inp['g_evid_white_max']:+.2%}]) → PE {pe_white('l', inp['g2_white']):.2f}/{pe_white('m', inp['g2_white']):.2f}/{pe_white('h', inp['g2_white']):.2f} vs 现 {inp['pe_white_now']}x; "
          f"check_branch ✓ (符号) · payout_gap: 模型派息率 {modelled_w:.1%} vs 实付 {inp['payout_white']:.1%} 差 {gap_w:+.1%} (账面 ROE ≠ 边际 ROE, 只披露)")
    modelled_r, gap_r = payout_gap(inp["g2_res_m"], inp["roe_idx"], inp["payout_res"])
    print(f"残余腿: 透视派息率 {inp['payout_res']:.1%} (股息率 {inp['idx_dy_lo']:.1%}–{inp['idx_dy_hi']:.1%} 中值 × PE {inp['pe_res_now']}) · ROE {inp['roe_idx']:.1%} 病态区 |ROE−r| {abs(inp['roe_idx'] - r):.1%} · "
          f"g2 M/H = (1−{inp['payout_res']:.3f}) × {inp['roe_idx']:.3f} = {g_res:+.2%} → PE {inp['pe_res_l']}/{inp['pe_res_m']}/{inp['pe_res_h']}; L 档具名零增长; "
          f"check_branch ✓ 模型派息率 {modelled_r:.1%} vs 实付 {inp['payout_res']:.1%} 差 {gap_r:+.1%}; 证据区间 [{inp['g_evid_res_min']:+.2%}, {inp['g_evid_res_max']:+.2%}]")
    print(f"兴业 (篮 {baskets['r_bank']}, r {r_bank:.0%}): fair PB {justified_pb(inp['g2_bank'], inp['roe_xyb'], r_bank):.3f} / {inp['pb_xyb']} = k {k_xyb:.3f}")
    for tag, val in zip("lmh", sotp):
        d = legs(tag, inp["g2_white"], base_res)
        print(f"{tag.upper()}: " + "  ".join(f"{kk} {v * nav:.4f}" for kk, v in d.items()) + f"  = {val:.4f}")
    print(f"对照 SOTP L/M/H {sotp[0]:.4f}/{sotp[1]:.4f}/{sotp[2]:.4f} A={cut_points(*sotp)[0]:.4f} zone={zone_of(inp['price'], *sotp)} (对照尺, 不出 zone); "
          f"flat 阶梯 {flat[0]:.4f}/{flat[1]:.4f}/{flat[2]:.4f}; 全市价对照带 {nav:.4f}; vs 通道 M {sotp[1] / M - 1:+.1%}")
    m_legs = legs("m", inp["g2_white"], base_res)
    # Each leg's all-at-market value is w_k x NAV x fee, so the excess is (leg - w_k) x nav.
    print("对照 SOTP M 高出全市价: " + "  ".join(f"{kk} {(v - inp[f'w_{kk}']) * nav:+.4f}" for kk, v in m_legs.items()))
    evid_w = (inp["g_evid_white_min"], inp["g_evid_white_max"])
    evid_r = (inp["g_evid_res_min"], inp["g_evid_res_max"])
    for gw in evid_w:
        for gr in evid_r:
            b = band(gw, res_pe(gr))
            print(f"对照 证据区间 白电 {gw:+.2%} × 残余 {gr:+.2%}: {'/'.join(f'{x:.4f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    print(f"对照 兴业冻结市价: SOTP M {sotp[1] - (m_legs['xyb'] - inp['w_xyb']) * nav:.4f}; 兴业 ROE 9%: SOTP M {sotp[1] + inp['w_xyb'] * (justified_pb(inp['g2_bank'], 0.09, r_bank) / inp['pb_xyb'] - k_xyb) * nav:.4f}")
    print(f"OK  L={L:.4f} M={M:.4f} H={H:.4f} A={A:.4f} B={B:.4f}  zone={zone}  price={inp['price']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
