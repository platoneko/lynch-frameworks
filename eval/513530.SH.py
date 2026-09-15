#!/usr/bin/env python3
"""513530.SH (Huatai-PB CSI HK Connect High Dividend QDII ETF) eval.

formula_id: huatai_hk_hdy_qdi_sotp_index_pe_v3

Index rolling PE (CSI daily) is the current blend.  HSBC/BOCHK use Gordon
PB-ROE (own ROE, not CMB's).  China Coal is look-through 1898.HK.  Cyclical
sleeves: numerator = constituents' FY2027E consensus three points over TTM,
earnings-weighted (w_k / PE_k) inside the sleeve; multiple = flat Gordon
generated from a named g2 and the leg's forward ROE.  The report-year regime
(energy 2020/2025 equal-weight, shipping 2023/2025) is only the deep_discount
pressure coordinate.  Per-name consensus, payout and the report-year net
profits are shared with 520900.SH.

Branch (valuation-rules「反解分支」, 2026-09-15).  v2 priced the energy and
industrial legs at g2 = -1.11% / -1.36% (flat 9.0x / 8.8x): the 100%-payout,
perpetually-shrinking branch, on baskets whose constituents pay out 45-85% and
retain the rest -- the wrong branch, and check_branch fails it on sign.

  * energy: ONE shared leg with 520900.SH, parameters from the four HK-connect
    SOE majors (神华 / 中海油 / 中石油 / 中石化, earnings-weighted): FY2025 payout
    56.9%, forward ROE 12.9%, consensus TTM -> FY2027E up -> RETENTION branch,
    g2 = +5.56%, PE 12.82x flat.  This sleeve's own 3-name subset (神华 / 中海油 /
    中石油) reads 54.2% / 14.1% -> 6.44% -> clipped 6% = the evidence upper end;
    the lower end is the 930914 index payout cross (5.7% x 11.27 = 64.2%) x ROE
    = 4.61%.  The zone must hold across [4.61%, 6.00%] (校验步骤 4a).
  * industrial (中远 / 海丰 / 重汽): pays out 62% (retains) but the consensus
    reads 2025-26 as the shipping peak (FY27E = 0.92x TTM here, 0.64x for 中远)
    and 中远's realised FY22 -> FY25 EPS / DPS are -33%/yr -- "留存却萎缩", BOTH
    branches contradicted -> BLOCKED.  Resolved at the NAMED zero-growth
    reference g2 = 0 (10x flat); the retention alternative (+8.0% -> clip 6% ->
    17.9x on a 21% ROE) is printed as a cross only.

The price still lands `stretched` on the corrected branch, by 3% instead of
13%: the whole residual gap sits inside the 6% QDII fee drag (A12, A2f).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.etf_lookthrough import scale  # noqa: E402
from lib.gordon import (  # noqa: E402
    G_CAP, NEAR_FULL_PAYOUT, check_branch, check_g_cap, check_r, implied_g_retaining, justified_pb, payout_gap,
    perpetual_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_inputs, report, stated_anchors,
)
from lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "513530.SH.md"
PEER = Path(__file__).resolve().parent.parent / "frameworks" / "520900.SH.md"
COAL = Path(__file__).resolve().parent.parent / "frameworks" / "1898.HK.md"  # China Coal look-through source
FORMULA_ID = "huatai_hk_hdy_qdi_sotp_index_pe_v3"

# Sleeve constituents whose FY2027E consensus builds the sleeve numerator.
SLEEVES = {"ind": ("cosco", "sitc", "sinotruk"), "ene": ("shenhua", "cnooc", "petrochina")}
NAME_FIELDS = ("fy27_l", "fy27_m", "fy27_h", "ttm", "w", "pe")
# FY2025 DPS / basic EPS (one currency per name) and BPS in the fy27 currency (A2).
PAYOUT_FIELDS = ("dps25", "eps25", "bps")
# Report-year regime (pressure coordinate only) — four energy SOEs equal-weighted.
ENERGY_NI = ("shenhua_ni", "cnooc_ni", "petrochina_ni", "sinopec_ni")
SHARED_WITH_PEER = (
    tuple(f"{n}_{f}" for n in ("shenhua", "cnooc", "petrochina", "cosco") for f in ("fy27_l", "fy27_m", "fy27_h", "ttm", "pe"))
    + tuple(f"{n}_{f}" for n in ("shenhua", "cnooc", "petrochina", "cosco") for f in PAYOUT_FIELDS)
    + tuple(f"{k}_{t}" for k in ENERGY_NI for t in "lmh")
    + ("cosco_eps22", "cosco_dps22")
)
# The energy leg is ONE shared leg and the industrial resolution is shared: exact match.
SHARED_EXACT = ("payout_ene", "roe_ene", "g2_ene", "pe_ene", "g2_ind", "pe_ind", "g_evid_min", "g_evid_max")
GORDON_LEGS = (("ind", "g2_ind"), ("ene", "g2_ene"), ("res", "g2_res"))
CANDIDATE_TOL = 0.05
LEG_TOL = 0.005
G2_TOL = 0.0005
PE_TOL = 0.05

REQUIRED = [
    "price", "fee_drag", "pe_now", "r_perp", "g2_bank", "g2_ind", "g2_ene", "g2_res",
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
    *(f"{k}_{t}" for k in ENERGY_NI for t in "lmh"),
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


def leg_policy(inp: dict[str, float], names: tuple[str, ...]) -> tuple[float, float]:
    """(observed payout, forward ROE_M) of a sleeve, earnings-weighted like the numerator.

    payout_k = FY2025 DPS / FY2025 basic EPS (same currency per name);
    ROE_k = FY2027E mean EPS / BPS (same currency per name) -- the M-tier
    forward ROE valuation-rules asks for, so g2 and PE describe the same year
    as the numerator.
    """
    w = sleeve_weights(inp, names)
    payout = sum(w[n] * inp[f"{n}_dps25"] / inp[f"{n}_eps25"] for n in names)
    roe = sum(w[n] * inp[f"{n}_fy27_m"] / inp[f"{n}_bps"] for n in names)
    return payout, roe


def energy_regime_ratio(inp: dict[str, float], tag: str) -> float:
    """Report-year regime: equal-weighted <year>/2025 net-profit ratio of four SOEs."""
    return sum(inp[f"{k}_{tag}"] / inp[f"{k}_m"] for k in ENERGY_NI) / len(ENERGY_NI)


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
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
    r = inp["r_perp"]
    errors += check_r(r, "r_perp")
    if r != 0.10:
        errors.append("r_perp must be 0.10 (operating legs)")
    errors += check_g_cap(inp["g2_bank"], "g2_bank")
    for _, g_key in GORDON_LEGS:
        errors += check_g_cap(inp[g_key], g_key)

    # --- Step 1: sleeve numerators from the constituents ----------------------
    for leg, names in SLEEVES.items():
        for tier in "lmh":
            gen = sleeve_ratio(inp, names, tier)
            if abs(gen - inp[f"eps_{leg}_{tier}"]) > LEG_TOL:
                errors.append(f"eps_{leg}_{tier}={inp[f'eps_{leg}_{tier}']} != earnings-weighted FY27E/TTM {gen:.4f}")
        errors += ladder(f"eps_{leg}", *(inp[f"eps_{leg}_{t}"] for t in "lmh"))

    # --- Step 2: branch per Gordon leg (A2) -----------------------------------
    # Energy: shared leg (4-name 央企 basket, values cross-checked against the
    # peer file below).  This sleeve's own 3-name subset is the evidence upper end.
    payout_own, roe_own = leg_policy(inp, SLEEVES["ene"])
    g_own_raw = (1.0 - payout_own) * roe_own
    if payout_own >= NEAR_FULL_PAYOUT:
        errors.append(f"energy subset pays out {payout_own:.0%} — the retention branch no longer describes it (A2)")
    if abs(inp["g_evid_max"] - min(G_CAP, g_own_raw)) > G2_TOL:
        errors.append(f"g_evid_max {inp['g_evid_max']} != min(cap, 3-name subset (1 - {payout_own:.3f}) x {roe_own:.3f}) = {min(G_CAP, g_own_raw):.4f} (A2)")
    g_ene_raw = (1.0 - inp["payout_ene"]) * inp["roe_ene"]
    if abs(inp["g2_ene"] - min(G_CAP, g_ene_raw)) > G2_TOL:
        errors.append(f"g2_ene {inp['g2_ene']} != min(cap, (1 - payout_ene {inp['payout_ene']}) x roe_ene {inp['roe_ene']}) = {min(G_CAP, g_ene_raw):.4f}")
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
    if PEER.exists():
        peer = parse_inputs(PEER.read_text(encoding="utf-8"))
        for k in SHARED_WITH_PEER:
            if k in peer and abs(peer[k] - inp[k]) > 0.2:
                errors.append(f"shared {k}: 513530={inp[k]} 520900={peer[k]}")
        for k in SHARED_EXACT:
            if k not in peer or abs(peer[k] - inp[k]) > 1e-9:
                errors.append(f"shared leg {k}: 513530={inp[k]} 520900={peer.get(k)} — one leg, one value (A2)")
    errors += ladder("cc", inp["cc_l"], inp["cc_m"], inp["cc_h"])
    # China Coal is a look-through of 1898.HK: the copied anchors must track that framework.
    coal = stated_anchors(COAL.read_text(encoding="utf-8"))
    for tier in "LMH":
        said, ref = inp[f"cc_{tier.lower()}"], coal[tier]
        if ref is None or abs(said - ref) > 0.01:
            errors.append(f"cc_{tier.lower()}={said} != 1898.HK stated {tier}={ref} — re-copy from source")
    if errors:
        return report(errors)

    # --- Step 3: anchors --------------------------------------------------------
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
        return scale(inp["price"], inp["fee_drag"], sum(legs(tag, **kw).values()))

    def band(pe_ene: float, pe_ind: float) -> tuple[float, float, float]:
        return tuple(anchor(t, pe_ene=pe_ene, pe_ind=pe_ind) for t in "lmh")  # type: ignore[return-value]

    nav = inp["price"] * inp["fee_drag"]
    computed = {t.upper(): anchor(t) for t in "lmh"}
    if not (computed["L"] < computed["M"] < computed["H"]):
        return report(["ladder collapsed"])
    A, B = cut_points(computed["L"], computed["M"], computed["H"])
    computed["A"], computed["B"] = A, B
    zone = zone_of(inp["price"], computed["L"], computed["M"], computed["H"])
    errors = check_against_stated(md, computed, zone, tol=0.01)
    # 校验步骤 4a: the zone must hold across the energy g2 evidence interval.
    evid = {g: band(perpetual_pe(g, inp["roe_ene"], r), inp["pe_ind"]) for g in (inp["g_evid_min"], inp["g_evid_max"])}
    for g, b in evid.items():
        if zone_of(inp["price"], *b) != zone:
            errors.append(f"zone flips to {zone_of(inp['price'], *b)} at g2_ene={g:+.2%} inside the evidence interval — BLOCKED (A2)")
    # A2e-7h candidate band: same formula, only cc_h swapped for the single-source cc_h_cand.
    cand = (computed["L"], computed["M"], anchor("h", cc_h=inp["cc_h_cand"]))
    stated_cand = stated_candidate(md)
    if stated_cand is None:
        errors.append("candidate band row missing (A2e-7h)")
    else:
        for lab, got, said in zip("LMH", cand, stated_cand):
            if abs(got - said) > CANDIDATE_TOL:
                errors.append(f"candidate {lab}′: stated {said} vs recomputed {got:.4f}")
    if errors:
        return report(errors)

    # --- report -----------------------------------------------------------------
    L, M, H = computed["L"], computed["M"], computed["H"]
    regime_l = anchor("l", ind=inp["cosco_ni_l"] / inp["cosco_ni_m"], ene=energy_regime_ratio(inp, "l"))
    print(f"formula_id={FORMULA_ID}")
    print("sleeve FY27E/TTM: ind " + "/".join(f"{sleeve_ratio(inp, SLEEVES['ind'], t):.3f}" for t in "lmh")
          + " | ene " + "/".join(f"{sleeve_ratio(inp, SLEEVES['ene'], t):.3f}" for t in "lmh")
          + f" | HSBC k {k_hsbc:.3f}  BOCHK k {k_bochk:.3f} | flat PE ind/ene/res {inp['pe_ind']}/{inp['pe_ene']}/{inp['pe_res']} vs index {inp['pe_now']}")
    print("成份 (FY2025 DPS/EPS → 派息率; FY27E/BPS → ROE; 留存分支 g = (1−派息)×ROE):")
    for leg, names in SLEEVES.items():
        w = sleeve_weights(inp, names)
        for n in names:
            pay = inp[f"{n}_dps25"] / inp[f"{n}_eps25"]
            roe = inp[f"{n}_fy27_m"] / inp[f"{n}_bps"]
            g = (1 - pay) * roe
            print(f"  {leg} {n:<10} DPS {inp[f'{n}_dps25']:.4f} / EPS {inp[f'{n}_eps25']:.4f} = {pay:.1%}  ROE {roe:.1%}  g_ret {g:+.2%}"
                  f"{' → clip ' + format(G_CAP, '.0%') if g > G_CAP else ''}  权重 {w[n]:.3f}")
    band_pin = "病态区 |ROE−r| < 3pp" if abs(inp["roe_ene"] - r) < 0.03 else ("单调区 ROE > r" if inp["roe_ene"] > r else "峰形区 ROE < r")
    modelled, gap = payout_gap(inp["g2_ene"], inp["roe_ene"], inp["payout_ene"])
    own_mod, own_gap = payout_gap(inp["g2_ene"], roe_own, payout_own)
    print(f"能源腿 (共享腿, 四名央企篮子): 派息率 {inp['payout_ene']:.1%} (< {NEAR_FULL_PAYOUT:.0%} 留存) · ROE_M {inp['roe_ene']:.1%} ({band_pin}) · 共识 TTM→FY27E {inp['eps_ene_m']:.3f} 向上 → 留存分支; "
          f"g2 = (1−{inp['payout_ene']:.3f}) × {inp['roe_ene']:.3f} = {g_ene_raw:+.2%} (cap {G_CAP:.0%} 未触) → PE {perpetual_pe(inp['g2_ene'], inp['roe_ene'], r):.2f}x flat; "
          f"check_branch ✓ 模型派息率 {modelled:.1%} vs 实付 {inp['payout_ene']:.1%} 差 {gap:+.1%}")
    print(f"  本票三名子集 (神华/中海油/中石油): 派息率 {payout_own:.1%} · ROE_M {roe_own:.1%} (单调区) → (1−payout)×ROE = {g_own_raw:+.2%} → 截顶 {min(G_CAP, g_own_raw):+.2%} = g_evid_max; "
          f"共享 g2 在子集 ROE 下模型派息率 {own_mod:.1%} vs 实付 {payout_own:.1%} 差 {own_gap:+.1%} (单调区只做符号, 披露)")
    print(f"  证据区间 [{inp['g_evid_min']:+.2%}, {inp['g_evid_max']:+.2%}]: 下沿 = 930914 指数派息率交叉 {inp['idx_dy']:.1%} × {inp['pe_now']} = {inp['idx_dy'] * inp['pe_now']:.1%} → (1−{inp['idx_dy'] * inp['pe_now']:.3f}) × {inp['roe_ene']:.3f} = {g_evid_min:+.2%}; "
          f"上沿 = 上限 (子集 {g_own_raw:+.2%} 截顶)")
    print(f"  PE(g) 在 ROE {inp['roe_ene']:.1%} 下: g 0/2/4/6% → {perpetual_pe(0, inp['roe_ene'], r):.2f}/{perpetual_pe(0.02, inp['roe_ene'], r):.2f}/"
          f"{perpetual_pe(0.04, inp['roe_ene'], r):.2f}/{perpetual_pe(0.06, inp['roe_ene'], r):.2f}x — 病态区边缘, 倍数未钉死, 故靠证据区间 zone 稳定性定案")
    g_ind_alt = (1 - inp["payout_ind"]) * inp["roe_ind"]
    pe_ind_alt = perpetual_pe(min(G_CAP, g_ind_alt), inp["roe_ind"], r)
    print(f"工业腿 (中远/海丰/重汽): 派息率 {inp['payout_ind']:.1%} 留存 · ROE_M {inp['roe_ind']:.1%} (单调区) · 共识 TTM→FY27E {inp['eps_ind_m']:.3f} 向下 · "
          f"中远 EPS FY22→25 CAGR {cosco_eps_cagr:+.1%} / DPS {cosco_dps_cagr:+.1%} → 留存却萎缩 → BLOCKED:")
    print(f"  全派息分支 (v2 −1.36%): {check_branch(-0.0136, inp['roe_ind'], r, inp['payout_ind'], 'g2_ind')[0].split(': ', 1)[1]}")
    print(f"  留存分支 g = (1−{inp['payout_ind']:.3f}) × {inp['roe_ind']:.3f} = {g_ind_alt:+.2%} → 截顶 {min(G_CAP, g_ind_alt):+.2%} → PE {pe_ind_alt:.2f}x: 方向向下, 过不了同世界门 (裁决顺序 ④) — 只作对照")
    print(f"  → 具名 g2 = 0 (零增长参照, 10x, 对 17.9x 是保守解): 留存用于船队更替不换来稳态增长; check_branch(0) 仍标『留存』= BLOCKED 的记录, 非红线")
    for tag in "lmh":
        print(f"{tag.upper()}: " + "  ".join(f"{k} {v * nav:.4f}" for k, v in legs(tag).items()) + f"  = {computed[tag.upper()]:.4f}")
    # Multiples are flat and the PB-ROE k is tier-invariant, so the flat-multiple
    # ladder (A2e-2c) is the base ladder itself: every tier step is a numerator step.
    print(f"flat-multiple ladder = base ladder (flat pe, tier-invariant k): {L:.4f}/{M:.4f}/{H:.4f}")
    print(f"候选带 (cc_h → {inp['cc_h_cand']}): {cand[0]:.4f}/{cand[1]:.4f}/{cand[2]:.4f} | "
          f"deep_discount 压力坐标 (报表年 regime: ene {energy_regime_ratio(inp, 'l'):.3f}, ind {inp['cosco_ni_l'] / inp['cosco_ni_m']:.3f}) = {regime_l:.4f}")
    print(
        f"L/M {L / M:.3f} = num {L / M:.3f} x pe 1.000 | H/M {H / M:.3f} = num {H / M:.3f} x pe 1.000 | "
        f"width {(H - L) / (2 * M):.3f} | V_opt/M 0.000 | "
        f"market-frozen at M: {inp['w_feh'] + inp['w_fin_rest']:.1%} of basket | all-at-market ref {nav:.4f} | ex-fee H {H / inp['fee_drag']:.4f}"
    )
    for g, b in evid.items():
        print(f"证据区间 g2_ene={g:+.2%} (PE {perpetual_pe(g, inp['roe_ene'], r):.2f}): {'/'.join(f'{x:.3f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    for dg in (-0.01, 0.01):
        g = min(G_CAP, inp["g2_ene"] + dg)
        b = band(perpetual_pe(g, inp["roe_ene"], r), inp["pe_ind"])
        print(f"敏感性 g2_ene {dg:+.0%} ({g:+.2%}): {'/'.join(f'{x:.3f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    g_floor = min((1 - inp[f"{n}_dps25"] / inp[f"{n}_eps25"]) * inp[f"{n}_fy27_m"] / inp[f"{n}_bps"] for n in SLEEVES["ene"])
    b = band(perpetual_pe(g_floor, inp["roe_ene"], r), inp["pe_ind"])
    print(f"敏感性 单名下限 g2_ene {g_floor:+.2%} (神华, 非腿读数): {'/'.join(f'{x:.3f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    b = band(perpetual_pe(inp["g2_ene"], roe_own, r), inp["pe_ind"])
    print(f"敏感性 能源腿改用子集 ROE {roe_own:.1%} ({perpetual_pe(inp['g2_ene'], roe_own, r):.2f}x): {'/'.join(f'{x:.3f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    b = band(inp["pe_ene"], pe_ind_alt)
    print(f"敏感性 工业腿改留存分支 {pe_ind_alt:.2f}x: {'/'.join(f'{x:.3f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    b = band(10.0, 10.0)
    print(f"对照 g=0 全腿 10x: {'/'.join(f'{x:.3f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    b = band(9.0, 8.8)
    print(f"对照 v2 全派息分支 (ene −1.11% → 9.0x, ind −1.36% → 8.8x, 现行其它输入): {'/'.join(f'{x:.3f}' for x in b)} zone={zone_of(inp['price'], *b)} (分支错误的坐标)")
    b = band(inp["pe_now"], inp["pe_now"])
    print(f"对照 周期腿按市场滚动 {inp['pe_now']}x: {'/'.join(f'{x:.3f}' for x in b)} zone={zone_of(inp['price'], *b)}")
    # 属性 A: the top-ten earnings-weighted denominator (10.4) on the three pe_now legs.
    top = tuple(scale(inp["price"], inp["fee_drag"], sum(v * (inp["pe_now"] / 10.4 if k in ("ind", "ene", "res") else 1.0) for k, v in legs(t).items())) for t in "lmh")
    print(f"对照 pe_now 换前十大盈利加权 10.4 (属性 A 禁用): {'/'.join(f'{x:.3f}' for x in top)} zone={zone_of(inp['price'], *top)}")
    # DDM cross at the ETF level: D0 = TTM distributions per unit; g = weight-blended leg g2.
    g_blend = ((inp["w_hsbc"] + inp["w_bochk"]) * inp["g2_bank"] + inp["w_ene_rest"] * inp["g2_ene"]
               + inp["w_ind"] * inp["g2_ind"] + inp["w_res"] * inp["g2_res"])
    for label, d0 in (("ETF TTM 实派", inp["etf_dps_ttm"]), ("指数股息率×NAV", inp["idx_dy"] * inp["price"])):
        g_px = (inp["price"] * r - d0) / (inp["price"] + d0)
        print(f"DDM 对照 ({label} D0 {d0:.4f}): g=0 → {d0 / r:.3f}; g=腿加权 {g_blend:+.2%} (中煤/市价冻结腿计 0) → {d0 * (1 + g_blend) / (r - g_blend):.3f}; "
              f"现价 {inp['price']} 隐含股息增长 {g_px:+.2%}")
    w_e = sleeve_weights(inp, SLEEVES["ene"])
    pe_leg_now = 1 / sum(w_e[n] / inp[f"{n}_pe"] for n in SLEEVES["ene"])
    g_mkt, ok = implied_g_retaining(pe_leg_now, roe_own, r)
    print(f"市价读数: 能源子集现 PE {pe_leg_now:.2f}x → 留存分支反解 g {g_mkt:+.2%} (conditioned={ok}) — 低于 10x 顶, 单调区不可达, 说的是 r 不是 g (循环: 反解对象是篮子自身)")
    print(f"OK  L={L:.4f} M={M:.4f} H={H:.4f} A={A:.4f} B={B:.4f}  zone={zone}  price={inp['price']}"
          + (f"  P/H {inp['price'] / H:.3f}  P/H′ {inp['price'] / cand[2]:.3f}  P/(H÷fee) {inp['price'] / (H / inp['fee_drag']):.3f}" if zone == "stretched" else ""))
    return 0


def stated_candidate(md: str) -> tuple[float, float, float] | None:
    import re
    m = re.search(r"候选带（[^）]+）[^\n]*?L′\s*=\s*\*\*([0-9.]+)\*\*[^\n]*?M′\s*=\s*\*\*([0-9.]+)\*\*[^\n]*?H′\s*=\s*\*\*([0-9.]+)\*\*", md)
    return tuple(float(x) for x in m.groups()) if m else None


if __name__ == "__main__":
    raise SystemExit(main())
