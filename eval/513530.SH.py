#!/usr/bin/env python3
"""513530.SH (Huatai-PB CSI HK Connect High Dividend QDII ETF) eval.

formula_id: etf_tr_trend_channel_v1  (cross-check: huatai_hk_hdy_qdi_sotp_index_pe_v3)

Ruler (valuation-rules「§ETF 例外」): a passive basket has no fair value apart
from its NAV, so L/M/H come from the total-return trend channel of the
underlying index (930914 港股通高股息 全收益, H20914): M = log-linear trend,
L / H = residual p10 / p90, mapped to the ETF price by k = nav_ref / index
level on the same as-of date.  No r and no g2 enter the ruler; the look-through
basket r (A13) is only the hurdle the realised slope is read against, and
`r_perp` is declared for the index basket column (篮 4, the r the SOTP
cross-check runs at).

The framework states no current price (AGENTS.md「现价 — 禁写契约」): no zone,
no distance-to-anchor, no market-implied r / g; the digest and the app zone
the live quote themselves.  Sub-window, evidence-interval and 对照 bands are
printed as L/M/H only.

Cross-check: the former look-through SOTP (HSBC / BOCHK Gordon PB-ROE, China
Coal via 1898.HK, cyclical sleeves = constituents' FY2027E consensus over TTM
x flat Gordon multiples generated from the leg's payout policy — energy on the
retention branch, industrial BLOCKED and resolved at the named zero-growth
reference) is recomputed at r_perp (NAV = nav_ref) and must reproduce the
Outputs「对账」row.
The energy ROE is E_{2027}/B_{2026 末} (A14; valuation-rules 裁决表 ② as of
2026-09-21): per name FY27E EPS over the 2Q26 BPS rolled over the
2H26 unbooked EPS (FY26E − 1H26 actual) at b1 = g2_ene/ROE, closed form
ROE = (EPS27 − g2·N)/BPS_2Q26; the 4-name leg values (roe_ene / g2_ene) are
the joint fixed point solved in 520900.SH and copied here, this file rolls
its own 3-name subset at that g2 for the evidence upper end;
its branch guards stay red lines because they are the sleeve facts the
framework's E-side reading rests on.  Constituent raw data is cross-checked
against 520900.SH; the shared leg's Gordon parameters are printed only, since
that framework now generates its multiples at its own basket r.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.etf import REGIME_GAP, SUBWINDOWS, channel, history, slope_since  # noqa: E402
from lib.etf_lookthrough import scale  # noqa: E402
from lib.gordon import (  # noqa: E402
    NEAR_FULL_PAYOUT, check_branch, check_g_cap, check_r, g_cap, implied_g_retaining, justified_pb, payout_gap,
    perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report, stated_anchors,
)
from lib.zones import cut_points  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "513530.SH.md"
PEER = Path(__file__).resolve().parents[2] / "frameworks" / "520900.SH.md"
COAL = Path(__file__).resolve().parents[2] / "frameworks" / "1898.HK.md"  # China Coal look-through source
FORMULA_ID = "etf_tr_trend_channel_v1"
SOTP_FORMULA_ID = "huatai_hk_hdy_qdi_sotp_index_pe_v3"

# ---- channel ruler: the index this ETF tracks (was the `ETF` table entry) ----
INDEX_SRC, INDEX_CODE = "csi", "H20914"
INDEX_LABEL = "930914 港股通高股息 全收益"
KIND = "channel"            # not look-through: the TR index exists and is the ruler
DIVIDEND_CROSS = False      # rate-neutral cross-read needs the listing-currency 10Y; HKD axis pending _AXIS.rates.md
CCY = "HKD"
REGIME: tuple[str, str] | None = None   # sub-window slopes stay within REGIME_GAP of the full window (A13 / Outputs 通道)
CHAN_FIELDS = {  # Inputs row -> channel key, tolerance
    "chan_slope": ("slope", 0.005), "chan_sigma": ("sigma", 0.005),
    "chan_l_idx": ("L", 5.0), "chan_m_idx": ("M", 5.0), "chan_h_idx": ("H", 5.0), "idx_cur": ("cur", 0.5),
}

# ---- SOTP cross-check (former ruler) ----
SLEEVES = {"ind": ("cosco", "sitc", "sinotruk"), "ene": ("shenhua", "cnooc", "petrochina")}
NAME_FIELDS = ("fy27_l", "fy27_m", "fy27_h", "ttm", "w", "pe")
# FY2025 DPS / basic EPS (one currency per name) and BPS in the fy27 currency (A2).
PAYOUT_FIELDS = ("dps25", "eps25", "bps")
# FY2026E consensus mean and 1H26 actual EPS (fy27 currency): the 2H26 unbooked
# earnings that roll the 2Q26 book to the opening-2027 book (A14, energy only).
ROLL_FIELDS = ("fy26_m", "h1_26")
# Report-year regime (pressure coordinate only) — four energy SOEs equal-weighted.
ENERGY_NI = ("shenhua_ni", "cnooc_ni", "petrochina_ni", "sinopec_ni")
SHARED_WITH_PEER = (
    tuple(f"{n}_{f}" for n in ("shenhua", "cnooc", "petrochina", "cosco") for f in ("fy27_l", "fy27_m", "fy27_h", "ttm", "pe"))
    + tuple(f"{n}_{f}" for n in ("shenhua", "cnooc", "petrochina", "cosco") for f in PAYOUT_FIELDS)
    + tuple(f"{n}_{f}" for n in ("shenhua", "cnooc", "petrochina") for f in ROLL_FIELDS)
    + tuple(f"{k}_{t}" for k in ENERGY_NI for t in "lmh")
    + ("cosco_eps22", "cosco_dps22")
)
# Same energy leg as 520900.SH; that framework now runs it at its own basket r,
# so these are reported, not asserted (A2 / Formula step 6, 待办).
SHARED_LEG = ("payout_ene", "roe_ene", "g2_ene", "pe_ene", "g2_ind", "pe_ind", "g_evid_min", "g_evid_max")
GORDON_LEGS = (("ind", "g2_ind"), ("ene", "g2_ene"), ("res", "g2_res"))
SOTP_TOL = 0.01
CANDIDATE_TOL = 0.05
LEG_TOL = 0.005
G2_TOL = 0.0005
PE_TOL = 0.05
_SOTP_ROW = re.compile(r"对账（袖套 look-through SOTP[^）]*）\*\*：([0-9.]+) / ([0-9.]+) / ([0-9.]+)")

REQUIRED = [
    "nav_ref", "fee_drag", "pe_now", "r_perp", "g2_bank", "g2_ind", "g2_ene", "g2_res",
    "payout_ene", "roe_ene", "payout_ind", "roe_ind", "g_evid_min", "g_evid_max",
    "idx_dy", "etf_dps_ttm",
    "w_hsbc", "pb_hsbc", "roe_hsbc",
    "w_bochk", "pb_bochk", "roe_bochk",
    "w_feh", "w_fin_rest",
    "w_ind", "w_ene_rest", "w_cc", "w_res",
    "pe_ind", "pe_ene", "pe_res",
    "eps_ind_l", "eps_ind_m", "eps_ind_h",
    "eps_ene_l", "eps_ene_m", "eps_ene_h",
    "eps_res_l", "eps_res_m", "eps_res_h",
    "k_bank_l", "k_bank_m", "k_bank_h",
    "k_feh_l", "k_feh_m", "k_feh_h",
    "px_cc", "cc_l", "cc_m", "cc_h", "cc_h_cand",
    "cosco_ni_l", "cosco_ni_m", "cosco_eps22", "cosco_dps22",
    *(f"{n}_{f}" for names in SLEEVES.values() for n in names for f in NAME_FIELDS + PAYOUT_FIELDS),
    *(f"{n}_{f}" for n in SLEEVES["ene"] for f in ROLL_FIELDS),
    *(f"{k}_{t}" for k in ENERGY_NI for t in "lmh"),
    *CHAN_FIELDS, "chan_slope_2019", "chan_slope_2021",
    "pe_1y_lo", "pe_1y_hi", "dy_10y_p25", "dy_10y_med", "dy_10y_p75", "beta_rate_prior",
]


def sleeve_weights(inp: dict[str, float], names: tuple[str, ...]) -> dict[str, float]:
    """Earnings share w_k / PE_k inside a sleeve, normalised."""
    raw = {n: inp[f"{n}_w"] / inp[f"{n}_pe"] for n in names}
    total = sum(raw.values())
    return {n: v / total for n, v in raw.items()}


def sleeve_ratio(inp: dict[str, float], names: tuple[str, ...], tier: str) -> float:
    """Earnings-weighted FY2027E-consensus / TTM ratio of a sleeve's constituents."""
    w = sleeve_weights(inp, names)
    return sum(w[n] * inp[f"{n}_fy27_{tier}"] / inp[f"{n}_ttm"] for n in names)


def name_roe(inp: dict[str, float], n: str, g: float) -> float:
    """E_{2027}/B_{2026 末} of one name: FY27E mean EPS over the 2Q26 BPS rolled
    over the 2H26 unbooked EPS (FY26E − 1H26 actual) at b1 = g/ROE; with
    ROE = eps/BPS the fixed point is BPS = BPS0/(1 − g·N/eps), i.e.
    ROE = (eps − g·N)/BPS0 (A14).  g = 0 is the old current-book reading
    (industrial names carry no roll fields and are read at g = 0)."""
    n_unbooked = inp.get(f"{n}_fy26_m", 0.0) - inp.get(f"{n}_h1_26", 0.0)
    return (inp[f"{n}_fy27_m"] - g * n_unbooked) / inp[f"{n}_bps"]


def leg_policy(inp: dict[str, float], names: tuple[str, ...], g_roll: float = 0.0) -> tuple[float, float]:
    """(observed payout, forward ROE_M) of a sleeve, earnings-weighted like the numerator.

    payout_k = FY2025 DPS / FY2025 basic EPS (same currency per name);
    ROE_k = FY2027E mean EPS / opening-2027 BPS (same currency per name), the
    2Q26 book rolled at `g_roll` (A14) -- the M-tier forward ROE
    valuation-rules asks for, so g2 and PE describe the same year as the
    numerator.
    """
    w = sleeve_weights(inp, names)
    payout = sum(w[n] * inp[f"{n}_dps25"] / inp[f"{n}_eps25"] for n in names)
    roe = sum(w[n] * name_roe(inp, n, g_roll) for n in names)
    return payout, roe


def energy_regime_ratio(inp: dict[str, float], tag: str) -> float:
    """Report-year regime: equal-weighted <year>/2025 net-profit ratio of four SOEs."""
    return sum(inp[f"{k}_{tag}"] / inp[f"{k}_m"] for k in ENERGY_NI) / len(ENERGY_NI)


def stated_sotp(md: str) -> tuple[float, float, float] | None:
    m = _SOTP_ROW.search(md)
    return tuple(float(x) for x in m.groups()) if m else None


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
    errors += [f"probability-looking input {k}" for k in inp if k.startswith("p_")]  # A2e-7a
    wsum = (
        inp["w_hsbc"] + inp["w_bochk"] + inp["w_feh"] + inp["w_fin_rest"]
        + inp["w_ind"] + inp["w_ene_rest"] + inp["w_cc"] + inp["w_res"]
    )
    if abs(wsum - 1.0) > 0.003:
        errors.append(f"weights sum {wsum:.4f} != 1")
    if abs(inp["fee_drag"] - 0.94) > 0.005:
        errors.append("QDII fee_drag must be 0.94 (0.60%/10%)")
    # r is disclosure-only for the channel ruler; it is the r the SOTP cross-check runs at (A13).
    baskets = parse_baskets(md)
    r = inp["r_perp"]
    if "r_perp" not in baskets:
        errors.append("r_perp: no 篮 N in the Inputs source cell (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(inp["g2_bank"], r, "g2_bank")
    for _, g_key in GORDON_LEGS:
        errors += check_g_cap(inp[g_key], r, g_key)
    if errors:
        return report(errors)

    # --- Step 1: the ruler — total-return trend channel, mapped to the ETF price ---
    s = history(INDEX_SRC, INDEX_CODE)
    full = channel(s)
    sub = {w[:4]: slope_since(s, w) for w in SUBWINDOWS}
    ch = full
    if REGIME:
        start, _ = REGIME
        ch = channel(s[s.index >= start])
        if abs(ch["slope"] - full["slope"]) < REGIME_GAP:
            errors.append(f"regime declared from {start} but slope gap < {REGIME_GAP:.0%}")
    elif any(abs(v - full["slope"]) >= REGIME_GAP for v in sub.values()):
        errors.append(f"sub-window slope {sub} is >= {REGIME_GAP:.0%} from the full window {full['slope']:+.1%} — name the break or explain (Outputs 通道)")
    for key, (ck, tol) in CHAN_FIELDS.items():
        if abs(inp[key] - ch[ck]) > tol:
            errors.append(f"{key}={inp[key]} != channel {ck} {ch[ck]:.4f} (tol {tol})")
    for key, w in (("chan_slope_2019", "2019"), ("chan_slope_2021", "2021")):
        if abs(inp[key] - sub[w]) > 0.005:
            errors.append(f"{key}={inp[key]} != slope since {w} {sub[w]:.4f}")
    k = inp["nav_ref"] / ch["cur"]  # NAV tracks the TR index: map by NAV / index on the as-of date
    computed = {"L": ch["L"] * k, "M": ch["M"] * k, "H": ch["H"] * k}
    computed["A"], computed["B"] = cut_points(computed["L"], computed["M"], computed["H"])
    errors += check_against_stated(md, computed, tol=0.01)
    if errors:
        return report(errors)

    # --- Step 2: SOTP cross-check at r_perp — sleeve facts are red lines, the band must match the 对账 row ---
    for leg, names in SLEEVES.items():
        for tier in "lmh":
            gen = sleeve_ratio(inp, names, tier)
            if abs(gen - inp[f"eps_{leg}_{tier}"]) > LEG_TOL:
                errors.append(f"eps_{leg}_{tier}={inp[f'eps_{leg}_{tier}']} != earnings-weighted FY27E/TTM {gen:.4f}")
        errors += ladder(f"eps_{leg}", *(inp[f"eps_{leg}_{t}"] for t in "lmh"))
    cap = g_cap(r)
    # Energy: shared leg (4-name 央企 basket; roe_ene / g2_ene are its joint
    # fixed point, solved in 520900.SH).  This sleeve's own 3-name subset, rolled
    # at the leg's g2 (A14), is the evidence upper end.
    for n in SLEEVES["ene"]:
        if inp["g2_ene"] * (inp[f"{n}_fy26_m"] - inp[f"{n}_h1_26"]) / inp[f"{n}_fy27_m"] >= 1.0:
            errors.append(f"{n}: book roll diverges (g2·N/eps >= 1, A14)")
    if errors:
        return report(errors)
    payout_own, roe_own = leg_policy(inp, SLEEVES["ene"], inp["g2_ene"])
    g_own_raw = (1.0 - payout_own) * roe_own
    if payout_own >= NEAR_FULL_PAYOUT:
        errors.append(f"energy subset pays out {payout_own:.0%} — the retention branch no longer describes it (A2)")
    if abs(inp["g_evid_max"] - min(cap, g_own_raw)) > G2_TOL:
        errors.append(f"g_evid_max {inp['g_evid_max']} != min(cap, 3-name subset (1 - {payout_own:.3f}) x {roe_own:.3f}) = {min(cap, g_own_raw):.4f} (A2)")
    g_ene_raw = (1.0 - inp["payout_ene"]) * inp["roe_ene"]
    if abs(inp["g2_ene"] - min(cap, g_ene_raw)) > G2_TOL:
        errors.append(f"g2_ene {inp['g2_ene']} != min(cap, (1 - payout_ene {inp['payout_ene']}) x roe_ene {inp['roe_ene']}) = {min(cap, g_ene_raw):.4f}")
    if inp["g2_ene"] <= 0:
        errors.append(f"g2_ene {inp['g2_ene']:+.4f} <= 0 is the full-payout branch — the basket pays out {inp['payout_ene']:.0%} (A2)")
    errors += check_branch(inp["g2_ene"], inp["roe_ene"], r, inp["payout_ene"], "g2_ene")
    g_evid_min = (1.0 - inp["idx_dy"] * inp["pe_now"]) * inp["roe_ene"]
    if abs(g_evid_min - inp["g_evid_min"]) > G2_TOL:
        errors.append(f"g_evid_min {inp['g_evid_min']} != (1 - idx_dy x pe_now) x roe_ene = {g_evid_min:.4f} (A2)")
    if not (inp["g_evid_min"] - 1e-9 <= inp["g2_ene"] <= inp["g_evid_max"] + 1e-9):
        errors.append(f"g2_ene {inp['g2_ene']} outside the evidence interval [{inp['g_evid_min']}, {inp['g_evid_max']}] (A2)")
    # Industrial: BLOCKED leg resolved at the named zero-growth reference.  The
    # resolution only stands while the leg still retains AND still shrinks.
    payout_ind, roe_ind = leg_policy(inp, SLEEVES["ind"])
    if abs(payout_ind - inp["payout_ind"]) > LEG_TOL:
        errors.append(f"payout_ind {inp['payout_ind']} != earnings-weighted FY2025 DPS/EPS {payout_ind:.4f}")
    if abs(roe_ind - inp["roe_ind"]) > LEG_TOL:
        errors.append(f"roe_ind {inp['roe_ind']} != earnings-weighted FY27E/BPS {roe_ind:.4f}")
    if inp["g2_ind"] != 0.0:
        errors.append(f"g2_ind {inp['g2_ind']} must be exactly 0: the BLOCKED industrial leg is resolved at the named zero-growth reference (A2)")
    cosco_eps_cagr = (inp["cosco_eps25"] / inp["cosco_eps22"]) ** (1 / 3) - 1
    cosco_dps_cagr = (inp["cosco_dps25"] / inp["cosco_dps22"]) ** (1 / 3) - 1
    retains_ind = inp["payout_ind"] < NEAR_FULL_PAYOUT
    shrinks_ind = inp["eps_ind_m"] < 1.0 and cosco_eps_cagr < 0 and cosco_dps_cagr < 0
    if not (retains_ind and shrinks_ind):
        errors.append(
            f"industrial leg no longer 留存却萎缩 (payout {inp['payout_ind']:.0%}, FY27E/TTM {inp['eps_ind_m']}, "
            f"中远 EPS CAGR {cosco_eps_cagr:+.1%}, DPS CAGR {cosco_dps_cagr:+.1%}) — re-decide the branch (A2)"
        )
    # Generated flat multiples: energy from the shared leg ROE; g2 = 0 legs sit at 1/r.
    for leg, g_key in GORDON_LEGS:
        roe = inp["roe_ene"] if leg == "ene" else 1.0  # g = 0: payout capped, ROE drops out
        pe_gen = perpetual_pe(inp[g_key], roe, r)
        if abs(pe_gen - inp[f"pe_{leg}"]) > PE_TOL:
            errors.append(f"pe_{leg}={inp[f'pe_{leg}']} != perpetual_pe(g={inp[g_key]}, ROE={roe}, r={r}) = {pe_gen:.2f}")
    peer_leg_diff: list[str] = []
    if PEER.exists():
        peer = parse_inputs(PEER.read_text(encoding="utf-8"))
        for key in SHARED_WITH_PEER:
            if key in peer and abs(peer[key] - inp[key]) > 0.2:
                errors.append(f"shared {key}: 513530={inp[key]} 520900={peer[key]}")
        peer_leg_diff = [f"{key} {inp[key]} vs {peer.get(key)}" for key in SHARED_LEG
                         if key not in peer or abs(peer[key] - inp[key]) > 1e-9]
    errors += ladder("cc", inp["cc_l"], inp["cc_m"], inp["cc_h"])
    # China Coal is a look-through of 1898.HK: the copied anchors must track that framework.
    coal = stated_anchors(COAL.read_text(encoding="utf-8"))
    for tier in "LMH":
        said, ref = inp[f"cc_{tier.lower()}"], coal[tier]
        if ref is None or abs(said - ref) > 0.01:
            errors.append(f"cc_{tier.lower()}={said} != 1898.HK stated {tier}={ref} — re-copy from source")
    if errors:
        return report(errors)

    k_hsbc = justified_pb(inp["g2_bank"], inp["roe_hsbc"], r) / inp["pb_hsbc"]
    k_bochk = justified_pb(inp["g2_bank"], inp["roe_bochk"], r) / inp["pb_bochk"]

    def legs(tag: str, cc_h: float | None = None, ind: float | None = None, ene: float | None = None,
             pe_ind: float | None = None, pe_ene: float | None = None) -> dict[str, float]:
        kb, kf, pe_now = inp[f"k_bank_{tag}"], inp[f"k_feh_{tag}"], inp["pe_now"]
        cc = cc_h if (tag == "h" and cc_h is not None) else inp[f"cc_{tag}"]
        m_ind = pe_ind if pe_ind is not None else inp["pe_ind"]
        m_ene = pe_ene if pe_ene is not None else inp["pe_ene"]
        return {
            "hsbc": inp["w_hsbc"] * k_hsbc * kb,
            "bochk": inp["w_bochk"] * k_bochk * kb,
            "feh": inp["w_feh"] * kf,
            "fin_rest": inp["w_fin_rest"] * kb,
            "ind": inp["w_ind"] * (ind if ind is not None else inp[f"eps_ind_{tag}"]) * m_ind / pe_now,
            "ene": inp["w_ene_rest"] * (ene if ene is not None else inp[f"eps_ene_{tag}"]) * m_ene / pe_now,
            "cc": inp["w_cc"] * cc / inp["px_cc"],
            "res": inp["w_res"] * inp[f"eps_res_{tag}"] * inp["pe_res"] / pe_now,
        }

    def anchor(tag: str, **kw: float) -> float:
        return scale(inp["nav_ref"], inp["fee_drag"], sum(legs(tag, **kw).values()))

    def band(pe_ene: float, pe_ind: float) -> tuple[float, float, float]:
        return tuple(anchor(t, pe_ene=pe_ene, pe_ind=pe_ind) for t in "lmh")  # type: ignore[return-value]

    nav = inp["nav_ref"] * inp["fee_drag"]
    sotp = tuple(anchor(t) for t in "lmh")
    if not (sotp[0] < sotp[1] < sotp[2]):
        return report(["SOTP ladder collapsed"])
    said = stated_sotp(md)
    if said is None:
        errors.append("Outputs「对账（袖套 look-through SOTP…）」row missing")
    else:
        errors += [f"对账 {lab}: stated {s_} vs recomputed {g_:.4f}" for lab, g_, s_ in zip("LMH", sotp, said) if abs(g_ - s_) > SOTP_TOL]
    # The energy g2 evidence interval's two ends are printed as bands (A2, 校验步骤 5).
    evid = {g: band(perpetual_pe(g, inp["roe_ene"], r), inp["pe_ind"]) for g in (inp["g_evid_min"], inp["g_evid_max"])}
    if errors:
        return report(errors)

    # --- Step 3: report -------------------------------------------------------
    L, M, H = computed["L"], computed["M"], computed["H"]
    print(f"formula_id={FORMULA_ID}  (对账 {SOTP_FORMULA_ID})")
    print(f"通道 {INDEX_LABEL} ({INDEX_CODE}) {ch['start']}~{ch['end']}: 斜率 {ch['slope']:+.1%} (2019 起 {sub['2019']:+.1%} / 2021 起 {sub['2021']:+.1%}, "
          f"regime gap {max(abs(v - full['slope']) for v in sub.values()):.1%} < {REGIME_GAP:.0%}) · σ {ch['sigma']:.1%} · "
          f"L/M/H idx {ch['L']:,.0f}/{ch['M']:,.0f}/{ch['H']:,.0f}")
    print(f"折算 k = nav_ref {inp['nav_ref']} / idx {ch['cur']:,.1f} = {k:.4e} → L/M/H {L:.4f}/{M:.4f}/{H:.4f}  A {computed['A']:.4f} B {computed['B']:.4f}")
    print(f"L/M {L / M:.3f} | H/M {H / M:.3f} | width {(H - L) / (2 * M):.3f}")
    for start in SUBWINDOWS:
        c2 = channel(s[s.index >= start])
        b2 = tuple(v * k for v in (c2["L"], c2["M"], c2["H"]))
        print(f"敏感性 通道窗改 {start[:4]} 起 (斜率 {c2['slope']:+.1%}): {'/'.join(f'{x:.3f}' for x in b2)} (M {b2[1] / M - 1:+.1%}; 只披露, 不改窗)")
    print(f"E 侧护栏 (只披露): PE {inp['pe_now']} in 1y [{inp['pe_1y_lo']}, {inp['pe_1y_hi']}] · 指数派息率 {inp['idx_dy'] * inp['pe_now']:.1%} (DY {inp['idx_dy']:.1%}) · "
          f"DY 10y p25/med/p75 {inp['dy_10y_p25']:.1%}/{inp['dy_10y_med']:.1%}/{inp['dy_10y_p75']:.1%} · "
          f"look-through 篮 {baskets['r_perp']} r_perp {r:.1%} (P 加权 ≈11.7%, A13) vs 斜率 {ch['slope']:+.1%} · β 先验 {inp['beta_rate_prior']:.0f} ({CCY} 轴待 _AXIS.rates.md)")
    print("地板: 不设 (只披露)")

    print(f"--- 对账 SOTP @ r_perp {r:.0%} (篮 {baskets['r_perp']}): {sotp[0]:.4f}/{sotp[1]:.4f}/{sotp[2]:.4f}")
    print("sleeve FY27E/TTM: ind " + "/".join(f"{sleeve_ratio(inp, SLEEVES['ind'], t):.3f}" for t in "lmh")
          + " | ene " + "/".join(f"{sleeve_ratio(inp, SLEEVES['ene'], t):.3f}" for t in "lmh")
          + f" | HSBC k {k_hsbc:.3f}  BOCHK k {k_bochk:.3f} | flat PE ind/ene/res {inp['pe_ind']}/{inp['pe_ene']}/{inp['pe_res']} vs index {inp['pe_now']}")
    print("成份 (FY2025 DPS/EPS → 派息率; 能源 FY27E ÷ 2027 年初 BPS → ROE, 2Q26 账面按 b1 = g2_ene/ROE 滚过 2H26 未入账 EPS (A14), 工业 FY27E/BPS; 留存分支 g = (1−派息)×ROE):")
    for leg, names in SLEEVES.items():
        w = sleeve_weights(inp, names)
        for n in names:
            pay = inp[f"{n}_dps25"] / inp[f"{n}_eps25"]
            g_roll = inp["g2_ene"] if leg == "ene" else 0.0
            roe = name_roe(inp, n, g_roll)
            g = (1 - pay) * roe
            print(f"  {leg} {n:<10} DPS {inp[f'{n}_dps25']:.4f} / EPS {inp[f'{n}_eps25']:.4f} = {pay:.1%}  ROE {roe:.1%}  g_ret {g:+.2%}"
                  f"{' → clip ' + format(cap, '.0%') if g > cap else ''}  权重 {w[n]:.3f}")
            if leg == "ene":
                n_unbooked = inp[f"{n}_fy26_m"] - inp[f"{n}_h1_26"]
                b1 = g_roll / roe
                print(f"      ROE basis: 2Q26 BPS {inp[f'{n}_bps']:.3f} + 2H26 未入账 {n_unbooked:.3f} (FY26E {inp[f'{n}_fy26_m']:.3f} − 1H26 {inp[f'{n}_h1_26']:.4f}) × b1 {b1:.3f} "
                      f"→ 2027 年初 {inp[f'{n}_bps'] / (1 - g_roll * n_unbooked / inp[f'{n}_fy27_m']):.3f}; 旧口径 ÷ 2Q26 BPS {inp[f'{n}_fy27_m'] / inp[f'{n}_bps']:.1%}; "
                      f"模型视同派出、实际留存 ({1 - pay:.1%} − b1) × N = {((1 - pay) - b1) * n_unbooked:+.3f} 元/股 (只披露)")
    print(f"  腿级 (A14): b1 = g2_ene/roe_ene = {inp['g2_ene'] / inp['roe_ene']:.3f} ≡ 1 − 实付派息率 {1 - inp['payout_ene']:.3f} (g2 由派息政策生成 → 留存去向审计 B 桶在腿级恒为 0); "
          f"四名不动点 roe_ene / g2_ene 由 520900.SH 复算, 本票抄值; 旧口径 (÷ 2Q26 BPS) 子集 ROE_M {leg_policy(inp, SLEEVES['ene'])[1]:.1%}")
    band_pin = "病态区 |ROE−r| < 3pp" if abs(inp["roe_ene"] - r) < 0.03 else ("单调区 ROE > r" if inp["roe_ene"] > r else "峰形区 ROE < r")
    modelled, gap = payout_gap(inp["g2_ene"], inp["roe_ene"], inp["payout_ene"])
    own_mod, own_gap = payout_gap(inp["g2_ene"], roe_own, payout_own)
    print(f"能源腿 (共享腿, 四名央企篮子): 派息率 {inp['payout_ene']:.1%} (< {NEAR_FULL_PAYOUT:.0%} 留存) · ROE_M {inp['roe_ene']:.1%} ({band_pin}) · 共识 TTM→FY27E {inp['eps_ene_m']:.3f} 向上 → 留存分支; "
          f"g2 = (1−{inp['payout_ene']:.3f}) × {inp['roe_ene']:.3f} = {g_ene_raw:+.2%} (cap {cap:.0%} 未触) → PE {perpetual_pe(inp['g2_ene'], inp['roe_ene'], r):.2f}x flat; "
          f"check_branch ✓ 模型派息率 {modelled:.1%} vs 实付 {inp['payout_ene']:.1%} 差 {gap:+.1%}")
    print(f"  本票三名子集 (神华/中海油/中石油): 派息率 {payout_own:.1%} · ROE_M {roe_own:.1%} (单调区) → (1−payout)×ROE = {g_own_raw:+.2%} → 截顶 {min(cap, g_own_raw):+.2%} = g_evid_max; "
          f"共享 g2 在子集 ROE 下模型派息率 {own_mod:.1%} vs 实付 {payout_own:.1%} 差 {own_gap:+.1%} (单调区只做符号, 披露)")
    print(f"  证据区间 [{inp['g_evid_min']:+.2%}, {inp['g_evid_max']:+.2%}]: 下沿 = 930914 指数派息率交叉 {inp['idx_dy']:.1%} × {inp['pe_now']} = {inp['idx_dy'] * inp['pe_now']:.1%} → (1−{inp['idx_dy'] * inp['pe_now']:.3f}) × {inp['roe_ene']:.3f} = {g_evid_min:+.2%}; "
          f"上沿 = 上限 (子集 {g_own_raw:+.2%} 截顶)")
    print(f"  与 520900.SH 腿参数差异 (该票按其篮子 r 生成倍数, 只披露): {'; '.join(peer_leg_diff) if peer_leg_diff else '无'}")
    g_ind_alt = (1 - inp["payout_ind"]) * inp["roe_ind"]
    pe_ind_alt = perpetual_pe(min(cap, g_ind_alt), inp["roe_ind"], r)
    print(f"工业腿 (中远/海丰/重汽): 派息率 {inp['payout_ind']:.1%} 留存 · ROE_M {inp['roe_ind']:.1%} (单调区) · 共识 TTM→FY27E {inp['eps_ind_m']:.3f} 向下 · "
          f"中远 EPS FY22→25 CAGR {cosco_eps_cagr:+.1%} / DPS {cosco_dps_cagr:+.1%} → 留存却萎缩 → BLOCKED:")
    print(f"  全派息分支 (SOTP 旧版 −1.36%): {check_branch(-0.0136, inp['roe_ind'], r, inp['payout_ind'], 'g2_ind')[0].split(': ', 1)[1]}")
    print(f"  留存分支 g = (1−{inp['payout_ind']:.3f}) × {inp['roe_ind']:.3f} = {g_ind_alt:+.2%} → 截顶 {min(cap, g_ind_alt):+.2%} → PE {pe_ind_alt:.2f}x: 方向向下, 过不了同世界门 (裁决顺序 ④) — 只作对照")
    print(f"  → 具名 g2 = 0 (零增长参照, 10x, 对 17.9x 是保守解): 留存用于船队更替不换来稳态增长")
    for tag in "lmh":
        print(f"SOTP {tag.upper()}: " + "  ".join(f"{kk} {v * nav:.4f}" for kk, v in legs(tag).items()) + f"  = {anchor(tag):.4f}")
    cand = (sotp[0], sotp[1], anchor("h", cc_h=inp["cc_h_cand"]))
    regime_l = anchor("l", ind=inp["cosco_ni_l"] / inp["cosco_ni_m"], ene=energy_regime_ratio(inp, "l"))
    print(f"SOTP 候选带 (cc_h → {inp['cc_h_cand']}, 不进主行): {cand[0]:.4f}/{cand[1]:.4f}/{cand[2]:.4f} | "
          f"deep_discount 压力坐标 (报表年 regime: ene {energy_regime_ratio(inp, 'l'):.3f}, ind {inp['cosco_ni_l'] / inp['cosco_ni_m']:.3f}) = {regime_l:.4f} | "
          f"ex-fee H {sotp[2] / inp['fee_drag']:.4f} (对账 H 去掉 QDII 费层, A12)")
    for g, b in evid.items():
        print(f"SOTP 证据区间 g2_ene={g:+.2%} (PE {perpetual_pe(g, inp['roe_ene'], r):.2f}): {'/'.join(f'{x:.3f}' for x in b)}")
    for dg in (-0.01, 0.01):
        g = min(cap, inp["g2_ene"] + dg)
        b = band(perpetual_pe(g, inp["roe_ene"], r), inp["pe_ind"])
        print(f"SOTP 敏感性 g2_ene {dg:+.0%} ({g:+.2%}): {'/'.join(f'{x:.3f}' for x in b)}")
    g_floor = min((1 - inp[f"{n}_dps25"] / inp[f"{n}_eps25"]) * name_roe(inp, n, inp["g2_ene"]) for n in SLEEVES["ene"])
    b = band(perpetual_pe(g_floor, inp["roe_ene"], r), inp["pe_ind"])
    print(f"SOTP 敏感性 单名下限 g2_ene {g_floor:+.2%} (神华, 非腿读数): {'/'.join(f'{x:.3f}' for x in b)}")
    b = band(perpetual_pe(inp["g2_ene"], roe_own, r), inp["pe_ind"])
    print(f"SOTP 敏感性 能源腿改用子集 ROE {roe_own:.1%} ({perpetual_pe(inp['g2_ene'], roe_own, r):.2f}x): {'/'.join(f'{x:.3f}' for x in b)}")
    b = band(inp["pe_ene"], pe_ind_alt)
    print(f"SOTP 敏感性 工业腿改留存分支 {pe_ind_alt:.2f}x: {'/'.join(f'{x:.3f}' for x in b)}")
    b = band(1 / r, 1 / r)
    print(f"SOTP 对照 g=0 全腿 {1 / r:.0f}x: {'/'.join(f'{x:.3f}' for x in b)}")
    # 属性 A: the top-ten earnings-weighted denominator (10.4) on the three pe_now legs.
    top = tuple(scale(inp["nav_ref"], inp["fee_drag"], sum(v * (inp["pe_now"] / 10.4 if kk in ("ind", "ene", "res") else 1.0) for kk, v in legs(t).items())) for t in "lmh")
    print(f"SOTP 对照 pe_now 换前十大盈利加权 10.4 (属性 A 禁用): {'/'.join(f'{x:.3f}' for x in top)}")
    # DDM cross at the ETF level: D0 = TTM distributions per unit; g = weight-blended leg g2.
    g_blend = ((inp["w_hsbc"] + inp["w_bochk"]) * inp["g2_bank"] + inp["w_ene_rest"] * inp["g2_ene"]
               + inp["w_ind"] * inp["g2_ind"] + inp["w_res"] * inp["g2_res"])
    for label, d0 in (("ETF TTM 实派", inp["etf_dps_ttm"]), ("指数股息率×nav_ref", inp["idx_dy"] * inp["nav_ref"])):
        print(f"DDM 对照 ({label} D0 {d0:.4f}): g=0 → {d0 / r:.3f}; g=腿加权 {g_blend:+.2%} (中煤/市价冻结腿计 0) → {d0 * (1 + g_blend) / (r - g_blend):.3f}")
    w_e = sleeve_weights(inp, SLEEVES["ene"])
    pe_leg_now = 1 / sum(w_e[n] / inp[f"{n}_pe"] for n in SLEEVES["ene"])
    g_mkt, ok = implied_g_retaining(pe_leg_now, roe_own, r)
    print(f"成份市价读数 (他股, 09-11): 能源子集 PE {pe_leg_now:.2f}x → 留存分支反解 g {g_mkt:+.2%} (conditioned={ok}) — 低于 1/r 顶, 单调区不可达, 说的是 r 不是 g")
    print(f"OK  L={L:.4f} M={M:.4f} H={H:.4f} A={computed['A']:.4f} B={computed['B']:.4f}"
          f"  (对账 SOTP {sotp[0]:.3f}/{sotp[1]:.3f}/{sotp[2]:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
