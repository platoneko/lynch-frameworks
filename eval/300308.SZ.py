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

2026-10-16 framework correction (valuation-rules「经营价值与超额现金」):
  * data fix: the 2026-09 A-share buyback (4,997.25 百万, held for the ESOP, not
    cancelled) leaves the cash and the book (A25);
  * parent share 95.30% = parent equity / (parent + minority 4,208) on C_ex, its
    income and the operating book;
  * time alignment: Gordon value at 2027-01-01 x (1+r)^-tau (tau 0.5) plus the
    2H26 window distributable profit (unbooked consensus less half a year of
    cash income) x (1 - b), b = g/RONIC of the book roll, at tau/2;
  * three-stage return: forward RONIC through Y1 2028, linear to the steady
    return by Y2 2032 (_AXIS.pluggable-module: module assembly, medium barrier),
    steady = min(forward, axis 18%) = 18% (2026-10-19 ordered pick, no max:
    own cycle 14.4% is the pre-AI module era, no full cycle since the
    structural change -> own unusable, comparison only; business model
    unchanged -> not narrative-shift; peer layer empty -> axis fallback);
  * the user-set k on the whole operating value (A20) is removed (wrong object).

2026-10-19 framework correction (user-approved parameters; rules/retention.md
稳态回报三段「同一公司内部一致」「高回报期对产品阶段」):
  * main margin path (A27): each tier's starting net margin (L FY25 realised,
    M / H FY2028 company-level consensus) is held through Y1 2028 and fades
    linearly to the normal 20% (nm_norm_main) by Y2 2032 — the profit stream in
    path_value is scaled by that ratio; reason: CPO replaces pluggables in
    scale-out, plus competition;
  * NPO option (A13): count = UBS single-house path — 2028 10% of FY28 revenue,
    2030 30% of total revenue with NPO on top of the pluggable business
    (incremental: scale-up takes copper's share), 2029 geometric interpolation,
    g_npo 2% after 2030; unit economics: FY2028 consensus margin and the old
    H-tier book ROE 94.3% held to 2030, faded to 20% / 18% by 2035 (packaging
    link of _AXIS.ai-capex, cross-file checked: near-package ships from 2027H2,
    so it is not in the module-assembly 2028 bottleneck); payout 1 - g_t/ROE_t
    (negative in ramp years = capital the ramp needs); valued at the start of
    2028, back to FY2027, then tau.
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
)
from eval.lib.inputs import parse_baskets  # noqa: E402
from eval.lib.tiers import decompose, flat_multiple_ladder  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "300308.SZ.md"
AXIS_PLUG = REPO_ROOT / "frameworks" / "axes" / "pluggable-module.md"
AXIS_CAPEX = REPO_ROOT / "frameworks" / "axes" / "ai-capex.md"
NPO_INTERP_YEAR = 2029  # geometric interpolation between UBS 2028 and 2030 (插值年, A13)
NPO_LAST_NAMED = 2030   # last year with a named NPO quantity (UBS 30% of revenue)
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
    "buyback", "minority_h1", "parent_ratio", "tau", "y1", "y2", "ss_return", "ss_return_m", "ss_return_h", "ss_return_npo", "own_cycle", "npo_roe", "npo_nm_norm",
    "nm_norm_main", "y1_npo", "y2_npo", "npo_share_30",
]


def lin_path(cal: int, a: float, b: float, y1: int, y2: int) -> float:
    """a through y1, linear to b by y2, b after (稳态回报三段 / 未建模期权 单位经济回落)."""
    return a if cal <= y1 else (b if cal >= y2 else a + (b - a) * (cal - y1) / (y2 - y1))


def path_value(g1: float, n: int, g2: float, roe: float, r: float, t0: int, y1: int, y2: int, r_s: float,
               m_ratio: float = 1.0) -> float:
    """Three-stage retention Gordon (valuation-rules ② 稳态回报三段) per unit of t0 earnings at the start of
    t0: n transition years at g1 (retention g1/roe), then g2 with RONIC = roe through y1, linear to
    min(roe, r_s) by y2, perpetual after.  The profit stream is scaled by the margin path: 1 through y1,
    linear to min(1, m_ratio) = normal / starting net margin by y2, that ratio after (A26, 2026-10-19)."""
    ss = min(roe, r_s)
    mr = min(1.0, m_ratio)
    pv, e, t = 0.0, 1.0, 1
    for _ in range(n):
        cal = t0 + t - 1
        pv += e * lin_path(cal, 1.0, mr, y1, y2) * (1.0 - g1 / roe) / (1 + r) ** t
        e *= 1 + g1
        t += 1
    while True:
        cal = t0 + t - 1
        if cal > y1 and cal >= y2:
            return pv + e * mr * payout(g2, ss) / ((r - g2) * (1 + r) ** (t - 1))
        ro = lin_path(cal, roe, ss, y1, y2)
        pv += e * lin_path(cal, 1.0, mr, y1, y2) * payout(g2, ro) / (1 + r) ** t
        e *= 1 + g2
        t += 1


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
    if any(inp[f"k_{x}"] != 0.0 for x in ("l", "m", "h")):
        e.append("k must be 0: the k on the whole operating value was removed 2026-10-16 (A20)")
    if inp["shares_a"] >= inp["shares_total"]:
        e.append("shares_a must be below shares_total (H-share dilution)")
    if inp["t_opt"] <= NUM_YEAR:
        e.append("option realisation year must lie after the numerator year (A13)")
    if not 0 < inp["citi_nm28"] < 1:
        e.append("citi_nm28 must be a fraction")
    if not inp["npo_share_28"] < inp["npo_share_30"] < 1:
        e.append("npo_share_30 must be a fraction above npo_share_28 (UBS 2030 path, A13)")
    if abs(inp["npo_nm_norm"] - inp["nm_norm_main"]) > 1e-9:
        e.append("npo_nm_norm must equal nm_norm_main: one normal margin inside one company (A13 / A26)")
    if not (inp["t_opt"] <= inp["y1_npo"] < inp["y2_npo"]):
        e.append("NPO high-return window must satisfy t_opt <= y1_npo < y2_npo")
    if not 0 < inp["nm_norm_main"] < 1:
        e.append("nm_norm_main must be a fraction")
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
        for mine, theirs in (("ss_return", "ss_return_plug"), ("y1", "y1_plug"), ("y2", "y2_plug")):
            if theirs not in ax or abs(ax[theirs] - inp[mine]) > 1e-9:
                errors.append(f"{mine} {inp[mine]:g} != _AXIS.pluggable-module {theirs} {ax.get(theirs)}")
    else:
        errors.append("frameworks/axes/pluggable-module.md missing — g2 unchecked")
    # NPO high-return window = the packaging link of _AXIS.ai-capex §4b (near-package product, A13).
    if AXIS_CAPEX.is_file():
        axc = parse_inputs(AXIS_CAPEX.read_text(encoding="utf-8"))
        for mine, theirs in (("y1_npo", "y1_ai_capex_package"), ("y2_npo", "y2_ai_capex_package"),
                             ("ss_return_npo", "ss_floor_ai_capex_package")):
            if theirs not in axc or abs(axc[theirs] - inp[mine]) > 1e-9:
                errors.append(f"{mine} {inp[mine]:g} != _AXIS.ai-capex {theirs} {axc.get(theirs)}")
    else:
        errors.append("frameworks/axes/ai-capex.md missing — NPO Y1/Y2 unchecked")
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
    bb = inp["buyback"]                            # 2026-09 A-share buyback (ESOP), cash out, book down
    eq0 = inp["equity_h1"] + h_net - div - bb
    c_tot = inp["net_cash_ext_h1"] + h_net - div - bb  # operating-cash anchor 0 (A25)
    if abs(c_tot - inp["c_ex"]) > 1.0:
        errors.append(f"c_ex {inp['c_ex']:.2f} != net_cash_ext_h1 + H-share net - declared div - buyback {c_tot:.2f}")
    pr = eq0 / (eq0 + inp["minority_h1"])          # ① 归母份额: no subsidiary cash disclosure
    if abs(pr - inp["parent_ratio"]) > 5e-5:
        errors.append(f"parent_ratio {inp['parent_ratio']} != recomputed {pr:.4f}")
    c_ex = c_tot * pr
    if c_ex < 0.15 * eq0:
        errors.append("c_ex below 15% of parent equity: the excess-cash line should not exist")
    c_inc = c_ex * inp["cash_yield"] * (1 - inp["tax_eff"])  # after-tax, out of every numerator
    cps = c_ex / sh
    eop = {t: eps[t] - c_inc / sh for t in TIERS}
    tau = inp["tau"]
    y1, y2 = int(inp["y1"]), int(inp["y2"])
    r_s = inp["ss_return"]
    # M steady: de-cycled M forward (normal margin x pre-AI turnover 1.05; the margin step is in the
    # FY2024-25 reports, medium barrier -> raised, A26); H: normal margin x own mean turnover 1.33.
    if abs(inp["ss_return_m"] - round(inp["nm_norm_main"] * 1.05, 3)) > 5e-4:
        errors.append(f"ss_return_m {inp['ss_return_m']} != nm_norm_main x pre-AI turnover 1.05 (A26)")
    if not r_s + 0.02 - 1e-9 <= inp["ss_return_m"] <= inp["ss_return_h"] + 1e-9:
        errors.append(f"ss_return_m {inp['ss_return_m']} outside [ordered {r_s} + 2pp, H {inp['ss_return_h']}] (A26)")
    if not inp["ss_return_m"] - 1e-9 <= inp["ss_return_h"] <= 0.30 + 1e-9:
        errors.append(f"ss_return_h {inp['ss_return_h']} outside [ss_return_m {inp['ss_return_m']}, 30%] (A26)")
    if abs(inp["ss_return_h"] - round(inp["nm_norm_main"] * 1.33, 3)) > 5e-4:
        errors.append(f"ss_return_h {inp['ss_return_h']} != nm_norm_main x own mean turnover 1.33 (A26)")
    # Ordered pick (2026-10-19): own cycle unusable (no full cycle after the structural change), so the
    # steady return is the axis value as-is (checked against the axis above); own_cycle is display only.

    # Margin path (A26, 2026-10-19): each tier's starting net margin (L: FY25 realised; M / H: FY2028
    # company-level consensus = the shortage-period margin) held through y1, linear to nm_norm_main by y2.
    nm_ubs28 = inp["ubs_eps28"] * inp["shares_a"] / inp["ubs_rev28"]
    nm_opt = (nm_ubs28 + inp["citi_nm28"]) / 2
    nm0 = {"L": inp["nm_fy25"], "M": nm_opt, "H": nm_opt}

    def mratio(t: str, norm: float | None = None) -> float:
        return (inp["nm_norm_main"] if norm is None else norm) / nm0[t]

    def tier(e: float, with_g1: bool, g: float = g2, cash: float = cps, rs: float | None = None,
             yy: tuple[int, int] | None = None, mr: float = 1.0) -> tuple[float, float, float, float]:
        """(operating BPS_open, RONIC, three-stage multiple, b) for one FY27 numerator."""
        grow = g1 if with_g1 else g
        bps = (eq0 + inp["ni_h2_cons"]) / sh - cash
        for _ in range(300):
            roe = e / bps
            nxt = (eq0 + inp["ni_h2_cons"] * min(1.0, grow / roe)) / sh - cash
            if abs(nxt - bps) < 1e-12:
                break
            bps = nxt
        roe = e / bps
        a1, a2 = yy or (y1, y2)
        pe = path_value(g1 if with_g1 else 0.0, N_STAGE if with_g1 else 0, g, roe, r, NUM_YEAR, a1, a2,
                        r_s if rs is None else rs, m_ratio=mr)
        return bps, roe, pe, min(1.0, grow / roe)

    def window(b: float) -> float:
        """2H26 window distributable profit per share (③ 时点对齐), discounted tau/2."""
        return max(inp["ni_h2_cons"] - 0.5 * c_inc, 0.0) * (1 - b) / sh * (1 + r) ** -(tau / 2)

    bps, roe, pe, bb_ = {}, {}, {}, {}
    # Per-tier steady (retention「三档各取各的稳态」2026-10-19): L = the ordered value (axis 18%);
    # M = normal margin 20% x pre-AI turnover 1.05 = 21%; H = normal margin 20% x own mean turnover
    # 1.33 = 26.6% (A26).
    rs_tier = {"L": r_s, "M": inp["ss_return_m"], "H": inp["ss_return_h"]}
    for t in TIERS:
        bps[t], roe[t], pe[t], bb_[t] = tier(eop[t], stage[t], mr=mratio(t), rs=rs_tier[t])
    k = {"L": inp["k_l"], "M": inp["k_m"], "H": inp["k_h"]}
    pre = {t: eop[t] * pe[t] * (1 + r) ** -tau for t in TIERS}  # operating value, aligned to today
    win = {t: window(bb_[t]) for t in TIERS}
    L, M, H = (pre[t] * (1 - k[t]) + win[t] + cps for t in TIERS)
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
    # Count (A13, 2026-10-19): UBS single-house path — 2028 NPO = 10% of FY28 revenue; 2030 NPO = 30% of
    # total revenue with NPO on top of the pluggable main business (FY28 pluggable x (1+g2)^2: incremental,
    # scale-up takes copper's share); 2029 geometric interpolation (插值年); after 2030 g_npo.
    t_opt = int(inp["t_opt"])
    y1n, y2n = int(inp["y1_npo"]), int(inp["y2_npo"])
    rev28_npo = inp["ubs_rev28"] * inp["npo_share_28"]
    plug28 = inp["ubs_rev28"] * (1 - inp["npo_share_28"])
    plug30 = plug28 * (1 + g2) ** (NPO_LAST_NAMED - t_opt)

    def npo_path(share30: float = inp["npo_share_30"], after: float = inp["g_npo"], end: int = 2100) -> dict[int, float]:
        rev30 = plug30 * share30 / (1 - share30)
        path = {t_opt: rev28_npo, NPO_INTERP_YEAR: (rev28_npo * rev30) ** 0.5, NPO_LAST_NAMED: rev30}
        for yr in range(NPO_LAST_NAMED + 1, end + 1):
            path[yr] = path[yr - 1] * (1 + after)
        return path

    npo_ni = rev28_npo * nm_opt
    eps_npo = npo_ni / sh
    roe_book_h = inp["npo_roe"]  # option leg's forward return: the old H-tier book ROE (ruling 2026-10-15)

    def npo_value(nm_norm: float, path: dict[int, float] | None = None, g_term: float | None = None,
                  a1: int = y1n, a2: int = y2n) -> float:
        """NPO stream per share at the start of t_opt: margin (nm_opt) and return (npo_roe) held to a1,
        linear to nm_norm / the steady return by a2, normal after; payout 1 - g_t/ROE_t (negative = the
        capital the ramp needs); Gordon at g_term once past a2 and the last named jump."""
        p = path or npo_path()
        gt = inp["g_npo"] if g_term is None else g_term
        # The NPO leg sits on the packaging link: its steady is that link's axis floor (A13), not the
        # pluggable-module 18% of the main leg.
        ss = min(roe_book_h, inp["ss_return_npo"])
        pv, yr = 0.0, t_opt
        while True:
            t = yr - t_opt + 1
            e = p[yr] * lin_path(yr, nm_opt, nm_norm, a1, a2) / sh
            if yr >= a2 and yr > NPO_LAST_NAMED:
                return pv + e * payout(gt, ss) / ((r - gt) * (1 + r) ** (t - 1))
            g_t = p[yr + 1] / p[yr] - 1
            pv += e * payout(g_t, lin_path(yr, roe_book_h, ss, a1, a2)) / (1 + r) ** t
            yr += 1

    disc = (1 + r) ** (inp["t_opt"] - NUM_YEAR + tau)
    v_opt_t = npo_value(inp["npo_nm_norm"])
    pe_npo = v_opt_t / eps_npo
    v_opt = v_opt_t / disc
    plus_v = tuple(x + p * v_opt for x, p in zip((L, M, H), P_TIERS))

    # ---- A2e-2c flat ladder + decomposition ----
    flat_errs, flat_op = flat_multiple_ladder((eop["L"], eop["M"], eop["H"]), pe["M"] * (1 - k["M"]))
    errors += flat_errs
    flat = tuple(x * (1 + r) ** -tau + win[t] + cps for x, t in zip(flat_op, TIERS))
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
          f" − 9 月回购 {bb:.0f} − 锚 0 − 增长期资金缺口 0 = {c_tot:.0f} × 归母比例 {pr:.4f} = C_ex {c_ex:.0f} 百万"
          f"（每股 {cps:.2f}，占归母权益 {eq0:.0f} 的 {c_ex / eq0:.1%}，λ 1）；"
          f"税后收益 {c_inc:.0f} 百万 = 每股 {c_inc / sh:.4f}，三档分子同扣")
    print(f"三段回报: Y1 {y1} → Y2 {y2}（_AXIS.pluggable-module），稳态 {r_s:.0%}（按序取 = 轴；自身周期 {inp['own_cycle']:.1%} 结构变化后不可用、只对照，"
          f"≤ 前瞻）= L 档；M 档 {inp['ss_return_m']:.1%}、H 档 {inp['ss_return_h']:.1%}（去周期前瞻）；τ {tau:g}；k 全为 0")
    for t in TIERS:
        print(f"{t}: EPS {eps[t]:.4f} -> 经营 EPS {eop[t]:.4f} 经营 BPS_open {bps[t]:.2f} RONIC {roe[t]:.3f} PE(三段) {pe[t]:.2f}"
              f" -> V_op x 1.1^-τ {pre[t]:.2f} + 窗口 {win[t]:.2f}（b {bb_[t]:.3f}）+ C_ex {cps:.2f} = {pre[t] + win[t] + cps:.2f}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"branch: payout_op {inp['payout_op']:.1%} (分红 + 现金积累, FY2018–25); 实付派息 {inp['payout_obs']:.0%}; "
          f"约束 2 上限 (1-d) x RONIC: " + " ".join(f"{t} {ret_obs * roe[t]:.1%}" for t in TIERS) + f" vs g2 {g2:.0%}")
    print(f"NPO option: FY28 net margin UBS {nm_ubs28:.4f} / Citi {inp['citi_nm28']:.4f} -> {nm_opt:.4f}"
          f" (FY25 realised {inp['nm_fy25']:.4f}, lower-bound disclosure only)")
    pth = npo_path()
    print("NPO path (亿 CNY; 2029 = geometric interpolation): "
          + " ".join(f"{yr} {pth[yr] / 100:.1f}" for yr in range(t_opt, NPO_LAST_NAMED + 3))
          + f" | 2030 NPO / total {pth[NPO_LAST_NAMED] / (pth[NPO_LAST_NAMED] + plug30):.1%}"
          f" = ${pth[NPO_LAST_NAMED] * 1e6 / inp['usdcny'] / 1e9:.2f}B")
    print(f"main margin path: start L {nm0['L']:.2%} / M,H {nm0['M']:.2%} held to {y1} -> {inp['nm_norm_main']:.0%} by {y2}"
          f" (ratio L {mratio('L'):.3f} / M,H {mratio('M'):.3f})")
    print(f"NPO option: FY28 NI {npo_ni:.0f} 百万 -> EPS {eps_npo:.4f}; margin {nm_opt:.2%} held to {y1n} -> {inp['npo_nm_norm']:.0%} by {y2n},"
          f" return {roe_book_h:.1%} -> {min(roe_book_h, inp['ss_return_npo']):.0%} (after {NPO_LAST_NAMED} g {inp['g_npo']:.0%}) -> value in {t_opt} {v_opt_t:.2f}"
          f" (implied x{pe_npo:.2f} FY28 NPO EPS) / 1.1^{inp['t_opt'] - NUM_YEAR + tau:g} = V_opt {v_opt:.2f}"
          f"; p {P_TIERS} -> +V {plus_v[0]:.2f}/{plus_v[1]:.2f}/{plus_v[2]:.2f}"
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

    def anchor(t: str, g: float = g2, g1_: float | None = None, rs: float | None = None,
               norm: float | None = None) -> float:
        e_ = eop[t]
        mr_ = mratio(t, norm)
        if rs is None:
            rs = rs_tier[t]
        _, r_, pe_, b_ = tier(e_, stage[t], g, rs=rs, mr=mr_)
        if stage[t] and g1_ is not None:
            pe_ = path_value(g1_, N_STAGE, g, r_, r, NUM_YEAR, y1, y2, r_s if rs is None else rs, m_ratio=mr_)
        return e_ * pe_ * (1 - k[t]) * (1 + r) ** -tau + window(b_) + cps

    for nrm in (0.12, 0.15, 0.28):
        print(f"  sens normal net margin {nrm:.0%} (main and NPO together): "
              + "/".join(f"{anchor(t, norm=nrm):.2f}" for t in TIERS)
              + f" | V_opt {npo_value(nrm) / disc:.2f}")
    print("  sens no margin fade (main at its starting margin; NPO held at FY28 consensus): "
          + "/".join(f"{anchor(t, norm=nm0[t]):.2f}" for t in TIERS)
          + f" | V_opt {npo_value(nm_opt) / disc:.2f}")
    for g in (g2 - 0.01, g2 + 0.01, MACRO_G):
        print(f"  sens g2={g:.2%}: " + "/".join(f"{anchor(t, g):.2f}" for t in TIERS))
    for lab, gt in (("derived 4-house mean", (84.96 / 60.69 + 1670 / 970 + 79 / 59.89 + 82.4 / 59.67) / 4),):
        g1_alt = gt * (1 - inp["npo_share_28"]) - 1
        print(f"  sens g1 from {lab} ({g1_alt:+.1%}): " + "/".join(f"{anchor(t, g1_=g1_alt):.2f}" for t in TIERS))
    for cut in (0.20, 0.40):
        e_ = inp["rev_fy26_cons"] * (1 - cut) * inp["nm_fy25"] / sh - c_inc / sh
        _, _, pe_c, b_c = tier(e_, False, mr=mratio("L"))
        print(f"  sens rev_cut_l={cut:.0%}: L {e_ * pe_c * (1 + r) ** -tau + window(b_c) + cps:.2f}")
    print("  sens steady return = forward (no return fade; margin still fades): "
          + "/".join(f"{anchor(t, rs=1.0):.2f}" for t in TIERS))
    print("  sens Y1/Y2 = ai-capex default 2030/2035 (return and margin move together): " + "/".join(
        f"{eop[t] * tier(eop[t], stage[t], yy=(2030, 2035), mr=mratio(t), rs=rs_tier[t])[2] * (1 + r) ** -tau + win[t] + cps:.2f}"
        for t in TIERS))
    # NPO option sensitivities (A13)
    v_g6 = npo_value(inp["npo_nm_norm"], path=npo_path(after=0.06), g_term=0.06) / disc
    v_g0 = npo_value(inp["npo_nm_norm"], path=npo_path(after=0.0), g_term=0.0) / disc
    v_fix = npo_value(inp["npo_nm_norm"],
                      path={yr: rev28_npo * (1 + inp["g_npo"]) ** (yr - t_opt) for yr in range(t_opt, 2101)}) / disc
    v_can = v_opt - npo_value(inp["npo_nm_norm"], a1=y1, a2=y2) / disc
    v_can6 = (npo_value(inp["npo_nm_norm"], path=npo_path(after=0.06), g_term=0.06)
              - npo_value(inp["npo_nm_norm"], path=npo_path(after=0.06), g_term=0.06, a1=y1, a2=y2)) / disc
    print(f"  NPO sens: after-2030 growth 6% {v_g6:.2f} · 0% {v_g0:.2f} · 2028 count held (no 2030 step) {v_fix:.2f}"
          f" · if NPO cannibalises own pluggable (valued on the main {y1}/{y2} path), net add {v_can:.2f}"
          f" (after-2030 6%: {v_can6:.2f})")
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
