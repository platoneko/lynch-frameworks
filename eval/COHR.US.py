#!/usr/bin/env python3
"""COHR.US (Coherent Corp.) valuation eval — recompute anchors from frameworks/COHR.US.md.

frameworks/COHR.US.md is the source of truth; this script re-parses its §3 Inputs,
recomputes L/M/H / A/B and exits 1 on mismatch.  The doc carries no current price
(AGENTS.md「现价 — 禁写契约」): which zone a quote falls in is derived live by the
daily digest and the app, so nothing here reads a price.

formula_id: cohr_sotp_dcc_industrial_pe_fy28_disc_gordon_v2_sic_vopt

Main ruler: two-leg SOTP on FY2028 (fiscal year ending 2028-06-30).
Each leg = segment revenue x segment-profit margin, less a revenue-pro-rata share
of corporate + SBC, taxed at the normalized non-GAAP rate, per diluted share.
Multiples are GENERATED, not borrowed (AGENTS.md「永续增长口径」): each leg names a
perpetual g2 and the multiple is `perpetual_pe(g2, ROE_x, r)` with the company
tier ROE (no leg equity is disclosed, so both legs share it).  ROE (A21) =
FY2028 econ EPS_x / the FY2028 OPENING BPS (E_{n+1}/B_n): the FY26 book (latest
balance sheet, 2026-06-30) is rolled over the FY27 consensus EPS -- the whole
year not yet booked before FY28 opens -- at the growth-required retention
b1 = g/ROE, g = the EPS-weighted company g2 the two legs charge (no g1 window),
closed form BPS = BPS0 / (1 - g·N/EPS) (valuation-rules 裁决表 ② as of
2026-09-21).  FY28's own retention is NOT rolled (year-end error);
the actual retention above b1 is printed as the B-bucket disclosure only.  Datacom g2 is the AI-optical peer cross-section reverse-solved
and truncated at the repo cap; Industrial g2 = 0 (flat revenue, 无同业锚).  One g2
per leg is shared across tiers (`fast_grower` primary), so the tier ladder lives
in the numerator and the multiple only moves with ROE.  The sum is discounted
from 2027-06-30 (where a forward PE on FY2028 earnings sits) back to today, then
net debt per share is added.

Option (A12, never in the base): the SiC subsidiary has no computable numerator
(loss-making, no standalone consensus) but a one-off external mark — the
2023-12 Denso/MELCO purchase of 25% at $1B.  Its ceiling is Coherent's 75% of
that mark plus the capitalised loss the base carries inside the Industrial leg;
表3 = base_k + p_k x V_opt with P_K an eval constant (same 拍值 as WOLF / 2631).

Sanity checks beyond the L<M<H / Outputs reconciliation:
  - every r row names a basket (`篮 N`) and equals that basket's value
    (gordon.BASKET_R); g2 <= g_cap(r); r - g2 >= 2% (not at the pole)
  - every tier's generated multiple inside the ticker's own realised band
    (pe_own_min / pe_own_max — the guardrail that replaced the borrowed PE band)
  - scenario monotonicity on revenue and margins; m_dcc_h hard cap
  - numerator ladder + flat-multiple ladder (A2e-2c), decomposition (A2e-5)
  - the M-scenario bottom-up economic EPS must land within +/-20% of the
    FY2028 street consensus non-GAAP EPS (the A2d cross-constraint, mechanised),
    and that consensus mean must sit inside [eps_M, eps_H] (裁决表 ②-b (i))
  - shared-axis rungs (ai-capex, optical-comms) match the axis files
  - option: stated V_opt and 表3 reconcile; p never leaks into the base

Run:  python3 frameworks/eval/COHR.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import check_capex_mount, check_optical_oe_mount  # noqa: E402
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.gordon import check_g_cap, check_r, g_cap, implied_g, perpetual_pe  # noqa: E402
from eval.lib.inputs import parse_baskets  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402
from eval.lib.tiers import decompose, flat_multiple_ladder  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "COHR.US.md"
FORMULA_ID = "cohr_sotp_dcc_industrial_pe_fy28_disc_gordon_v2_sic_vopt"
LISTING_CCY = "USD"
TOL = 0.05  # outputs rounded to 2 decimals

MGN_DCC_HARD_CAP = 0.35  # DC&C segment-profit margin: 19.0/24.1/25.2% FY24-26
CONSENSUS_BAND = 0.20  # |bottom-up M economic EPS / street FY28 non-GAAP EPS - 1|
MIN_R_MINUS_G = 0.02  # AGENTS.md: below this the multiple sits at the pole
TIERS = ("L", "M", "H")
# 表3 per-tier credit on the SiC option (A12): 拍值, never an Input, never the base.
P_K = (0.0, 0.25, 1.0)


def parse_inputs(md: str) -> dict[str, float]:
    """Parse §3 Inputs table: | field | value | meaning | as-of |"""
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
        if key in ("字段名", "--------", "---") or raw in ("取值",):
            continue
        if raw in ("待补", "", "—"):
            continue
        try:
            out[key] = float(raw.replace(",", ""))
        except ValueError:
            continue
    return out


def first_float(pattern: str, md: str) -> float | None:
    m = re.search(pattern, md)
    return float(m.group(1)) if m else None


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    required = [
        "shares_diluted",
        "equity",
        "rev_dcc_l",
        "rev_dcc_m",
        "rev_dcc_h",
        "rev_ind",
        "m_dcc_l",
        "m_dcc_m",
        "m_dcc_h",
        "m_ind_l",
        "m_ind_m",
        "m_ind_h",
        "corp_pct",
        "tax_rate",
        "r_perp",
        "g2_dcc",
        "g2_ind",
        "r_disc",
        "t_disc",
        "net_debt_ps",
        "eps_cons_fy28",
        "eps_cons_fy27",
        "payout_3y",
        "pe_own_min",
        "pe_own_max",
        "oe_l",
        "oe_m",
        "oe_h",
        "capex_l",
        "capex_m",
        "capex_h",
        "sic_stake",
        "sic_deal_value",
        "sic_nci_loss",
    ]
    missing = [k for k in required if k not in inp]
    if missing:
        print(f"FAIL: missing inputs {missing}", file=sys.stderr)
        return 1

    # --- Step 0: sanity guards on the inputs themselves -------------------
    guards: list[str] = []
    guards.extend(check_optical_oe_mount((inp["oe_l"], inp["oe_m"], inp["oe_h"])))
    guards.extend(check_capex_mount((inp["capex_l"], inp["capex_m"], inp["capex_h"])))
    # Both legs are ordinary operating cash flow (no take-or-pay contract, no
    # unfunded customer): the framework names the basket on the r_perp row
    # (A20) and r must be that basket's value; r_disc bridges the 0.82y to the
    # forward-PE date at the same rate.
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        guards.append("r_perp: Inputs source cell names no 篮 N (A20)")
    guards.extend(check_r(inp["r_perp"], "r_perp", baskets.get("r_perp")))
    guards.extend(check_r(inp["r_disc"], "r_disc"))
    if abs(inp["r_disc"] - inp["r_perp"]) > 1e-9:
        guards.append(f"r_disc={inp['r_disc']} must equal r_perp={inp['r_perp']} (A17)")
    for leg in ("dcc", "ind"):
        g = inp[f"g2_{leg}"]
        guards.extend(check_g_cap(g, inp["r_perp"], f"g2_{leg}"))
        gap = inp["r_perp"] - g
        if gap <= 0:
            guards.append(f"perpetuity diverges on {leg}: g2 >= r")
        elif gap < MIN_R_MINUS_G:
            guards.append(f"r - g2_{leg} = {gap:.2%} < {MIN_R_MINUS_G:.0%} — at the pole")
    if not (inp["m_dcc_l"] < inp["m_dcc_m"] < inp["m_dcc_h"]):
        guards.append("m_dcc order violated")
    if inp["m_dcc_h"] > MGN_DCC_HARD_CAP + 1e-9:
        guards.append(f"m_dcc_h={inp['m_dcc_h']} exceeds hard cap {MGN_DCC_HARD_CAP}")
    if not (inp["m_ind_l"] < inp["m_ind_m"] < inp["m_ind_h"]):
        guards.append("m_ind order violated")
    if not (inp["rev_dcc_l"] < inp["rev_dcc_m"] < inp["rev_dcc_h"]):
        guards.append("rev_dcc order violated")
    if not (0.0 < inp["tax_rate"] <= 0.35):
        guards.append(f"tax_rate={inp['tax_rate']} outside (0, 0.35]")
    if inp["net_debt_ps"] > 0:
        guards.append(f"net_debt_ps={inp['net_debt_ps']} must be <= 0 (net debt, not net cash)")
    if not (0 < inp["pe_own_min"] < inp["pe_own_max"]):
        guards.append("pe_own_min/max guardrail band malformed")
    if inp["equity"] <= 0:
        guards.append("equity must be positive")
    if not (0 < inp["sic_stake"] < 1):
        guards.append(f"sic_stake={inp['sic_stake']} must be a minority-partner split in (0, 1)")
    if guards:
        print("FAIL:", "; ".join(guards), file=sys.stderr)
        return 1

    # --- Step 1: per-scenario two-leg SOTP, multiples generated by Gordon ---
    # ROE = E_{n+1} / B_n (A21): the FY26 book is the latest balance sheet, so
    # the whole FY27 consensus is the unbooked N (non-GAAP basis: SBC lands in
    # APIC, so it accretes book like cash earnings).  It is rolled at the
    # growth-required retention b1 = g/ROE with g = the EPS-weighted company g2
    # the two legs charge -- no g1 window here -- closed form
    # BPS = BPS0 / (1 - g·N/EPS).  Actual retention above b1 is the B bucket,
    # a disclosure line, never put into the book.
    bps0 = inp["equity"] / inp["shares_diluted"]
    unbooked = inp["eps_cons_fy27"]

    def scenario(
        rev_dcc: float, m_dcc: float, m_ind: float,
        g_dcc: float | None = None, g_ind: float | None = None,
    ) -> dict[str, float]:
        g_dcc = inp["g2_dcc"] if g_dcc is None else g_dcc
        g_ind = inp["g2_ind"] if g_ind is None else g_ind
        rev_ind = inp["rev_ind"]
        rev_tot = rev_dcc + rev_ind
        corp = inp["corp_pct"] * rev_tot  # corporate + SBC, allocated pro-rata by revenue
        ebit_dcc = rev_dcc * m_dcc - corp * rev_dcc / rev_tot
        ebit_ind = rev_ind * m_ind - corp * rev_ind / rev_tot
        after_tax = 1.0 - inp["tax_rate"]
        eps_dcc = ebit_dcc * after_tax * 1e6 / inp["shares_diluted"]  # inputs in $M
        eps_ind = ebit_ind * after_tax * 1e6 / inp["shares_diluted"]
        eps = eps_dcc + eps_ind
        # Company retention the legs charge, then the opening-FY28 book (A21).
        g_co = (eps_dcc * g_dcc + eps_ind * g_ind) / eps
        if g_co * unbooked / eps >= 1.0:
            raise ValueError(f"opening-book roll diverges: g·N/EPS = {g_co * unbooked / eps:.3f} ≥ 1")
        bps_open = bps0 / (1.0 - g_co * unbooked / eps)
        roe = eps / bps_open
        pe_dcc = perpetual_pe(g_dcc, roe, inp["r_perp"])
        pe_ind = perpetual_pe(g_ind, roe, inp["r_perp"])
        v_dcc = eps_dcc * pe_dcc
        v_ind = eps_ind * pe_ind
        return {
            "eps_dcc": eps_dcc,
            "eps_ind": eps_ind,
            "eps": eps,
            "roe": roe,
            "g_co": g_co,
            "bps_open": bps_open,
            "b1": g_co / roe,
            "pe_dcc": pe_dcc,
            "pe_ind": pe_ind,
            "v_dcc": v_dcc,
            "v_ind": v_ind,
            "sum": v_dcc + v_ind,
            "blend": (v_dcc + v_ind) / eps,
        }

    s = {
        "L": scenario(inp["rev_dcc_l"], inp["m_dcc_l"], inp["m_ind_l"]),
        "M": scenario(inp["rev_dcc_m"], inp["m_dcc_m"], inp["m_ind_m"]),
        "H": scenario(inp["rev_dcc_h"], inp["m_dcc_h"], inp["m_ind_h"]),
    }

    # --- Step 2: A2d cross-constraint, mechanised -------------------------
    dev = s["M"]["eps"] / inp["eps_cons_fy28"] - 1.0
    if abs(dev) > CONSENSUS_BAND:
        print(
            f"FAIL: M-scenario economic EPS {s['M']['eps']:.2f} deviates {dev:+.1%} from"
            f" street FY2028 non-GAAP consensus {inp['eps_cons_fy28']}"
            f" (band +/-{CONSENSUS_BAND:.0%})",
            file=sys.stderr,
        )
        return 1
    # 裁决表 ②-b (i): the bottom-up ladder may stand beside the consensus three
    # points only if the farthest banded consensus mean sits inside [M, H].
    if not (s["M"]["eps"] <= inp["eps_cons_fy28"] <= s["H"]["eps"]):
        print(
            f"FAIL: street FY2028 consensus mean {inp['eps_cons_fy28']} outside"
            f" [eps_M {s['M']['eps']:.2f}, eps_H {s['H']['eps']:.2f}] (裁决表 ②-b (i))",
            file=sys.stderr,
        )
        return 1

    # --- Step 3: discount to today, then close with net debt --------------
    disc = (1.0 + inp["r_disc"]) ** (-inp["t_disc"])
    anchors = {t: s[t]["sum"] * disc + inp["net_debt_ps"] for t in TIERS}
    L, M, H = (anchors[t] for t in TIERS)
    A = (L + M) / 2
    B = (M + H) / 2

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1

    # --- Step 3a: SiC option ceiling (A12) — external mark, not a multiple ---
    # The base carries the subsidiary only as its loss inside the Industrial
    # margin, capitalised at the g=0 multiple and discounted like the leg; the
    # success world replaces that drag with the 2023 deal mark on the 75% stake.
    per_share = 1e6 / inp["shares_diluted"]
    v_deal = inp["sic_stake"] * inp["sic_deal_value"] * per_share
    loss_100 = inp["sic_nci_loss"] / (1.0 - inp["sic_stake"])
    drag_base = loss_100 * per_share * perpetual_pe(inp["g2_ind"], s["M"]["roe"], inp["r_perp"]) * disc
    v_opt = v_deal + drag_base
    adj = tuple(x + p * v_opt for x, p in zip((L, M, H), P_K))
    adj_a, adj_b = (adj[0] + adj[1]) / 2, (adj[1] + adj[2]) / 2

    errors: list[str] = []
    # Guardrail (AGENTS.md「永续增长口径」): a generated multiple outside the
    # ticker's own realised band is red — do not force g, do not widen the band.
    for t in TIERS:
        for label, pe in (("blended", s[t]["blend"]), ("dcc", s[t]["pe_dcc"])):
            if not (inp["pe_own_min"] <= pe <= inp["pe_own_max"]):
                errors.append(
                    f"{t} {label} PE {pe:.1f}x outside own realised band "
                    f"[{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]"
                )

    # --- Step 3b: A2e-2c flat ladder + A2e-5 decomposition ----------------
    # Numerator ladder must hold on its own; then re-price every tier at the
    # M-tier leg multiples (datacom and industrial each held at their M rung).
    flat_errs, _ = flat_multiple_ladder((s["L"]["eps"], s["M"]["eps"], s["H"]["eps"]), s["M"]["blend"])
    errors += flat_errs
    flat = tuple(
        (s[t]["eps_dcc"] * s["M"]["pe_dcc"] + s[t]["eps_ind"] * s["M"]["pe_ind"]) * disc + inp["net_debt_ps"]
        for t in TIERS
    )
    if not (flat[0] < flat[1] < flat[2]):
        errors.append(f"flat-multiple ladder broken: {flat}")
    dec = decompose((L, M, H), (s["L"]["blend"], s["M"]["blend"], s["H"]["blend"]))

    # --- Step 4: reconcile against the stated Outputs ---------------------
    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    triples = re.findall(
        r"L = \*\*[0-9.]+\*\* · M = \*\*[0-9.]+\*\* · H = \*\*[0-9.]+\*\*", out_sec
    )
    if len(triples) != 1:
        errors.append(
            f"### Outputs must state the L/M/H triple exactly once, found {len(triples)}"
        )
    vo = re.search(r"V_\{opt\}\\?\)?\s*=\s*\*\*([0-9.]+)\*\*", out_sec)
    if vo is None:
        errors.append("stated V_opt not found in Outputs")
    elif abs(float(vo.group(1)) - v_opt) > TOL:
        errors.append(f"V_opt: stated {vo.group(1)} vs recomputed {v_opt:.4f}")
    if abs(adj[0] - L) > 1e-9:
        errors.append(f"p leaked into the base: 表3 L row {adj[0]:.4f} != base L {L:.4f}")
    if "表3" not in out_sec:
        errors.append("V_opt > 0 but Outputs has no 表3")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")

    stated = {
        "L": first_float(r"L = \*\*([0-9.]+)\*\*", out_sec),
        "M": first_float(r"M = \*\*([0-9.]+)\*\*", out_sec),
        "H": first_float(r"H = \*\*([0-9.]+)\*\*", out_sec),
        "A": first_float(r"A = \*\*([0-9.]+)\*\*", out_sec),
        "B": first_float(r"B = \*\*([0-9.]+)\*\*", out_sec),
    }
    recomputed = {"L": L, "M": M, "H": H, "A": A, "B": B}
    for k, v in recomputed.items():
        st = stated.get(k)
        if st is None:
            errors.append(f"stated {k} not found")
        elif abs(st - v) > TOL:
            errors.append(f"{k}: stated {st} vs recomputed {v:.4f}")

    # --- Report -----------------------------------------------------------
    print(f"formula_id={FORMULA_ID}")
    print(
        f"r_perp={inp['r_perp']:g} (篮 {baskets['r_perp']}) g2_dcc={inp['g2_dcc']:.4f} g2_ind={inp['g2_ind']:.4f}"
        f"  equity={inp['equity']:.4g} shares={inp['shares_diluted']:.4g}"
    )
    print(
        f"econ EPS FY28  L/M/H = {s['L']['eps']:.2f}/{s['M']['eps']:.2f}/{s['H']['eps']:.2f}"
        f"   (street non-GAAP {inp['eps_cons_fy28']}, M dev {dev:+.1%}; ②-b mean in [M, H] ok)"
    )
    print(
        f"tier ROE L/M/H = {s['L']['roe']:.4f}/{s['M']['roe']:.4f}/{s['H']['roe']:.4f} "
        f"(FY28 econ EPS / opening-FY28 BPS {s['L']['bps_open']:.2f}/{s['M']['bps_open']:.2f}/{s['H']['bps_open']:.2f}; "
        f"FY26 book {bps0:.2f} rolled over unbooked FY27 {unbooked:.3f} at b1 = g_co/ROE = "
        f"{s['L']['b1']:.3f}/{s['M']['b1']:.3f}/{s['H']['b1']:.3f}, g_co {s['L']['g_co']:.2%}/{s['M']['g_co']:.2%}/{s['H']['g_co']:.2%}; "
        f"v2 basis EPS/FY26 book would read {s['L']['eps'] / bps0:.4f}/{s['M']['eps'] / bps0:.4f}/{s['H']['eps'] / bps0:.4f})"
    )
    ret_actual = 1.0 - inp["payout_3y"]
    print(
        f"B bucket (modelled-as-distributed, actually retained): actual retention {ret_actual:.0%} − b1 → "
        + "/".join(f"{(ret_actual - s[t]['b1']) * unbooked:.2f}" for t in TIERS)
        + " USD/share over FY27 (disclosure only; not a leg, not in BPS)"
    )
    print(
        f"generated PE  dcc L/M/H = {s['L']['pe_dcc']:.2f}/{s['M']['pe_dcc']:.2f}/{s['H']['pe_dcc']:.2f}x"
        f"  ind = {s['L']['pe_ind']:.2f}/{s['M']['pe_ind']:.2f}/{s['H']['pe_ind']:.2f}x"
        f"  blended undisc = {s['L']['blend']:.2f}/{s['M']['blend']:.2f}/{s['H']['blend']:.2f}x"
        f"  guardrail [{inp['pe_own_min']:g}, {inp['pe_own_max']:g}]"
    )
    print(
        f"表1 数通  L/M/H = {s['L']['v_dcc'] * disc:.2f}/{s['M']['v_dcc'] * disc:.2f}/{s['H']['v_dcc'] * disc:.2f}"
        f"  (disc={disc:.4f})"
    )
    print(f"表1 工业  L/M/H = {s['L']['v_ind'] * disc:.2f}/{s['M']['v_ind'] * disc:.2f}/{s['H']['v_ind'] * disc:.2f}")
    print(f"表1 闭合项 = {inp['net_debt_ps']}")
    print(f"undisc dcc  L/M/H = {s['L']['v_dcc']:.2f}/{s['M']['v_dcc']:.2f}/{s['H']['v_dcc']:.2f}")
    print(f"undisc ind  L/M/H = {s['L']['v_ind']:.2f}/{s['M']['v_ind']:.2f}/{s['H']['v_ind']:.2f}")
    print(
        f"sum undisc     L/M/H = {s['L']['sum']:.2f}/{s['M']['sum']:.2f}/{s['H']['sum']:.2f}"
        f"  disc={disc:.4f}  net_debt_ps={inp['net_debt_ps']}"
    )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"flat-multiple ladder (dcc held at M {s['M']['pe_dcc']:.2f}x, ind at M {s['M']['pe_ind']:.2f}x):"
        f" {flat[0]:.2f}/{flat[1]:.2f}/{flat[2]:.2f}"
    )
    # `decompose` folds the fixed net-debt term into its residual numerator ratio;
    # the pure EPS ratio is printed alongside so the two can be told apart.
    print(
        f"L/M {dec['lm']:.3f} = eps {s['L']['eps'] / s['M']['eps']:.3f} x pe {dec['pe_lm']:.3f} (+net debt; residual num {dec['num_lm']:.3f})"
        f" | H/M {dec['hm']:.3f} = eps {s['H']['eps'] / s['M']['eps']:.3f} x pe {dec['pe_hm']:.3f} (residual num {dec['num_hm']:.3f})"
        f" | width {(H - L) / (2 * M):.3f} | V_opt/M {v_opt / M:.3f}"
    )
    print(
        f"option SiC  deal {inp['sic_stake']:.0%} x {inp['sic_deal_value']:.0f}M -> {v_deal:.2f}/sh"
        f" + base drag (loss {loss_100:.1f}M x {perpetual_pe(inp['g2_ind'], s['M']['roe'], inp['r_perp']):.1f}x x disc) {drag_base:.2f}"
        f" -> V_opt {v_opt:.2f}"
    )
    print(
        f"表3  p_k={P_K[0]:.2f}/{P_K[1]:.2f}/{P_K[2]:.2f}  L'/M'/H' = {adj[0]:.2f}/{adj[1]:.2f}/{adj[2]:.2f}"
        f"  A'={adj_a:.2f} B'={adj_b:.2f}"
    )
    print(
        f"capex axis implied share (wide, DC&C FY28 incl. pluggables):"
        f" M {inp['rev_dcc_m'] * 1e6 / inp['capex_m']:.2%}"
    )
    print(
        f"implied PE on street FY28 EPS: L={L / inp['eps_cons_fy28']:.1f}x"
        f" M={M / inp['eps_cons_fy28']:.1f}x H={H / inp['eps_cons_fy28']:.1f}x"
    )

    # Band as evidence (裁决顺序 ③): the datacom g each guardrail edge implies at
    # the tier ROE. The lower edge sits under the payout cap; the upper edge is
    # within 2pp of the pole and is a market reading, not a candidate g.
    edges = []
    for t in TIERS:
        g_lo, _ = implied_g(inp["pe_own_min"], s[t]["roe"], inp["r_perp"])
        g_hi, _ = implied_g(inp["pe_own_max"], s[t]["roe"], inp["r_perp"])
        edges.append(f"{t} [{g_lo:+.2%}, {g_hi:+.2%}{' pole' if inp['r_perp'] - g_hi < MIN_R_MINUS_G else ''}]")
    print(
        "band-edge implied g_dcc @ tier ROE: " + "  ".join(edges)
        + f"  — g2_dcc {inp['g2_dcc']:.2%} inside every tier: "
        f"{all(implied_g(inp['pe_own_min'], s[t]['roe'], inp['r_perp'])[0] <= inp['g2_dcc'] <= implied_g(inp['pe_own_max'], s[t]['roe'], inp['r_perp'])[0] for t in TIERS)}"
    )

    # Sensitivities the doc quotes (Outputs 敏感性): g2_dcc ±1pp and the
    # untruncated peer median (above-cap values are reference only); g2_ind ±1pp
    # (无同业锚) and the single-house MKSI reverse-solve.
    # The book re-rolls with the shifted g (b1 = g/ROE moves with it).
    def reprice(g_dcc: float, g_ind: float) -> tuple[float, float, float]:
        out = []
        for t in TIERS:
            sc = scenario(inp[f"rev_dcc_{t.lower()}"], inp[f"m_dcc_{t.lower()}"], inp[f"m_ind_{t.lower()}"], g_dcc, g_ind)
            out.append(sc["sum"] * disc + inp["net_debt_ps"])
        return tuple(out)

    for g in (inp["g2_dcc"] - 0.01, inp["g2_dcc"] + 0.01, 0.0606):
        tag = " (above cap, reference only)" if g > g_cap(inp["r_perp"]) + 1e-9 else ""
        print(f"  sens g2_dcc={g:.4f}{tag}: " + "/".join(f"{x:.2f}" for x in reprice(g, inp["g2_ind"])))
    for g in (inp["g2_ind"] - 0.01, inp["g2_ind"] + 0.01, 0.0409):
        tag = " (MKSI single house, reference)" if abs(g - 0.0409) < 1e-9 else " (no peer anchor)"
        print(f"  sens g2_ind={g:+.4f}{tag}: " + "/".join(f"{x:.2f}" for x in reprice(inp["g2_dcc"], g)))

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # every priced r 1:1 — r_perp (both legs' Gordon multiple) and r_disc (the
    # t_disc pull-back of the FY28 sum; A17 pins it to r_perp, so it moves with
    # it).  g2, the re-rolled ROE, numerators and net debt stay put.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        saved = inp["r_perp"], inp["r_disc"]
        inp["r_perp"], inp["r_disc"] = saved[0] + dr, saved[1] + dr
        try:
            disc_r = (1.0 + inp["r_disc"]) ** (-inp["t_disc"])
            lmh = [
                scenario(inp[f"rev_dcc_{t.lower()}"], inp[f"m_dcc_{t.lower()}"], inp[f"m_ind_{t.lower()}"])["sum"]
                * disc_r + inp["net_debt_ps"]
                for t in TIERS
            ]
            return lmh[0], lmh[1], lmh[2]
        finally:
            inp["r_perp"], inp["r_disc"] = saved

    rf = rf_block(LISTING_CCY, {"r_perp": inp["r_perp"], "r_disc": inp["r_disc"]}, band_rf)
    if any(abs(x - y) > TOL for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    # Only a clean run writes, so a FAIL never feeds the daily digest.
    write_rf_readings("COHR.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
