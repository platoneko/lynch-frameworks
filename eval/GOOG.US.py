#!/usr/bin/env python3
"""GOOG.US (Alphabet) valuation eval — recompute anchors from frameworks/GOOG.US.md.

frameworks/GOOG.US.md is the source of truth; this script re-derives
L/M/H / A/B / zone from the §3 Inputs table and exits 1 on mismatch.

formula_id: goog_sotp_services_cloud_pe_assets_v1

Main ruler: SOTP on *current-run-rate* (H1 2026 x2) segment operating income —
Google Services and the Alphabet-level cost line at a Services PE band
(17/22/30; H's +4 turns = A17 stopgap until Search/API is separately disclosed), Google Cloud at a growth PE band (18/28/38), both after a 17%
normalized tax; plus a discounted securities portfolio, a discounted Waymo
private mark, and net cash excluding listed equity securities.

Why GAAP EPS is not used: H1 2026 other income carries $135.9B of unrealized
equity-securities gains (SpaceX and a private company), so trailing EPS - and
every screen PE built on it - is meaningless for this name.

Run:  python3 eval/GOOG.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import (  # noqa: E402
    capex_constituent_share,
    check_capex_constituent,
)

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "GOOG.US.md"
FORMULA_ID = "goog_sotp_services_cloud_pe_assets_v1"
TOL = 0.05
BN = 1e3  # inputs are in $M; report in $B
# 10-Q 2026-06-30 Note 15: H1 consolidated income from operations ($M)
H1_TOTAL_OPERATING_INCOME = 80466.0
# Current-run-rate EBIT may sit below the FY26E consensus (it is trailing, not
# forward) but a large gap means the numerator or the consensus row went stale.
MAX_CONSENSUS_GAP = 0.10


def parse_inputs(md: str) -> dict[str, float]:
    """Parse §3 Inputs table: | field | value | ... |"""
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


def first_float(pattern: str, md: str) -> float | None:
    m = re.search(pattern, md)
    return float(m.group(1)) if m else None


REQUIRED = [
    "price",
    "shares_diluted",
    "tax_rate",
    "oi_services_h1",
    "oi_cloud_h1",
    "oi_corp_h1",
    "corp_oneoff_h1",
    "oi_other_bets_h1",
    "pe_services_l",
    "pe_services_m",
    "pe_services_h",
    "pe_cloud_l",
    "pe_cloud_m",
    "pe_cloud_h",
    "cash_and_securities",
    "mkt_equity_sec",
    "other_mkt_equity_sec",
    "nonmkt_sec",
    "lt_debt",
    "pref_liq",
    "dtl_noncurrent",
    "d_port_l",
    "d_port_m",
    "d_port_h",
    "waymo_post_money",
    "waymo_stake",
    "d_ob_l",
    "d_ob_m",
    "d_ob_h",
    "capex_h1",
    "dep_h1",
    "ebit_fy26e_consensus",
    "eps_fy27e_consensus",
    "cloud_om_l",
    "cloud_om_now",
    "cloud_premium",
    "capex_guide_low",
    "capex_guide_high",
]


def sanity_checks(inp: dict[str, float]) -> list[str]:
    """Ticker-specific guards: band ordering, segment identity, no double count."""
    errs: list[str] = []

    if not (inp["pe_services_l"] < inp["pe_services_m"] < inp["pe_services_h"]):
        errs.append("pe_services band not increasing")
    if not (inp["pe_cloud_l"] < inp["pe_cloud_m"] < inp["pe_cloud_h"]):
        errs.append("pe_cloud band not increasing")
    # A2e-2b: no traded cloud comparable exists (no sell-side SOTP on Alphabet;
    # the vendor peer set is 互联网内容). So the cloud band is the *same*
    # distribution as Services times one premium -- a tier-varying premium would
    # be a second, unsourced lever hiding inside the multiples.
    for tier in ("l", "m", "h"):
        want = inp[f"pe_services_{tier}"] * inp["cloud_premium"]
        if abs(inp[f"pe_cloud_{tier}"] - want) > 0.01:
            errs.append(
                f"pe_cloud_{tier}={inp[f'pe_cloud_{tier}']:.4f} != "
                f"pe_services_{tier} x cloud_premium = {want:.4f} (A20/A2e-2b)"
            )
    errs.extend(check_capex_constituent(inp["capex_guide_low"], inp["capex_guide_high"]))
    # Cloud must carry a growth premium, else splitting the legs buys nothing.
    if inp["pe_cloud_m"] <= inp["pe_services_m"]:
        errs.append("pe_cloud_m must exceed pe_services_m (A7)")

    for name in ("d_port", "d_ob"):
        l, m, h = (inp[f"{name}_{k}"] for k in "lmh")
        if not (1.0 >= l > m > h >= 0.0):
            errs.append(f"{name}_* must be a decreasing band inside [0,1]")

    if not (0.0 < inp["tax_rate"] < 0.5):
        errs.append("tax_rate out of plausible range")

    # 10-Q Note 15 segment identity — guards against a stale/miskeyed segment row.
    seg_sum = (
        inp["oi_services_h1"]
        + inp["oi_cloud_h1"]
        + inp["oi_other_bets_h1"]
        + inp["oi_corp_h1"]
    )
    if abs(seg_sum - H1_TOTAL_OPERATING_INCOME) > 1.0:
        errs.append(
            f"segment identity: sum {seg_sum:.0f} != H1 operating income "
            f"{H1_TOTAL_OPERATING_INCOME:.0f}"
        )

    # Other Bets losses stay out of the earnings legs (A2/A15 no-double-count).
    if inp["oi_other_bets_h1"] >= 0:
        errs.append("oi_other_bets_h1 expected negative; recheck A15 handling")

    return errs


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

    errors = sanity_checks(inp)

    # Step 1 — numerator: current run-rate (H1 x2), after normalized tax.
    keep = 1.0 - inp["tax_rate"]
    nopat_services = inp["oi_services_h1"] * 2 * keep
    nopat_cloud = inp["oi_cloud_h1"] * 2 * keep
    nopat_corp = (inp["oi_corp_h1"] + inp["corp_oneoff_h1"]) * 2 * keep
    core_eps = (nopat_services + nopat_cloud + nopat_corp) / inp["shares_diluted"]

    # Step 3 — asset legs and closing item (listed equities moved out of net cash).
    net_cash = (
        inp["cash_and_securities"]
        - inp["mkt_equity_sec"]
        - inp["lt_debt"]
        - inp["pref_liq"]
    )
    # other_mkt_equity_sec sits under Other non-current assets, so it is in
    # neither cash_and_securities nor nonmkt_sec — without this term the
    # restricted SpaceX stake is in no leg at all.
    portfolio_gross = (
        inp["mkt_equity_sec"]
        + inp["other_mkt_equity_sec"]
        + inp["nonmkt_sec"]
        - inp["dtl_noncurrent"]
    )
    waymo_gross = inp["waymo_post_money"] * inp["waymo_stake"]

    # The L tier retreats the Cloud numerator to a margin this segment actually
    # printed a year ago (A18) — Alphabet gives no EPS guidance, but a realised
    # segment margin is evidence, not a forecast (skill A2e-2c).
    cloud_retreat = inp["cloud_om_l"] / inp["cloud_om_now"]

    def anchor(
        pe_svc: float, pe_cld: float, d_port: float, d_ob: float, cloud_scale: float = 1.0
    ) -> float:
        ops = (
            nopat_services * pe_svc
            + nopat_cloud * cloud_scale * pe_cld
            + nopat_corp * pe_svc
        )
        assets = portfolio_gross * (1 - d_port) + waymo_gross * (1 - d_ob)
        return (ops + net_cash + assets) / inp["shares_diluted"]

    L = anchor(
        inp["pe_services_l"], inp["pe_cloud_l"], inp["d_port_l"], inp["d_ob_l"],
        cloud_retreat,
    )
    M = anchor(inp["pe_services_m"], inp["pe_cloud_m"], inp["d_port_m"], inp["d_ob_m"])
    H = anchor(inp["pe_services_h"], inp["pe_cloud_h"], inp["d_port_h"], inp["d_ob_h"])
    A, B = (L + M) / 2, (M + H) / 2

    if not (L < M < H):
        print(f"FAIL: L<M<H violated: {L}, {M}, {H}", file=sys.stderr)
        return 1
    zone = zone_of(inp["price"], L, M, H)

    # A2e-2c: re-price every tier at pe_m. Alphabet is a stalwart running the
    # 2c-ex exemption (de-rate-driven band), so the ladder is allowed to be
    # narrow here — but it must not be empty, and H must stay under the realised
    # trailing-PE top (2c-ex conditions 2 and 3 live in the framework's A6/A17).
    flat_l = anchor(
        inp["pe_services_m"], inp["pe_cloud_m"], inp["d_port_l"], inp["d_ob_l"],
        cloud_retreat,
    )
    flat_m = M
    flat_h = anchor(
        inp["pe_services_m"], inp["pe_cloud_m"], inp["d_port_h"], inp["d_ob_h"]
    )
    if not (flat_l < flat_m < flat_h):
        print(
            f"FAIL: flat-multiple ladder collapsed: "
            f"{flat_l:.2f}/{flat_m:.2f}/{flat_h:.2f} — tiers have no content "
            f"outside the multiples (A2e-2c)",
            file=sys.stderr,
        )
        return 1

    # Diagnostics: is the numerator trailing (as claimed) and how big is the
    # depreciation lag the numerator does not yet carry (A5)?
    ebit_runrate = (
        inp["oi_services_h1"]
        + inp["oi_cloud_h1"]
        + inp["oi_corp_h1"]
        + inp["oi_other_bets_h1"]
    ) * 2
    consensus_gap = ebit_runrate / inp["ebit_fy26e_consensus"] - 1.0
    if abs(consensus_gap) > MAX_CONSENSUS_GAP:
        errors.append(
            f"run-rate EBIT {ebit_runrate:.0f} deviates {consensus_gap:+.1%} "
            f"from FY26E consensus (>{MAX_CONSENSUS_GAP:.0%})"
        )
    capex_lag = inp["capex_h1"] / inp["dep_h1"]

    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    stated = {
        "L": first_float(r"L = \*\*([0-9.]+)\*\*", out_sec),
        "M": first_float(r"M = \*\*([0-9.]+)\*\*", out_sec),
        "H": first_float(r"H = \*\*([0-9.]+)\*\*", out_sec),
        "A": first_float(r"A = \*\*([0-9.]+)\*\*", out_sec),
        "B": first_float(r"B = \*\*([0-9.]+)\*\*", out_sec),
    }
    for k, v in {"L": L, "M": M, "H": H, "A": A, "B": B}.items():
        s = stated.get(k)
        if s is None:
            errors.append(f"stated {k} not found")
        elif abs(s - v) > TOL:
            errors.append(f"{k}: stated {s} vs recomputed {v:.4f}")

    zm = re.search(r"zone = \*\*`([a-z_]+)`\*\*", out_sec)
    stated_zone = zm.group(1) if zm else None
    if stated_zone != zone:
        errors.append(f"zone: stated {stated_zone} vs recomputed {zone}")

    print(f"formula_id={FORMULA_ID}")
    print(
        f"run-rate OI($B) services={nopat_services / keep / BN:.1f}"
        f" cloud={nopat_cloud / keep / BN:.1f}"
        f" corp={nopat_corp / keep / BN:.1f}"
        f" | total incl OtherBets={ebit_runrate / BN:.1f}"
        f" vs FY26E consensus {inp['ebit_fy26e_consensus'] / BN:.1f} ({consensus_gap:+.1%})"
    )
    print(
        f"core EPS(3 legs)={core_eps:.2f}  price/core={inp['price'] / core_eps:.2f}x"
        f"  net_cash/sh={net_cash / inp['shares_diluted']:.2f}"
        f"  portfolio/sh(gross)={portfolio_gross / inp['shares_diluted']:.2f}"
        f"  waymo/sh(gross)={waymo_gross / inp['shares_diluted']:.2f}"
    )
    print(
        f"depreciation lag: capex_h1/dep_h1={capex_lag:.1f}x"
        f" — numerator does NOT yet carry the 2026-27 capex wave (A5)"
    )
    print(f"L={L:.2f} M={M:.2f} H={H:.2f} A={A:.2f} B={B:.2f}")
    print(
        f"implied PE on core EPS: L={L / core_eps:.1f}x M={M / core_eps:.1f}x"
        f" H={H / core_eps:.1f}x | on FY27E consensus EPS {inp['eps_fy27e_consensus']}:"
        f" L={L / inp['eps_fy27e_consensus']:.1f}x M={M / inp['eps_fy27e_consensus']:.1f}x"
        f" H={H / inp['eps_fy27e_consensus']:.1f}x"
    )
    print(
        f"cloud L retreat: OI margin {inp['cloud_om_l']:.1%} (realised, a year ago)"
        f" vs {inp['cloud_om_now']:.1%} now -> x{cloud_retreat:.4f}"
    )
    print(
        f"flat-multiple ladder (A2e-2c, all tiers at pe_m):"
        f" {flat_l:.2f}/{flat_m:.2f}/{flat_h:.2f}  width {(flat_h - flat_l) / flat_m:.1%}"
    )
    print(
        f"tier decomposition (A2e-5):  L/M {L / M:.2f} = non-pe {flat_l / M:.2f}"
        f" x pe {(L / M) / (flat_l / M):.2f}  |  H/M {H / M:.2f} ="
        f" non-pe {flat_h / M:.2f} x pe {(H / M) / (flat_h / M):.2f}"
    )
    _lo, _hi = capex_constituent_share(inp["capex_guide_low"], inp["capex_guide_high"])
    print(
        f"capex axis (constituent, A19): 2026 guide"
        f" ${inp['capex_guide_low'] / 1e9:.0f}-{inp['capex_guide_high'] / 1e9:.0f}B"
        f" = {_lo:.1%}-{_hi:.1%} of the axis 2026 base"
    )
    print(f"price={inp['price']} zone={zone}")

    if errors:
        print("FAIL:", "; ".join(errors), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
