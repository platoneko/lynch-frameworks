#!/usr/bin/env python3
"""COIN.US (Coinbase Global) valuation eval — recompute anchors from frameworks/COIN.US.md.

frameworks/COIN.US.md is the source of truth; this script re-derives
L/M/H / A/B from its §3 Inputs table and exits 1 on mismatch.  The doc carries no
current price (AGENTS.md「现价 — 禁写契约」): which zone a quote falls in is
derived live by the daily digest and the app, so nothing here reads a price.

formula_id: coin_midcycle_gordon_plus_assets_v1

Main ruler: whole-company Gordon on *mid-cycle* earnings, plus a non-operating
asset leg.  Earnings flipped sign four times in six years (§1 属性 C), so no
single year's profit may be multiplied; the three tiers are bridged from the
shared axis's 2028 steady-state EBITDA rungs instead.

  NI_x   = (EBITDA_x * 100 - addback_x - interest) * (1 - tax)
  PE_M,H = (1 - g2/ROE_x) / (r - g2);   PE_L = 1/r   (g = 0, growth switched off)
  asset  = crypto held for investment + strategic investments, hair-cut per tier
  anchor = EPS_x * PE_x + asset_x

The asset leg deliberately excludes net cash: the interest that cash earns is
already inside the axis EBITDA and therefore inside the numerator, so adding
the principal back would double-count it (A10).

r is the leg's basket value read from the Inputs row and checked against
gordon.BASKET_R via the 篮 N tag.  A2 records that no basket's written
criterion holds positively and that 篮 4 is the user's ruling, not a derivation.

Axis: full mount on _AXIS.crypto-cycle — all three numerators are the axis's
own rungs, so editing either side alone turns this eval red.

Run:  python3 frameworks/eval/COIN.US.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))

from lib.axes import check_crypto_mount  # noqa: E402
from lib.gordon import (  # noqa: E402
    check_branch, check_g_cap, check_r, payout_gap, perpetual_pe,
    recovery_two_stage_pe,
)
from lib.inputs import (  # noqa: E402
    check_against_stated, check_missing, ladder, parse_baskets, parse_inputs, report,
)
from lib.zones import cut_points  # noqa: E402
# rf_report imports `eval.lib.*`, so the repo root must be importable too.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from eval.lib.bands_io import write_rf_readings  # noqa: E402
from eval.lib.rf_report import rf_block  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parents[2] / "frameworks" / "COIN.US.md"
FORMULA_ID = "coin_midcycle_gordon_plus_assets_v1"

# Axis rungs are stated in 亿 USD to match the axis file; the bridge works in $M.
EBITDA_UNIT = 100.0
# A16: point-basis comparison for the bear tier — n is the years the axis's own
# deck takes to normalise; the decay side (H) is a repo-level [待建].
POINT_N = 2
# _AXIS.rates segment: a US listing reads the USD r_f (valuation-rules「按上市货币取段」).
LISTING_CCY = "USD"

REQUIRED = [
    "shares", "equity",
    "ebitda_l", "ebitda_m", "ebitda_h",
    "addback_l", "addback_m", "addback_h",
    "interest", "tax",
    "crypto_inv", "strat_inv",
    "crypto_hair_l", "strat_hair_l", "crypto_up_h", "strat_up_h",
    "r_op", "g2", "g2_l", "net_cash", "payout_obs",
    "seller_tp_mean", "seller_tp_lo", "seller_tp_hi",
]


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    inp = parse_inputs(md)
    errors = check_missing(inp, REQUIRED)
    if errors:
        return report(errors)

    r, g2, g2_l = inp["r_op"], inp["g2"], inp["g2_l"]
    shares, equity, tax = inp["shares"], inp["equity"], inp["tax"]

    # --- guards that are about the ruler, not the arithmetic -----------------
    baskets = parse_baskets(md)
    errors += check_r(r, "r_op", baskets.get("r_op"))
    errors += check_g_cap(g2, r, "g2")
    errors += check_crypto_mount((inp["ebitda_l"], inp["ebitda_m"], inp["ebitda_h"]))

    # --- 1) bridge: axis EBITDA -> attributable net income (A6) --------------
    def bridge(ebitda: float, addback: float) -> float:
        return (ebitda * EBITDA_UNIT - addback - inp["interest"]) * (1 - tax)

    ni_l = bridge(inp["ebitda_l"], inp["addback_l"])
    ni_m = bridge(inp["ebitda_m"], inp["addback_m"])
    ni_h = bridge(inp["ebitda_h"], inp["addback_h"])
    eps_l, eps_m, eps_h = ni_l / shares, ni_m / shares, ni_h / shares

    # --- 2) forward ROE per tier, on the one `equity` field ------------------
    roe_l, roe_m, roe_h = ni_l / equity, ni_m / equity, ni_h / equity

    # --- 3) operating-leg multiples ------------------------------------------
    # L runs g = 0 as a *scenario*, not a payout policy, so check_branch is not
    # the right test for it; M is the tier whose g has to be funded out of
    # retention, and it is the one the branch test applies to.
    def multiples(r_: float) -> tuple[float, float, float]:
        pe_l_ = 1.0 / r_ if g2_l == 0 else perpetual_pe(g2_l, roe_l, r_)
        return pe_l_, perpetual_pe(g2, roe_m, r_), perpetual_pe(g2, roe_h, r_)

    pe_l, pe_m, pe_h = multiples(r)
    errors += check_branch(g2, roe_m, r, inp["payout_obs"], "M")

    core_l, core_m, core_h = eps_l * pe_l, eps_m * pe_m, eps_h * pe_h

    # --- 4) non-operating asset leg (A10; net cash deliberately excluded) ----
    crypto, strat = inp["crypto_inv"], inp["strat_inv"]
    asset_l = (crypto * (1 - inp["crypto_hair_l"]) + strat * (1 - inp["strat_hair_l"])) / shares
    asset_m = (crypto + strat) / shares
    asset_h = (crypto * (1 + inp["crypto_up_h"]) + strat * (1 + inp["strat_up_h"])) / shares

    # --- 5) anchors ----------------------------------------------------------
    L, M, H = core_l + asset_l, core_m + asset_m, core_h + asset_h
    errors += ladder("eps", eps_l, eps_m, eps_h)
    errors += ladder("anchor", L, M, H)
    # A2e-2c: the ladder must already hold with the multiple held flat at pe_m.
    errors += ladder(
        "flat-multiple", eps_l * pe_m + asset_l, core_m + asset_m, eps_h * pe_m + asset_h
    )

    A, B = cut_points(L, M, H)
    errors += check_against_stated(md, {"L": L, "M": M, "H": H, "A": A, "B": B}, None)

    # --- disclosure ----------------------------------------------------------
    modelled_payout, gap = payout_gap(g2, roe_m, inp["payout_obs"])
    ev = M * shares - inp["net_cash"]
    ev_ebitda = ev / (inp["ebitda_m"] * EBITDA_UNIT)
    g1_point = (eps_m / eps_l) ** (1 / POINT_N) - 1
    point_l = eps_l * recovery_two_stage_pe(g1_point, POINT_N, g2, roe_m, r) + asset_l

    print(f"formula_id {FORMULA_ID}")
    print(f"  NI    {ni_l:.1f} / {ni_m:.1f} / {ni_h:.1f}   EPS {eps_l:.4f} / {eps_m:.4f} / {eps_h:.4f}")
    print(f"  ROE   {roe_l:.2%} / {roe_m:.2%} / {roe_h:.2%}   (r {r:.0%}, g2 {g2:.0%})")
    print(f"  PE    {pe_l:.2f}x / {pe_m:.2f}x / {pe_h:.2f}x")
    print(f"  core  {core_l:.2f} / {core_m:.2f} / {core_h:.2f}   asset {asset_l:.2f} / {asset_m:.2f} / {asset_h:.2f}")
    print(f"  L/M/H {L:.2f} / {M:.2f} / {H:.2f}   A {A:.2f}  B {B:.2f}")
    print(f"  ratios L/M {L / M:.3f}  H/M {H / M:.3f}  (H-L)/2M {(H - L) / (2 * M):.1%}")
    print(f"  EV/EBITDA at M {ev_ebitda:.2f}x   (MS 21.0x on the same 2028 rung)")
    print(f"  payout modelled {modelled_payout:.1%} vs observed {inp['payout_obs']:.1%} gap {gap:+.1%}")
    print(f"  A16 point-basis L {point_l:.2f} (g1 {g1_point:.1%}, n={POINT_N}) vs regime L {L:.2f}")

    # r_f readings (_AXIS.rates, valuation-rules「利率轴与 r_f 敏感性」): Δr_f moves
    # r_op 1:1 in all three multiples; numerators, ROE, g and the asset leg stay
    # put.  Disclosure only — the anchors above are the 中枢 column.
    def band_at(dr: float) -> tuple[float, float, float]:
        pl, pm, ph = multiples(r + dr)
        return eps_l * pl + asset_l, eps_m * pm + asset_m, eps_h * ph + asset_h

    rf = rf_block(LISTING_CCY, {"r_op": r}, band_at)
    # Only a clean run feeds the daily digest.
    if not errors:
        write_rf_readings("COIN.US", rf.seg, (L, M, H), rf.consensus, rf.pressure)
    return report(errors)


if __name__ == "__main__":
    raise SystemExit(main())
