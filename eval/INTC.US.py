#!/usr/bin/env python3
"""INTC.US valuation eval — base L/M/H with the Foundry transition loss, V_opt = Foundry profit above breakeven.

frameworks/INTC.US.md is the source of truth for inputs; this script recomputes
the base L/M/H (CPU leg on Gordon multiples + closing items + the Foundry
leg's consensus-implied loss until the management breakeven year, then the
government escrow shares added once), A/B, the per-tier option values V_k,
V_opt = V_H and p_k = V_k / V_H, and exits 1 on mismatch with stated Outputs.
The doc carries no current price (AGENTS.md「现价 — 禁写契约」): which zone a
quote falls in is derived live by the daily digest and the app.

formula_id (CPU):     intc_cpu_product_gordon_v6
formula_id (Foundry): intc_foundry_above_breakeven_option_v8  (ceiling only; the pre-breakeven loss is in the base, A21)

CPU leg (A5 / A5c / A15, unchanged in v6 except the share count):
  numerators  L = FY2025 Intel Products operating income (cyclical L
              exception); M / H = FY2027 company revenue consensus mean / high
              x product share x product margin, both inferred from two disclosed
              quarters (Q1'26 / Q2'26) that print the same values (A5c).
  multiples   perpetual_pe(g2_cpu, ROE_x, r_perp), ROE_x = NI_x / company
              equity (no leg equity disclosed).  r_perp = 篮 4 (A19).
  guardrail   generated multiples inside the own realised trailing-PE band.
  closure     $/share items + corporate unallocated capitalised at the M multiple (A10b).

Foundry in the base (A21): FY2027 loss = product EPS + bridge - FY2027 company
EPS consensus (yfinance, >=2 ranged houses); FY2028 loss = the same bridge on
the FY2028 company consensus mean (WallStreetZen, single aggregator -- a point
estimate for a transition year, not a numerator; 2026-10-04).  H stops at
end-2027, L / M at end-2028 (CFO 2026-08-26).  After breakeven the leg is 0 in
the base.

Escrow shares (A10d, 2026-10-04): the 1.43e8 shares still in escrow for the US
government (10-Q 2Q26) are added once at $20 cash each; the $15.6B derivative
liability is NOT also deducted (net cash only nets interest-bearing debt).

Foundry option (A6 / A22, valuation-rules「未建模期权」2026-10-04):
  quantity    L / M: foundry revenue = internal (product revenue x H1'26 internal
              ratio, growing at g2_cpu) + external path cross-combined from
              each house's LATEST note (user 2026-10-05): low = lowest house per
              year (GF Securities packaging-only 2027/2028, Goldman 2030 =
              wafers 11 + packaging 10), high = highest (Citi 2027/2028, BofA
              2026-08 "nearly $40B" 2030), mid = yearly mean, 2029 geometric
              interpolation (marked).  Advanced packaging is inside the path
              exactly once: the CFO-named packaging quantity (1 customer x $2B)
              is checked to sit below every path in 2029, so it adds nothing.
              H = the higher of (a) full capacity and (b) the sell-side high
              path on the same flat-price basis (internal leg held at FY2027);
              when (b) wins, the wafers it needs beyond every named fab (at the
              same discounted prices) become new 14A-class capacity at Intel's
              own capital per WSPM, deducted and added to the H ROE denominator
              (user 2026-10-05; formula v8).
              (a) FULL-CAPACITY
              revenue = wafer starts per month by fab / node group (Fab 52 named;
              Fab 62 = the Arizona JV budget / Intel's own capex per WSPM minus
              Fab 52, checked; Ireland, Intel 7, legacy inferred and marked; Ohio =
              budget / Intel's own capex per WSPM) x 12 x TSMC's wafer price for the
              comparable node x (1 - price discount), the discount being the one
              that turns TSMC's 10y margin into the H margin at TSMC's cost per
              wafer; + own-wafer packaging/test at TSMC's packaging share of
              revenue + external packaging (Goldman 2030 $10B, the CFO-named $2B
              inside it).  Revenue follows the capacity in service each year;
              margin ramps linearly from breakeven to ss_year_h (Ohio Mod 2).
              Unspent named capital (Arizona Fab 62, Ireland Intel 3 program,
              Ohio) is deducted and sits in the H ROE denominator.  The flat-price
              basis holds internal revenue at its FY2027 level: transfer prices
              track wafer prices, not product ASP / g2 (10-K Note 3).  H g2 = the
              caught-up peer's own reverse-solve (TSM, single sample, capped),
              used only if ROE > r.
  unit        steady-state operating margin from _AXIS.leading-edge-foundry:
              L = weak peer (Samsung foundry), H = strong peer (TSMC 10y) minus
              the named yield discount, M = midpoint.
  timing      linear ramp from the tier's breakeven year to 2030 (t_align).
  value       ROE = 2030 NI / the foundry's own operating capital (company
              PP&E net as proxy); ROE < r -> 1/r (g = 0), else
              perpetual_pe(g2_foundry, ROE, r).  Discounted to FY2027 at the
              base basket r.  Built capacity is not deducted (sunk); only
              unspent named capital (Penang) is.  The product leg's FY2027
              consensus already carries the external-foundry increment over
              today's run-rate -> that overlap is DEDUCTED from V_M / V_H.
  table 3     V_opt = V_H, p_k = V_k / V_H (eval-derived, never Inputs, A7).

Run:  python3 frameworks/eval/INTC.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import axis_path  # noqa: E402
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    check_g_cap,
    check_r,
    implied_g,
    perpetual_pe,
)
from eval.lib.inputs import (  # noqa: E402
    check_against_stated,
    check_missing,
    ladder,
    parse_baskets,
    parse_inputs,
    report,
)
from eval.lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from eval.lib.zones import cut_points  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "INTC.US.md"
FORMULA_IDS = (
    "intc_cpu_product_gordon_v6",
    "intc_foundry_above_breakeven_option_v8",
)
TOL = 0.05
P_TOL = 0.0005
MIN_R_MINUS_G = 0.02  # AGENTS.md: below this the multiple sits at the pole
# _AXIS.rates segment: a US listing reads the USD r_f (valuation-rules「按上市货币取段」).
LISTING_CCY = "USD"

# The foundry g2 is the foundry-cluster reverse-solve GFS A5 stores as `g2_rest_src`;
# the leg ruler (g2, margins) lives on _AXIS.leading-edge-foundry.
PEER = REPO_ROOT / "frameworks" / "GFS.US.md"
AXIS = axis_path("leading-edge-foundry")
AXIS_ROWS = {"g2_foundry": "g2_foundry_src", "g2_foundry_h": "g2_foundry_h_src", "foundry_opm_l": "opm_weak_peer"}

ADJ_PS = ("net_cash_ps", "nci_ps", "mbly_stake_ps", "altera_stake_ps", "tax_asset_ps")

QTRS = ("q1", "q2")
EXT_YEARS = (2027, 2028, 2030)
# H full capacity (A6b): wafer starts per month by node group, priced at TSMC's comparable node.
WSPM = ("wspm_f52", "wspm_f62", "wspm_ie_now", "wspm_ie_full", "wspm_i7", "wspm_legacy")
PX = {"18A": "px_n3", "14A": "px_n2", "I3": "px_n5", "I7": "px_n7", "LEG": "px_n16"}
REQUIRED = [
    "shares_diluted", "equity", "tax_rate", "oi_products_l",
    "rev_fy27_low", "rev_fy27_m", "rev_fy27_h",
    *(f"{k}_{q}" for k in ("prod_rev", "prod_oi", "cons_rev") for q in QTRS),
    "prod_rev_fy25", "cons_rev_fy25",
    "r_perp", "g2_cpu", "pe_own_min", "pe_own_max", "eps_fy27_hsbc",
    "cons_eps_fy27_low", "cons_eps_fy27_m", "cons_eps_fy27_h",
    "cons_rev_fy28_m", "cons_rev_fy28_h", "cons_eps_fy28_m",
    "oi_products_trough", "bridge_other_eps", "sbc_acq_eps", "be_year_l", "be_year_m", "be_year_h",
    "escrow_shares", "escrow_price", "warrant_shares",
    "foundry_oi_h1", "foundry_oi_q2", "foundry_rev_h1", "foundry_ext_h1", "foundry_ext_q2",
    *(f"ext_rev_{s}_{y}" for s in ("l", "h") for y in EXT_YEARS), "ext_pkg_h_2030",
    "opt_rev_pkg", "opt_opm", "foundry_opm_l", "foundry_opm_h", "ppe_net", "g2_foundry",
    "ss_year", "t_num", "pkg_capex_budget", "pkg_capex_done",
    *WSPM, *PX.values(), "capex_per_wspm", "pkg_share_tsm",
    "az_budget", "az_spent_q2", "az_done", "ohio_budget", "ohio_spent", "ohio_done", "ohio_mod1_ops",
    "ie_budget", "ie_done",
    "ss_year_h", "g2_foundry_h", "tsm_rev_2025", "tsm_ppe_net_2025", "tsm_ppe_net_2024",
    "corp_other_eps", *ADJ_PS,
]
TIERS = ("L", "M", "H")
MM = 1e6  # $M fields
B = 1e9


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    for fid in FORMULA_IDS:
        if fid not in md:
            print(f"FAIL: formula_id {fid} missing from framework", file=sys.stderr)
            return 1

    inp = parse_inputs(md)
    baskets = parse_baskets(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r, g2 = inp["r_perp"], inp["g2_cpu"]
    sh, eq, keep = inp["shares_diluted"], inp["equity"], 1.0 - inp["tax_rate"]
    esc_sh, esc_px = inp["escrow_shares"], inp["escrow_price"]
    sh_post = sh + esc_sh

    def esc(v: float) -> float:
        """Per-share value on 5.29e9 shares -> per share after the escrow shares come in at $20."""
        return (v * sh + esc_sh * esc_px) / sh_post

    # ---- Guards on the growth 口径 (AGENTS.md 永续增长口径) ----
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (valuation-rules.md「§r 篮子」)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(g2, r, "g2_cpu")
    if r - g2 < MIN_R_MINUS_G:
        errors.append(f"r - g2_cpu = {r - g2:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")

    # ---- Step 0: leg economics by public-data inference (A5c) ----
    q_margin = {q: inp[f"prod_oi_{q}"] / inp[f"prod_rev_{q}"] for q in QTRS}
    q_share = {q: inp[f"prod_rev_{q}"] / inp[f"cons_rev_{q}"] for q in QTRS}
    for lab, d in (("margin", q_margin), ("share", q_share)):
        if max(d.values()) - min(d.values()) > 0.01:
            errors.append(f"product {lab} not constant across {QTRS}: {d} — inference assumption fails (A5c)")
    p_rev_h1 = sum(inp[f"prod_rev_{q}"] for q in QTRS)
    margin = sum(inp[f"prod_oi_{q}"] for q in QTRS) / p_rev_h1
    share = p_rev_h1 / sum(inp[f"cons_rev_{q}"] for q in QTRS)
    margin_fy25 = inp["oi_products_l"] / inp["prod_rev_fy25"]
    bridge = inp["bridge_other_eps"] + inp["corp_other_eps"] + inp["sbc_acq_eps"]
    t0 = inp["t_num"]
    be = {"L": inp["be_year_l"], "M": inp["be_year_m"], "H": inp["be_year_h"]}

    def prod_eps(rev: float, m_: float = margin, s_: float = share) -> float:
        return rev * s_ * m_ * keep / sh

    def compute(m_: float = margin, s_: float = share, g_: float = g2, r_: float = r,
                l28: float | None = None, be_: dict | None = None, fy28_num: bool = False,
                eq_: float = eq, l27: float | None = None) -> dict:
        """Base band on the escrow-adjusted share count; consensus EPS fixed, so a
        different product EPS implies a different foundry loss (A21)."""
        be_ = be if be_ is None else be_
        rev = ({"M": inp["cons_rev_fy28_m"], "H": inp["cons_rev_fy28_h"]} if fy28_num
               else {"M": inp["rev_fy27_m"], "H": inp["rev_fy27_h"]})
        e = {"L": inp["oi_products_l"] * MM * keep / sh, "M": prod_eps(rev["M"], m_, s_), "H": prod_eps(rev["H"], m_, s_)}
        roe_ = {t: e[t] * sh / eq_ for t in TIERS}
        pe_ = {t: perpetual_pe(g_, roe_[t], r_) for t in TIERS}
        df_num = {t: ((1 + r_) ** -1 if fy28_num and t != "L" else 1.0) for t in TIERS}  # construction §3: FY+2 discounted
        cpu_ = {t: e[t] * pe_[t] * df_num[t] for t in TIERS}
        adj_ = sum(inp[k] for k in ADJ_PS) + inp["corp_other_eps"] * pe_["M"]
        l27_ = (prod_eps(inp["rev_fy27_m"], m_, s_) + bridge - inp["cons_eps_fy27_m"]) if l27 is None else l27
        l28_ = (prod_eps(inp["cons_rev_fy28_m"], m_, s_) + bridge - inp["cons_eps_fy28_m"]) if l28 is None else l28
        loss = {2027: l27_, 2028: l28_}
        f_ = {t: -sum(loss.get(y, l28_) * (1 + r_) ** -(y - t0) for y in range(int(t0), int(be_[t]) + 1)) for t in TIERS}
        pre = {t: cpu_[t] + adj_ + f_[t] for t in TIERS}
        return dict(eps=e, roe=roe_, pe=pe_, cpu=cpu_, adj=adj_, l27=l27_, l28=l28_, F=f_, pre=pre,
                    base={t: esc(pre[t]) for t in TIERS})

    c = compute()
    eps, roe, pe, cpu, adj, fdy = c["eps"], c["roe"], c["pe"], c["cpu"], c["adj"], c["F"]
    loss27, loss28 = c["l27"], c["l28"]
    base = c["base"]
    L, M, H = (base[t] for t in TIERS)
    A, B_ = cut_points(L, M, H)
    oi = {t: eps[t] * sh / keep / MM for t in TIERS}
    errors += ladder("oi_products", oi["L"], oi["M"], oi["H"])
    for t in TIERS:
        if not (inp["pe_own_min"] <= pe[t] <= inp["pe_own_max"]):
            errors.append(f"{t} generated PE {pe[t]:.2f}x outside own realised band "
                          f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] — 回对话，不拧 g")
    if loss27 <= 0:
        errors.append(f"consensus implies no FY2027 foundry loss ({loss27:.3f}) — recheck A21 bridge")
    if loss28 <= 0:
        errors.append(f"FY2028 consensus implies a foundry profit ({loss28:.3f}) — breakeven moved earlier, back to the conversation (A21)")
    if not all(be[t] >= t0 for t in TIERS) or not be["L"] >= be["M"] >= be["H"]:
        errors.append(f"breakeven years {be} must be >= t_num {t0} and L >= M >= H (A21)")

    # ---- A2e-2c flat ladder + A2e-5 decomposition ----
    flat_errs, flat_eps = flat_multiple_ladder((eps["L"], eps["M"], eps["H"]), pe["M"])
    errors += flat_errs
    flat = tuple(esc(v + adj + fdy[t]) for v, t in zip(flat_eps, TIERS))
    dec = decompose((L, M, H), (pe["L"], pe["M"], pe["H"]))

    # ---- single-house cross-check (A5b / A18) ----
    eps_c = inp["eps_fy27_hsbc"]
    if not (eps["M"] <= eps_c <= eps["H"]):
        errors.append(f"HSBC core 2027E {eps_c} outside inferred product EPS [M {eps['M']:.2f}, H {eps['H']:.2f}] — recheck A5c")
    meta = load_framework(FRAMEWORK)
    if meta.candidate is not None:
        errors.append("候选带 line still in Outputs — retired 2026-10-03 (A18)")

    # ---- Foundry option above breakeven (A6 / A22) ----
    g2f, g2fh = inp["g2_foundry"], inp["g2_foundry_h"]
    errors += check_g_cap(g2f, r, "g2_foundry")
    errors += check_g_cap(g2fh, r, "g2_foundry_h")
    ss = int(inp["ss_year"])
    ext = {s.upper(): {y: inp[f"ext_rev_{s}_{y}"] for y in EXT_YEARS} for s in ("l", "h")}
    for s in ("L", "H"):  # gap year: geometric interpolation (marked in A6)
        ext[s][2029] = (ext[s][2028] * ext[s][2030]) ** 0.5
    ext["M"] = {y: (ext["L"][y] + ext["H"][y]) / 2 for y in ext["L"]}
    for y in sorted(ext["L"]):
        if not ext["L"][y] <= ext["M"][y] <= ext["H"][y]:
            errors.append(f"external path {y}: low {ext['L'][y]:.3g} <= mid <= high {ext['H'][y]:.3g} violated")
    # Packaging exactly once: the CFO-named packaging quantity must already sit inside every path.
    pkg_named = inp["opt_rev_pkg"]
    if not pkg_named <= ext["L"][2029]:
        errors.append(f"named packaging {pkg_named / B:.1f}B above the low path in 2029 ({ext['L'][2029] / B:.2f}B) — add the excess, A6")
    if not inp["ext_pkg_h_2030"] <= ext["H"][2030]:
        errors.append("high-path packaging exceeds the high path total — recheck A6")
    int_ratio = (inp["foundry_rev_h1"] - inp["foundry_ext_h1"]) / p_rev_h1
    prod_rev = {"L": inp["prod_rev_fy25"] * MM, "M": inp["rev_fy27_m"] * share, "H": inp["rev_fy27_h"] * share}

    # Leg ruler from _AXIS.leading-edge-foundry
    opm = {"L": inp["foundry_opm_l"], "H": inp["foundry_opm_h"]}
    opm["M"] = (opm["L"] + opm["H"]) / 2
    opm_strong = float("nan")
    if AXIS.is_file():
        ax = parse_inputs(AXIS.read_text(encoding="utf-8"))
        opm_strong = ax.get("opm_strong_peer", float("nan"))
        for k, ak in AXIS_ROWS.items():
            if ak not in ax or abs(ax[ak] - inp[k]) > 1e-9:
                errors.append(f"{k} {inp[k]:g} != _AXIS.leading-edge-foundry {ak} {ax.get(ak)} — the leg ruler drifted")
        h_ax = ax.get("opm_strong_peer", float("nan")) - ax.get("yield_discount", float("nan"))
        if abs(h_ax - opm["H"]) > 1e-9:
            errors.append(f"foundry_opm_h {opm['H']:g} != axis strong peer - yield discount {h_ax:.4f}")
        if not opm["H"] < ax.get("opm_strong_peer_min", 0.0):
            errors.append(f"foundry_opm_h {opm['H']:g} not below the strong peer's worst year — discount too small")
        if abs(ax.get("t_align", float("nan")) - ss) > 1e-9:
            errors.append(f"ss_year {ss} != axis t_align {ax.get('t_align')}")
    else:
        errors.append("frameworks/axes/leading-edge-foundry.md missing — leg ruler unchecked")
    if not opm["L"] < opm["M"] < opm["H"]:
        errors.append(f"foundry margins not L < M < H: {opm}")
    if PEER.is_file():
        peer = parse_inputs(PEER.read_text(encoding="utf-8"))
        if abs(peer.get("g2_rest_src", float("nan")) - g2f) > 1e-9:
            errors.append(f"g2_foundry {g2f:g} != foundry-cluster reading g2_rest_src {peer.get('g2_rest_src')} (A19)")
    else:
        errors.append("frameworks/GFS.US.md missing — foundry-cluster g2 unchecked")

    def option(t: str, m_: float | None = None, path: dict | None = None, be_t: float | None = None,
               r_: float = r, capital: float | None = inp["ppe_net"], internal: bool = True,
               retain: bool = False) -> dict:
        """PV (total $) at FY2027 of foundry profit above breakeven for tier t.
        capital=None -> company-equity ROE (old convention, sensitivity only)."""
        m_ = opm[t] if m_ is None else m_
        path = ext[t] if path is None else path
        b_ = int(be[t] if be_t is None else be_t)
        ni = {}
        for y in range(b_ + 1, ss + 1):
            frev = (prod_rev[t] * int_ratio * (1 + g2) ** (y - t0) if internal else 0.0) + path[y]
            ni[y] = frev * m_ * (y - b_) / (ss - b_) * keep
        ni_ss = ni[ss]
        roe_ = ni_ss / capital if capital is not None else (eps[t] * sh + ni_ss) / eq
        pe_ = perpetual_pe(g2f, roe_, r_) if roe_ > r_ else 1 / r_
        pv = sum(ni[y] * (1 + r_) ** -(y - t0) for y in ni if y < ss) + ni_ss * pe_ * (1 + r_) ** -(ss - t0)
        if retain and roe_ > 0:  # sensitivity: ramp growth paid from retained capital the year before
            pv -= sum((ni[y] - ni.get(y - 1, 0.0)) / roe_ * (1 + r_) ** -(y - 1 - t0) for y in ni)
        return dict(ni=ni, roe=roe_, pe=pe_, pv=pv)

    # ---- H quantity = full-capacity revenue = wafer capacity x market wafer price (A6b, 2026-10-05) ----
    az_left_q2 = inp["az_budget"] - inp["az_spent_q2"]
    ohio_left = inp["ohio_budget"] - inp["ohio_spent"]
    ie_left = inp["ie_budget"]  # announced 2026-07-13, treated as wholly unspent at the 2Q26 point (A6b)
    if min(az_left_q2, ohio_left) < 0:
        errors.append("named project spent above budget — recheck A6b")
    ss_h = int(inp["ss_year_h"])
    if ss_h < ss:
        errors.append(f"ss_year_h {ss_h} before ss_year {ss} — H full capacity realised before the aligned year?")
    if not inp["ohio_mod1_ops"] <= ss_h:
        errors.append("Ohio Mod 1 operations after the H full-capacity year — recheck A6b")
    wspm_ohio = inp["ohio_budget"] / inp["capex_per_wspm"]  # both Ohio mods, Intel's own capital intensity
    # Arizona JV (Fab 52 + 62): same budget-to-capacity rule as Ohio; Fab 52's named 40k sits inside it (A6b).
    wspm_az = inp["az_budget"] / inp["capex_per_wspm"]
    f62_extra = 2 * inp["wspm_f52"] * inp["capex_per_wspm"] - inp["az_budget"]  # unnamed capital for a full twin
    if abs(inp["wspm_f52"] + inp["wspm_f62"] - wspm_az) > 0.01 * wspm_az:
        errors.append(f"Fab 52 + Fab 62 {inp['wspm_f52'] + inp['wspm_f62']:,.0f} WSPM != Arizona budget / capex per WSPM "
                      f"{wspm_az:,.0f} (A6b)")

    def price_disc(m_: float) -> float:
        """Price discount to TSMC that, at TSMC's cost per wafer, lands on margin m_ (A6b)."""
        return 1 - (1 - opm_strong) / (1 - m_)

    def capacity(y: int, ohio_w: float = wspm_ohio, f62: float | None = None, with_ohio: bool = True) -> dict:
        """Wafer starts per month in service in year y, by node group (H world: full utilisation)."""
        f62 = inp["wspm_f62"] if f62 is None else f62
        oh = (ohio_w / 2 if y >= inp["ohio_mod1_ops"] else 0.0) + (ohio_w / 2 if y >= ss_h else 0.0)
        return {"18A": inp["wspm_f52"] + (f62 if y >= inp["az_done"] else 0.0),
                "14A": oh if with_ohio else 0.0,
                "I3": inp["wspm_ie_full"] if y > inp["ie_done"] else inp["wspm_ie_now"],
                "I7": inp["wspm_i7"], "LEG": inp["wspm_legacy"]}

    def rev_cap(y: int, m_: float | None = None, own_pkg: bool = True, **kw) -> dict:
        """Full-capacity foundry revenue in year y: wafers + own-wafer packaging/test + external packaging."""
        d_ = price_disc(opm["H"] if m_ is None else m_)
        c_ = capacity(y, **kw)
        by = {k: c_[k] * 12 * inp[PX[k]] * (1 - d_) for k in c_}
        wafer = sum(by.values())
        pkg_own = wafer * inp["pkg_share_tsm"] / (1 - inp["pkg_share_tsm"]) if own_pkg else 0.0
        # External packaging rides the high path's shape up to Goldman's 2030 $10B; none before the path starts.
        pkg_ext = 0.0 if y < min(ext["H"]) else inp["ext_pkg_h_2030"] * min(1.0, ext["H"].get(y, ext["H"][2030]) / ext["H"][2030])
        return dict(by=by, wafer=wafer, pkg_own=pkg_own, pkg_ext=pkg_ext, total=wafer + pkg_own + pkg_ext,
                    wspm=sum(c_.values()), disc=d_)

    rev_full = rev_cap(ss_h)["total"]
    tsm_turn = inp["tsm_rev_2025"] / ((inp["tsm_ppe_net_2025"] + inp["tsm_ppe_net_2024"]) / 2)

    def spread_pv(amount: float, done: int, r_: float) -> float:
        """Unspent budget spread evenly from 2026 to the completion year; spend before t_num not discounted."""
        yrs = range(2026, done + 1)
        return sum(amount / len(yrs) * (1 + r_) ** -max(0, y - t0) for y in yrs)

    def option_full(m_: float | None = None, be_t: float | None = None, r_: float = r, with_ohio: bool = True,
                    g_: float | None = None, az_extra: float = 0.0, **kw) -> dict:
        """H tier: revenue follows capacity in service, margin ramps linearly from breakeven to 30% at
        ss_year_h; ROE on operating PP&E + unspent named capital; unspent capital deducted.
        az_extra: sensitivity only -- capital beyond the JV budget to tool a larger Fab 62."""
        m_ = opm["H"] if m_ is None else m_
        b_ = int(be["H"] if be_t is None else be_t)
        g_ = g2fh if g_ is None else g_
        ss_ = ss_h if with_ohio else max(ss, int(inp["az_done"]), int(inp["ie_done"]) + 1)
        rev_ = {y: rev_cap(y, m_=m_, with_ohio=with_ohio, **kw)["total"] for y in range(b_ + 1, ss_ + 1)}
        ni = {y: rev_[y] * m_ * keep * (y - b_) / (ss_ - b_) for y in rev_}
        az_left = az_left_q2 + az_extra
        cap = inp["ppe_net"] + az_left + ie_left + (ohio_left if with_ohio else -inp["ohio_spent"])
        roe_ = ni[ss_] / cap
        pe_ = perpetual_pe(g_, roe_, r_) if roe_ > r_ else 1 / r_
        pv = sum(ni[y] * (1 + r_) ** -(y - t0) for y in ni if y < ss_) + ni[ss_] * pe_ * (1 + r_) ** -(ss_ - t0)
        uns = (spread_pv(az_left, int(inp["az_done"]), r_) + spread_pv(ie_left, int(inp["ie_done"]), r_)
               + (spread_pv(ohio_left, int(inp["ohio_done"]), r_) if with_ohio else 0.0))
        return dict(ni=ni, roe=roe_, pe=pe_, pv=pv, rev=rev_[ss_], revs=rev_, cap=cap, unspent=uns)

    int_flat = prod_rev["H"] * int_ratio  # H internal held at FY2027: transfer price ~ market wafer price (A6b)

    def option_path_h(m_: float | None = None, be_t: float | None = None, r_: float = r, g_: float | None = None,
                      own_pkg: bool = True, internal_growth: bool = False, **kw) -> dict:
        """H tier when the sell-side high path beats full capacity (method (b), 2026-10-05): revenue = internal
        (flat at FY2027) + external high path, steady at ss_year; the wafers that path needs at the same
        discounted prices beyond all named capacity are new 14A-class capacity at Intel's own capital
        intensity; that capital plus the named unspent budgets is deducted and sits in the ROE denominator.
        Ohio and the unnamed capacity must be in service by ss_year -> their spend spreads 2026..ss_year."""
        m_ = opm["H"] if m_ is None else m_
        b_ = int(be["H"] if be_t is None else be_t)
        g_ = g2fh if g_ is None else g_
        d_ = price_disc(m_)
        rev_ = {y: int_flat * ((1 + g2) ** (y - t0) if internal_growth else 1.0) + ext["H"][y] for y in range(b_ + 1, ss + 1)}
        ni = {y: rev_[y] * m_ * keep * (y - b_) / (ss - b_) for y in rev_}
        az_left = az_left_q2 + kw.pop("az_extra", 0.0)
        named = rev_cap(ss_h, m_=m_, own_pkg=own_pkg, **kw)  # every named fab at full load (incl. Ohio)
        own = (1 - inp["pkg_share_tsm"]) if own_pkg else 1.0
        wafer_need = (rev_[ss] - inp["ext_pkg_h_2030"]) * own
        px_new = 12 * inp["px_n2"] * (1 - d_)
        wspm_new = max(0.0, wafer_need - named["wafer"]) / px_new
        capex_new = wspm_new * inp["capex_per_wspm"]
        oh_left = ohio_left if kw.get("with_ohio", True) else 0.0  # Ohio budget fixed; ohio_w only changes its WSPM
        cap = inp["ppe_net"] + az_left + ie_left + oh_left + capex_new
        roe_ = ni[ss] / cap
        pe_ = perpetual_pe(g_, roe_, r_) if roe_ > r_ else 1 / r_
        pv = sum(ni[y] * (1 + r_) ** -(y - t0) for y in ni if y < ss) + ni[ss] * pe_ * (1 + r_) ** -(ss - t0)
        uns = (spread_pv(az_left, int(inp["az_done"]), r_) + spread_pv(ie_left, int(inp["ie_done"]), r_)
               + spread_pv(oh_left + capex_new, ss, r_))
        return dict(ni=ni, roe=roe_, pe=pe_, pv=pv, rev=rev_[ss], revs=rev_, cap=cap, unspent=uns,
                    wafer_need=wafer_need, wafer_named=named["wafer"], wspm_new=wspm_new, capex_new=capex_new,
                    wspm_named=named["wspm"])

    unspent_ps = inp["pkg_capex_budget"] * (1 - inp["pkg_capex_done"]) / sh_post
    ext_now = inp["foundry_ext_h1"] * 2 * MM
    overlap = {t: (0.0 if t == "L" else
                   max(0.0, ext[t][2027] - ext_now) * share * margin * keep / sh * pe[t] * sh / sh_post)
               for t in TIERS}

    # H method (A6b, user 2026-10-05): the higher of (a) full-capacity revenue and (b) the sell-side high path on
    # the same flat-price basis (internal leg held at FY2027: its g2 growth is product price, not wafers).
    int_h = prod_rev["H"] * int_ratio * (1 + g2) ** (ss_h - t0)
    path_tot = {s: {y: prod_rev[s] * int_ratio * (1 + g2) ** (y - t0) + ext[s][y] for y in sorted(ext[s])} for s in ("M", "H")}
    path_flat = {y: int_flat + ext["H"][y] for y in sorted(ext["H"])}
    h_method = "path" if path_flat[ss] > rev_full else "capacity"

    def v_net(t: str, method: str | None = None, **kw) -> float:
        if t == "H":
            o = (option_path_h if (method or h_method) == "path" else option_full)(**kw)
            return (o["pv"] - o["unspent"]) / sh_post - unspent_ps - overlap[t]
        return option(t, **kw)["pv"] / sh_post - unspent_ps - overlap[t]

    opt = {t: option(t) for t in ("L", "M")}
    opt["H"] = option_path_h() if h_method == "path" else option_full()
    opt_cap = option_full()
    v_k = {t: v_net(t) for t in TIERS}
    v_h_alt = v_net("H", method="capacity" if h_method == "path" else "path")
    # The chosen H revenue must top the M path and every year of the high path it stands for.
    h_rev_ss = max(rev_full, path_flat[ss])
    if not h_rev_ss >= path_tot["M"][ss]:
        errors.append(f"H revenue {h_rev_ss / B:.1f}B below the M path {path_tot['M'][ss] / B:.1f}B (A6b)")
    if h_method == "path" and opt["H"]["wafer_need"] < 0:
        errors.append("high path needs negative wafer revenue -- external packaging above the path (A6b)")
    if not pkg_named <= inp["ext_pkg_h_2030"]:
        errors.append(f"named packaging {pkg_named / B:.1f}B exceeds the H external packaging {inp['ext_pkg_h_2030'] / B:.1f}B (A6b)")
    cap_check = {y: rev_cap(y)["total"] for y in path_tot["H"]}  # capacity in service that year (disclosure)
    v_opt = v_k["H"]
    p_k = {t: v_k[t] / v_opt for t in TIERS} if v_opt > 0 else {t: float("nan") for t in TIERS}
    adj_band = [base[t] + p_k[t] * v_opt for t in TIERS]
    a2, b2 = cut_points(*adj_band)
    if meta.v_opt is None or abs(meta.v_opt - v_opt) > TOL:
        errors.append(f"V_opt: stated {meta.v_opt} vs recomputed {v_opt:.4f}")
    if meta.p_tiers is None or any(abs(a - p_k[t]) > P_TOL for a, t in zip(meta.p_tiers, TIERS)):
        errors.append(f"p_L/p_M/p_H: stated {meta.p_tiers} vs eval " + "/".join(f"{p_k[t]:.4f}" for t in TIERS))

    # ---- Report ----
    print(f"formula_id: {FORMULA_IDS[0]} + {FORMULA_IDS[1]}")
    print(f"g2_cpu={g2:.4f} r={r:g} (篮 {baskets.get('r_perp')}) equity={eq / 1e9:.1f}B shares={sh / 1e9:.2f}B "
          f"+ escrow {esc_sh / 1e6:.0f}M @ ${esc_px:g} = {sh_post / 1e9:.3f}B")
    print(f"leg inference (A5c): margin " + " / ".join(f"{q} {q_margin[q]:.4f}" for q in QTRS)
          + f" -> H1 {margin:.4f} (FY25 {margin_fy25:.4f}); share " + " / ".join(f"{q} {q_share[q]:.4f}" for q in QTRS)
          + f" -> H1 {share:.4f}")
    for t in TIERS:
        print(f"{t}: OI {oi[t]:,.0f}M -> eps {eps[t]:.4f} ROE {roe[t]:.3f} -> PE {pe[t]:.2f}x -> CPU {cpu[t]:.2f}/sh")
    print(f"foundry leg (A21): FY2027 loss {loss27:.3f}/sh after tax (${loss27 * sh / keep / B:.2f}B pre-tax); "
          f"FY2028 loss from FY2028 consensus (rev {inp['cons_rev_fy28_m'] / B:.1f}B, EPS {inp['cons_eps_fy28_m']:g}) "
          f"{loss28:.3f}/sh (${loss28 * sh / keep / B:.2f}B pre-tax); breakeven L {be['L']:.0f} / M {be['M']:.0f} / H {be['H']:.0f} -> "
          + " ".join(f"{t} {fdy[t]:+.2f}" for t in TIERS))
    print(f"closure {adj:+.2f} (corp_other x M-PE {inp['corp_other_eps'] * pe['M']:+.2f})")
    print("pre-escrow L/M/H " + "/".join(f"{c['pre'][t]:.2f}" for t in TIERS) + " -> escrow "
          + "/".join(f"{base[t] - c['pre'][t]:+.2f}" for t in TIERS))
    print(f"base L={L:.2f} M={M:.2f} H={H:.2f}  A={A:.2f} B={B_:.2f}")
    num_lm, num_hm = eps["L"] / eps["M"], eps["H"] / eps["M"]
    print(f"L/M {dec['lm']:.3f} = eps {num_lm:.3f} x pe {dec['pe_lm']:.3f} x closure {dec['lm'] / (num_lm * dec['pe_lm']):.3f} | "
          f"H/M {dec['hm']:.3f} = eps {num_hm:.3f} x pe {dec['pe_hm']:.3f} x closure {dec['hm'] / (num_hm * dec['pe_hm']):.3f} | "
          f"width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.1%}")
    print(f"flat-multiple ladder @ M {pe['M']:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    g_lo, _ = implied_g(inp["pe_own_min"], roe["M"], r)
    g_hi, _ = implied_g(inp["pe_own_max"], roe["M"], r)
    print(f"guardrail: {pe['L']:.2f}/{pe['M']:.2f}/{pe['H']:.2f}x in [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]; "
          f"g at M-tier ROE [{g_lo:+.2%}, {g_hi:+.2%}]")
    print(f"cross-check HSBC 2027E core {eps_c:g} in [M {eps['M']:.2f}, H {eps['H']:.2f}]")
    w = inp["warrant_shares"]
    print("51% warrant if triggered (disclosure): " + "/".join(
        f"{(base[t] * sh_post + w * esc_px) / (sh_post + w) - base[t]:+.2f}" for t in TIERS))

    print(f"\nfoundry option: internal ratio {int_ratio:.4f} of product revenue; margins "
          + " / ".join(f"{t} {opm[t]:.2%}" for t in TIERS) + f"; capital {inp['ppe_net'] / B:.1f}B (PP&E net proxy)")
    print("external path $B (2029 interpolated): " + " | ".join(
        f"{t} " + " ".join(f"{y}:{ext[t][y] / B:.2f}" for y in sorted(ext[t])) for t in TIERS))
    print(f"packaging once: named {pkg_named / B:.1f}B <= low path 2029 {ext['L'][2029] / B:.2f}B; "
          f"high-path packaging {inp['ext_pkg_h_2030'] / B:.1f}B inside high 2030 {ext['H'][2030] / B:.1f}B")
    rf = rev_cap(ss_h)
    print(f"H (a) full capacity (A6b): price discount to TSMC {rf['disc']:.2%} (= 1 - (1 - {opm_strong:.3f}) / (1 - {opm['H']:.2f})); "
          f"Ohio {wspm_ohio:,.0f} WSPM (budget / capex per WSPM)")
    print(f"  {ss_h}: WSPM {rf['wspm']:,.0f} -> wafers $B " + " ".join(f"{k} {v / B:.2f}" for k, v in rf["by"].items())
          + f" = {rf['wafer'] / B:.2f} + own packaging/test {rf['pkg_own'] / B:.2f} + external packaging {rf['pkg_ext'] / B:.2f}"
          f" = {rev_full / B:.2f}B; H internal grown {int_h / B:.2f}B / flat {int_flat / B:.2f}B")
    print("  (b) sell-side high path, flat-price basis: " + " ".join(
        f"{y} {path_flat[y] / B:.2f} (grown {v / B:.2f}; in-service cap {cap_check[y] / B:.2f})"
        for y, v in path_tot["H"].items()) + f"; M path {ss} {path_tot['M'][ss] / B:.2f}"
        f"; Arizona JV {wspm_az:,.0f} WSPM (budget / capex per WSPM)")
    print(f"  H method: {'(b) high path' if h_method == 'path' else '(a) full capacity'} "
          f"({path_flat[ss] / B:.2f}B {ss} vs {rev_full / B:.2f}B {ss_h}); other method V_H {v_h_alt:.2f}")
    if h_method == "path":
        o = opt["H"]
        print(f"  (b) capacity: wafer revenue needed {o['wafer_need'] / B:.2f}B (= ({o['rev'] / B:.2f} - packaging "
              f"{inp['ext_pkg_h_2030'] / B:.1f}) x {1 - inp['pkg_share_tsm']:.2f}) vs all named fabs {o['wafer_named'] / B:.2f}B "
              f"({o['wspm_named']:,.0f} WSPM) -> new 14A-class {o['wspm_new']:,.0f} WSPM x ${inp['capex_per_wspm']:,.0f} "
              f"= ${o['capex_new'] / B:.1f}B unnamed capital")
    r26 = rev_cap(2026)
    print(f"  cross: capacity in service 2026 at H prices {r26['total'] / B:.2f}B vs H1'26 annualised foundry revenue "
          f"{inp['foundry_rev_h1'] * 2 / 1e3:.2f}B; revenue / net PP&E: H {opt['H']['rev'] / opt['H']['cap']:.2f} "
          f"(capital {opt['H']['cap'] / B:.1f}B) vs TSM 2025 {tsm_turn:.2f}")
    for t in TIERS:
        o = opt[t]
        extra = (f" - unspent capex PV {o['unspent'] / sh_post:.2f} (capital {o['cap'] / B:.1f}B)" if t == "H" else "")
        print(f"  {t}: NI $B " + " ".join(f"{y}:{v / B:.2f}" for y, v in o["ni"].items())
              + f" | ROE {o['roe']:.3f} -> PE {o['pe']:.2f}x | gross {o['pv'] / sh_post:.2f}" + extra
              + f" - unspent {unspent_ps:.3f} - overlap {overlap[t]:.2f} = V_{t} {v_k[t]:.2f}")
    print(f"表3  V_opt={v_opt:.2f}  p_k=" + "/".join(f"{p_k[t]:.4f}" for t in TIERS) + "  "
          + "  ".join(f"{t}:{base[t]:.2f}+{p_k[t]:.4f}xV={adj_band[i]:.2f}" for i, t in enumerate(TIERS))
          + f"  A'={a2:.2f} B'={b2:.2f}")

    # ---- Sensitivities ----
    def fmt(v) -> str:
        return "/".join(f"{x:.2f}" for x in v)

    def band(**kw) -> tuple[float, ...]:
        cc = compute(**kw)
        return tuple(cc["base"][t] for t in TIERS)

    for g in (g2 - 0.01, g2 + 0.01):
        print(f"sensitivity g2={g:.2%}: L/M/H {fmt(band(g_=g))}")
    print(f"sensitivity g2=6% (cap) / 0: M {band(g_=0.06)[1]:.2f} / {band(g_=0.0)[1]:.2f}; "
          f"equity pro forma 110.9B: M {band(eq_=1.109e11)[1]:.2f}; product share 89.7% (Citi external 2027E): M {band(s_=0.897)[1]:.2f}; "
          f"M loss FY2027 only: M {band(be_={'L': 2028, 'M': 2027, 'H': 2027})[1]:.2f}")
    print(f"sensitivity margin FY25 {margin_fy25:.4f}: L/M/H {fmt(band(m_=margin_fy25))} "
          f"(FY2028 loss -> {compute(m_=margin_fy25)['l28']:+.3f})")
    print(f"sensitivity FY2028 loss = FY2027 amount (old A21): {fmt(band(l28=loss27))}")
    print(f"sensitivity no escrow shares: " + fmt(tuple(c['pre'][t] for t in TIERS)))
    q2l = -inp["foundry_oi_q2"]
    mgmt27 = q2l * (3 + 2 + 1 + 0) / 6 * MM * keep / sh
    print(f"sensitivity management straight-line loss path (FY2027 {mgmt27:.3f}/sh, 0 from 2028): "
          f"{fmt(band(l27=mgmt27, l28=0.0))}")
    print(f"upgrade reading (not adopted): FY2028 consensus as numerator -> {fmt(band(fy28_num=True))}")
    print("option sensitivities (V_L/V_M/V_H, after unspent capital and overlap):")
    for dm in (-0.05, 0.05):
        print(f"  margin {dm:+.0%}: " + fmt(tuple(v_net(t, m_=opm[t] + dm) for t in TIERS)))
    print("  L/M path all-low: " + fmt(tuple(v_net(t, path=ext['L']) for t in ("L", "M")))
          + " | all-high: " + fmt(tuple(v_net(t, path=ext['H']) for t in ("L", "M"))))
    print("  breakeven +1y: " + fmt(tuple(v_net(t, be_t=be[t] + 1) for t in TIERS)))
    print("  discount at 15% (篮 7, not adopted): " + fmt(tuple(v_net(t, r_=0.15) for t in TIERS)))
    print("  L/M company-equity ROE (old convention, not adopted): " + fmt(tuple(v_net(t, capital=None) for t in ("L", "M"))))
    print("  L/M ramp retention deducted (not adopted: capacity built): " + fmt(tuple(v_net(t, retain=True) for t in ("L", "M"))))
    print("  L/M external only (no internal revenue): " + fmt(tuple(v_net(t, internal=False) for t in ("L", "M"))))
    print(f"  H at TSMC 10y margin and price without the yield discount: {v_net('H', m_=opm_strong):.2f}")
    print(f"  H Ohio at two Fab-52-size fabs ({2 * inp['wspm_f52']:,.0f} WSPM): {v_net('H', ohio_w=2 * inp['wspm_f52']):.2f}; "
          f"Fab 62 as a full twin ({inp['wspm_f52']:,.0f}) tooled with ${f62_extra / B:.1f}B beyond the JV budget: "
          f"{v_net('H', f62=inp['wspm_f52'], az_extra=f62_extra):.2f} (free, not adopted: {v_net('H', f62=inp['wspm_f52']):.2f}); "
          f"no own-wafer packaging/test revenue: {v_net('H', own_pkg=False):.2f}")
    print(f"  H without Ohio: {v_net('H', with_ohio=False):.2f}; "
          f"H g2 = cluster {g2f:.2%} instead of TSM {g2fh:.2%}: {v_net('H', g_=g2f):.2f} (binds only if ROE > r); "
          f"H +5pp with TSM g2: {v_net('H', m_=opm['H'] + 0.05):.2f} vs cluster g2 {v_net('H', m_=opm['H'] + 0.05, g_=g2f):.2f}")
    if h_method == "path":
        o_g = option_path_h(internal_growth=True)
        print(f"  H high path with internal grown at g2_cpu (L/M convention; needs ${o_g['capex_new'] / B:.1f}B unnamed capital): "
              f"{v_net('H', internal_growth=True):.2f}; H unnamed capital PV not deducted (ROE denominator unchanged, not adopted): "
              f"{(opt['H']['pv'] - opt['H']['unspent'] + spread_pv(opt['H']['capex_new'], ss, r)) / sh_post - unspent_ps - overlap['H']:.2f}")
    pkg_extra = {t: max(0.0, inp['opt_opm'] - opm[t]) * pkg_named * keep / sh_post * (1 + r) ** -(2029 - t0) / r for t in TIERS}
    print("  packaging 2B at the CFO's 30% instead of the tier margin (L/M uplift, perpetuity from 2029): "
          + fmt(tuple(pkg_extra[t] for t in TIERS)))
    print(f"  each extra $1B of unspent capital: -{B / sh_post:.3f}/sh; overlap disclosed only (not deducted): "
          + fmt(tuple(v_k[t] + overlap[t] for t in TIERS)))
    em_r = esc(eps["M"] / r + sum(inp[k] for k in ADJ_PS) + inp["corp_other_eps"] / r + fdy["M"])
    print(f"gate coordinate E_M/r {em_r:.2f}; M move vs 36.62 {M / 36.62 - 1:+.1%}")
    cons3 = (inp["cons_eps_fy27_low"], inp["cons_eps_fy27_m"], inp["cons_eps_fy27_h"])
    print("口径二 (company consensus EPS x tier PE + net cash, cross only): L/M/H "
          + fmt(tuple(esc(e_ * pe[t] + inp["net_cash_ps"]) for e_, t in zip(cons3, TIERS))))
    trough = inp["oi_products_trough"] * MM * keep / sh
    print(f"pressure: FY2023 trough eps {trough:.3f} x 1/r + closure + L foundry = {esc(trough / r + adj + fdy['L']):.2f}")

    def perpetual_loss_band() -> tuple[float, ...]:
        out = []
        pm = perpetual_pe(g2, (eps["M"] - loss27) * sh / eq, r)
        a_ = sum(inp[k] for k in ADJ_PS) + inp["corp_other_eps"] * pm
        for t in TIERS:
            e_ = eps[t] - loss27
            p_ = perpetual_pe(g2, e_ * sh / eq, r) if e_ * sh / eq > r else 1 / r
            out.append(esc(e_ * p_ + a_))
        return tuple(out)
    print("loss-perpetual SOTP (FY2027 foundry loss forever, not adopted): L/M/H " + fmt(perpetual_loss_band()))

    # ---- Checks ----
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B_}, tol=TOL)
    errors += ladder("base", L, M, H)
    if not 0 <= p_k["L"] <= p_k["M"] <= p_k["H"] == 1:
        errors.append(f"p_k must satisfy 0 <= p_L <= p_M <= p_H = 1, got {p_k}")
    if v_opt <= 0:
        errors.append(f"V_opt must be > 0 (valuation-rules: no zero for want of sell-side counts), got {v_opt:.2f}")
    if not all(t0 <= be[t] < ss for t in TIERS):
        errors.append(f"breakeven years must sit in [t_num, ss_year): {be} / {ss}")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")

    # r_f readings (_AXIS.rates): Δr_f moves r_perp 1:1 in every tier multiple,
    # the corp-unallocated closure and the FY2028 loss discount; the option is outside the base.
    def band_at(dr: float) -> tuple[float, float, float]:
        return band(r_=r + dr)  # type: ignore[return-value]

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_at)
    if not errors:
        write_rf_readings("INTC.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
