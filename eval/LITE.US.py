#!/usr/bin/env python3
"""LITE.US (Lumentum) valuation eval — recompute anchors from frameworks/LITE.US.md.

frameworks/LITE.US.md is the source of truth; this script re-derives
L/M/H / A/B from the §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」): which zone a quote falls in is
derived live by the daily digest and the app, so nothing here reads a price.

formula_id: lite_cycle_normalized_nongaap_eps_pe_gordon_v8

Main ruler (valuation-rules.md「增长的表达顺序」, 裁决顺序 ②): the numerator year
is FY28 — the furthest year with a >=2-house consensus — as one axis, three
points from the same record: L = FY28 digestion year (FY27 consensus mean x
SBC haircut x k_l), M = FY28 consensus mean x haircut, H = FY28 consensus HIGH
x haircut.  FY29 has no consensus anywhere, so there is no transition stage:
every tier prices off `perpetual_pe` (no `two_stage_pe`, so
`check_transition_years` does not apply).  Perpetual g2 is the peer
the peer-ruler axis value `_AXIS.inp-laser` (frameworks/axes/inp-laser.md; the
whole company rides the laser / device leg, A10 / A16) and must equal the axis
row `g2_inp_laser`; `cyclical` primary
means g is FLAT across tiers, so the only tier-to-tier multiple difference is
the mechanical ROE effect.  ROE is E_{n+1}/B_n (valuation-rules 2026-09-21): the
FY28 numerator over the FY28 OPENING book = FY26 reported equity rolled over
the not-yet-booked FY27 EPS at the growth-required retention b1 = g2/ROE, i.e.
BPS_open = BPS0 / (1 - g2 * N / EPS_x) with N = FY27 consensus EPS after the
SBC haircut.  No g1 window, so every tier rolls at g2.

Candidate band (A2e-7h, A19): the company's FY28 EPS target ($40, company
guidance, above the consensus high) replaces only the H numerator -> H'.
Never in the base band.

Option (A22; valuation-rules「未建模期权」2026-10-05 tiering): Greensboro, the
fifth InP fab, is the only named quantity outside FY28 consensus.  No
sell-side house sizes it, so the tiers are: L = 0 (digestion world, fab not
needed); M = one fab at today's measured output per InP fab (Q4 FY26
Components annualised / inp_fabs), valued at t_opt; H = full capacity as the
company states it (gso_rev_full, CEO answering the Greensboro capacity
question), valued at t_opt_h.  The margin is time-dependent (`_AXIS.inp-laser`
§1b, user 2026-10-05): the shortage-era margin (ebit_margin_inp_peer) holds
only through t_shortage_end (2027); both tiers realise after it, so both take
the axis normal (non-shortage) margin ebit_margin_inp_normal (LITE's own
FY19-FY22 non-GAAP operating income / revenue, recomputed here from the raw
sums), converted to net with this ticker's FY28 consensus net margin /
OFC-model operating margin om_lite_model.  The leg's perpetual growth is the
axis non-bottleneck value g2_inp_laser_normal (4%), not the shortage-era 6%.
Each tier on this ticker's own ruler (perpetual_pe at g2_gso, ROE_tier, r),
discounted to FY28 at r, less the unspent
capital that tier's quantity requires: the retrofit floor (budget gso_k_budget
- spent gso_k_spent, even over gso_k_n years from gso_k_y0, years after FY28
discounted; the $38.0M purchase is sunk), topped up to Q_k x today's capital
intensity (ppe_net_fy26 / (rev_q4_fy26 x 4), FY26 10-K net PP&E over the Q4
FY26 revenue run-rate) when that is larger, the top-up spent in the last spend
year (FY29).  Only H binds (full capacity $5B needs ~$1.44B, not $600M); the
$600M-only reading is printed as the disclosed alternative.  V_opt = V_H; p_k = V_k / V_H (same structure as INTC.US).  zone+V only.
Supply security (Greensboro not constrained by Chinese capacity) is tracked,
not priced (A23): no input here carries it.

Guardrail (valuation-rules 裁决顺序 ③): the M multiple must sit inside the
ticker's own realised current-FY forward-PE band [pe_own_min, pe_own_max];
L / H / H' are printed against the band but not asserted (the band is on the
current-FY consensus, the tiers are on FY28 scenarios — not the same basis).

r is set by the leg's basket (valuation-rules.md「§r 篮子」): the framework
names `篮 N` on the r_perp row (A20) and r must equal that basket's value
(gordon.BASKET_R); g2 must sit under g_cap(r).

Run:  python3 frameworks/eval/LITE.US.py
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
    optical_narrow_rev,
)
from eval.lib.frameworks import load_framework  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    check_g_cap,
    check_r,
    g_cap,
    implied_g,
    perpetual_pe,
)
from eval.lib.inputs import parse_baskets  # noqa: E402
from eval.lib.tiers import decompose, flat_multiple_ladder  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "LITE.US.md"
AXIS_LASER = Path(__file__).resolve().parents[2] / "frameworks" / "axes" / "inp-laser.md"
AXIS_PLUG = Path(__file__).resolve().parents[2] / "frameworks" / "axes" / "pluggable-module.md"
# (this ticker's Inputs key, axis Inputs key, axis file): rows taken from peer-ruler axes.
AXIS_ROWS = (
    ("g2", "g2_inp_laser", AXIS_LASER),
    ("opm_inp_shortage", "ebit_margin_inp_peer", AXIS_LASER),
    ("opm_inp_normal", "ebit_margin_inp_normal", AXIS_LASER),
    ("g2_gso", "g2_inp_laser_normal", AXIS_LASER),
    ("t_shortage_end", "t_shortage_end", AXIS_LASER),
    ("g2_plug_ref", "g2_pluggable", AXIS_PLUG),
)
FORMULA_ID = "lite_cycle_normalized_nongaap_eps_pe_gordon_v8"
TOL = 0.05  # outputs are rounded to 2 decimals
MIN_R_MINUS_G = 0.02  # valuation-rules: below this the multiple sits at the pole
SBC_HAIRCUT_MAX = 0.5
# _AXIS.rates segment: a US listing reads the USD r_f (valuation-rules「按上市货币取段」).
LISTING_CCY = "USD"
NUM_YEAR = 2028  # numerator fiscal year (FY28)
P_TOL = 0.0005  # p_k stated to 4 decimals (A22) — table 3 only, never an input

TIERS = ("L", "M", "H")


def parse_inputs(md: str) -> dict[str, float]:
    """Parse §3 Inputs table: | field | value | meaning | as-of |."""
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
        if len(cells) < 2:
            continue
        key, raw = cells[0], cells[1]
        if key in ("字段名", "--------", "---") or raw == "取值":
            continue
        if raw in ("待补", "", "—"):
            continue
        try:
            out[key] = float(raw.replace(",", ""))
        except ValueError:
            continue
    return out


def zone_of(price: float, L: float, M: float, H: float) -> str:
    A = (L + M) / 2
    B = (M + H) / 2
    if price < L:
        return "deep_discount"
    if price < A:
        return "conservative"
    if price < B:
        return "neutral"
    if price <= H:
        return "optimistic"
    return "stretched"


def first_float(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def check_inputs(inp: dict[str, float], baskets: dict[str, int]) -> list[str]:
    """Ticker-specific sanity gates — see §3 校验 and A1/A2/A3/A5/A19/A20."""
    errors: list[str] = []
    if not (0.0 <= inp["sbc_haircut"] < SBC_HAIRCUT_MAX):
        errors.append(f"sbc_haircut={inp['sbc_haircut']} outside [0, {SBC_HAIRCUT_MAX})")
    if not (0.0 < inp["k_l"] < 1.0):
        errors.append(f"k_l={inp['k_l']} must be a digestion factor in (0, 1) (A3)")
    if not (inp["eps_fy28_l"] < inp["eps_fy28_m"] < inp["eps_fy28_h"]):
        errors.append("FY28 consensus range must be ordered low < mean < high (A2e-2a: one record, two ends)")
    if inp["eps_fy28_m"] <= inp["eps_fy27"]:
        errors.append("FY28 consensus mean below FY27: FY28 is not the growth year the axis assumes")
    if inp["eps_fy28_guide"] <= inp["eps_fy28_h"]:
        errors.append("eps_fy28_guide inside the consensus range — it is not a missing input, drop the candidate band (A19)")
    # r from the named basket (A15/A20); g2 under g_cap(r) and away from the pole.
    if "r_perp" not in baskets:
        errors.append("r_perp: Inputs source cell names no 篮 N (A20)")
    errors += check_r(inp["r_perp"], "r_perp", baskets.get("r_perp"))
    errors += check_g_cap(inp["g2"], inp["r_perp"], "g2")
    gap = inp["r_perp"] - inp["g2"]
    if gap <= 0:
        errors.append("perpetuity diverges: g2 >= r")
    elif gap < MIN_R_MINUS_G:
        errors.append(f"r - g2 = {gap:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    if inp["t_opt"] <= NUM_YEAR:
        errors.append("option year must lie after the FY28 numerator year (A22)")
    if inp["inp_fabs"] < 1 or inp["comp_q4_fy26"] <= 0 or inp["rev_fy28_cons"] <= 0:
        errors.append("option unit inputs must be positive (A22)")
    if not (0 <= inp["gso_k_spent"] <= inp["gso_k_budget"]) or inp["gso_k_n"] < 1:
        errors.append("Greensboro capital: need 0 <= spent <= budget and >= 1 spend year (A22)")
    if inp["t_opt_h"] < inp["t_opt"]:
        errors.append("full-capacity year t_opt_h must not precede the snapshot year t_opt (A22)")
    for k in ("opm_inp_shortage", "opm_inp_normal", "om_lite_model"):
        if not (0.0 < inp[k] < 1.0):
            errors.append(f"{k}={inp[k]} must lie in (0, 1) (A22)")
    if inp["opm_inp_normal"] >= inp["opm_inp_shortage"]:
        errors.append("normal margin must sit below the shortage-era margin (axis §1b)")
    # The normal margin is recomputed from LITE's own pre-shortage years (A22).
    if abs(inp["opi_ng_fy19_22"] / inp["rev_fy19_22"] - inp["opm_inp_normal"]) > 5e-5:
        errors.append(
            f"opm_inp_normal {inp['opm_inp_normal']} != FY19-22 non-GAAP OI / revenue "
            f"{inp['opi_ng_fy19_22'] / inp['rev_fy19_22']:.4f} (A22)"
        )
    if inp["g2_gso"] > inp["g2"]:
        errors.append("option-leg g2 (non-bottleneck) must not exceed the shortage-era axis g2 (A22)")
    if min(inp["t_opt"], inp["t_opt_h"]) <= inp["t_shortage_end"]:
        errors.append("an option tier realises inside the shortage era — it must take the shortage margin (axis §1b)")
    if inp["gso_rev_full"] <= inp["comp_q4_fy26"] * 4.0 / max(inp["inp_fabs"], 1):
        errors.append("stated full capacity below one average fab — H would sit under M (A22)")
    if inp["ppe_net_fy26"] <= 0 or inp["rev_q4_fy26"] <= 0:
        errors.append("capital intensity inputs must be positive (A22)")
    if inp["gso_k_y0"] + inp["gso_k_n"] - 1 > inp["t_opt"]:
        errors.append("Greensboro capital spend runs past the realisation year t_opt (A22)")
    if inp["equity"] <= 0 or inp["shares_dil"] <= 0:
        errors.append("equity and shares_dil must be positive")
    # A2e-7a: probabilities never enter the base deck.
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")
    return errors


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    required = [
        "eps_fy27",
        "eps_fy28_m",
        "eps_fy28_h",
        "eps_fy28_l",
        "eps_fy28_guide",
        "sbc_haircut",
        "k_l",
        "r_perp",
        "g2",
        "shares_dil",
        "equity",
        "payout_3y",
        "pe_own_min",
        "pe_own_max",
        "rev_fy27_cons",
        "oe_l",
        "oe_m",
        "oe_h",
        "laser_usd_per_oe",
        "lite_laser_share",
        "capex_l",
        "capex_m",
        "capex_h",
        "comp_q4_fy26",
        "inp_fabs",
        "rev_fy28_cons",
        "t_opt",
        "gso_k_budget",
        "gso_k_spent",
        "gso_k_y0",
        "gso_k_n",
        "ppe_net_fy26",
        "rev_q4_fy26",
        "gso_rev_full",
        "t_opt_h",
        "om_lite_model",
        "opm_inp_shortage",
        "opm_inp_normal",
        "opi_ng_fy19_22",
        "rev_fy19_22",
        "g2_gso",
        "t_shortage_end",
        "g2_plug_ref",
        "sys_share",
    ]
    missing = [k for k in required if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1

    baskets = parse_baskets(md)
    errors = check_inputs(inp, baskets)
    # Peer-ruler axes (contracts.md「同业尺轴」): rows sourced `_AXIS.<name>` must equal the axis file.
    for key, axis_key, path in AXIS_ROWS:
        if not path.is_file():
            errors.append(f"{path.name} missing — {key} unchecked")
            continue
        ax = parse_inputs(path.read_text(encoding="utf-8"))
        if axis_key not in ax or abs(ax[axis_key] - inp[key]) > 1e-9:
            errors.append(f"{key} {inp[key]:g} != _AXIS.{path.stem} {axis_key} {ax.get(axis_key)} — the leg ruler drifted")
    if not (0.0 < inp["sys_share"] < 0.5):
        errors.append(f"sys_share={inp['sys_share']} must be the minority Systems revenue share (A10)")
    errors.extend(check_optical_oe_mount((inp["oe_l"], inp["oe_m"], inp["oe_h"])))
    errors.extend(check_capex_mount((inp["capex_l"], inp["capex_m"], inp["capex_h"])))
    opt_rev = {
        tier: optical_narrow_rev(
            inp[f"oe_{tier.lower()}"],
            inp["laser_usd_per_oe"],
            inp["lite_laser_share"],
        )
        for tier in TIERS
    }
    errors.extend(check_optical_narrow_attach(opt_rev))
    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    r = inp["r_perp"]
    g2 = inp["g2"]
    shares = inp["shares_dil"] * 1e6
    haircut = 1.0 - inp["sbc_haircut"]

    bps0 = inp["equity"] / shares  # FY26 reported book per share
    unbooked = inp["eps_fy27"] * haircut  # FY27 EPS not yet in the book (A21)

    def tier(eps: float, g: float = g2) -> tuple[float, float]:
        """(ROE, Gordon multiple) for one FY28 numerator — no transition stage.

        ROE = EPS_FY28 / BPS_open(FY28); the book rolls over the unbooked FY27
        EPS at b1 = g/ROE, closed form BPS_open = BPS0 / (1 - g*N/EPS) (A21).
        """
        if g * unbooked / eps >= 1.0:
            raise ValueError(f"book roll diverges: g*N/EPS = {g * unbooked / eps:.3f}")
        roe = eps / (bps0 / (1.0 - g * unbooked / eps))
        return roe, perpetual_pe(g, roe, r)

    # ---- Step 1: one FY28 numerator axis, three points (裁决顺序 ②, A2e-2a) ----
    eps = {
        "L": inp["eps_fy27"] * haircut * inp["k_l"],  # FY28 digestion year (A3)
        "M": inp["eps_fy28_m"] * haircut,  # FY28 consensus mean
        "H": inp["eps_fy28_h"] * haircut,  # FY28 consensus high, same record
    }
    flat_errs, _ = flat_multiple_ladder((eps["L"], eps["M"], eps["H"]), 1.0)
    errors += flat_errs

    # ---- Step 2-3: tier ROE on the FY28 opening book, then generated multiples ----
    roe, pe = {}, {}
    for t in TIERS:
        roe[t], pe[t] = tier(eps[t])
    b1 = {t: g2 / roe[t] for t in TIERS}
    for t in TIERS:
        if not (0.0 < b1[t] < 1.0):
            errors.append(f"{t}: b1 = g2/ROE = {b1[t]:.3f} outside (0,1) — stage payout would be priced negative")

    # Guardrail (valuation-rules 裁决顺序 ③ / A17): the generated M multiple must
    # sit inside the ticker's own realised current-FY forward-PE band. L / H / H'
    # are reported against the band only — they are FY28 scenarios, the band is
    # current-FY consensus, so a tier straddling the floor is disclosure, not a stop.
    def in_band(mult: float) -> bool:
        return inp["pe_own_min"] <= mult <= inp["pe_own_max"]

    if not in_band(pe["M"]):
        errors.append(
            f"M multiple {pe['M']:.2f}x outside own realised band "
            f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}] — ③ 出带, stop, back to dialogue"
        )

    # ---- Step 4-5: anchors, cut points ----
    L, M, H = (eps[t] * pe[t] for t in TIERS)
    A = (L + M) / 2
    B = (M + H) / 2
    if not (L < M < H):
        errors.append(f"L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}")

    # ---- Step 6: candidate band — company FY28 target replaces the H numerator only (A19) ----
    eps_c = inp["eps_fy28_guide"] * haircut
    roe_c, pe_c = tier(eps_c)
    cand = (L, M, eps_c * pe_c)
    if not (cand[0] < cand[1] < cand[2]):
        errors.append(f"candidate band not ordered: {cand}")

    # ---- Step 6b: option (A22) — Greensboro, tiered (2026-10-05 rule) ----
    k_remain = inp["gso_k_budget"] - inp["gso_k_spent"]
    k_years = [int(inp["gso_k_y0"]) + i for i in range(int(inp["gso_k_n"]))]
    k_ps = sum(
        k_remain / len(k_years) / (1.0 + r) ** max(0, y - NUM_YEAR) for y in k_years
    ) / (inp["shares_dil"] * 1e6)
    # Capital the tier's quantity requires: Q_k x today's intensity, floored at the
    # retrofit budget; the top-up lands in the last spend year (A22, 2026-10-05).
    k_int = inp["ppe_net_fy26"] / (inp["rev_q4_fy26"] * 4.0)
    k_top_df = (1.0 + r) ** max(0, k_years[-1] - NUM_YEAR)
    nm_cons = eps["M"] / haircut * inp["shares_dil"] / inp["rev_fy28_cons"]  # FY28 consensus net margin
    op_to_net = nm_cons / inp["om_lite_model"]  # this ticker's operating -> net ratio

    def leg_nm(year: float) -> float:
        """Axis §1b: shortage-era margin through t_shortage_end, normal margin after."""
        opm = inp["opm_inp_shortage"] if year <= inp["t_shortage_end"] else inp["opm_inp_normal"]
        return opm * op_to_net

    g_opt = inp["g2_gso"]  # axis non-bottleneck g2 (A22)
    pe_opt = {t: perpetual_pe(g_opt, roe[t], r) for t in TIERS}
    fab_rev = inp["comp_q4_fy26"] * 4.0 / inp["inp_fabs"]  # USD / yr, measured per fab
    opt_q = {
        "M": (fab_rev, leg_nm(inp["t_opt"]), inp["t_opt"]),
        "H": (inp["gso_rev_full"], leg_nm(inp["t_opt_h"]), inp["t_opt_h"]),
    }
    v_k, v_gross_k, inc_k, k_k = {"L": 0.0}, {"L": 0.0}, {"L": 0.0}, {"L": 0.0}
    for t, (rev_t, nm_t, yr) in opt_q.items():
        inc_k[t] = rev_t * nm_t * haircut / shares
        v_gross_k[t] = inc_k[t] * pe_opt[t] / (1.0 + r) ** (yr - NUM_YEAR)
        k_k[t] = k_ps + max(0.0, rev_t * k_int - k_remain) / k_top_df / shares
        v_k[t] = v_gross_k[t] - k_k[t]
    v_opt = v_k["H"]
    if not (0.0 <= v_k["M"] <= v_opt):
        errors.append(f"option tiers not ordered: V_M {v_k['M']:.2f} vs V_H {v_opt:.2f}")
    p_k = {t: v_k[t] / v_opt for t in TIERS}
    opt_band = tuple(a + p_k[t] * v_opt for a, t in zip((L, M, H), TIERS))
    a_opt = (opt_band[0] + opt_band[1]) / 2
    b_opt = (opt_band[1] + opt_band[2]) / 2
    # Disclosed alternative: H deducts only the $600M retrofit floor (pre-2026-10-05 reading).
    v_h_floor = v_gross_k["H"] - k_ps

    # ---- A2e-2c flat ladder + A2e-5 decomposition ----
    _, flat = flat_multiple_ladder((eps["L"], eps["M"], eps["H"]), pe["M"])
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")
    dec = decompose((L, M, H), (pe["L"], pe["M"], pe["H"]))

    # ---- Step 7: reconcile against the stated Outputs ----
    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    stated = {
        "L": first_float(r"L = \*\*([0-9.]+)\*\*", out_sec),
        "M": first_float(r"M = \*\*([0-9.]+)\*\*", out_sec),
        "H": first_float(r"H = \*\*([0-9.]+)\*\*", out_sec),
        "A": first_float(r"A = \*\*([0-9.]+)\*\*", out_sec),
        "B": first_float(r"B = \*\*([0-9.]+)\*\*", out_sec),
    }
    recomputed = {"L": L, "M": M, "H": H, "A": A, "B": B}
    for k, v in recomputed.items():
        s = stated.get(k)
        if s is None:
            errors.append(f"stated {k} not found in Outputs")
        elif abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")
    fw = load_framework(FRAMEWORK)
    if fw.v_opt is None or abs(fw.v_opt - v_opt) > TOL:
        errors.append(f"V_opt: stated {fw.v_opt} vs recomputed {v_opt:.4f} (A22)")
    if fw.p_tiers is None or any(abs(a - p_k[t]) > P_TOL for a, t in zip(fw.p_tiers, TIERS)):
        errors.append(f"p_L/p_M/p_H stated {fw.p_tiers} vs eval " + "/".join(f"{p_k[t]:.4f}" for t in TIERS))
    for lab, val in (("A'", a_opt), ("B'", b_opt)):
        said = first_float(re.escape(lab) + r" = \*\*([0-9.]+)\*\*", out_sec)
        if said is None or abs(said - val) > TOL:
            errors.append(f"zone+V {lab}: stated {said} vs recomputed {val:.4f}")
    # Candidate band line: the digest reads it through frameworks.py; compare ±TOL.
    stated_cand = fw.candidate
    if stated_cand is None:
        errors.append("候选带 line missing from Outputs (A19)")
    else:
        for lab, said, got in zip(("L′", "M′", "H′"), stated_cand, cand):
            if abs(said - got) > TOL:
                errors.append(f"候选带 {lab}: stated {said} vs recomputed {got:.4f}")

    # ---- Report ----
    mcap = lambda v: v * inp["shares_dil"] / 1000.0  # noqa: E731 — 十亿 USD
    eps27_adj = inp["eps_fy27"] * haircut
    print(f"formula_id={FORMULA_ID}")
    print(
        f"FY28 axis: cons {inp['eps_fy28_l']}/{inp['eps_fy28_m']}/{inp['eps_fy28_h']}, guide {inp['eps_fy28_guide']};"
        f" sbc_haircut={inp['sbc_haircut']:.0%} k_l={inp['k_l']} (on FY27 {inp['eps_fy27']})"
        f" -> EPS L/M/H = {eps['L']:.4f}/{eps['M']:.4f}/{eps['H']:.4f}"
    )
    print(f"g2={g2:.4f} (flat, no transition) r={r:g} (篮 {baskets['r_perp']}, cap {g_cap(r):.3f})")
    print(
        f"ROE basis (A21): EPS_FY28 / BPS_open(FY28); BPS0 {bps0:.2f} (FY26 book) rolled over unbooked FY27 {unbooked:.3f}"
        f" at b1 = g2/ROE -> BPS_open L/M/H = "
        + "/".join(f"{eps[t] / roe[t]:.2f}" for t in TIERS)
    )
    print(
        f"tier ROE L/M/H = {roe['L']:.3f}/{roe['M']:.3f}/{roe['H']:.3f}"
        f" (on current book: {'/'.join(f'{eps[t] * shares / inp['equity']:.3f}' for t in TIERS)});"
        f" b1 = {b1['L']:.3f}/{b1['M']:.3f}/{b1['H']:.3f}"
    )
    ret_actual = 1.0 - inp["payout_3y"]
    print(
        "模型视同派出、实际留存的现金 / 股 (B bucket, disclosure only) L/M/H = "
        + "/".join(f"{(ret_actual - b1[t]) * unbooked:.2f}" for t in TIERS)
        + f"  [(1 - payout {inp['payout_3y']:.2f} - b1) x unbooked {unbooked:.2f}]"
    )
    for t in TIERS:
        print(f"{t}: eps {eps[t]:.4f} x {pe[t]:.2f}x = {eps[t] * pe[t]:.2f}  [perpetual_pe, payout {1 - b1[t]:.3f}]")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"candidate (A19, guide {inp['eps_fy28_guide']:g} -> H' only): "
        f"L'={cand[0]:.2f} M'={cand[1]:.2f} H'={cand[2]:.2f}  [eps {eps_c:.3f} x {pe_c:.2f}x, ROE {roe_c:.3f}]"
    )
    flags = {t: "" if in_band(pe[t]) else " OUT" for t in TIERS}
    print(
        f"guardrail (③ asserts M only): multiples L {pe['L']:.2f}{flags['L']} / M {pe['M']:.2f}{flags['M']}"
        f" / H {pe['H']:.2f}{flags['H']}x (H' {pe_c:.2f}{'' if in_band(pe_c) else ' OUT'}x) vs own band "
        f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]; on FY27 basis M {M / eps27_adj:.1f}x H {H / eps27_adj:.1f}x"
    )
    for t in TIERS:
        g_lo, ok_lo = implied_g(inp["pe_own_min"], roe[t], r)
        g_hi, ok_hi = implied_g(inp["pe_own_max"], roe[t], r)
        print(
            f"band-edge implied g @ ROE_{t} {roe[t]:.3f}: [{g_lo:+.2%}{'' if ok_lo else ' (ill-conditioned)'}, "
            f"{g_hi:+.2%}{'' if ok_hi else ' (ill-conditioned)'}] — g2 {g2:.2%} inside: {g_lo <= g2 <= g_hi}"
        )
    print(f"flat-multiple ladder @ M {pe['M']:.2f}x: {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}")
    print(
        f"L/M {dec['lm']:.3f} = num {dec['num_lm']:.3f} x pe {dec['pe_lm']:.3f}"
        f" | H/M {dec['hm']:.3f} = num {dec['num_hm']:.3f} x pe {dec['pe_hm']:.3f}"
        f" | width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}"
    )
    print(
        f"option (A22): normal OPM {inp['opm_inp_normal']:.4f} (FY19-22 {inp['opi_ng_fy19_22']:.1f}/{inp['rev_fy19_22']:.1f})"
        f" x op->net {op_to_net:.4f} [{nm_cons:.4f}/{inp['om_lite_model']:g}] = NM {opt_q['H'][1]:.4f};"
        f" g2_gso {g_opt:.2%} -> PE_opt M {pe_opt['M']:.2f} / H {pe_opt['H']:.2f}"
        f" (shortage-era g2 {g2:.0%}: {pe['M']:.2f} / {pe['H']:.2f})"
    )
    print(
        f"  L 0 | M 1 fab ${fab_rev / 1e6:.1f}M x NM {opt_q['M'][1]:.4f} x (1-SBC) = {inc_k['M']:.4f}/sh"
        f" x {pe_opt['M']:.2f} / {1 + r:g}^{int(inp['t_opt']) - NUM_YEAR} = {v_gross_k['M']:.2f}"
        f" | H full ${inp['gso_rev_full'] / 1e9:.1f}B x NM {opt_q['H'][1]:.4f}"
        f" x (1-SBC) = {inc_k['H']:.4f}/sh x {pe_opt['H']:.2f} / {1 + r:g}^{int(inp['t_opt_h']) - NUM_YEAR} = {v_gross_k['H']:.2f}"
    )
    print(
        f"  unspent capital: floor {k_ps:.2f}/sh [(${inp['gso_k_budget'] / 1e6:.0f}M - ${inp['gso_k_spent'] / 1e6:.0f}M) over FY{k_years[0]}-FY{k_years[-1]}, to FY{NUM_YEAR} at r];"
        f" intensity {k_int:.4f} (PP&E ${inp['ppe_net_fy26'] / 1e6:.1f}M / ${inp['rev_q4_fy26'] * 4 / 1e6:.1f}M)"
        f" -> need M ${opt_q['M'][0] * k_int / 1e6:.0f}M / H ${opt_q['H'][0] * k_int / 1e6:.0f}M; K_M/K_H = {k_k['M']:.2f}/{k_k['H']:.2f}/sh\n"
        f" -> V_L/V_M/V_H = {v_k['L']:.2f}/{v_k['M']:.2f}/{v_k['H']:.2f}; V_opt={v_opt:.2f}"
        f" p_k {p_k['L']:.4f}/{p_k['M']:.4f}/{p_k['H']:.4f} -> zone+V {opt_band[0]:.2f}/{opt_band[1]:.2f}/{opt_band[2]:.2f}"
        f" A'={a_opt:.2f} B'={b_opt:.2f}"
    )
    def v_alt(t: str, nm: float, mult: float) -> float:
        rev_t, _, yr = opt_q[t]
        return rev_t * nm * haircut / shares * mult / (1.0 + r) ** (yr - NUM_YEAR) - k_k[t]

    nm_short = inp["opm_inp_shortage"] * op_to_net
    print(
        f"  alt: H capital = $600M floor only -> V_H {v_h_floor:.2f} (p_M {v_k['M'] / v_h_floor:.4f});"
        f" H realised FY29 (undiscounted 2nd yr) -> V_H {inc_k['H'] * pe_opt['H'] / (1 + r) - k_k['H']:.2f}"
    )
    print(
        "  sens (shortage persists past 2027): V_M/V_H at shortage NM "
        f"{nm_short:.4f} + g2 {g2:.0%} = {v_alt('M', nm_short, pe['M']):.2f}/{v_alt('H', nm_short, pe['H']):.2f}"
        f" (H = the pre-rework V_H; old M used the FY28 consensus NM); normal NM + g2 {g2:.0%}"
        f" = {v_alt('M', opt_q['M'][1], pe['M']):.2f}/{v_alt('H', opt_q['H'][1], pe['H']):.2f};"
        f" FY28 consensus NM {nm_cons:.4f} + g2_gso = {v_alt('M', nm_cons, pe_opt['M']):.2f}/{v_alt('H', nm_cons, pe_opt['H']):.2f}"
    )
    for lo_opm, tag in ((0.205, "FY19 trough-of-normal 20.5%"), (0.105, "COHR Networking FY22 GAAP segment 10.5%")):
        nm_lo = lo_opm * op_to_net
        print(f"  sens normal OPM {tag}: V_M/V_H = {v_alt('M', nm_lo, pe_opt['M']):.2f}/{v_alt('H', nm_lo, pe_opt['H']):.2f}")
    fy27_axis = {
        "L": eps["L"] * pe["L"],
        "M": eps27_adj * tier(eps27_adj)[1],
        "H": 25.27 * haircut * tier(25.27 * haircut)[1],
    }
    print(
        f"cross-check, FY27 axis (21.643 x k_l / 21.643 / 25.27, no FY28): "
        f"{fy27_axis['L']:.2f}/{fy27_axis['M']:.2f}/{fy27_axis['H']:.2f}"
    )
    eps_lo = inp["eps_fy28_l"] * haircut
    print(f"FY28 consensus-low coordinate: {eps_lo:.3f} x {tier(eps_lo)[1]:.2f}x = {eps_lo * tier(eps_lo)[1]:.2f} -> {zone_of(eps_lo * tier(eps_lo)[1], L, M, H)}")
    print(f"implied mcap (bn USD) L/M/H = {mcap(L):.1f}/{mcap(M):.1f}/{mcap(H):.1f}")
    # Sensitivities the doc quotes (Outputs 敏感性)
    for g in (g2 - 0.01, g2 + 0.01, 0.0664, 0.04):
        vals = [eps[t] * tier(eps[t], g)[1] for t in TIERS]  # book re-rolls at the perturbed g
        tag = " (above cap, reference only)" if g > g_cap(r) + 1e-9 else ""
        print(f"  sens g2={g:.4f}{tag}: {vals[0]:.2f}/{vals[1]:.2f}/{vals[2]:.2f}")
    # Bias bound of the whole-company mount (A10 / A16): Systems revenue share priced at the
    # pluggable-module leg g2, the rest at the laser leg g2; the book rolls at the EPS-weighted g.
    s_sys, g_p = inp["sys_share"], inp["g2_plug_ref"]
    g_mix = (1 - s_sys) * g2 + s_sys * g_p
    mix = []
    for t in TIERS:
        roe_mix = eps[t] / (bps0 / (1.0 - g_mix * unbooked / eps[t]))
        mix.append(eps[t] * ((1 - s_sys) * perpetual_pe(g2, roe_mix, r) + s_sys * perpetual_pe(g_p, roe_mix, r)))
    print(f"  sens Systems {s_sys:.1%} of EPS at module g2 {g_p:.2%} (bias bound, A16): {mix[0]:.2f}/{mix[1]:.2f}/{mix[2]:.2f}")
    for f in (0.9, 1.1):
        e = eps["M"] * f
        print(f"  sens FY28 consensus x{f:g}: M {e * tier(e)[1]:.2f}")
    for s in (0.06, 0.13):
        e = {t: eps[t] / haircut * (1 - s) for t in TIERS}
        print(f"  sens sbc_haircut={s}: {e['L'] * tier(e['L'])[1]:.2f}/{e['M'] * tier(e['M'])[1]:.2f}/{e['H'] * tier(e['H'])[1]:.2f}")
    for k in (0.45, 0.573, 0.60):
        e = eps27_adj * k
        print(f"  sens k_l={k}: L {e * tier(e)[1]:.2f}")
    eq_fy28 = inp["equity"] + (inp["eps_fy27"] + inp["eps_fy28_m"]) * shares
    roe_m28 = eps["M"] * shares / eq_fy28
    print(f"  sens equity at FY28-end book {eq_fy28 / 1e9:.1f}B (ROE_M {roe_m28:.3f}): M {eps['M'] * perpetual_pe(g2, roe_m28, r):.2f} (not adopted)")
    print(f"  discounted 1y reference (/1.1): {L / 1.1:.1f}/{M / 1.1:.1f}/{H / 1.1:.1f} (not adopted)")
    att = {t: optical_attachment(opt_rev[t], t) for t in TIERS}
    print(
        "optical narrow (A14): rev L/M/H = "
        f"${opt_rev['L']/1e9:.3f}B/${opt_rev['M']/1e9:.3f}B/${opt_rev['H']/1e9:.3f}B "
        f"(laser ${inp['laser_usd_per_oe']:.0f}/OE × share {inp['lite_laser_share']:.0%}); "
        f"attach vs oe×$450 = {att['L']:.1%}/{att['M']:.1%}/{att['H']:.1%}"
    )
    print(
        f"capex axis implied share (wide, FY27 revenue consensus incl. industrial/commercial lasers):"
        f" M {inp['rev_fy27_cons'] * 1e6 / inp['capex_m']:.2%}"
    )

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_perp 1:1 inside tier(); EPS, the rolled ROE and g2 stay put.  Disclosure
    # only — the anchors above are the 中枢 column; the /1.1 line is not a rate.
    def band_at(dr: float) -> tuple[float, float, float]:
        nonlocal r
        saved = r
        r = r + dr
        try:
            return tuple(eps[t] * tier(eps[t])[1] for t in TIERS)  # type: ignore[return-value]
        finally:
            r = saved

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_at)
    if any(abs(x - y) > TOL for x, y in zip(band_at(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    # Only a clean run feeds the daily digest.
    write_rf_readings("LITE.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
