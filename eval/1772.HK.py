#!/usr/bin/env python3
"""1772.HK (Ganfeng Lithium H) valuation eval.

frameworks/1772.HK.md is the source of truth; this script re-derives the
anchors, candidate band and V_opt from its §3 Inputs table and exits 1 on
mismatch.  The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so
nothing here computes a zone for the price or a market-implied reading — the
digest and the app zone on live quotes.
formula_id: ganfeng_li2co3_twopoint_batt_pe10_v3_gordon_v4

Ganfeng does not disclose lithium sales volumes or its self-supplied feed
share, so the lithium leg (salts + mining + JV share, all inside the reported
segment results) is not built bottom-up.  Its pre-tax profit is a straight
line through two of the company's own realised half-years -- 2025H1 at the
cycle trough and 2026H1 on the 2026 platform -- read at the shared Li2CO3 axis
rungs.  The base deck keeps the line's own 2026H1 volume structure (2026E
23 万吨 is a two-house consensus and matches it); the sell-side 2027E volume
(27 万吨, single house) is NOT in the base deck -- it is the candidate band
(A2e-7h): the same formula with the leg scaled by vol_2027e/vol_2026e and
discounted one year.  The battery leg is its annualised segment result
(current, undiscounted).  The first V_opt component is
solid-state (valuation-rules「未建模期权」2026-10-05: a pre-revenue leg takes
peers' unit economics through a peer-ruler axis, never 0 or a snapshot): no
sell-side quantity exists for Ganfeng's solid-state, so only the H tier is
sized (p_L = p_M = 0, 分档 rule) -- the named Chongqing 20 GWh base at full capacity x the steady-state
price on _AXIS.solid-state-battery (东吴 path far end, 0.8 元/Wh), at the
axis H margin (adjacent liquid-cell layer: CATL measured less an entrant
discount), on the project's own ROE (budget as capital) with the axis g2,
realised 2029 (aligned year 2027 + 2, no named date) and discounted back to
the numerator year 2026 at the basket r; L / M carry p = 0.  The second
component is volume growth beyond the base, sized ONLY from the company's own
named quantity (valuation-rules「未建模期权」, 2026-10-03): the 2030 design
capacity target 60 万吨 vs today's ~30 万吨 nameplate = one more 2026
structure, read on the two-point line at the axis M rung (unit economics of
this ticker's own lithium leg), valued at this ticker's own post-realisation
multiple and discounted 2030 -> 2026 (A12).  Both components are new
capacity, so each nets out this ticker's equity share of the capital not yet
spent (valuation-rules「未建模期权」2026-10-04; budget less spent, spread
evenly over t_num+1 .. realisation year and discounted at the basket r):
solid-state = the Chongqing 20 GWh solid-state base (budget 96 亿, 12.5%
spent, 64.52% via Ganfeng LiEnergy); volume = PPGS stage 1 (67%) + Cauchari
stage 2 (46.67%, RIGI amount) + the unnamed remainder of the 30 万吨 increment
at the company's own Fengcheng conversion budget per ton (A9 / A12).  Per-tier credits for both
components are hard-coded here and never enter Inputs (A2e-7a); a
value-weighted blend is also stated in the doc for the daily digest, which
only reads one p triple.

Multiples: Gordon at the leg's basket r (篮 6 周期商品, both legs share it,
A14) with ONE flat g2 = the commodity-leg tier default 0 (§13: lithium's
long-run real price drift is negative, not taken below zero; the peer
cross-section value is withdrawn, A7), tier ROE = EPS_HKD / BPS; at g = 0 the
multiple is 1/r on every tier.  The axis 永续 g2 row is referenced verbatim
(`axis_g2_li`) and superseded.  The L tier is the axis L regime, not the
company's realised trough (FY2024 loss); `recovery_two_stage_pe` on the
measured path (FY2025 17.63 亿 HKD -> 2026H1 x 2) is printed as a coordinate
only.  The PB 0.70 floor (realised at the 2025-04-08 low) is DISCLOSED, never
max()-ed into L: an asset number that does not move with r has no place inside
an earnings ruler that shrinks with it (A8).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_LI2CO3, axis_path, check_li2co3_mount, load_axis_g2  # noqa: E402
from lib.gordon import check_g_cap, check_r, implied_g, perpetual_pe, recovery_two_stage_pe  # noqa: E402
from lib.inputs import check_against_stated, outputs_section, parse_baskets, parse_inputs  # noqa: E402
from lib.tiers import report as tier_report  # noqa: E402
from lib.zones import zone_of  # noqa: E402

# rf_report / bands_io import through the `eval.lib` package, so the repo root
# must be importable too; appended so `lib.*` above still resolves first.
sys.path.append(str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "1772.HK.md"
FORMULA_ID = "ganfeng_li2co3_twopoint_batt_pe10_v3_gordon_v4"
TOL = 0.05
MIN_R_MINUS_G = 0.02
# The single perpetual r leg (both business legs share the basket, A14); r_disc
# is the same number by construction but is a discount input, not a leg.
LEG_R = ("r_perp",)
# Peer-ruler axis for the solid-state leg: shared rows must match it verbatim.
SSB_AXIS = axis_path("_AXIS.solid-state-battery")
SSB_SHARED = ("ssb_px_ss", "ssb_px_2029", "ssb_px_2030", "ssb_opm_weak", "ssb_opm_strong",
              "ssb_entrant_disc", "g2_ssb_src")
# _AXIS.rates segment: HKD rides the USD r_f via the peg (valuation-rules「按上市货币取段」).
LISTING_CCY = "HKD"

# Per-tier option credits (A9).  valuation-rules「未建模期权」分档 (2026-10-05):
# an item with no sell-side quantity for this ticker enters H only, p_L = p_M = 0.
# Solid-state has none (no house sizes Ganfeng's solid-state) -> 0 / 0 / 1.
# Volume keeps its L/M: the lithium leg does carry sell-side volume (大华 2027E,
# single house); its p_M 0.25 is a judgement call (no probability anchor).
P_SS = {"l": 0.0, "m": 0.0, "h": 1.0}
P_VOL = {"l": 0.0, "m": 0.25, "h": 1.0}
# A13: the company's own realised trough→recovery path (Longbridge annual parent NI,
# HKD: FY2024 −22.45 亿 loss trough; FY2025 17.63 亿 → 2026H1 42.6 亿 CNY × 2 × fx).
RECOVERY_MEASURED = {"FY2025→2026H1×2": (17.63, 42.6 * 2 * 1.136, 1)}

REQUIRED = [
    "shares", "bps", "fx_hkd_per_cny",
    "li2co3_l", "li2co3_m", "li2co3_h",
    "cal_p0", "cal_li_pretax_0", "cal_p1", "cal_li_pretax_1",
    "vol_2026e", "vol_2027e", "cap_now", "cap_2030", "r_disc", "n_disc",
    "t_num", "t_opt_ss", "t_opt_vol",
    "ss_k", "ss_eq", "ss_cap_gwh", "ss_budget", "g2_ssb", *SSB_SHARED, "ppg_k", "ppg_eq", "cau_k_usd", "cau_eq", "fx_cny_per_usd",
    "cap_ppg1", "cap_cau2", "conv_k_per_wt", "ppg23_k_usd",
    "batt_pretax", "net_finance",
    "tax_rate", "nci_share",
    "r_perp", "g2", "axis_g2_li",
    "pe_own_min", "pe_own_max", "pb_floor",
]


def num(s: str) -> float:
    """Doc numbers may carry a U+2212 minus."""
    return float(s.replace("−", "-"))


def first_float(pattern: str, md: str) -> float | None:
    m = re.search(pattern, md)
    return float(m.group(1)) if m else None


def parent_from_pretax(pretax: float, inp: dict[str, float]) -> float:
    return pretax * (1.0 - inp["tax_rate"]) * (1.0 - inp["nci_share"])


def per_share_hkd(parent_yi: float, inp: dict[str, float]) -> float:
    """亿 CNY → HKD per share (shares in millions)."""
    return parent_yi * 100.0 / inp["shares"] * inp["fx_hkd_per_cny"]


def vol_scale(inp: dict[str, float]) -> float:
    """Candidate band only: 2027E/2026E sales ratio (single house), discounted one year (A11)."""
    disc = (1.0 + inp["r_disc"]) ** (-inp["n_disc"])
    return inp["vol_2027e"] / inp["vol_2026e"] * disc


def li_2026(inp: dict[str, float], li2co3: float) -> float:
    """Lithium-leg pre-tax at 2026H1 volume structure, 亿 CNY (the raw two-point line)."""
    slope = (inp["cal_li_pretax_1"] - inp["cal_li_pretax_0"]) / (
        inp["cal_p1"] - inp["cal_p0"]
    )
    return inp["cal_li_pretax_0"] + (li2co3 - inp["cal_p0"]) * slope


def option_share(inp: dict[str, float]) -> float:
    """Shares of the 2026 structure in the named 2030 design-capacity target (A12, 7c-1)."""
    return (inp["cap_2030"] - inp["cap_now"]) / inp["cap_now"]


def disc_to_num(inp: dict[str, float], t_opt: float) -> float:
    """Realisation year -> numerator year (2026 structure) at the basket r (7c-1 时点)."""
    return (1.0 + inp["r_disc"]) ** (-(t_opt - inp["t_num"]))


def post_pe(inp: dict[str, float], eps_h: float, d_eps: float) -> float:
    """This ticker's own ruler after realisation: Gordon at the H-tier ROE plus the increment."""
    return perpetual_pe(inp["g2"], (eps_h + d_eps) / inp["bps"], inp["r_perp"])


def disc_spread(inp: dict[str, float], t_opt: float) -> float:
    """Unspent capital spread evenly over t_num+1 .. t_opt, each tranche discounted to t_num (A9 / A12)."""
    years = range(int(inp["t_num"]) + 1, int(t_opt) + 1)
    return sum((1.0 + inp["r_disc"]) ** (-(t - inp["t_num"])) for t in years) / len(years)


def ss_tier(inp: dict[str, float], opm: float, px: float | None = None, g2: float | None = None) -> dict[str, float]:
    """Solid-state option at full capacity (A9): 20 GWh x price x margin, project ROE on the budget,
    valued in t_opt_ss on this ticker's r (ROE <= r -> 1/r; else Gordon at the axis g2),
    discounted to t_num, less the equity share of unspent capital spread 2027..t_opt_ss."""
    px = inp["ssb_px_ss"] if px is None else px
    g = inp["g2_ssb"] if g2 is None else g2
    rev = inp["ss_cap_gwh"] * px * 10.0  # GWh x 元/Wh -> 亿 CNY
    pretax = rev * opm
    ni = pretax * (1.0 - inp["tax_rate"])
    roe = ni / inp["ss_budget"]
    pe = perpetual_pe(g, roe, inp["r_perp"]) if roe > inp["r_perp"] else 1.0 / inp["r_perp"]
    eps = per_share_hkd(ni * inp["ss_eq"], inp)
    gross = eps * pe * disc_to_num(inp, inp["t_opt_ss"])
    net = gross - k_ps(inp, inp["ss_k"] * inp["ss_eq"], inp["t_opt_ss"])
    return {"rev": rev, "pretax": pretax, "roe": roe, "pe": pe, "eps": eps, "gross": gross, "net": net}


def k_vol_parts(inp: dict[str, float]) -> dict[str, float]:
    """Equity share of unspent capital behind the 30 万吨 increment, 亿 CNY (A12)."""
    rest = inp["cap_2030"] - inp["cap_now"] - inp["cap_ppg1"] - inp["cap_cau2"]
    return {
        "ppg1": inp["ppg_k"] * inp["ppg_eq"],
        "cau2": inp["cau_k_usd"] / 100.0 * inp["fx_cny_per_usd"] * inp["cau_eq"],
        "rest": rest * inp["conv_k_per_wt"],
    }


def k_ps(inp: dict[str, float], k_yi: float, t_opt: float, spread: bool = True) -> float:
    """Unspent capital 亿 CNY -> HKD/share at the numerator year."""
    d = disc_spread(inp, t_opt) if spread else disc_to_num(inp, t_opt)
    return per_share_hkd(k_yi * d, inp)


def v_opt_vol_gross(inp: dict[str, float], li2co3: float, eps_h: float) -> float:
    """Named 2030 capacity target beyond today's nameplate, read at the given rung, discounted (A12)."""
    d_eps = per_share_hkd(parent_from_pretax(li_2026(inp, li2co3) * option_share(inp), inp), inp)
    return d_eps * post_pe(inp, eps_h, d_eps) * disc_to_num(inp, inp["t_opt_vol"])


def v_opt_vol(inp: dict[str, float], li2co3: float, eps_h: float) -> float:
    """Gross volume option less the equity share of unspent capital (2026-10-04 rule)."""
    return v_opt_vol_gross(inp, li2co3, eps_h) - k_ps(inp, sum(k_vol_parts(inp).values()), inp["t_opt_vol"])


def scenario(inp: dict[str, float], tag: str, scale: float = 1.0, g2: float | None = None) -> dict[str, float]:
    """Base deck: scale = 1.0 (the line's own 2026 volume structure).  Candidate: vol_scale."""
    g = inp["g2"] if g2 is None else g2
    li = li_2026(inp, inp[f"li2co3_{tag}"]) * scale
    pretax = li + inp["batt_pretax"] - inp["net_finance"]
    parent = parent_from_pretax(pretax, inp)
    eps = per_share_hkd(parent, inp)
    roe = eps / inp["bps"]
    pe = perpetual_pe(g, roe, inp["r_perp"])
    return {"li": li, "pretax": pretax, "parent": parent, "eps": eps, "roe": roe, "pe": pe, "px": eps * pe}


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    missing = [k for k in REQUIRED if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1

    errors: list[str] = []
    if not (inp["li2co3_l"] < inp["li2co3_m"] < inp["li2co3_h"]):
        errors.append("li2co3 ladder violated")
    # valuation-rules「§r 篮子」/「永续增长口径」: r is the named basket's value, one
    # flat g2 ≤ cap(r); the axis row is referenced verbatim and superseded.
    baskets = parse_baskets(md)
    for field in LEG_R:
        if field not in baskets:
            errors.append(f"{field}: no 篮 N in Inputs source cell (A14)")
        errors += check_r(inp[field], field, baskets.get(field))
        errors += check_g_cap(inp["g2"], inp[field], f"g2@{field}")
        errors += check_g_cap(inp["axis_g2_li"], inp[field], f"axis_g2_li@{field}")
        if inp[field] - inp["g2"] < MIN_R_MINUS_G:
            errors.append(f"{field} − g2 = {inp[field] - inp['g2']:.4f} < {MIN_R_MINUS_G} (pole)")
    # The candidate band / volume option discount at the same basket r as the leg (A14).
    if abs(inp["r_disc"] - inp["r_perp"]) > 1e-9:
        errors.append(f"r_disc={inp['r_disc']} must equal the leg's basket r r_perp={inp['r_perp']} (A14)")
    want_axis = load_axis_g2(AXIS_LI2CO3)
    if abs(inp["axis_g2_li"] - want_axis) > 1e-9:
        errors.append(f"axis_g2_li={inp['axis_g2_li']} vs _AXIS.lithium-carbonate 永续 g2 {want_axis}")
    if not (inp["cal_p0"] < inp["cal_p1"] and inp["cal_li_pretax_0"] < inp["cal_li_pretax_1"]):
        errors.append("calibration points must be ordered (trough below platform)")
    if not inp["vol_2027e"] > inp["vol_2026e"]:
        errors.append("2027E volume must exceed 2026E (the candidate scale is a growth factor)")
    if not inp["cap_2030"] > inp["cap_now"]:
        errors.append("2030 capacity target must exceed today's nameplate (V_opt share)")
    if not inp["cap_2030"] - inp["cap_now"] - inp["cap_ppg1"] - inp["cap_cau2"] >= 0:
        errors.append("named brine capacity exceeds the 30 万吨 increment (A12)")
    if SSB_AXIS.exists():
        peer = parse_inputs(SSB_AXIS.read_text(encoding="utf-8"))
        for k in SSB_SHARED:
            if k not in peer or abs(inp[k] - peer[k]) > 1e-9:
                errors.append(f"{k} {inp[k]:g} != _AXIS.solid-state-battery {peer.get(k)} — the leg ruler drifted")
    else:
        errors.append("frameworks/axes/solid-state-battery.md missing — leg ruler unchecked")
    errors += check_g_cap(inp["g2_ssb"], inp["r_perp"], "g2_ssb")
    if abs(inp["g2_ssb"] - min(inp["g2_ssb_src"], 0.06)) > 1e-9:
        errors.append(f"g2_ssb {inp['g2_ssb']} must be the axis source {inp['g2_ssb_src']} capped at G_cap 6%")
    if abs(inp["ss_k"] - inp["ss_budget"] * (1.0 - 0.125)) > 0.01:
        errors.append("ss_k must equal ss_budget x (1 − 12.50% spent)")
    if not all(0.0 < inp[k] <= 1.0 for k in ("ss_eq", "ppg_eq", "cau_eq")):
        errors.append("equity shares must lie in (0, 1]")
    if not (inp["t_opt_ss"] > inp["t_num"] and inp["t_opt_vol"] > inp["t_num"]):
        errors.append("option realisation years must not precede the numerator year")
    errors += check_li2co3_mount(
        (inp["li2co3_l"], inp["li2co3_m"], inp["li2co3_h"])
    )
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    S = {t: scenario(inp, t) for t in ("l", "m", "h")}
    pe_l, pe_m, pe_h = (S[t]["pe"] for t in ("l", "m", "h"))
    # Guardrail (裁决顺序 ③): a tier outside the own band is BLOCKED, never fixed by twisting g or r.
    for tag, pe in (("L", pe_l), ("M", pe_m), ("H", pe_h)):
        if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
            errors.append(f"guardrail: PE_{tag}={pe:.2f} outside own band [{inp['pe_own_min']}, {inp['pe_own_max']}] — BLOCKED, do not twist g")
    # A8: the floor is disclosed only; L is the scenario value.
    floor = inp["pb_floor"] * inp["bps"]
    scenario_L = S["l"]["px"]
    L = scenario_L
    M = S["m"]["px"]
    H = S["h"]["px"]
    A, B = (L + M) / 2, (M + H) / 2

    # Option components (valuation-rules「未建模期权」2026-10-03 / 10-04 / 10-05):
    # solid-state = the Chongqing 20 GWh base at full capacity x the axis steady
    # price x the axis H margin (no sell-side quantity -> only H is sized; L / M
    # margins printed as readings), realised 2029; volume = the named 2030
    # capacity target beyond today's nameplate at the axis M rung, realised 2030.
    # Both discounted to the numerator year at the basket r, less unspent capital.
    # Sign: the rule sets V = value − unspent capital with no floor, so a negative
    # net would be carried as is.
    opm_h = inp["ssb_opm_strong"] - inp["ssb_entrant_disc"]
    opm_m = (inp["ssb_opm_weak"] + opm_h) / 2.0
    SS = {"h": ss_tier(inp, opm_h), "m": ss_tier(inp, opm_m), "l": ss_tier(inp, inp["ssb_opm_weak"])}
    v_ss_gross = SS["h"]["gross"]
    k_ss_ps = k_ps(inp, inp["ss_k"] * inp["ss_eq"], inp["t_opt_ss"])
    v_ss = SS["h"]["net"]
    v_vol_gross = v_opt_vol_gross(inp, inp["li2co3_m"], S["h"]["eps"])
    kv = k_vol_parts(inp)
    k_vol_ps = k_ps(inp, sum(kv.values()), inp["t_opt_vol"])
    v_vol = v_vol_gross - k_vol_ps
    v_opt = v_ss + v_vol

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1
    # A2e-2c flat-multiple ladder at PE_M.
    flat = (S["l"]["eps"] * pe_m, M, S["h"]["eps"] * pe_m)
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken at PE_M={pe_m:.2f}: {flat}")
    # Candidate band (A2e-7h): same formula, only the single-house 2027E volume
    # scale (× δ) swapped in; g2 / r / bridge untouched; L′ is the scenario value like L.
    C = {t: scenario(inp, t, vol_scale(inp)) for t in ("l", "m", "h")}
    Lc, Mc, Hc = (C[t]["px"] for t in ("l", "m", "h"))
    if not (Lc < Mc < Hc):
        errors.append(f"candidate band not ordered: {Lc:.2f}/{Mc:.2f}/{Hc:.2f}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, TOL)
    out_sec = outputs_section(md)
    for label, want_v, rx in (
        ("scenario_L", scenario_L, r"`scenario_L` = \*\*([0-9.]+)\*\*"),
        ("floor", floor, r"`floor` = \*\*([0-9.]+)\*\*"),
        ("L′", Lc, r"候选带（[^）]+）[^\n]*?L′ = \*\*([0-9.]+)\*\*"),
        ("M′", Mc, r"候选带（[^）]+）[^\n]*?M′ = \*\*([0-9.]+)\*\*"),
        ("H′", Hc, r"候选带（[^）]+）[^\n]*?H′ = \*\*([0-9.]+)\*\*"),
    ):
        s = first_float(rx, out_sec)
        if s is None or abs(s - want_v) > TOL:
            errors.append(f"{label}: stated {s} vs recomputed {want_v:.4f}")
    vm = re.search(
        r"V_\{opt\}\\\) = \*\*([−\-]?[0-9.]+)\*\*（固态 \*\*([−\-]?[0-9.]+)\*\* \+ 量增 \*\*([−\-]?[0-9.]+)\*\*）",
        out_sec,
    )
    if vm is None:
        errors.append("stated V_opt line (total + two components) not found")
    else:
        for label, stated, want in (
            ("V_opt", num(vm.group(1)), v_opt),
            ("V_opt^ss", num(vm.group(2)), v_ss),
            ("V_opt^vol", num(vm.group(3)), v_vol),
        ):
            if abs(stated - want) > TOL:
                errors.append(f"{label}: stated {stated} vs recomputed {want:.4f}")

    # zone+V table: the two per-tier credit triples are hard-coded above; the
    # doc must restate them verbatim and the corrected band must reproduce.
    for name, table, rx in (
        ("p^ss", P_SS, r"p\^\{ss\}_\{L/M/H\}\\\) = \*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*"),
        ("p^vol", P_VOL, r"p\^\{vol\}_\{L/M/H\}\\\) = \*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*"),
    ):
        pm = re.search(rx, out_sec)
        if pm is None:
            errors.append(f"{name} triple not stated")
            continue
        for k, got in zip("lmh", pm.groups()):
            if abs(float(got) - table[k]) > 1e-9:
                errors.append(f"{name}_{k}: stated {got} vs eval constant {table[k]}")
    base = {"L": L, "M": M, "H": H}
    adj = {k: base[k] + P_SS[t] * v_ss + P_VOL[t] * v_vol for k, t in zip("LMH", "lmh")}
    # Table 3 rows: | L | 10.27 | 0 | 0.00 | 0 | 0.00 | **10.27** | ...
    for k, v in adj.items():
        m3 = re.search(rf"^\| {k} \| [0-9.]+ \| [^|]+\| [−\-]?[0-9.]+ \| [^|]+\| [−\-]?[0-9.]+ \| \*\*([0-9.]+)\*\* \|", out_sec, re.MULTILINE)
        if m3 is None or abs(float(m3.group(1)) - v) > TOL:
            errors.append(f"table3 {k}: stated {m3.group(1) if m3 else None} vs recomputed {v:.4f}")
    for label, want_v, rx in (("A′", (adj["L"] + adj["M"]) / 2, r"A′ = \*\*([0-9.]+)\*\*"),
                              ("B′", (adj["M"] + adj["H"]) / 2, r"B′ = \*\*([0-9.]+)\*\*")):
        s = first_float(rx, out_sec)
        if s is None or abs(s - want_v) > TOL:
            errors.append(f"{label}: stated {s} vs recomputed {want_v:.4f}")
    # The daily digest reads a single p triple applied to the total: the stated
    # blend must land on the same corrected band.
    pm = re.search(
        r"p_L/p_M/p_H\\\) = \*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*", out_sec
    )
    if pm is None:
        errors.append("blended p_L/p_M/p_H (digest) not stated")
    else:
        for k, t, got in zip("LMH", "lmh", pm.groups()):
            blended = base[k] + float(got) * v_opt
            if abs(blended - adj[k]) > TOL:
                errors.append(
                    f"blended p_{t}={got} gives {k}′={blended:.4f}, components give {adj[k]:.4f}"
                )

    slope = (inp["cal_li_pretax_1"] - inp["cal_li_pretax_0"]) / (inp["cal_p1"] - inp["cal_p0"])
    print(f"formula_id={FORMULA_ID}")
    print(
        "li2co3 OK: "
        + "/".join(f"{inp[k]:g}" for k in ("li2co3_l", "li2co3_m", "li2co3_h"))
        + f"  slope={slope*1e4:.2f} 亿/万元"
        + f"  base scale 1.0 (2026 structure); candidate scale={inp['vol_2027e']:g}/{inp['vol_2026e']:g} x disc = {vol_scale(inp):.4f}"
    )
    print("baskets: " + ", ".join(f"{k} 篮 {baskets[k]} r={inp[k]:g}" for k in LEG_R) + f"; r_disc={inp['r_disc']:g}")
    print(f"{'档':<3}{'锂腿税前':>9}{'税前':>8}{'归母':>8}{'EPS_HKD':>9}{'ROE':>7}{'PE':>7}{'锚点':>8}")
    for t in ("l", "m", "h"):
        s_ = S[t]
        print(
            f"{t.upper():<3}{s_['li']:9.1f}{s_['pretax']:8.1f}{s_['parent']:8.1f}"
            f"{s_['eps']:9.3f}{s_['roe']:7.1%}{s_['pe']:7.2f}{s_['px']:8.2f}"
        )
    print(f"floor={floor:.2f} (PB {inp['pb_floor']:g} × bps, disclosed only, A8)  scenario_L={scenario_L:.2f} = L  "
          f"scenario_L/M={scenario_L / M:.3f}  floor vs band: {zone_of(floor, L, M, H)}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}  "
          f"V_opt={v_opt:.2f} = ss {v_ss:.2f} + vol {v_vol:.2f} "
          f"[gross ss {v_ss_gross:.2f} − K {k_ss_ps:.2f}; gross vol {v_vol_gross:.2f} − K {k_vol_ps:.2f}] "
          f"(vol: {option_share(inp):.2f} x 2026 structure = {inp['cap_now']:g}→{inp['cap_2030']:g} 万吨 nameplate @axis M, "
          f"disc {disc_to_num(inp, inp['t_opt_vol']):.4f} ({inp['t_opt_vol']:g}→{inp['t_num']:g}); "
          f"ss disc {disc_to_num(inp, inp['t_opt_ss']):.4f} ({inp['t_opt_ss']:g}→{inp['t_num']:g}, 无时点锚·拍值))")
    print("zone+V: " + "  ".join(
        f"{k}={adj[k]:.2f}(p_ss={P_SS[t]:g},p_vol={P_VOL[t]:g})" for k, t in zip("LMH", "lmh")
    ) + f"  A′={(adj['L'] + adj['M']) / 2:.2f} B′={(adj['M'] + adj['H']) / 2:.2f}"
        f"  vol option (net) @L/H rung = {v_opt_vol(inp, inp['li2co3_l'], S['h']['eps']):.2f}/{v_opt_vol(inp, inp['li2co3_h'], S['h']['eps']):.2f}")
    # Unspent capital (valuation-rules「未建模期权」2026-10-04): equity share, 亿 CNY, and readings.
    print(f"unspent capital: ss {inp['ss_k']:g} x {inp['ss_eq']:g} = {inp['ss_k'] * inp['ss_eq']:.2f} 亿, "
          f"spread disc {disc_spread(inp, inp['t_opt_ss']):.4f} -> {k_ss_ps:.2f} HKD/sh; "
          f"vol ppg1 {kv['ppg1']:.2f} + cau2 {kv['cau2']:.2f} + rest {kv['rest']:.2f} = {sum(kv.values()):.2f} 亿, "
          f"spread disc {disc_spread(inp, inp['t_opt_vol']):.4f} -> {k_vol_ps:.2f} HKD/sh")
    named_only = v_vol_gross - k_ps(inp, kv["ppg1"] + kv["cau2"], inp["t_opt_vol"])
    ppg23 = inp["ppg23_k_usd"] / 100.0 * inp["fx_cny_per_usd"] * inp["ppg_eq"]
    rest_less = kv["rest"] - 10.0 * inp["conv_k_per_wt"]  # PPGS stages 2-3 = 10 万吨 replace conversion
    ppgs_full = v_vol_gross - k_ps(inp, kv["ppg1"] + kv["cau2"] + ppg23 + rest_less, inp["t_opt_vol"])
    oneshot_vol = v_vol_gross - k_ps(inp, sum(kv.values()), inp["t_opt_vol"], spread=False)
    oneshot_ss = v_ss_gross - k_ps(inp, inp["ss_k"] * inp["ss_eq"], inp["t_opt_ss"], spread=False)
    ss_r10 = ss_tier({**inp, "r_disc": 0.10}, opm_h)["net"]
    r10 = {**inp, "r_disc": 0.10}
    v10 = (v_opt_vol(r10, inp["li2co3_m"], S["h"]["eps"]), ss_r10)
    print(f"K sensitivities: vol named-only (no remainder) {named_only:.2f}; PPGS all 3 stages (stages 2-3 replace 10 万吨 conversion) {ppgs_full:.2f}; "
          f"one-shot at realisation year vol {oneshot_vol:.2f} / ss {oneshot_ss:.2f}; r_disc 10% vol {v10[0]:.2f} / ss {v10[1]:.2f}")
    print("solid-state (A9, _AXIS.solid-state-battery): " + "  ".join(
        f"{t.upper()} opm {o:.2%}: rev {SS[t]['rev']:.0f} 亿 pretax {SS[t]['pretax']:.2f} ROE {SS[t]['roe']:.1%} "
        f"PE {SS[t]['pe']:.2f} gross {SS[t]['gross']:.2f} net {SS[t]['net']:.2f}"
        for t, o in (("l", inp["ssb_opm_weak"]), ("m", opm_m), ("h", opm_h))))
    print(f"  ss sensitivities (H margin): price 2029E {inp['ssb_px_2029']:g} -> {ss_tier(inp, opm_h, inp['ssb_px_2029'])['net']:.2f}; "
          f"2030E {inp['ssb_px_2030']:g} -> {ss_tier(inp, opm_h, inp['ssb_px_2030'])['net']:.2f}; "
          f"no entrant discount -> {ss_tier(inp, inp['ssb_opm_strong'])['net']:.2f}; g2 0 -> {ss_tier(inp, opm_h, g2=0.0)['net']:.2f}; "
          f"break-even margin at 0.8 元/Wh -> {next(o / 1000 for o in range(1, 400) if ss_tier(inp, o / 1000)['net'] >= 0):.1%}")
    print(f"candidate (2027E 量·大华单家, scale {vol_scale(inp):.4f}): L′={Lc:.2f} M′={Mc:.2f} H′={Hc:.2f}")
    print(f"gordon: r={inp['r_perp']:g} (篮 {baskets['r_perp']}) g2={inp['g2']:g} flat [§13 commodity-leg tier default] "
          f"(axis 永续 g2 {inp['axis_g2_li']:g} referenced, superseded — A7) "
          f"roe={S['l']['roe']:.3f}/{S['m']['roe']:.3f}/{S['h']['roe']:.3f} -> pe={pe_l:.2f}/{pe_m:.2f}/{pe_h:.2f} "
          f"inside own band [{inp['pe_own_min']}, {inp['pe_own_max']}]")
    g_lo, ok_lo = implied_g(inp["pe_own_min"], S["m"]["roe"], inp["r_perp"])
    g_hi, ok_hi = implied_g(inp["pe_own_max"], S["m"]["roe"], inp["r_perp"])
    print(f"guardrail band-edge g at ROE_M: {g_lo:+.2%} ({'ok' if ok_lo else 'ill-conditioned'}) / {g_hi:+.2%} ({'ok' if ok_hi else 'ill-conditioned'}) — reported only (A7)")
    for dg in (-0.01, 0.01):
        alt = {t: scenario(inp, t, g2=inp["g2"] + dg) for t in ("l", "m", "h")}
        print(f"  g2 {dg:+.0%} -> PE {alt['l']['pe']:.2f}/{alt['m']['pe']:.2f}/{alt['h']['pe']:.2f}, "
              f"band {alt['l']['px']:.2f}/{alt['m']['px']:.2f}/{alt['h']['px']:.2f}")
    # A13 谷底档 coordinates: (i) measured trough→recovery CAGR on the L numerator; (ii) the
    # measured n with the model's own L→M magnitude.  Printed, not anchors.
    for label, (np0, np1, n) in RECOVERY_MEASURED.items():
        g1_meas = (np1 / np0) ** (1.0 / n) - 1.0
        pe_i = recovery_two_stage_pe(g1_meas, n, inp["g2"], S["m"]["roe"], inp["r_perp"])
        g1_lm = (S["m"]["eps"] / S["l"]["eps"]) ** (1.0 / n) - 1.0
        pe_ii = recovery_two_stage_pe(g1_lm, n, inp["g2"], S["m"]["roe"], inp["r_perp"])
        print(f"谷底档坐标（A13）{label} n={n}: (i) measured CAGR {g1_meas:.0%} -> {pe_i:.1f}x -> {S['l']['eps'] * pe_i:.1f} "
              f"(vs M {M:.2f}: {'overshoot' if S['l']['eps'] * pe_i > M else 'below M'}); "
              f"(ii) L→M magnitude g1 {g1_lm:.1%} -> {pe_ii:.2f}x -> {S['l']['eps'] * pe_ii:.2f} (L/M {S['l']['eps'] * pe_ii / M:.3f}, collapsed)")
    print(f"谷底 x 1/r = {S['l']['eps'] / inp['r_perp']:.2f}  (deep_discount pressure coordinate; = L at g = 0)")
    print(f"flat-multiple ladder @ PE_M {pe_m:.2f}x (A2e-2c): {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    for line in tier_report((L, M, H), (pe_l, pe_m, pe_h), (S["l"]["eps"], S["m"]["eps"], S["h"]["eps"])):
        print(line)
    print(
        f"L/M={L/M:.2f} H/M={H/M:.2f} (H-L)/2M={(H-L)/2/M:.2%} V_opt/M={v_opt/M:.1%} "
        f"numerator L/M={S['l']['eps']/S['m']['eps']:.2f} H/M={S['h']['eps']/S['m']['eps']:.2f} "
        f"| multiple ratio L/M={pe_l/pe_m:.2f} H/M={pe_h/pe_m:.2f} (ROE term only, g flat)"
    )
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): r_perp is
    # the only r in the base anchors; r_disc discounts only the candidate band
    # and V_opt, so it stays put.  The Li2CO3 rungs, g2 and bridge stay put too.
    # Disclosure only — the anchors above are the 中枢 column.
    def band_rf(dr: float) -> tuple[float, float, float]:
        shifted = {**inp, "r_perp": inp["r_perp"] + dr}
        return tuple(scenario(shifted, t)["px"] for t in ("l", "m", "h"))  # type: ignore[return-value]

    rf = rf_block(LISTING_CCY, {"r_perp": inp["r_perp"]}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1
    # Only a clean run writes, so a FAIL never feeds the daily digest.
    write_rf_readings("1772.HK", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
