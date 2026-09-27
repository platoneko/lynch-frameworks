#!/usr/bin/env python3
"""1072.HK (Dongfang Electric) valuation eval.

frameworks/1072.HK.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries
no current price (AGENTS.md「现价 — 禁写契约」), so nothing here computes a zone
or a market-implied reading — the digest and the app zone on live quotes.

formula_id: dec_three_leg_plus_g50_g200_vopt_perpetual_g_hk_anchored_v6

v6 (2026-09-14, 裁决顺序 walk): (1) L is FY2025, the latest complete year, not
the FY2024 trough — a trough numerator paired with a steady g2 counts the cycle
twice (valuation-rules「谷底档」); the trough only sets the deep_discount
pressure coordinate (`ni_trough_fy2024` x 1/r).  (2) Each incumbent leg carries
ONE steady g2 shared by all tiers (coal -4% / wings +3% / legacy gas 0%): a
cyclical's tiers separate on the numerator, and the v5 tiered g produced a
same-direction 8.0/9.0/10.1 band, which 裁决顺序 ⑤ forbids.  Multiples are now
~flat (9.08/9.02/8.89, weight mechanics only).  (3) The FY2027 A-share
consensus (n=3, with range) is a ② question left to the user (A19) — H already
sits on its mean.

G50 + G200 are V_opt (A2e-7): current profit ≈ 0 and units are unverified, so
neither enters the base L/M/H. 表3 recovers the pre-split anchors via
p_k = (0, G50_M / (G50_H+G200_H), 1) — G200 is 0 in the M world (2027 下线).

Main ruler: split the NUMERATOR by leg, then let each tier name a PERPETUAL
GROWTH RATE per leg and read the multiple off Gordon.

  E   = jv_ni * jv_stake        equity income of the 49% Mitsubishi associate
  R   = NI - E                  residual group profit
  NI_C = E + R * gpw_C,  NI_A = R * gpw_A,  NI_B = R * gpw_B
  w_i = NI_i / NI               leg profit weight
  g   = sum(w_i * g_i)          blended perpetual growth
  PE  = (1 - g/ROE) / (r - g),  r = basket r (all three legs 篮 4 龙头制造,
                                10%, A20)  ->  a no-growth business is worth 10x

Assign what has a known home, then spread the rest.  The one piece of profit
with a documented leg is 三菱重工东方燃气轮机（广州）— 49%, equity-accounted, so
the M701F hot-parts and LTSA service margin lands in 投资收益 and never touches
the 气电 segment's revenue or cost.  Ignoring it understates leg C; folding it
into a gross-profit weight numerator would mix pre-tax gross profit with
after-tax net income in one ratio.  Assigning it and spreading the residual on
measured segment gross profit (A2/A3/A14) is the only dimensionally clean read.
`variant_band` re-prices the two rejected treatments every run and prints all
three bands side by side — the moment they diverge materially, the treatment
has stopped being a bookkeeping choice.

Two things make this ticker different from the other Gordon mounts.

First, the residual weights are not estimated — they are the「营业收入、营业成本
按板块」note, verbatim, for each tier's own period.  That note carries the whole
finding, and the off-balance-sheet pool sharpens rather than softens it: on
gross profit leg C is flat at 4.80% / 4.78% / 4.58%, and on the profit weight
that includes the JV it is *falling* — 10.52% (FY2024) -> 7.29% (FY2025) ->
7.37% (TTM) -> 6.76% (H1'26 annualised), because the associate's net income
halved while DEC's own grew.  `leg_c_weight_cap` guards the claim, but only on
the M tier (A15): L and H are scenario tiers whose leg mix swings for reasons
that are not about how big the leg structurally is — FY2024 pairs DEC's own
trough with the associate's peak and prints 10.53% for that reason alone.

Second, ROE(TTM) = 10.05% sits on top of the basket r = 10%.  In that regime growth is
value-neutral, the multiple is pinned near 1/r whatever g does, and inverting a
price for g returns a number rather than a reading — `implied_g` flags the
street's target price as ill-conditioned.  The framework therefore rests on the
numerator and the leg weights, and §3 states the g/r ambiguity both ways (A9).

The multiples are NOT quantiles of the ticker's own historical PE: a realised PE
carries whatever growth the market was pricing that year.  Per AGENTS.md
「永续增长口径」this overrides skill A2e-2b.  The measured H-share band survives
as a fence in `pe_own_lo/hi` — a generated multiple outside [7.04, 11.97] means
the normative anchor has walked past any price this stock has printed, and the
construction goes back to the conversation.

Run:  python3 frameworks/eval/1072.HK.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
from lib.axes import AXIS_SOUTHBOUND  # noqa: E402
from lib.gordon import check_g_cap, check_r, implied_g, payout, perpetual_pe  # noqa: E402
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402

# rf_report / bands_io import eval.lib.*, so the repo root must be importable too.
sys.path.append(str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORKS = Path(__file__).resolve().parents[2] / "frameworks"
FRAMEWORK = FRAMEWORKS / "1072.HK.md"
FORMULA_ID = "dec_three_leg_plus_g50_g200_vopt_perpetual_g_hk_anchored_v6"
LISTING_CCY = "HKD"

TIERS = ("l", "m", "h")
LEGS = ("a", "b", "c")
LEG_CN = {"a": "周期装备", "b": "两翼", "c": "燃机"}

REQUIRED = (
    ["ni_cons_fy27_lo", "ni_cons_fy27_mean", "ni_cons_fy27_hi", "shares", "bps", "fx_hkdcny", "r_perp", "equity",
     "net_cash", "tp_street", "leg_c_weight_cap", "ni_trough_fy2024",
     "pe_own_lo", "pe_own_hi", "pe_own_mid", "pe_own_a_mid", "jv_stake",
     "g50_price", "g50_k", "r_disc", "usdcny", "g50_mw",
     "g50_usdkw_lo", "g50_usdkw_hi",
     "g200_mw", "g200_units_l", "g200_units_m", "g200_units_h"]
    + [f"jv_ni_{t}" for t in TIERS]
    + [f"ni_{t}" for t in TIERS]
    + [f"gp_{leg}_{t}" for leg in LEGS for t in TIERS]
    + [f"g2_{leg}_{t}" for leg in LEGS for t in TIERS]
    + [f"g50_{f}_{t}" for f in ("units", "gm", "g", "lag") for t in TIERS]
)


def nondecreasing(name: str, *values: float) -> list[str]:
    """Assert a non-decreasing ladder.

    Several ladders here legitimately repeat a value: the mature gas leg's
    perpetual g is 0 at both L and M, and the G50 option leg's g is 0 until it
    has capacity to grow into.  A strict ladder would force a fake difference.
    """
    if all(a <= b + 1e-12 for a, b in zip(values, values[1:])):
        return []
    return [f"{name} non-decreasing ladder violated: "
            f"{' <= '.join(f'{v:g}' for v in values)} is false"]


def gross_weights(inp: dict[str, float], tag: str) -> dict[str, float]:
    """Leg share of that tier's own measured segment gross profit — the key the
    residual profit is spread on, not the ruler's leg weight."""
    gp = {leg: inp[f"gp_{leg}_{tag}"] for leg in LEGS}
    total = sum(gp.values())
    return {leg: v / total for leg, v in gp.items()}


def weights(inp: dict[str, float], tag: str) -> dict[str, float]:
    """Leg profit weight under the ruler: assign the JV, spread the residual."""
    return variant_weights(inp, tag, "assign")


def blended_g(inp: dict[str, float], tag: str) -> float:
    w = weights(inp, tag)
    return sum(w[leg] * inp[f"g2_{leg}_{tag}"] for leg in LEGS)


def forward_roe(inp: dict[str, float], tag: str) -> float:
    return inp[f"ni_{tag}"] / inp["equity"]


def multiple(inp: dict[str, float], tag: str) -> float:
    return perpetual_pe(blended_g(inp, tag), forward_roe(inp, tag), inp["r_perp"])


def g50_leg(inp: dict[str, float], tag: str) -> tuple[float, float, float]:
    """(net income, multiple, discounted value) of the domestic-G50 option leg.

    Additive, not a weight.  The leg earns ~nothing today — the first complete
    unit shipped 2026-08-28 — so a profit weight would round it to zero and the
    story would end up living in leg C's growth rate, which skill A2e-2c-ex
    forbids ("有新业务值钱 → 做成一条腿（分子）").  Same shape as 000338.SZ's
    M-series leg: units x price x margin, and zero at L.

    Only this leg is discounted.  `perpetual_pe` already prices next-period
    earnings, so a tier whose earnings start exactly next period needs no
    discount; H's 25 units/yr is end-2027 capacity, first full year FY2028,
    one period later — hence g50_lag_h = 1 (A17).
    """
    ni = inp[f"g50_units_{tag}"] * inp["g50_price"] * inp[f"g50_gm_{tag}"] * inp["g50_k"]
    if ni <= 0:
        return 0.0, 0.0, 0.0
    pe = perpetual_pe(inp[f"g50_g_{tag}"], forward_roe(inp, tag), inp["r_perp"])
    return ni, pe, ni * pe / (1.0 + inp["r_disc"]) ** inp[f"g50_lag_{tag}"]


def g50_usd_per_kw(inp: dict[str, float]) -> float:
    """Unit price translated to the global heavy-frame quoting convention."""
    return inp["g50_price"] * 1e8 / inp["g50_mw"] / inp["usdcny"] / 1e3


def to_hkd(inp: dict[str, float], cny: float) -> float:
    """CNY market value (亿元) -> HKD per share."""
    return cny * 1e8 / inp["shares"] / inp["fx_hkdcny"]


def incumbent_cny(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    """存量三腿 CNY 市值（亿元）。G50 不进底牌（A2e-7）。"""
    pe = flat_pe if flat_pe is not None else multiple(inp, tag)
    return inp[f"ni_{tag}"] * pe


def anchor(inp: dict[str, float], tag: str, flat_pe: float | None = None) -> float:
    """底牌 HKD/股 = 存量三腿；G50 计 0."""
    return to_hkd(inp, incumbent_cny(inp, tag, flat_pe))


def g50_ps(inp: dict[str, float], tag: str) -> float:
    """G50 腿 HKD/股（未乘 p_k）。"""
    return to_hkd(inp, g50_leg(inp, tag)[2])


def g200_price(inp: dict[str, float]) -> float:
    """亿元/台 = G50 单价按 MW 放大，同一 $/kW。"""
    return inp["g50_price"] * (inp["g200_mw"] / inp["g50_mw"])


def g200_leg(inp: dict[str, float], tag: str) -> tuple[float, float, float]:
    """G200 option: same $/kW and H-tier gm/g/lag as G50; units 0 at L and M.

    2027 下线, not a current run-rate — M-world credit is 0.  H-tier 3 units
    come from the same UBS sentence that set g50_units_h = 25.
    """
    units = inp[f"g200_units_{tag}"]
    if units <= 0:
        return 0.0, 0.0, 0.0
    ni = units * g200_price(inp) * inp[f"g50_gm_{tag}"] * inp["g50_k"]
    pe = perpetual_pe(inp[f"g50_g_{tag}"], forward_roe(inp, tag), inp["r_perp"])
    return ni, pe, ni * pe / (1.0 + inp["r_disc"]) ** inp[f"g50_lag_{tag}"]


def g200_ps(inp: dict[str, float], tag: str) -> float:
    return to_hkd(inp, g200_leg(inp, tag)[2])


def option_mv(inp: dict[str, float], tag: str) -> float:
    """G50 + G200 CNY 市值（亿元）。"""
    return g50_leg(inp, tag)[2] + g200_leg(inp, tag)[2]


def variant_weights(inp: dict[str, float], tag: str, mode: str) -> dict[str, float]:
    """Leg weights under the three candidate treatments of the JV (A14).

    The gas-turbine leg's fattest profit pool — M701F hot parts and the LTSA
    service contracts — sits in a 49%-held associate carried at equity, so it
    lands in 投资收益 and never touches the 气电 segment's revenue or cost.
    Whether it belongs in leg C's weight is an open construction question; all
    three answers are priced here so the choice is made against numbers.

      base    leg weights are segment gross profit, full stop (rejected: the
              filings show the JV's profit exists and belongs to leg C)
      assign  the JV's equity income goes to leg C, the rest of group NI is
              split on gross-profit weights (THE RULER, A14)
      addw    the JV's equity income is added to leg C's weight numerator
              (rejected: mixes pre-tax gross profit with after-tax net income)
    """
    w = gross_weights(inp, tag)
    if mode == "base":
        return w
    equity_income = inp[f"jv_ni_{tag}"] * inp["jv_stake"]
    if mode == "assign":
        residual = inp[f"ni_{tag}"] - equity_income
        legs = {
            "a": residual * w["a"],
            "b": residual * w["b"],
            "c": equity_income + residual * w["c"],
        }
    elif mode == "addw":
        legs = {leg: inp[f"gp_{leg}_{tag}"] for leg in LEGS}
        legs["c"] += equity_income
    else:
        raise ValueError(f"unknown variant: {mode}")
    total = sum(legs.values())
    return {leg: v / total for leg, v in legs.items()}


def variant_band(inp: dict[str, float], mode: str) -> tuple[list[float], list[float]]:
    """(anchors, leg-C weights) for one JV treatment."""
    anchors, wc = [], []
    for t in TIERS:
        w = variant_weights(inp, t, mode)
        g = sum(w[leg] * inp[f"g2_{leg}_{t}"] for leg in LEGS)
        pe = perpetual_pe(g, forward_roe(inp, t), inp["r_perp"])
        anchors.append(to_hkd(inp, inp[f"ni_{t}"] * pe))
        wc.append(w["c"])
    return anchors, wc


def check_southbound_mount(md: str) -> list[str]:
    """Axis §3 rule 3: a mounted ticker reports both the H and the A-share bands.

    The southbound axis is a weak axis — it locks no numerator and, since
    AGENTS.md「永续增长口径」took multiples away from historical quantiles, no
    multiple either.  What it still locks is the reporting contract that makes
    its own §4 cross-ticker direction check possible, so that is what is
    enforced here, plus the mount being declared on the axis side.  The live
    H/A is a function of today's two prices and no longer lives in the doc; the
    axis's cross-ticker direction check reads its own dated series (§1).
    """
    errors: list[str] = []
    if not AXIS_SOUTHBOUND.exists():
        return [f"axis file missing: {AXIS_SOUTHBOUND.name}"]
    axis = AXIS_SOUTHBOUND.read_text(encoding="utf-8")
    if "1072.HK" not in axis:
        errors.append(
            "1072.HK is not declared on _AXIS.southbound-repricing.md — "
            "a mount has to exist on both sides"
        )
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

    r = inp["r_perp"]
    lo, hi = inp["pe_own_lo"], inp["pe_own_hi"]

    # --- Step 0: r is a basket value (valuation-rules「§r 篮子」) -------------
    # The three incumbent legs share one r, so the blended-g Gordon is legal
    # (A20); the framework names the basket on the r_perp row and r must be
    # that basket's value.  r_disc is the option leg's discount rate and has to
    # equal r_perp (A17) — it carries no basket tag of its own.
    baskets = parse_baskets(md)
    if "r_perp" not in baskets:
        errors.append("r_perp row names no 篮 N in its source cell (A20)")
    errors += check_r(r, "r_perp", baskets.get("r_perp"))
    errors += check_r(inp["r_disc"], "r_disc")
    if abs(inp["r_disc"] - r) > 1e-9:
        errors.append(f"r_disc={inp['r_disc']} must equal r_perp={r} (A17)")
    if errors:
        return report(errors, "FAIL (basket r)")

    # --- Step 1: numerators and leg weights ---------------------------------
    errors += ladder("ni", *(inp[f"ni_{t}"] for t in TIERS))
    if inp["equity"] <= 0:
        errors.append(f"equity={inp['equity']} must be positive")
    for t in TIERS:
        total = sum(inp[f"gp_{leg}_{t}"] for leg in LEGS)
        if total <= 0:
            errors.append(f"tier {t.upper()}: segment gross profit sums to {total}")
    if errors:
        return report(errors, "FAIL (numerators)")

    w = {t: weights(inp, t) for t in TIERS}

    # --- Step 2: growth 口径 and convergence ---------------------------------
    # 裁决顺序 ⑤ (cyclical → flat or reversed) + valuation-rules「分子与 g 同世界」:
    # every incumbent leg carries ONE steady g2 shared by all three tiers; the
    # tiers differ in the numerator (FY2025 / TTM / 2026H1x2), not in g.  The
    # blend still moves a little with each tier's own leg weights — that is
    # weight mechanics, not a growth ladder, so it is printed, not laddered.
    for leg in LEGS:
        vals = [inp[f"g2_{leg}_{t}"] for t in TIERS]
        if max(vals) - min(vals) > 1e-12:
            errors.append(
                f"g2_{leg} ({LEG_CN[leg]}) differs across tiers {vals} — a cyclical's "
                "tiers separate on the numerator; a tiered g re-prices the cycle (裁决顺序 ⑤)"
            )
    for field in ("units", "gm", "g"):
        errors += nondecreasing(f"g50_{field}", *(inp[f"g50_{field}_{t}"] for t in TIERS))
    g = {t: blended_g(inp, t) for t in TIERS}
    for t in TIERS:
        if r - g[t] <= 0:
            errors.append(f"g_{t}={g[t]:.4f} >= r={r} — perpetuity diverges")
    # 永续上限 g_cap(r) = min(6%, r − 4%): every named perpetual g — the three
    # incumbent legs (`g2_*`, visible to calibration.py), the option leg, and
    # the blend.
    for leg in LEGS:
        for t in TIERS:
            errors += check_g_cap(inp[f"g2_{leg}_{t}"], r, f"g2_{leg}_{t}")
    for t in TIERS:
        errors += check_g_cap(inp[f"g50_g_{t}"], r, f"g50_g_{t}")
        errors += check_g_cap(g[t], r, f"g_blended_{t}")
    if errors:
        return report(errors, "FAIL (ladders/convergence)")

    # --- Step 3: normative guards -------------------------------------------
    # A1: L is the latest complete year, a realised steady level — not the
    # FY2024 trough.  A trough numerator paired with a steady g2 counts the
    # cycle twice (valuation-rules「谷底档」); the trough only sets the
    # deep_discount pressure coordinate.
    if inp["ni_l"] <= inp["ni_trough_fy2024"]:
        errors.append(
            f"ni_l {inp['ni_l']} <= FY2024 trough {inp['ni_trough_fy2024']} — a trough numerator "
            "cannot carry a steady g2 (valuation-rules「谷底档」); L is the latest complete year"
        )
    # A8: generated multiples must stay inside prices this stock has printed.
    pe = {t: multiple(inp, t) for t in TIERS}
    for t in TIERS:
        if not (lo - 1e-9 <= pe[t] <= hi + 1e-9):
            errors.append(
                f"PE_{t.upper()}={pe[t]:.2f} outside H-share own-year band "
                f"[{lo}, {hi}] — the normative anchor left the ticker's history (A8)"
            )
    # A12: growth is paid for out of retained earnings; a shrinking business is
    # not assumed to hand back more than it earns.
    for t in TIERS:
        pay = payout(g[t], forward_roe(inp, t))
        if not 0.0 < pay <= 1.0 + 1e-12:
            errors.append(f"payout_{t}={pay:.3f} outside (0, 1]")
        if g[t] <= 0 and abs(pay - 1.0) > 1e-12:
            errors.append(f"payout_{t}={pay:.3f} but g={g[t]:.2%} <= 0 — cap not binding")
    # §1 属性 F / A15: the gas-turbine leg is an option leg *because* it is
    # small.  Only the M tier can carry that structural claim — it is the tier
    # that states current known facts long-run.  L and H are scenario tiers, and
    # L in particular pairs DEC's own trough year with the associate's peak, so
    # its leg mix says something about FY2024's arithmetic, not about the leg.
    cap = inp["leg_c_weight_cap"]
    if w["m"]["c"] >= cap:
        errors.append(
            f"leg C weight {w['m']['c']:.2%} at the M tier >= cap {cap:.0%} — "
            "the gas-turbine leg is no longer an option leg; revisit lynch_primary"
        )
    over = [t.upper() for t in ("l", "h") if w[t]["c"] >= cap]
    # Leg C must remain the smallest leg at M, or the three-leg split is mislabelled.
    if not (w["m"]["c"] < w["m"]["a"] and w["m"]["c"] < w["m"]["b"]):
        errors.append("M tier: leg C is not the smallest leg")
    # A16: the option leg must vanish at L, or L stops being "the measured bad".
    if inp["g50_units_l"] != 0:
        errors.append(
            f"g50_units_l={inp['g50_units_l']} — the option leg MUST be zero at L"
        )
    if inp["g200_units_l"] != 0 or inp["g200_units_m"] != 0:
        errors.append(
            f"g200_units L/M = {inp['g200_units_l']:.0f}/{inp['g200_units_m']:.0f} "
            "— G200 2027 下线, MUST be zero until H"
        )
    if abs(inp["g200_mw"] / inp["g50_mw"] - 4.0) > 1e-9:
        errors.append(
            f"g200_mw/g50_mw = {inp['g200_mw'] / inp['g50_mw']:.3f} — "
            "the name is 200 MW vs 50 MW, ratio must be 4"
        )
    # A16: the unit price has to be comparable to what heavy frames actually
    # quote for.  Citi's CNY 2.0e8 per 50 MW is $596/kW against GEV's ~$600/kW
    # for 2027; a price outside the global cluster means the two口径 are not the
    # same thing and the leg is being fed a number from a different scope.
    usdkw = g50_usd_per_kw(inp)
    if not (inp["g50_usdkw_lo"] <= usdkw <= inp["g50_usdkw_hi"]):
        errors.append(
            f"g50 unit price = ${usdkw:.0f}/kW outside the global heavy-frame "
            f"cluster [{inp['g50_usdkw_lo']:.0f}, {inp['g50_usdkw_hi']:.0f}] — "
            "the price scope is not comparable (A16)"
        )
    # The option leg must not push the whole-company multiple outside anything
    # this stock has printed.  The incumbent legs are fenced above; this fences
    # the sum, which is what a reader actually compares to a market PE.
    # G50-only implied multiple must stay in the printed band.  G200 is a 2027
    # machine that is not in the 2019-2025 own-year PE history, so the combined
    # 表3 multiple may overshoot pe_own_hi — printed, not a fail (A18).
    for t in TIERS:
        implied_g50 = (inp[f"ni_{t}"] * pe[t] + g50_leg(inp, t)[2]) / inp[f"ni_{t}"]
        if not (lo - 1e-9 <= implied_g50 <= hi + 1e-9):
            errors.append(
                f"G50-only implied multiple at {t.upper()} = {implied_g50:.2f} "
                f"outside own-year band [{lo}, {hi}]"
            )
    # Comparison-only fields must not have leaked into the multiple path.
    for key in ("pe_own_mid", "pe_own_a_mid"):
        if abs(inp[key] - pe["m"]) < 1e-9:
            errors.append(f"{key} leaked into the multiple path — it is a comparison field")
    if errors:
        return report(errors, "FAIL (guards)")

    errors += check_southbound_mount(md)
    if errors:
        return report(errors, "FAIL (shared axis)")

    # --- Step 4: anchors -----------------------------------------------------
    L, M, H = (anchor(inp, t) for t in TIERS)
    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L:.2f}, {M:.2f}, {H:.2f}", file=sys.stderr)
        return 1
    A, B = cut_points(L, M, H)
    v_g50 = g50_ps(inp, "h")
    v_g200 = g200_ps(inp, "h")
    v_opt = v_g50 + v_g200
    p_m = (g50_ps(inp, "m") / v_opt) if v_opt else 0.0
    p_k = (0.0, p_m, 1.0)
    adj_band = [base + pk * v_opt for base, pk in zip((L, M, H), p_k)]

    flat = {t: anchor(inp, t, flat_pe=pe["m"]) for t in TIERS}
    errors += ladder("flat-multiple", *(flat[t] for t in TIERS))
    errors += ladder("base", L, M, H)
    if abs(adj_band[0] - L) > 1e-9:
        errors.append(f"p leaked into the base: 表3 L {adj_band[0]:.4f} != {L:.4f}")
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs (A2e-7a): {leaked}")

    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B})

    # 裁决顺序 ②-b (valuation-rules): own realised numerators may stand in for
    # the FY2027 consensus three points only while the consensus mean sits inside
    # [ni_m, ni_h] and M is within 20% of it (A19).
    if not (inp["ni_m"] <= inp["ni_cons_fy27_mean"] <= inp["ni_h"]):
        errors.append(f"②-b: consensus FY27 mean {inp['ni_cons_fy27_mean']} outside [ni_m {inp['ni_m']}, ni_h {inp['ni_h']}]")
    cons_dev = inp["ni_m"] / inp["ni_cons_fy27_mean"] - 1.0
    if abs(cons_dev) > 0.20 and "②-b" not in md:
        errors.append(f"②-b: M deviates {cons_dev:+.1%} from consensus with no ②-b named-variable row")
    print(f"②-b: consensus FY27 NI {inp['ni_cons_fy27_lo']}/{inp['ni_cons_fy27_mean']}/{inp['ni_cons_fy27_hi']} vs tiers {inp['ni_l']}/{inp['ni_m']}/{inp['ni_h']}; M dev {cons_dev:+.1%}")

    # --- report --------------------------------------------------------------
    fx = inp["fx_hkdcny"]
    print(f"formula_id={FORMULA_ID}  (r={r:.0%} 篮 {baskets['r_perp']}, 零增长={1 / r:.1f}x)")
    print(f"{'档':<3}{'归母(亿)':>10}{'w_A':>8}{'w_B':>8}{'w_C':>8}"
          f"{'g':>9}{'ROE':>8}{'派息':>8}{'PE':>8}{'锚点HKD':>10}{'A股CNY':>9}")
    for t in TIERS:
        roe = forward_roe(inp, t)
        print(f"{t.upper():<3}{inp[f'ni_{t}']:10.2f}{w[t]['a']:8.2%}{w[t]['b']:8.2%}"
              f"{w[t]['c']:8.2%}{g[t]:9.2%}{roe:8.2%}{payout(g[t], roe):8.1%}"
              f"{pe[t]:8.2f}{anchor(inp, t):10.2f}{anchor(inp, t) * fx:9.2f}")

    print(f"腿 D 自主 G50（加总式期权腿，L 档归零）— 单价 {inp['g50_price']}亿/台 / "
          f"{inp['g50_mw']:.0f}MW = ${g50_usd_per_kw(inp):.0f}/kW "
          f"（护栏 [{inp['g50_usdkw_lo']:.0f}, {inp['g50_usdkw_hi']:.0f}]，GEV 2027 报价 ~$600）✓")
    print(f"{'档':<3}{'台数':>6}{'毛利率':>8}{'G50归母':>9}{'g':>7}{'腿D PE':>8}"
          f"{'折现年':>7}{'腿D市值':>9}{'合计市值':>10}{'整体倍数':>9}")
    for t in TIERS:
        ni50, pe50, mv50 = g50_leg(inp, t)
        tot = inp[f"ni_{t}"] * pe[t] + option_mv(inp, t)
        print(f"{t.upper():<3}{inp[f'g50_units_{t}']:6.0f}{inp[f'g50_gm_{t}']:8.0%}{ni50:9.2f}"
              f"{inp[f'g50_g_{t}']:7.0%}{pe50:8.2f}{inp[f'g50_lag_{t}']:7.0f}{mv50:9.1f}"
              f"{tot:10.1f}{tot / inp[f'ni_{t}']:9.2f}")
    ni200, pe200, mv200 = g200_leg(inp, "h")
    print(f"G200  H {inp['g200_units_h']:.0f} 台 × {g200_price(inp):.1f}亿/台 "
          f"({inp['g200_mw']:.0f}MW, 同 ${g50_usd_per_kw(inp):.0f}/kW)  "
          f"NI {ni200:.2f}亿  PE {pe200:.2f}  折{inp['g50_lag_h']:.0f}年  "
          f"V={v_g200:.2f} HKD")
    implied_all_h = (inp["ni_h"] * pe["h"] + option_mv(inp, "h")) / inp["ni_h"]
    if implied_all_h > hi + 1e-9:
        print(f"  ⚠ 表3 整体隐含倍数 H={implied_all_h:.2f} 越过 own-year 顶 {hi:g} "
              f"— 越出来自 G200（2019–2025 带里没有这台机），G50-only 仍在带内")
    print(f"表3  V_opt={v_opt:.2f} (G50 {v_g50:.2f} + G200 {v_g200:.2f})"
          f"  p_k={p_k[0]:.2f}/{p_k[1]:.3f}/{p_k[2]:.2f}  "
          + "  ".join(
              f"{n}:{b:.2f}+{pk:.3f}xV={a:.2f}"
              for n, b, pk, a in zip("LMH", (L, M, H), p_k, adj_band)))
    print(f"V_opt/M={v_opt / M:.1%}")

    gw = {t: gross_weights(inp, t) for t in TIERS}
    print(f"腿 C 分部毛利权重 {gw['l']['c']:.2%} / {gw['m']['c']:.2%} / {gw['h']['c']:.2%}"
          f"  →  含表外利润权重 {w['l']['c']:.2%} / {w['m']['c']:.2%} / {w['h']['c']:.2%}")
    print(f"  上限守卫 {inp['leg_c_weight_cap']:.0%} 只硬约束 M 档（A15）：M {w['m']['c']:.2%} ✓"
          + (f"；{'/'.join(over)} 档超限 ⚠（情景档，不报错）" if over else ""))

    # The single most load-bearing sensitivity: leg C cannot move the anchor.
    stress = 0.20
    w_m = w["m"]
    g_stress = (w_m["a"] * inp["g2_a_m"] + w_m["b"] * inp["g2_b_m"] + w_m["c"] * stress)
    pe_stress = perpetual_pe(g_stress, forward_roe(inp, "m"), r)
    m_stress = inp["ni_m"] * pe_stress * 1e8 / inp["shares"] / fx
    print(f"腿 C 压力测试：g_C {inp['g2_c_m']:.0%} -> {stress:.0%} 时 M {M:.2f} -> {m_stress:.2f} HKD "
          f"({m_stress / M - 1:+.1%})")

    # Disclosure row (Outputs): the three-leg g2 ±1pp band, L/M/H and H+V only.
    # Printed only — the anchors above are the ruler.
    for delta in (-0.01, 0.01):
        band = []
        for t in TIERS:
            g_d = sum(w[t][leg] * (inp[f"g2_{leg}_{t}"] + delta) for leg in LEGS)
            band.append(to_hkd(inp, inp[f"ni_{t}"] * perpetual_pe(g_d, forward_roe(inp, t), r)))
        print(f"敏感区 三腿 g₂ {delta:+.0%}: {band[0]:.2f}/{band[1]:.2f}/{band[2]:.2f}"
              f"  H+V={band[2] + v_opt:.2f}")

    # A14 — the open construction question, priced rather than argued.  All
    # three bands print side by side; if they drift apart materially the choice
    # stops being a bookkeeping detail and becomes a call the framework cannot defer.
    print("A14 腿 C 表外利润（三菱重工东方燃机 49% 权益法，不进气电分部）三个构造：")
    for mode, label in (("base", "备选① 纯毛利权重"), ("assign", "现行 指派腿C"),
                        ("addw", "备选② 并入权重分子")):
        anchors, wc = variant_band(inp, mode)
        cap_hits = [t.upper() for t, x in zip(TIERS, wc) if x >= inp["leg_c_weight_cap"]]
        trip = f" ⚠ {'/'.join(cap_hits)} 档 w_C 超 {inp['leg_c_weight_cap']:.0%}" if cap_hits else ""
        print(f"  {label:<14} w_C {wc[0]:6.2%}/{wc[1]:6.2%}/{wc[2]:6.2%}  "
              f"L/M/H {anchors[0]:5.2f}/{anchors[1]:5.2f}/{anchors[2]:5.2f}{trip}")

    print(f"三档 PE {pe['l']:.2f}/{pe['m']:.2f}/{pe['h']:.2f} 落在 H 股 own-year 实测带 "
          f"[{lo}, {hi}] 内 (p50={inp['pe_own_mid']:g}) ✓  — 形状 (裁决顺序 ⑤): 各腿 g2 三档共用, "
          f"合成 g {g['l']:+.2%}/{g['m']:+.2%}/{g['h']:+.2%} 只随权重微动, 倍数 ≈ flat")
    # 被否决口径: the pre-v6 tiered g (A −6/−4/−2, B 0/+3/+5, C 0/0/+2) generates a
    # same-direction 8.0/9.0/10.1 band on a cyclical — printed so the rejection
    # stays visible; and the FY2024 trough x 1/r pressure coordinate (A1).
    tiered = {"a": (-0.06, -0.04, -0.02), "b": (0.0, 0.03, 0.05), "c": (0.0, 0.0, 0.02)}
    pe_tier = []
    for i, t in enumerate(TIERS):
        gt = sum(w[t][leg] * tiered[leg][i] for leg in LEGS)
        pe_tier.append(perpetual_pe(gt, forward_roe(inp, t), r))
    print(f"被否决口径 分档 g（A −6/−4/−2, B 0/+3/+5, C 0/0/+2）→ PE {pe_tier[0]:.2f}/{pe_tier[1]:.2f}/{pe_tier[2]:.2f} 同向 "
          f"→ 带 {to_hkd(inp, inp['ni_l'] * pe_tier[0]):.2f}/{to_hkd(inp, inp['ni_m'] * pe_tier[1]):.2f}/{to_hkd(inp, inp['ni_h'] * pe_tier[2]):.2f}"
          f"（cyclical 同向倍数，裁决顺序 ⑤ 不采用）")
    print(f"谷底压力坐标 (A1): FY2024 {inp['ni_trough_fy2024']:.2f} 亿 x 1/r = {to_hkd(inp, inp['ni_trough_fy2024'] / r):.2f} HKD")
    print(f"flat-multiple @PE={pe['m']:.2f}: {flat['l']:.2f}/{flat['m']:.2f}/{flat['h']:.2f}")
    print(f"L={L:.2f} A={A:.2f} M={M:.2f} B={B:.2f} H={H:.2f}")
    print(f"L/M={L / M:.2f} H/M={H / M:.2f} (H-L)/2M={(H - L) / (2 * M):.0%}")
    print(f"分子比 L/M={inp['ni_l'] / inp['ni_m']:.3f} H/M={inp['ni_h'] / inp['ni_m']:.3f} | "
          f"倍数比 L/M={pe['l'] / pe['m']:.3f} H/M={pe['h'] / pe['m']:.3f}")

    # What the street and book are each paying for, in g terms.  ROE sits on r
    # here, so a price well above 1/r comes back ill-conditioned — the flag is
    # the point, not the number (A9).
    roe_m = forward_roe(inp, "m")
    for label, cny in (("卖方 TP", inp["tp_street"] * fx * inp["shares"] / 1e8),
                       ("账面 PB=1.0", inp["bps"] * inp["shares"] / 1e8)):
        p = cny / inp["ni_m"]
        gi, ok = implied_g(p, roe_m, r)
        print(f"  {label:<10} 隐含 PE={p:6.2f}x → g={gi:+.2%}"
              f"{'' if ok else '  ⚠ ROE≈r，只能当方向读 (A9)'}")

    # A12 — the open question this framework hands back to research.
    tp_pe = inp["tp_street"] * fx * inp["shares"] / 1e8 / inp["ni_m"]
    print(f"A12 未解释项：卖方 TP {inp['tp_street']} HKD 对 TTM 隐含 {tp_pe:.2f}x = "
          f"own-year 带顶 {hi} 的 {tp_pe / hi:.1f} 倍 — 分歧在倍数，不在盈利年份；逐机构口径仍 待补")

    # What the framework itself gives the gas-turbine business at M (交叉备注).
    ni_ab = inp["ni_m"] * (w_m["a"] + w_m["b"])
    gas_framework = inp["ni_m"] * w_m["c"] * pe["m"] + option_mv(inp, "m")
    print(f"  M 档 腿AB@{pe['m']:.2f}x {ni_ab * pe['m']:.1f} 亿；燃机业务 腿C+腿D {gas_framework:.1f} 亿")
    print(f"净现金 {inp['net_cash']:.2f} 亿 = 每股 {inp['net_cash'] * 1e8 / inp['shares']:.2f} CNY "
          f"/ {inp['net_cash'] * 1e8 / inp['shares'] / fx:.2f} HKD（不进主公式，A11）")
    print(f"BPS {inp['bps']:.2f} CNY = {inp['bps'] / fx:.2f} HKD")
    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_perp 1:1 in the three incumbent legs' multiple; NI, leg weights, g2 and
    # ROE stay put.  r_disc only discounts the G50/G200 V_opt legs, which are
    # outside L/M/H, so it is not shifted.  Disclosure only.
    def band_rf(dr: float) -> tuple[float, float, float]:
        shifted = dict(inp, r_perp=r + dr)
        return tuple(anchor(shifted, t) for t in TIERS)

    rf = rf_block(LISTING_CCY, {"r_perp": r}, band_rf)
    if any(abs(x - y) > 1e-9 for x, y in zip(band_rf(0.0), (L, M, H))):
        errors.append("r_f readings: the dr = 0 column does not reproduce L/M/H")

    # Only a clean run feeds the daily digest.
    if not errors:
        write_rf_readings("1072.HK", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    sys.exit(main())
