#!/usr/bin/env python3
"""6655.HK (Huaxin Cement / Huaxin Building Materials) valuation eval.

frameworks/6655.HK.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied r — the digest and the app zone on live quotes.  The δ
readings printed below are for price-free coordinates only (sell-side TP, book).

formula_id: huaxin_dom_ovs_split_perpetual_g_hk_anchored_v5

Main ruler: split the NUMERATOR by leg, let each tier name a PERPETUAL GROWTH
RATE for each leg, price each leg on its own Gordon multiple at its BASKET r
and its OWN ROE, and add the legs up (SOTP).

  L numerator per leg  = FY2025 segment note (境内 / 境外 pre-tax profit, one
                         effective tax rate, NCI profit allocated by the same
                         rule as NCI equity) -> overseas 19.70 / domestic 8.83
  M / H numerator      = consensus mean / high group NI x the FY2025 realised
                         overseas share (constant across tiers)
  ROE_leg              = NI_leg / end-FY2025 leg 归母 net assets (segment assets
                         - segment liabilities, parent's investment in overseas
                         subs eliminated, NCI subtracted) -- valuation-rules
                         「分腿 ROE 来源优先序」①, numerator year's opening book
  PE_leg               = min(1, 1 - g_leg/ROE_leg) / (r_leg - g_leg)
  V                    = NI_dom x PE_dom + NI_ovs x PE_ovs

r comes from the basket each leg is assigned to (valuation-rules.md「§r 篮子」,
values in gordon.BASKET_R); the Inputs rows `r_dom` / `r_ovs` name the basket
in their source cell and `check_r` enforces that the value is that basket's.
Both legs sit in 篮 6 (13%), so a no-growth leg is worth 1/r = 7.69x.

Until 2026-09-21 the overseas leg was overseas EBITDA x a company-wide
NI/EBITDA conversion with the domestic leg as the residual, and both legs
shared the company ROE.  The FY2025 segment note replaces both: overseas
already earns ~69% of 归母, so EBITDA x k_FY2025 on the 2026 EBITDA rows would
push the domestic residual below its L value in every tier (a broken leg
ladder, construction.md §2c).  The overseas EBITDA rows therefore stay in
Inputs ONLY as a cross-check (implied conversion per tier) and a leak guard
asserts they never reach the anchors.

The multiples are NOT quantiles of the ticker's own historical PE.  A realised
PE carries whatever growth the market was pricing at the time; using those
quantiles as tiers imports the past's growth expectations into today's
numerator.  This deviates from skill A2e-2b by explicit user decision
(2026-09-09); the measured band survives as a fence, and every tier's
company-level multiple (anchor / group EPS) has to land inside it.

V_opt (A15, valuation-rules「未建模期权」2026-10-03): the signed Holcim
Philippines (HPI) stage-1 purchase is the only named quantity beyond consensus.
Units = HPI 2025 revenue x the overseas leg's own FY2025 segment after-tax
margin x the stake, less after-tax interest on the consideration at this
ticker's own debt cost; priced at the overseas leg's H multiple (own basket r,
axis g, own leg ROE -- no peer multiple) and discounted from the realisation
year back to the numerator year.  p_k lives in table 3 only.

Guards:

  * the zero-growth floor on the overseas leg's H (A10): g_ovs_H >= 0.
  * the historical fence (A9): company-level multiple inside [4.24, 12.78].
  * 回代校验: leg 归母 net assets + unallocated = group 归母 equity (±0.5),
    and the two L-tier leg numerators add back to the group L numerator.
  * EBITDA rows must not leak into the anchor path.

Run:  python3 frameworks/eval/6655.HK.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_SOUTHBOUND, check_africa_mount  # noqa: E402
from lib.gordon import basket_r, check_g_cap, check_r, payout, perpetual_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

# rf_report / bands_io import through the `eval.lib` package, so the repo root
# must be importable too; appended so `lib.*` above still resolves first.
sys.path.append(str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "6655.HK.md"
FORMULA_ID = "huaxin_dom_ovs_split_perpetual_g_hk_anchored_v5"

TIERS = ("l", "m", "h")
# Perpetual-g inputs carry the `g2_` prefix so scripts/calibration.py reports
# them in its g2 column (valuation-rules.md「永续增长口径」).  Each leg has its
# own basket r row.
LEGS = ("dom", "ovs")
R_ROWS = {"dom": "r_dom", "ovs": "r_ovs"}
MONOTONIC_GAP = 0.03        # |ROE - r| threshold of the domain table (gordon._ROE_NEAR_R)
# _AXIS.rates segment: HKD rides the USD r_f via the peg (valuation-rules「按上市货币取段」).
LISTING_CCY = "HKD"
NUM_YEAR = 2026             # numerator year of M/H (FY2026E consensus)
P_TIERS = (0.0, 0.25, 1.0)  # A15 — table 3 only, never an input
TOL = 0.05
H1_OVS_REV = 85.42         # 2026H1 overseas revenue 亿 (§0 snapshot); V_opt sensitivity print only

REQUIRED = [
    "shares", "bps", "fx_hkdcny",
    "equity_group", "equity_ovs", "equity_dom", "equity_unalloc",
    "nci_equity", "nci_equity_ovs", "nci_profit", "nci_profit_ovs",
    "pretax_ovs", "pretax_dom", "tax_eff", "da_ovs",
    "r_dom", "r_ovs",
    "ni_group_l", "ni_group_m", "ni_group_h",
    "ebitda_ovs_l", "ebitda_ovs_m", "ebitda_ovs_h",
    "g2_dom_l", "g2_dom_m", "g2_dom_h",
    "g2_ovs_l", "g2_ovs_m", "g2_ovs_h",
    "pe_own_lo", "pe_own_hi", "pe_own_mid",
    "eps_consensus_low", "pe_a_mid",
    "rev_ovs", "opt_rev_usd", "opt_stake", "opt_price_usd", "fx_usdcny", "int_cost", "t_opt",
]


def stated_v_opt(md: str) -> float | None:
    m = re.search(r"V_\{opt\}\\\)\s*=\s*\*\*([0-9.]+)\*\*", md)
    return float(m.group(1)) if m else None


def stated_p_tiers(md: str) -> tuple[float, float, float] | None:
    m = re.search(
        r"p_L\s*/\s*p_M\s*/\s*p_H\\?\)?\s*[≈=]\s*\*{0,2}\s*"
        r"([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)\s*/\s*([0-9]*\.?[0-9]+)",
        md,
    )
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def opt_delta_ni(inp: dict[str, float], margin: float | None = None, int_cost: float | None = None) -> float:
    """A15: HPI stage-1 incremental 归母, 亿元 CNY.

    Revenue (USD 亿 -> CNY) x the overseas leg's FY2025 segment after-tax margin
    (before NCI) x the stake, less after-tax interest on the consideration at
    this ticker's own debt cost (the numerator is 归母 after interest, A11).
    """
    if margin is None:
        margin = inp["pretax_ovs"] * (1.0 - inp["tax_eff"]) / inp["rev_ovs"]
    rate = inp["int_cost"] if int_cost is None else int_cost
    fx = inp["fx_usdcny"]
    earn = inp["opt_rev_usd"] * fx * margin * inp["opt_stake"]
    carry = inp["opt_price_usd"] * fx * rate * (1.0 - inp["tax_eff"])
    return earn - carry


def domain(roe: float, r: float) -> str:
    """valuation-rules.md 域判定表, per leg and tier."""
    if roe - r >= MONOTONIC_GAP:
        return "单调区"
    if abs(roe - r) < MONOTONIC_GAP:
        return "病态区"
    return "峰形区"


def nci_profit_ovs(inp: dict[str, float], nci_equity_ovs: float) -> float:
    """NCI profit assigned to the overseas leg under an NCI-equity allocation.

    The disclosed Lafarge Africa share (equity 7.06 / profit 0.68, A18) is the
    only hard datum; NCI equity beyond it is split domestic/overseas by
    assumption, and its profit follows the same split pro rata.
    """
    laf_eq, laf_profit = inp["nci_equity_ovs"], inp["nci_profit_ovs"]
    rest_eq = inp["nci_equity"] - laf_eq
    rest_profit = inp["nci_profit"] - laf_profit
    extra = max(0.0, nci_equity_ovs - laf_eq) / rest_eq if rest_eq > 0 else 0.0
    return laf_profit * min(1.0, nci_equity_ovs / laf_eq) + rest_profit * extra


def leg_split(inp: dict[str, float], nci_equity_ovs: float | None = None) -> tuple[dict[str, float], dict[str, float]]:
    """({leg: 归母 net assets}, {leg: FY2025 归母 NI}) for an NCI allocation.

    Default = the framework's base allocation (only the disclosed Lafarge
    Africa NCI sits overseas).  Other allocations move NCI equity between the
    legs and move NCI profit with it.
    """
    base = inp["nci_equity_ovs"]
    nci_ovs = base if nci_equity_ovs is None else nci_equity_ovs
    equity = {"ovs": inp["equity_ovs"] + base - nci_ovs,
              "dom": inp["equity_dom"] - (base - nci_ovs)}
    p_ovs = nci_profit_ovs(inp, nci_ovs)
    after_tax = 1.0 - inp["tax_eff"]
    ni_l = {"ovs": inp["pretax_ovs"] * after_tax - p_ovs,
            "dom": inp["pretax_dom"] * after_tax - (inp["nci_profit"] - p_ovs)}
    return equity, ni_l


def legs(inp: dict[str, float], tag: str, ni_l: dict[str, float]) -> dict[str, float]:
    """{leg: net income} for one tier, 亿元 CNY: L from the segment note,
    M/H = consensus group NI x the FY2025 realised overseas share."""
    if tag == "l":
        return dict(ni_l)
    share = ni_l["ovs"] / (ni_l["ovs"] + ni_l["dom"])
    group = inp[f"ni_group_{tag}"]
    return {"ovs": group * share, "dom": group * (1.0 - share)}


def leg_pe(inp: dict[str, float], leg: str, tag: str, roe: float, r_shift: float = 0.0,
           g_override: float | None = None) -> float:
    g = inp[f"g2_{leg}_{tag}"] if g_override is None else g_override
    return perpetual_pe(g, roe, inp[R_ROWS[leg]] + r_shift)


class Model:
    """One SOTP under one NCI allocation; everything else read from Inputs."""

    def __init__(self, inp: dict[str, float], nci_equity_ovs: float | None = None):
        self.inp = inp
        self.equity, self.ni_l = leg_split(inp, nci_equity_ovs)
        self.ni = {t: legs(inp, t, self.ni_l) for t in TIERS}
        self.roe = {t: {leg: self.ni[t][leg] / self.equity[leg] for leg in LEGS} for t in TIERS}
        self.pe = {t: {leg: leg_pe(inp, leg, t, self.roe[t][leg]) for leg in LEGS} for t in TIERS}

    def value_cny(self, tag: str, pes: dict[str, float] | None = None) -> float:
        pe = pes or self.pe[tag]
        return sum(self.ni[tag][leg] * pe[leg] for leg in LEGS)

    def per_share_cny(self, tag: str, pes: dict[str, float] | None = None) -> float:
        return self.value_cny(tag, pes) * 1e8 / self.inp["shares"]

    def anchor(self, tag: str, pes: dict[str, float] | None = None) -> float:
        """HKD per share."""
        return self.per_share_cny(tag, pes) / self.inp["fx_hkdcny"]

    def band(self, pes_by_tier: dict[str, dict[str, float]] | None = None) -> list[float]:
        return [self.anchor(t, pes_by_tier[t] if pes_by_tier else None) for t in TIERS]

    def implied_r_shift(self, price_cny: float) -> float:
        """δ such that the M-tier SOTP with every leg at r_leg + δ equals a price coordinate.

        Both legs' basket r move together; the answer is the parallel shift the
        coordinate (sell-side TP, book) applies to the basket table, not a per-leg r.  Bisection on
        δ ∈ [-8%, +20%]: the SOTP is monotone decreasing in δ over that range.
        """
        lo, hi = -0.08, 0.20

        def f(delta: float) -> float:
            pes = {leg: leg_pe(self.inp, leg, "m", self.roe["m"][leg], r_shift=delta) for leg in LEGS}
            return self.per_share_cny("m", pes) - price_cny

        if f(lo) < 0 or f(hi) > 0:
            raise ValueError("implied r shift outside bisection bracket")
        for _ in range(80):
            mid = (lo + hi) / 2
            if f(mid) > 0:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2


def check_southbound_mount(md: str) -> list[str]:
    """Axis §3 rule 3: a mounted ticker reports both the H and the A-share bands.

    The southbound axis locks no numerator and, since valuation-rules.md
    「永续增长口径」took multiples away from historical quantiles, no multiple
    either (A16: it acts on the required-return convergence).  What it still
    locks is the reporting contract its own §4 direction check depends on.  The
    live H/A is a function of today's two prices and no longer lives in the
    doc; the axis's direction check reads its own dated series (§1).
    """
    if not AXIS_SOUTHBOUND.exists():
        return [f"axis file missing: {AXIS_SOUTHBOUND.name}"]
    errors: list[str] = []
    if "6655.HK" not in AXIS_SOUTHBOUND.read_text(encoding="utf-8"):
        errors.append("6655.HK is not declared on _AXIS.southbound-repricing.md — "
                      "a mount has to exist on both sides")
    if "A 股对照带" not in md:
        errors.append("framework lacks the A-share companion band (axis §3 rule 3)")
    return errors


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in md:
        print(f"FAIL: formula_id {FORMULA_ID} missing from framework", file=sys.stderr)
        return 1

    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    lo, hi = inp["pe_own_lo"], inp["pe_own_hi"]
    r = {leg: inp[R_ROWS[leg]] for leg in LEGS}

    # --- Step 1: baskets — each leg's r must be the basket it names -----------
    baskets = parse_baskets(md)
    for leg in LEGS:
        row = R_ROWS[leg]
        if row not in baskets:
            errors.append(f"{row}: Inputs source cell names no 篮 N (AGENTS.md「篮子声明」)")
        errors += check_r(r[leg], row, baskets.get(row))
    if errors:
        return report(errors, "FAIL (baskets)")

    # --- Step 2: leg book and numerators -------------------------------------
    m = Model(inp)
    # 回代校验 (valuation-rules.md 分腿 ROE 来源优先序 护栏): the two legs'
    # 归母 net assets plus the unallocated block must rebuild group 归母 equity,
    # and the segment-derived L legs must rebuild the group L numerator.
    rebuilt = m.equity["ovs"] + m.equity["dom"] + inp["equity_unalloc"]
    if abs(rebuilt - inp["equity_group"]) > 0.5:
        errors.append(f"leg equity {m.equity['ovs']:.2f} + {m.equity['dom']:.2f} + unallocated "
                      f"{inp['equity_unalloc']:.2f} = {rebuilt:.2f} != equity_group {inp['equity_group']}")
    leg_sum = m.ni_l["ovs"] + m.ni_l["dom"]
    if abs(leg_sum - inp["ni_group_l"]) > 0.05:
        errors.append(f"segment legs {m.ni_l['ovs']:.2f} + {m.ni_l['dom']:.2f} = {leg_sum:.2f} "
                      f"!= ni_group_l {inp['ni_group_l']} (tax / NCI allocation does not add back)")
    for leg in LEGS:
        if m.equity[leg] <= 0:
            errors.append(f"equity_{leg}={m.equity[leg]:.2f} must be positive (回对话)")
    for t in TIERS:
        for leg in LEGS:
            if m.roe[t][leg] > 0.60:
                errors.append(f"ROE_{leg}_{t}={m.roe[t][leg]:.1%} > 60% — leg book implausible (回对话)")
    errors += ladder("ni_group", inp["ni_group_l"], inp["ni_group_m"], inp["ni_group_h"])
    errors += ladder("ebitda_ovs (cross-check)", inp["ebitda_ovs_l"], inp["ebitda_ovs_m"], inp["ebitda_ovs_h"])
    # Both legs must ladder on their own.
    errors += ladder("ni_dom", *(m.ni[t]["dom"] for t in TIERS))
    errors += ladder("ni_ovs", *(m.ni[t]["ovs"] for t in TIERS))
    if errors:
        return report(errors, "FAIL (book / numerators)")

    # --- Step 3: the growth ladders, per leg against its own basket r --------
    errors += ladder("g_dom", inp["g2_dom_l"], inp["g2_dom_m"], inp["g2_dom_h"])
    errors += ladder("g_ovs", inp["g2_ovs_l"], inp["g2_ovs_m"], inp["g2_ovs_h"])
    for leg in LEGS:
        for t in TIERS:
            g = inp[f"g2_{leg}_{t}"]
            if r[leg] - g <= 0:
                errors.append(f"g2_{leg}_{t}={g:.4f} >= r_{leg}={r[leg]} — perpetuity diverges")
            # valuation-rules.md 永续上限: min(6%, r − 4%) per leg.
            errors += check_g_cap(g, r[leg], f"g2_{leg}_{t}")
    if errors:
        return report(errors, "FAIL (ladders/convergence)")

    # --- Step 4: the overseas leg belongs to the Africa axis -----------------
    # Huaxin's African cement plants, Keda's ceramic lines and Jiayou's toll
    # corridors all sit on the same driver and overlap in Zambia / Tanzania /
    # Mozambique.  None of the three gets to write its own Africa case.
    errors += check_africa_mount(
        (inp["g2_ovs_l"], inp["g2_ovs_m"], inp["g2_ovs_h"])
    )
    errors += check_southbound_mount(md)
    if errors:
        return report(errors, "FAIL (shared axis)")

    # --- Step 5: the normative guards ----------------------------------------
    # A10: "modelled success" must not shrink the growth leg forever.
    if inp["g2_ovs_h"] < -1e-12:
        errors.append(
            f"H tier overseas g={inp['g2_ovs_h']:.2%} < 0 — the optimistic tier cannot "
            f"price perpetual decline on the growth leg (A10)"
        )
    # A9: the company-level multiple (SOTP value / group NI) still has to be a
    # price this stock could print.
    pe_company = {t: m.value_cny(t) / inp[f"ni_group_{t}"] for t in TIERS}
    for t in TIERS:
        if not (lo - 1e-9 <= pe_company[t] <= hi + 1e-9):
            errors.append(
                f"PE_{t.upper()} (company)={pe_company[t]:.2f} outside own-year measured band "
                f"[{lo}, {hi}] — the normative anchor left the ticker's history (A9)"
            )
    # A12: growth is paid for out of retained earnings, and a shrinking
    # business is not assumed to hand back more than it earns — per leg.
    for t in TIERS:
        for leg in LEGS:
            g = inp[f"g2_{leg}_{t}"]
            pay = payout(g, m.roe[t][leg])
            if not 0.0 < pay <= 1.0 + 1e-12:
                errors.append(f"payout_{leg}_{t}={pay:.3f} outside (0, 1]")
            if g <= 0 and abs(pay - 1.0) > 1e-12:
                errors.append(f"payout_{leg}_{t}={pay:.3f} but g={g:.2%} <= 0 — cap not binding")
    # Comparison-only fields must stay out of the computation path.
    for key in ("pe_a_mid", "pe_own_mid"):
        if any(abs(inp[key] - m.pe["m"][leg]) < 1e-9 for leg in LEGS):
            errors.append(f"{key} leaked into the multiple path — it is a comparison field")
    # A4: the overseas EBITDA rows are a cross-check only.  Doubling them must
    # leave every anchor untouched.
    scaled = Model({**inp, **{f"ebitda_ovs_{t}": 2 * inp[f"ebitda_ovs_{t}"] for t in TIERS}})
    if any(abs(a - b) > 1e-9 for a, b in zip(m.band(), scaled.band())):
        errors.append("ebitda_ovs_* leaked into the anchor path — they are cross-check rows (A4)")
    if errors:
        return report(errors, "FAIL (guards)")

    # --- Step 6: anchors ----------------------------------------------------
    L, M, H = m.band()
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)

    # flat-multiple: each leg held at its own PE_M across the three tiers.
    flat = m.band({t: m.pe["m"] for t in TIERS})
    errors += ladder("flat-multiple", *flat)

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # --- Step 7: V_opt (A15) — own ruler, discounted from the realisation year --
    if inp["t_opt"] <= NUM_YEAR:
        errors.append("option year must lie after the numerator year (A15)")
    p_fields = [k for k in inp if k.startswith("p_")]
    if p_fields:
        errors.append(f"Inputs carry probability fields {p_fields} — p_k belongs in table 3 only")
    disc = (1.0 + r["ovs"]) ** (inp["t_opt"] - NUM_YEAR)
    pe_ovs_h = m.pe["h"]["ovs"]

    def v_opt_of(delta_ni: float) -> float:
        return delta_ni * 1e8 / inp["shares"] / inp["fx_hkdcny"] * pe_ovs_h / disc

    d_ni = opt_delta_ni(inp)
    v_opt = v_opt_of(d_ni)
    if d_ni <= 0:
        errors.append(f"HPI incremental NI {d_ni:.2f} <= 0 — financing cost exceeds the unit (A15, 回对话)")
    said_v = stated_v_opt(md)
    if said_v is None or abs(said_v - v_opt) > TOL:
        errors.append(f"V_opt: stated {said_v} vs recomputed {v_opt:.4f}")
    if stated_p_tiers(md) != P_TIERS:
        errors.append(f"p_L/p_M/p_H stated {stated_p_tiers(md)} vs A15 {P_TIERS}")
    opt = tuple(a + p * v_opt for a, p in zip((L, M, H), P_TIERS))
    a2, b2 = cut_points(*opt)

    # --- report --------------------------------------------------------------
    fx = inp["fx_hkdcny"]
    print(f"formula_id={FORMULA_ID}")
    print("篮子: " + "; ".join(
        f"{R_ROWS[leg]} 篮 {baskets[R_ROWS[leg]]} {basket_r(baskets[R_ROWS[leg]]):.0%}"
        f" (零增长 {1 / r[leg]:.2f}x)" for leg in LEGS))
    share = m.ni_l["ovs"] / inp["ni_group_l"]
    print(f"分腿净资产(FY2025 末, 归母): 海外 {m.equity['ovs']:.2f} 国内 {m.equity['dom']:.2f} "
          f"未分配 {inp['equity_unalloc']:.2f} → 合计 {rebuilt:.2f} vs 归母权益 {inp['equity_group']} ✓")
    print(f"FY2025 分部归母: 海外 {m.ni_l['ovs']:.2f} 国内 {m.ni_l['dom']:.2f} (合计 {leg_sum:.2f}; "
          f"税率 {inp['tax_eff']:.2%}; NCI 损益 海外 {nci_profit_ovs(inp, inp['nci_equity_ovs']):.2f} / "
          f"国内 {inp['nci_profit'] - nci_profit_ovs(inp, inp['nci_equity_ovs']):.2f}) → 海外份额 {share:.1%}")
    print(f"{'档':<3}{'集团归母':>10}{'海外NI':>9}{'国内NI':>9}{'ROE_ovs':>9}{'域':>6}{'ROE_dom':>9}{'域':>6}"
          f"{'PE_dom':>8}{'PE_ovs':>8}{'派息ovs':>9}{'公司PE':>8}{'CNY价值':>10}{'锚点HKD':>10}")
    for t in TIERS:
        print(f"{t.upper():<3}{inp[f'ni_group_{t}']:10.2f}{m.ni[t]['ovs']:9.2f}{m.ni[t]['dom']:9.2f}"
              f"{m.roe[t]['ovs']:9.2%}{domain(m.roe[t]['ovs'], r['ovs']):>6}"
              f"{m.roe[t]['dom']:9.2%}{domain(m.roe[t]['dom'], r['dom']):>6}"
              f"{m.pe[t]['dom']:8.2f}{m.pe[t]['ovs']:8.2f}"
              f"{payout(inp[f'g2_ovs_{t}'], m.roe[t]['ovs']):9.1%}{pe_company[t]:8.2f}"
              f"{m.value_cny(t):10.2f}{m.anchor(t):10.2f}")
    print("海外 EBITDA 交叉（不进锚点）: " + " / ".join(
        f"{t.upper()} {inp[f'ebitda_ovs_{t}']:.2f} → 隐含归母转化率 {m.ni[t]['ovs'] / inp[f'ebitda_ovs_{t}']:.3f}"
        for t in TIERS))
    alt_l = inp["eps_consensus_low"] * inp["shares"] / 1e8
    print(f"L 分子 {inp['ni_group_l']:.2f} 亿 vs 共识下沿隐含 {alt_l:.2f} 亿 — "
          f"L {'低于' if inp['ni_group_l'] < alt_l else '高于'}街上最低预期")
    print(f"公司口径 PE {pe_company['l']:.2f}/{pe_company['m']:.2f}/{pe_company['h']:.2f} "
          f"落在 own-year 实测带 [{lo}, {hi}] 内 (p50={inp['pe_own_mid']:g}) ✓ — ③ 不出带")
    print(f"flat-multiple @PE_M (国内 {m.pe['m']['dom']:.2f}× / 海外 {m.pe['m']['ovs']:.2f}×): "
          f"L={flat[0]:.2f} M={flat[1]:.2f} H={flat[2]:.2f} — 带宽 {(flat[2] - flat[0]) / (2 * flat[1]):.0%}")
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.1%} V_opt/M={v_opt / M:.1%}")
    margin = inp["pretax_ovs"] * (1.0 - inp["tax_eff"]) / inp["rev_ovs"]
    fxu = inp["fx_usdcny"]
    print(f"V_opt={v_opt:.2f} (HPI {inp['opt_rev_usd']:g} 亿美元 x {fxu:g} = {inp['opt_rev_usd'] * fxu:.2f} 亿 x 海外腿利润率 "
          f"{margin:.2%} x {inp['opt_stake']:g} = {inp['opt_rev_usd'] * fxu * margin * inp['opt_stake']:.2f} − 对价 "
          f"{inp['opt_price_usd'] * fxu:.2f} 亿 x {inp['int_cost']:.2%} x (1−t) = "
          f"{inp['opt_price_usd'] * fxu * inp['int_cost'] * (1 - inp['tax_eff']):.2f} → ΔNI {d_ni:.2f} 亿 = "
          f"{d_ni * 1e8 / inp['shares'] / inp['fx_hkdcny']:.4f} HKD/股 x PE_ovs_H {pe_ovs_h:.2f} / "
          f"{1 + r['ovs']:.2f}^{int(inp['t_opt']) - NUM_YEAR})")
    print(f"zone+V (p {P_TIERS[0]:g}/{P_TIERS[1]:g}/{P_TIERS[2]:g}): {opt[0]:.2f} / {opt[1]:.2f} / {opt[2]:.2f} "
          f"A'={a2:.2f} B'={b2:.2f}")
    infer_margin = inp["ni_group_m"] * (m.ni_l["ovs"] / inp["ni_group_l"]) / (2 * H1_OVS_REV)
    print(f"敏感区 V_opt: 债务成本 5% → {v_opt_of(opt_delta_ni(inp, int_cost=0.05)):.2f}; "
          f"单位利润率 {infer_margin:.1%}（2026 共识 mean × 份额 ÷ H1 海外收入 85.42 × 2）→ "
          f"{v_opt_of(opt_delta_ni(inp, margin=infer_margin)):.2f}")
    num_l = inp["ni_group_l"] / inp["ni_group_m"]
    num_h = inp["ni_group_h"] / inp["ni_group_m"]
    print(f"分子比 L/M={num_l:.2f} H/M={num_h:.2f} | 公司口径倍数比 "
          f"L/M={pe_company['l'] / pe_company['m']:.2f} H/M={pe_company['h'] / pe_company['m']:.2f}")
    ni = m.ni
    print(f"分腿价值比 海外 L/M={ni['l']['ovs'] * m.pe['l']['ovs'] / (ni['m']['ovs'] * m.pe['m']['ovs']):.2f} "
          f"H/M={ni['h']['ovs'] * m.pe['h']['ovs'] / (ni['m']['ovs'] * m.pe['m']['ovs']):.2f} | "
          f"国内 L/M={ni['l']['dom'] * m.pe['l']['dom'] / (ni['m']['dom'] * m.pe['m']['dom']):.2f} "
          f"H/M={ni['h']['dom'] * m.pe['h']['dom'] / (ni['m']['dom'] * m.pe['m']['dom']):.2f}")

    # Disclosure rows (never max()'d into the deck).
    print(f"地板（只披露）: BPS {inp['bps']:.2f} CNY = {inp['bps'] / fx:.2f} HKD; "
          f"锚点隐含 PB {L * fx / inp['bps']:.2f} / {M * fx / inp['bps']:.2f} / {H * fx / inp['bps']:.2f}")
    one_over_r = {t: {"dom": m.pe[t]["dom"], "ovs": 1 / r["ovs"]} for t in TIERS}
    alt = m.band(one_over_r)
    print(f"海外腿按 1/r（不给轴 credit）: {alt[0]:.2f} / {alt[1]:.2f} / {alt[2]:.2f}")
    naive = m.band({t: {leg: 1 / (r[leg] - inp[f"g2_{leg}_{t}"]) for leg in LEGS} for t in TIERS})
    print(f"若按 100% 派息的 1/(r-g)：{naive[0]:.2f} / {naive[1]:.2f} / {naive[2]:.2f}"
          f" — H 档高估 {naive[2] / H - 1:.0%}（留存成本，A12）")
    for dg, label in ((0.01, "+1pp"), (-0.01, "−1pp")):
        band = m.band({t: {"dom": m.pe[t]["dom"],
                           "ovs": leg_pe(inp, "ovs", t, m.roe[t]["ovs"], g_override=inp[f"g2_ovs_{t}"] + dg)}
                       for t in TIERS})
        print(f"敏感区 g2_ovs_* {label}: {band[0]:.2f} / {band[1]:.2f} / {band[2]:.2f}")
    for dg, label in ((0.01, "+1pp"), (-0.01, "−1pp")):
        band = m.band({t: {"ovs": m.pe[t]["ovs"],
                           "dom": leg_pe(inp, "dom", t, m.roe[t]["dom"], g_override=inp[f"g2_dom_{t}"] + dg)}
                       for t in TIERS})
        print(f"敏感区 g2_dom_* {label}: {band[0]:.2f} / {band[1]:.2f} / {band[2]:.2f}")
    for dr, label in ((-0.005, "12.5%"), (0.005, "13.5%"), (-0.02, "11%（篮 5 读数，仅示）")):
        band = m.band({t: {leg: leg_pe(inp, leg, t, m.roe[t][leg], r_shift=dr) for leg in LEGS} for t in TIERS})
        print(f"敏感区 两腿 r {label}: {band[0]:.2f} / {band[1]:.2f} / {band[2]:.2f}")
    # A18: the NCI allocation is the largest construction-side degree of
    # freedom left.  The base subtracts only the disclosed Lafarge Africa NCI
    # from the overseas segment; the alternatives move the rest across.
    print("敏感区 NCI 分配（A18；海外 NCI 权益 → 海外归母净资产 / 份额 → L/M/H）:")
    for label, nci_ovs in (("基准：仅 Lafarge 7.06", inp["nci_equity_ovs"]),
                           ("一半在海外", inp["nci_equity"] / 2),
                           ("全在海外", inp["nci_equity"]),
                           ("全在国内", 0.0)):
        alt_m = Model(inp, nci_ovs)
        band = alt_m.band()
        s = alt_m.ni_l["ovs"] / (alt_m.ni_l["ovs"] + alt_m.ni_l["dom"])
        print(f"  {label:<16} 海外净资产 {alt_m.equity['ovs']:7.2f} 份额 {s:5.1%} "
              f"ROE_ovs M {alt_m.roe['m']['ovs']:5.1%} → {band[0]:.2f} / {band[1]:.2f} / {band[2]:.2f}")

    # What the street and book value each require in r terms (属性 B): a
    # parallel shift δ of both baskets that makes the M-tier SOTP equal the
    # coordinate, plus the single-segment g=0 approximation E_M / P.
    eps_m_cny = inp["ni_group_m"] * 1e8 / inp["shares"]
    coords = [("账面 PB=1.0", inp["bps"])]
    if "tp_sellside_h" in inp:   # disclosure-only row; absent is fine
        coords.append(("卖方 H 股 TP", inp["tp_sellside_h"] * fx))
    for label, price_cny in coords:
        delta = m.implied_r_shift(price_cny)
        print(f"  {label:<10} 隐含 PE={price_cny / eps_m_cny:5.2f} → δ={delta:+.2%} "
              f"(两腿 r {r['dom'] + delta:.1%}) | g=0 近似 E_M/P={eps_m_cny / price_cny:.1%}")
    la, ma, ha = L * fx, M * fx, H * fx
    print(f"A股对照(CNY): L={la:.2f} M={ma:.2f} H={ha:.2f} A={(la + ma) / 2:.2f} B={(ma + ha) / 2:.2f}")

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): both legs'
    # basket r (r_dom, r_ovs) move 1:1; per-leg g, ROE and numerators stay put.
    # Disclosure only — the anchors above are the 中枢 column.
    def band_rf(dr: float) -> tuple[float, float, float]:
        return tuple(m.band({t: {leg: leg_pe(inp, leg, t, m.roe[t][leg], r_shift=dr) for leg in LEGS}  # type: ignore[return-value]
                             for t in TIERS}))

    rf = rf_block(LISTING_CCY, {R_ROWS[leg]: r[leg] for leg in LEGS}, band_rf)
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    # Only a clean run writes, so a FAIL never feeds the daily digest.
    if not errors:
        write_rf_readings("6655.HK", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
