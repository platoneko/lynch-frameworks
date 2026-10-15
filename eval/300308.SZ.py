#!/usr/bin/env python3
"""300308.SZ (中际旭创 / Zhongji Innolight) valuation eval — recompute anchors
from frameworks/300308.SZ.md.

frameworks/300308.SZ.md is the source of truth; this script re-derives
L/M/H / A/B and the NPO option from the §3 Inputs table and exits 1 on
mismatch.  The doc carries no current price (AGENTS.md「现价 — 禁写契约」), so
nothing here reads a quote.

formula_id: zjxc_pluggable_fy27_two_stage_gordon_npo_opt_v4

Main ruler: the pluggable-module business only (NPO is carved out into V_opt).
Numerator year FY2027 — the furthest year with a >=2-house consensus range
(yfinance +1y, 4 houses) — restated from the A-share count the consensus is
struck on to the post-H-share total count.  L = FY27 digestion year (FY26
revenue consensus x (1 - rev_cut_l) x FY25 realised net margin), no transition.
M / H = FY27 consensus mean / high, then ONE transition year: FY28 growth =
mean of the two houses that state FY28 (UBS EPS, Citi NI) with the NPO share
(UBS 10%, applied to both — A11) stripped out, then perpetual g2.  g2 is the
peer-ruler axis value `_AXIS.pluggable-module` (frameworks/axes/pluggable-
module.md, row g2_pluggable): user-set 2% (below the named macro 4%: a declared
rule deviation), peer-checked by leg and market (A16); cross-file checked.

Operating value + excess cash (valuation-rules「经营价值与超额现金」, 2026-10-15
framework correction, A25): C_ex = 2026H1 extended net cash (long-term payables
deducted) + post-period H-share net proceeds - declared interim dividend, anchor
0 (own 2017-2026H1 min net cash / revenue is negative).  The after-tax income of
C_ex comes out of all three numerators; RONIC is E^op_{n+1}/B^op_n: FY27
operating EPS over the FY27 opening book (2026-06-30 equity + H-share net
proceeds - interim dividend + the unbooked H2 FY26 consensus profit retained at
the growth-required b = g/RONIC, g1 for M/H, g2 for L; fixed point) minus C_ex
per share.  Anchor = operating value x (1 - k) + C_ex per share (lambda 1); the
user-set retention haircut k (2026-09-29, A20) stays and now touches the
operating part only.

The NPO option leg is left as it was (main-thread ruling 2026-10-15): its
multiple still uses the H-tier book ROE of the old roll (cash not stripped).

Option (A13, valuation-rules「未建模期权」2026-10-03): NPO FY28 net profit =
UBS FY28 revenue x NPO share (count still a single-house forecast: no company-
named NPO quantity — declared deviation) x the aligned-year (FY28, furthest
year with >=2 houses) company-level consensus net margin (mean of UBS derived
on A shares and Citi stated; a shared plug — no leg-level data), valued in the
realisation year t_opt (company-named: 2028 larger-scale shipments) on this
ticker's ruler — basket r, H-tier ROE, g_npo from the optical cross-section
(LITE.US A16 6.64% capped at 6%) — and discounted back (1+r)^-(t_opt - 2027).
p_L / p_M / p_H are constants here, never Inputs.

Run:  python3 frameworks/eval/300308.SZ.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import (  # noqa: E402
    check_capex_mount,
    check_optical_narrow_attach,
    check_optical_oe_mount,
    optical_attachment,
)
from eval.lib.gordon import (  # noqa: E402
    check_branch,
    check_g_cap,
    check_r,
    check_transition_years,
    g_cap,
    implied_g,
    payout,
    perpetual_pe,
    two_stage_pe,
)
from eval.lib.inputs import parse_baskets  # noqa: E402
from eval.lib.tiers import decompose, flat_multiple_ladder  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "300308.SZ.md"
AXIS_PLUG = REPO_ROOT / "frameworks" / "axes" / "pluggable-module.md"
FORMULA_ID = "zjxc_pluggable_fy27_two_stage_gordon_npo_opt_v4"
TOL = 0.05
MIN_R_MINUS_G = 0.02
N_STAGE = 1  # FY28 is the only year beyond the numerator with >=2 stated houses
CONSENSUS_YEARS_BEYOND = 1
NUM_YEAR = 2027  # numerator year FY2027 = t 1, not discounted
MACRO_G = 0.04  # valuation-rules「6% 的含义」: named long-run nominal growth
P_TIERS = (0.3, 0.6, 1.0)  # A13: 无概率锚·拍值; p_H default 1.0
TIERS = ("L", "M", "H")


def parse_inputs(md: str) -> dict[str, float]:
    """§3 Inputs: | field | value | meaning | as-of |."""
    out: dict[str, float] = {}
    in_inputs = False
    for line in md.splitlines():
        if line.startswith("### Inputs"):
            in_inputs = True
            continue
        if in_inputs and line.startswith("### "):
            break
        if not in_inputs or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("字段名", "--------", "---"):
            continue
        try:
            out[cells[0]] = float(cells[1].replace(",", ""))
        except ValueError:
            continue
    return out


def first_float(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


REQUIRED = [
    "eps_fy26_cons", "rev_fy26_cons", "nm_fy25", "rev_cut_l",
    "eps_fy27_l", "eps_fy27_m", "eps_fy27_h", "shares_a", "shares_total",
    "ubs_eps27", "ubs_eps28", "citi_ni27", "citi_ni28", "npo_share_28", "ubs_rev28",
    "citi_nm28", "t_opt",
    "equity_h1", "h_shares", "h_price_hkd", "hkdcny", "h_fee", "dps_interim",
    "shares_div", "ni_h2_cons", "r_perp", "g2", "g_npo", "k_l", "k_m", "k_h",
    "payout_obs", "pe_own_min", "pe_own_max", "rev_fy27_cons", "usdcny",
    "npo_units_27", "npo_units_28", "oe_l", "oe_m", "oe_h",
    "capex_l", "capex_m", "capex_h",
    "net_cash_ext_h1", "c_ex", "cash_yield", "tax_eff", "payout_op",
]


def check_inputs(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    e: list[str] = []
    if "r_perp" not in baskets:
        e.append("r_perp: Inputs source cell names no 篮 N (A15)")
    e += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    for key in ("g2", "g_npo"):
        e += check_g_cap(inp[key], inp["r_perp"], key)
        if inp["r_perp"] - inp[key] < MIN_R_MINUS_G:
            e.append(f"r - {key} < {MIN_R_MINUS_G:.0%}: at the pole")
    if inp["g2"] <= 0:
        e.append("g2 <= 0 barred: FY27 -> FY28 consensus rises (同世界门, A16)")
    e += check_transition_years(N_STAGE, CONSENSUS_YEARS_BEYOND, "g1")
    if not (inp["eps_fy27_l"] < inp["eps_fy27_m"] < inp["eps_fy27_h"]):
        e.append("FY27 consensus range must be ordered low < mean < high (one record, two ends)")
    if not (0 < inp["rev_cut_l"] < 1 and 0 < inp["nm_fy25"] < 1 and 0 < inp["npo_share_28"] < 1):
        e.append("rev_cut_l / nm_fy25 / npo_share_28 must be fractions")
    if not (0 <= inp["k_l"] <= inp["k_m"] <= inp["k_h"] < 1):
        e.append("k must satisfy 0 <= k_L <= k_M <= k_H < 1 (cyclical, 留存去向审计)")
    if inp["shares_a"] >= inp["shares_total"]:
        e.append("shares_a must be below shares_total (H-share dilution)")
    if inp["t_opt"] <= NUM_YEAR:
        e.append("option realisation year must lie after the numerator year (A13)")
    if not 0 < inp["citi_nm28"] < 1:
        e.append("citi_nm28 must be a fraction")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        e.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")
    return e


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1
    inp = parse_inputs(md)
    missing = [k for k in REQUIRED if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1
    baskets = parse_baskets(md)
    errors = check_inputs(inp, baskets)
    # Peer-ruler axis (contracts.md「同业尺轴」): g2 is the leg ruler, single source = the axis file.
    if AXIS_PLUG.is_file():
        ax = parse_inputs(AXIS_PLUG.read_text(encoding="utf-8"))
        if "g2_pluggable" not in ax or abs(ax["g2_pluggable"] - inp["g2"]) > 1e-9:
            errors.append(f"g2 {inp['g2']:g} != _AXIS.pluggable-module g2_pluggable {ax.get('g2_pluggable')} — the leg ruler drifted")
    else:
        errors.append("frameworks/axes/pluggable-module.md missing — g2 unchecked")
    errors += check_optical_oe_mount((inp["oe_l"], inp["oe_m"], inp["oe_h"]))
    errors += check_capex_mount((inp["capex_l"], inp["capex_m"], inp["capex_h"]))
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    r, g2 = inp["r_perp"], inp["g2"]
    sh = inp["shares_total"]  # 百万股; money inputs are 百万 CNY
    adj = inp["shares_a"] / sh

    # ---- Step 1: numerators (FY27, per total share) ----
    eps = {
        "L": inp["rev_fy26_cons"] * (1 - inp["rev_cut_l"]) * inp["nm_fy25"] / sh,
        "M": inp["eps_fy27_m"] * adj,
        "H": inp["eps_fy27_h"] * adj,
    }
    # ---- Step 2: FY28 transition, NPO stripped (A4 / A11) ----
    g_total = (inp["ubs_eps28"] / inp["ubs_eps27"] + inp["citi_ni28"] / inp["citi_ni27"]) / 2
    g1 = g_total * (1 - inp["npo_share_28"]) - 1
    stage = {"L": False, "M": True, "H": True}

    # ---- Step 3: FY27 opening book, excess cash, fixed point on b = g/RONIC (A5 / A25) ----
    h_net = inp["h_shares"] * inp["h_price_hkd"] * inp["hkdcny"] * (1 - inp["h_fee"])
    div = inp["dps_interim"] * inp["shares_div"]  # declared, ex 2026-10-12: debt-like
    eq0 = inp["equity_h1"] + h_net - div
    c_ex = inp["net_cash_ext_h1"] + h_net - div  # operating-cash anchor 0 (A25)
    if abs(c_ex - inp["c_ex"]) > 1.0:
        errors.append(f"c_ex {inp['c_ex']:.2f} != net_cash_ext_h1 + H-share net - declared div {c_ex:.2f}")
    if c_ex < 0.15 * eq0:
        errors.append("c_ex below 15% of parent equity: the excess-cash line should not exist")
    c_inc = c_ex * inp["cash_yield"] * (1 - inp["tax_eff"])  # after-tax, out of every numerator
    cps = c_ex / sh
    eop = {t: eps[t] - c_inc / sh for t in TIERS}

    def tier(e: float, with_g1: bool, g: float = g2, cash: float = cps) -> tuple[float, float, float]:
        """(operating BPS_open, RONIC, multiple) for one FY27 numerator; cash=0 gives the old book roll."""
        grow = g1 if with_g1 else g
        bps = (eq0 + inp["ni_h2_cons"]) / sh - cash
        for _ in range(300):
            roe = e / bps
            nxt = (eq0 + inp["ni_h2_cons"] * min(1.0, grow / roe)) / sh - cash
            if abs(nxt - bps) < 1e-10:
                break
            bps = nxt
        roe = e / bps
        pe = two_stage_pe(g1, N_STAGE, g, roe, r) if with_g1 else perpetual_pe(g, roe, r)
        return bps, roe, pe

    bps, roe, pe = {}, {}, {}
    for t in TIERS:
        bps[t], roe[t], pe[t] = tier(eop[t], stage[t])
    roe_book_h = tier(eps["H"], True, cash=0.0)[1]  # option leg unchanged (pre-correction H book ROE)
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}
    pre = {t: eop[t] * pe[t] for t in TIERS}  # operating value before k
    L, M, H = (pre[t] * (1 - k[t]) + cps for t in TIERS)
    A, B = (L + M) / 2, (M + H) / 2
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}")
    ret_obs = 1 - inp["payout_obs"]
    for t in TIERS:
        if roe[t] - r < 0.03:
            errors.append(f"{t}: RONIC {roe[t]:.3f} not in the monotone domain at r {r:g}")
        errors += check_branch(g2, roe[t], r, inp["payout_op"], f"g2@{t}")
        if g2 > ret_obs * roe[t]:  # ③ constraint 2: g <= (1 - d) x RONIC
            errors.append(f"{t}: g2 {g2:.2%} above (1 - d) x RONIC {ret_obs * roe[t]:.2%}")
    for t in ("M", "H"):
        if not (0 < g1 / roe[t] < 1):
            errors.append(f"{t}: stage-1 b1 = g1/RONIC {g1 / roe[t]:.3f} outside (0,1)")

    # ③ guardrail: M operating multiple inside own realised operating forward-PE band (A17).
    if not (inp["pe_own_min"] <= pe["M"] <= inp["pe_own_max"]):
        errors.append(f"M multiple {pe['M']:.2f}x outside own band [{inp['pe_own_min']}, {inp['pe_own_max']}] — ③ 出带")

    # ---- Step 5: NPO option (A13): aligned-year margin, own ruler, timed discount ----
    nm_ubs28 = inp["ubs_eps28"] * inp["shares_a"] / inp["ubs_rev28"]
    nm_opt = (nm_ubs28 + inp["citi_nm28"]) / 2
    npo_ni = inp["ubs_rev28"] * inp["npo_share_28"] * nm_opt
    eps_npo = npo_ni / sh
    pe_npo = perpetual_pe(inp["g_npo"], roe_book_h, r)
    disc = (1 + r) ** (inp["t_opt"] - NUM_YEAR)
    v_opt = eps_npo * pe_npo / disc
    plus_v = tuple(x + p * v_opt for x, p in zip((L, M, H), P_TIERS))

    # ---- A2e-2c flat ladder + decomposition ----
    flat_errs, flat_op = flat_multiple_ladder((eop["L"], eop["M"], eop["H"]), pe["M"] * (1 - k["M"]))
    errors += flat_errs
    flat = tuple(x + cps for x in flat_op)
    # Decomposition on the operating part (anchor - C_ex per share); full L/M, H/M printed beside it.
    dec = decompose((L - cps, M - cps, H - cps),
                    (pe["L"] * (1 - k["L"]), pe["M"] * (1 - k["M"]), pe["H"] * (1 - k["H"])))

    # ---- Axes (A18) ----
    npo_asp_cny = inp["ubs_rev28"] * inp["npo_share_28"] / inp["npo_units_28"]  # 百万 CNY / unit
    narrow = {
        # Axis tiers are one year (2028): L = delayed a year (2027 volume), M = H = UBS 2028.
        "L": inp["npo_units_27"] * npo_asp_cny * 1e6 / inp["usdcny"],
        "M": inp["ubs_rev28"] * inp["npo_share_28"] * 1e6 / inp["usdcny"],
        "H": inp["ubs_rev28"] * inp["npo_share_28"] * 1e6 / inp["usdcny"],
    }
    errors += check_optical_narrow_attach(narrow)
    oe = {"L": inp["oe_l"], "M": inp["oe_m"], "H": inp["oe_h"]}

    # ---- Reconcile stated Outputs ----
    out_sec = md.split("### Outputs", 1)[-1]
    stated = {
        "L": first_float(r"L = \*\*([0-9.]+)\*\*", out_sec),
        "M": first_float(r"M = \*\*([0-9.]+)\*\*", out_sec),
        "H": first_float(r"H = \*\*([0-9.]+)\*\*", out_sec),
        "A": first_float(r"A = \*\*([0-9.]+)\*\*", out_sec),
        "B": first_float(r"B = \*\*([0-9.]+)\*\*", out_sec),
        "V": first_float(r"V_\{opt\}\\\) = \*\*([0-9.]+)\*\*", out_sec),
    }
    for key, got in {"L": L, "M": M, "H": H, "A": A, "B": B, "V": v_opt}.items():
        said = stated.get(key)
        if said is None:
            errors.append(f"stated {key} not found in Outputs")
        elif abs(said - got) > TOL:
            errors.append(f"{key}: stated {said} vs recomputed {got:.4f}")
    p_line = re.search(r"p_L/p_M/p_H\\\) = \*\*([0-9.]+) / ([0-9.]+) / ([0-9.]+)\*\*", out_sec)
    if p_line is None or tuple(float(x) for x in p_line.groups()) != P_TIERS:
        errors.append(f"Outputs p_L/p_M/p_H must state {P_TIERS}")

    # ---- Report ----
    print(f"formula_id={FORMULA_ID}")
    print(f"share basis: consensus EPS on A shares {inp['shares_a']:.3f}M -> total {sh:.3f}M (x{adj:.4f})")
    print(f"FY28: UBS {inp['ubs_eps28'] / inp['ubs_eps27'] - 1:+.1%}, Citi {inp['citi_ni28'] / inp['citi_ni27'] - 1:+.1%}"
          f" -> mean {g_total - 1:+.1%}, NPO {inp['npo_share_28']:.0%} stripped -> g1 {g1:+.2%} (M/H, n={N_STAGE})")
    print(f"g2 {g2:.2%} (user-set; named macro {MACRO_G:.0%}, cap {g_cap(r):.0%}) r {r:g} (篮 {baskets['r_perp']})")
    print(f"FY27 opening equity: H1 {inp['equity_h1']:.0f} + H-share net {h_net:.0f} - interim div "
          f"{div:.0f} + retained share of H2 NI {inp['ni_h2_cons']:.0f} (百万 CNY)")
    print(f"超额现金: 扩展口径净现金 2026H1 {inp['net_cash_ext_h1']:.0f} + H 股净募资 {h_net:.0f} − 已宣派中期股息 {div:.0f}"
          f" − 锚 0 = C_ex {c_ex:.0f} 百万（每股 {cps:.2f}，占发行后归母权益 {eq0:.0f} 的 {c_ex / eq0:.1%}，λ 1）；"
          f"税后收益 {c_inc:.0f} 百万 = 每股 {c_inc / sh:.4f}，三档分子同扣")
    for t in TIERS:
        print(f"{t}: EPS {eps[t]:.4f} -> 经营 EPS {eop[t]:.4f} 经营 BPS_open {bps[t]:.2f} RONIC {roe[t]:.3f} PE {pe[t]:.2f}"
              f" -> V_op {pre[t]:.2f} x (1-k {k[t]:.2f}) + C_ex {cps:.2f} = {pre[t] * (1 - k[t]) + cps:.2f}"
              f"  [perpetual payout {payout(g2, roe[t]):.3f}{f', stage-1 b1 {g1 / roe[t]:.3f}' if stage[t] else ''}]")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"branch: payout_op {inp['payout_op']:.1%} (分红 + 现金积累, FY2018–25); 实付派息 {inp['payout_obs']:.0%}; "
          f"约束 2 上限 (1-d) x RONIC: " + " ".join(f"{t} {ret_obs * roe[t]:.1%}" for t in TIERS) + f" vs g2 {g2:.0%}")
    print(f"NPO option: FY28 net margin UBS {nm_ubs28:.4f} / Citi {inp['citi_nm28']:.4f} -> {nm_opt:.4f}"
          f" (FY25 realised {inp['nm_fy25']:.4f}, lower-bound disclosure only)")
    print(f"NPO option: NI {npo_ni:.0f} 百万 -> EPS {eps_npo:.4f} x PE {pe_npo:.2f} (g {inp['g_npo']:.0%}, H book ROE {roe_book_h:.3f}"
          f" — option leg unchanged, payout {payout(inp['g_npo'], roe_book_h):.3f}) = {eps_npo * pe_npo:.2f} in {int(inp['t_opt'])}"
          f" / {disc:.4f} = V_opt {v_opt:.2f}; p {P_TIERS} -> +V {plus_v[0]:.2f}/{plus_v[1]:.2f}/{plus_v[2]:.2f}"
          f" A' {(plus_v[0] + plus_v[1]) / 2:.2f} B' {(plus_v[1] + plus_v[2]) / 2:.2f}")
    print(f"guardrail: M operating {pe['M']:.2f}x (after k {pe['M'] * (1 - k['M']):.2f}x) vs own operating band "
          f"[{inp['pe_own_min']}, {inp['pe_own_max']}]; L {pe['L']:.2f}x H {pe['H']:.2f}x")
    for t in TIERS:
        g_lo, _ = implied_g(inp["pe_own_min"], roe[t], r)
        g_hi, _ = implied_g(inp["pe_own_max"], roe[t], r)
        print(f"  band-edge implied g @ RONIC_{t} {roe[t]:.3f}: [{g_lo:+.2%}, {g_hi:+.2%}]")
    print(f"flat ladder @ M {pe['M']:.2f}x x (1-k_M) + C_ex: " + "/".join(f"{x:.2f}" for x in flat))
    print(f"L/M {L / M:.3f} H/M {H / M:.3f} | operating part: L/M {dec['lm']:.3f} = num {dec['num_lm']:.3f} x pe {dec['pe_lm']:.3f}"
          f" | H/M {dec['hm']:.3f} = num {dec['num_hm']:.3f} x pe {dec['pe_hm']:.3f}"
          f" | width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}")
    print("多留部分 (1 - b - d, 元/股/年, FY27 经营分子; 落在超额现金, λ 1, PV 不进锚点; k 另作用于经营价值): "
          + " ".join(f"{t} {ret_obs - (g1 if stage[t] else g2) / roe[t]:.1%} = "
                     f"{(ret_obs - (g1 if stage[t] else g2) / roe[t]) * eop[t]:.2f}" for t in TIERS)
          + f"  [actual retention {ret_obs:.0%}]")

    def anchor(t: str, g: float = g2, g1_: float | None = None) -> float:
        e_ = eop[t]
        if stage[t]:
            r_ = tier(e_, True, g)[1]
            pe_ = two_stage_pe(g1 if g1_ is None else g1_, N_STAGE, g, r_, r)
        else:
            pe_ = tier(e_, False, g)[2]
        return e_ * pe_ * (1 - k[t]) + cps

    for g in (g2 - 0.01, g2 + 0.01, MACRO_G):
        print(f"  sens g2={g:.2%}: " + "/".join(f"{anchor(t, g):.2f}" for t in TIERS))
    for lab, gt in (("derived 4-house mean", (84.96 / 60.69 + 1670 / 970 + 79 / 59.89 + 82.4 / 59.67) / 4),):
        g1_alt = gt * (1 - inp["npo_share_28"]) - 1
        print(f"  sens g1 from {lab} ({g1_alt:+.1%}): " + "/".join(f"{anchor(t, g1_=g1_alt):.2f}" for t in TIERS))
    for cut in (0.20, 0.40):
        e_ = inp["rev_fy26_cons"] * (1 - cut) * inp["nm_fy25"] / sh - c_inc / sh
        print(f"  sens rev_cut_l={cut:.0%}: L {e_ * tier(e_, False)[2] * (1 - k['L']) + cps:.2f}")
    print(f"  k = 0 reference: " + "/".join(f"{pre[t] + cps:.2f}" for t in TIERS))
    print("optical narrow (NPO, USD): " + " ".join(
        f"{t} ${narrow[t] / 1e9:.3f}B attach {optical_attachment(narrow[t], t):.1%} (OE share {n_ / oe[t]:.1%})"
        for t, n_ in (("L", inp["npo_units_27"]), ("M", inp["npo_units_28"]), ("H", inp["npo_units_28"]))))
    rev_usd = inp["rev_fy27_cons"] * 1e6 / inp["usdcny"]
    print(f"capex axis implied share (wide, FY27 revenue ${rev_usd / 1e9:.1f}B): M {rev_usd / inp['capex_m']:.2%}")
    print("r_f readings: CNY segment of _AXIS.rates 待建 — not printed")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
