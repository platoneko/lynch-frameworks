#!/usr/bin/env python3
"""NOK.US (Nokia) valuation eval — recompute anchors from frameworks/NOK.US.md.

frameworks/NOK.US.md stays the human-facing source of truth for inputs; this
script is the enforcement layer that keeps its number chain honest:

    parse §3 Inputs table -> rebuild every SOTP leg -> L/M/H, A/B, zone
                          -> diff against the numbers printed in §3 Outputs
                          -> exit 1 on any mismatch or invariant violation

formula_id: nok_sotp_ni2028_ts_annuity_ran_v1_gordon_v1

Main ruler (SOTP, modelled in EUR, reported in USD per ADR):
  * Network Infrastructure — the only leg carrying a forward numerator.  The
    L/M/H scenario lives in the FY2027E consensus EPS range (7 houses, USD/ADR),
    bridged to group EBIT and reduced to the NI residual with the other legs
    pinned at FY26E.  Multiple by two-stage Gordon: g1 = 2028E multi-house point
    mean / FY27 mean - 1 for one year, then g2 (peer-cluster reverse-solve,
    capped), r on the operating tier, ROE on a proxy equity (invested capital x
    NI revenue share).  `two_stage_pe` prices FY2027 as NEXT-period earnings
    (t=1, valuation date = end-FY2026), so FY2027 = current FY + 1 carries no
    extra discount (n_disc_ni = 0; A14).  表1 reports this leg on the
    post-transition FY2028 numerator (skill A2e-3), the FY27-basis multiple is
    a cross line only.
  * Technology Standards (patent licensing annuity) — run-rate sales x margin,
    current-year basis, NOT discounted, the annuity-class EV/EBIT ladder
    10 / 12.4 / 18.9 (BofA "other businesses" 10x / sell-side QTL SOTP cluster
    midpoint / IDCC realised 18.9x) SHARED with QCOM.US's QTL leg and checked
    rung by rung against frameworks/QCOM.US.md.  Debt-like quality is carried
    by the ladder, not by r=7% (A2e-5b, no double count).
  * MI-core (Radio Networks + Core Software) — three-point numerator (FY2025
    actual / FY26E identity residual / FY26 guidance-top residual) x one flat
    EV/EBIT (无同业锚 · flat).  No leg equity and no same-world g2 source, so
    it does not run Gordon.
  * Corporate unallocated capitalised at 10x (negative -> deduction).
  * Closing items summed from components (net cash, pension credited at 0,
    one year of restructuring cash outflow).  No hand-written total.
  * EUR per share -> USD per ADR via fx_eur_usd x adr_ratio.

Hard checks mirror framework §3 校验步骤 (identity, ladders, shared annuity
ladder vs QCOM.US, perpetual-growth caps, 裁决顺序 ③ guardrail against the
realised trough multiple, stated Outputs incl. 表1 / zone-table bounds /
candidate band, flat-@M ladder, g2 evidence-range zone stability, no p_* leak,
optical axis mount).

Run after every edit of frameworks/NOK.US.md:  python3 eval/NOK.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import check_optical_oe_mount  # noqa: E402
from eval.lib.gordon import (  # noqa: E402
    G_CAP,
    R_OPERATING,
    check_g_cap,
    check_r,
    check_transition_years,
    implied_g,
    payout,
    perpetual_pe,
    two_stage_pe,
)
from eval.lib.inputs import check_missing, ladder, parse_inputs  # noqa: E402
from eval.lib.zones import cut_points, zone_of  # noqa: E402

FRAMEWORK = REPO_ROOT / "frameworks" / "NOK.US.md"
# The licensing-annuity ladder is one ladder for the asset class (A2e-5b): the
# same three prints value QCOM's QTL leg, so a rung moved on one side only is a
# drift, not a re-anchoring.  Pattern: eval/603799.SH.py SHARED_LADDER.
PEER = REPO_ROOT / "frameworks" / "QCOM.US.md"
SHARED_LADDER = {f"ev_ebit_ts_{k}": f"ev_ebit_ts_{k}" for k in ("l", "m", "h")}
FORMULA_ID = "nok_sotp_ni2028_ts_annuity_ran_v1_gordon_v1"

TOL = 0.05  # stated anchors are rounded to 2 decimals
EBIT_TOL = 5e6  # segment identity slack, EUR (inputs are quoted to 0.005bn)
# 2028E is the only year beyond the numerator with >= 2 house point estimates
# (A7b); FY2029 has none.  Stage 1 may not run longer than this.
CONSENSUS_YEARS_BEYOND_FY27 = 1
# Same-world evidence range for g2 (A7d): every well-conditioned optical-cluster
# reverse-solve sits above the cap, so the legal range collapses onto G_CAP.
G2_EVIDENCE_RANGE = (G_CAP, G_CAP)
G2_SENSITIVITY_PP = 0.01

CLOSING_COMPONENTS = ("net_cash_eur", "pension_net_eur", "restructuring_eur")
# 2028E multi-house point estimates feeding g1 (A7b); the JPM high scenario is
# single-house and reaches only the candidate band (A7c).
EPS28_POINTS = ("eps28_jpm_cons_eur", "eps28_jpm_low_eur", "eps28_ms_eur", "eps28_bofa_eur")
TIERS = ("l", "m", "h")

REQUIRED = [
    "price", "fx_eur_usd", "adr_ratio", "shares",
    "ebit_group_fy26", "guide_ebit_low", "guide_ebit_high",
    "ebit_ni_fy26", "ts_sales_rr", "ts_margin",
    "ebit_mi_core_l", "ebit_mi_core_m", "ebit_mi_core_h",
    "ebit_pb_fy26", "ebit_corp_fy26",
    "eps27_l_usd", "eps27_m_usd", "eps27_h_usd", "tax_rate", "fin_income_eur",
    *EPS28_POINTS, "eps28_jpm_high_eur",
    "n_g1", "g2_ni", "r_perp", "n_disc_ni", "ic_group_eur", "ni_rev_share",
    "ev_ebit_ts_l", "ev_ebit_ts_m", "ev_ebit_ts_h", "ev_ebit_mi", "ev_ebit_corp",
    *CLOSING_COMPONENTS, "price_trough_usd", "oe_l", "oe_m", "oe_h",
]


# ---------------------------------------------------------------- stated Outputs

CELL = r"([\d.]+)(?:（[^）]*）)?"
ZONE_IDS = ("deep_discount", "conservative", "neutral", "optimistic", "stretched")


def parse_stated(text: str) -> dict:
    """Anchors, cut-points, zone id, 表1 legs, zone-table bounds, candidate band."""
    out = text.split("### Outputs", 1)[1].split("## 4.", 1)[0]
    anchors = re.search(
        r"L = \*\*([\d.]+)\*\* · M = \*\*([\d.]+)\*\* · H = \*\*([\d.]+)\*\*", out)
    cuts = re.search(r"A = \*\*([\d.]+)\*\* · B = \*\*([\d.]+)\*\*", out)
    zone = re.search(r"zone = \*\*`(\w+)`\*\*", out)
    cand = re.search(
        r"候选带（[^）]+）[^\n]*?L′ = \*\*([\d.]+)\*\*[^\n]*?M′ = \*\*([\d.]+)\*\*[^\n]*?H′ = \*\*([\d.]+)\*\*",
        out)
    if not (anchors and cuts and zone and cand):
        sys.exit("FATAL: cannot parse Outputs section (anchors/cuts/zone/candidate line)")
    # 表1: 档 | NI | 授权 | RAN | 闭合项 | 合计
    legs: dict[str, tuple[float, ...]] = {}
    row_re = re.compile(
        rf"\|\s*([LMH])\s*\|\s*{CELL}\s*\|\s*{CELL}\s*\|\s*{CELL}\s*\|"
        rf"\s*{CELL}\s*\|\s*(?:\*\*)?{CELL}(?:\*\*)?\s*\|"
    )
    for line in out.splitlines():
        m = row_re.match(line)
        if m:
            legs[m.group(1)] = tuple(float(m.group(i)) for i in range(2, 7))
    # Zone table: only rows whose first cell is a backticked zone id, and only
    # their price-interval column — the g2-leverage table also carries backticks.
    zone_row = re.compile(r"^\|\s*`(" + "|".join(ZONE_IDS) + r")`\s*\|")
    interval = "\n".join(
        line.strip().strip("|").split("|")[2]
        for line in out.splitlines() if zone_row.match(line.strip()))
    return {
        "L": float(anchors.group(1)), "M": float(anchors.group(2)),
        "H": float(anchors.group(3)),
        "A": float(cuts.group(1)), "B": float(cuts.group(2)),
        "zone": zone.group(1),
        "legs": legs,
        "table_nums": {float(x) for x in re.findall(r"\d+(?:\.\d+)?", interval)},
        "cand": tuple(float(cand.group(i)) for i in (1, 2, 3)),
    }


# ---------------------------------------------------------------- computation

def bridge(v: dict) -> dict:
    """Inputs -> the derived quantities every tier shares (framework §3 steps 1-3)."""
    ebit_ts = v["ts_sales_rr"] * v["ts_margin"]
    others_fy26 = ebit_ts + v["ebit_mi_core_m"] + v["ebit_pb_fy26"] + v["ebit_corp_fy26"]
    net = 1.0 - v["tax_rate"]
    eps27_eur = {k: v[f"eps27_{k}_usd"] / v["fx_eur_usd"] for k in TIERS}
    ebit_grp27 = {k: e * v["shares"] / net - v["fin_income_eur"] for k, e in eps27_eur.items()}
    ni27 = {k: g - others_fy26 for k, g in ebit_grp27.items()}
    eps28_mean = sum(v[f] for f in EPS28_POINTS) / len(EPS28_POINTS)
    return {
        "ebit_ts": ebit_ts,
        "legs_sum_fy26": v["ebit_ni_fy26"] + others_fy26,
        "mi_core_h_expected": v["guide_ebit_high"] - v["ebit_ni_fy26"] - ebit_ts
        - v["ebit_pb_fy26"] - v["ebit_corp_fy26"],
        "eps27_eur": eps27_eur, "ebit_grp27": ebit_grp27, "ni27": ni27,
        "equity_ni": v["ic_group_eur"] * v["ni_rev_share"],
        "g1": eps28_mean / eps27_eur["m"] - 1.0,
        "g1_cand": v["eps28_jpm_high_eur"] / eps27_eur["m"] - 1.0,
        "ev_corp": v["ebit_corp_fy26"] * v["ev_ebit_corp"],
        "adj": sum(v[k] for k in CLOSING_COMPONENTS),
        "unit": v["fx_eur_usd"] * v["adr_ratio"] / v["shares"],  # EUR total -> USD/ADR
    }


def compute(v: dict, b: dict, *, g2: float | None = None, disc_years: float | None = None,
            ts_mult: dict[str, float] | None = None, ran_mult: float | None = None,
            g1_by_tier: dict[str, float] | None = None, pin_pe: float | None = None,
            ni_evebit_flat: float | None = None) -> dict:
    """Full chain per framework §3 Formula; keyword overrides serve the sensitivities."""
    g2 = v["g2_ni"] if g2 is None else g2
    disc = (1.0 + v["r_perp"]) ** (-(v["n_disc_ni"] if disc_years is None else disc_years))
    ts_mult = ts_mult or {k: v[f"ev_ebit_ts_{k}"] for k in TIERS}
    ran_mult = v["ev_ebit_mi"] if ran_mult is None else ran_mult
    net = 1.0 - v["tax_rate"]

    tiers, anchors = {}, {}
    for k in TIERS:
        ni = b["ni27"][k]
        roe = ni * net / b["equity_ni"]
        g1 = (g1_by_tier or {}).get(k, b["g1"])
        pe = pin_pe if pin_pe is not None else two_stage_pe(g1, int(v["n_g1"]), g2, roe, v["r_perp"])
        ev_ni = ni * ni_evebit_flat * disc if ni_evebit_flat is not None else ni * net * pe * disc
        ev_ts = b["ebit_ts"] * ts_mult[k]
        ev_mi = v[f"ebit_mi_core_{k}"] * ran_mult
        ev = ev_ni + ev_ts + ev_mi + b["ev_corp"]
        tiers[k] = {
            "roe": roe, "pe": pe, "evx": pe * net, "payout1": 1.0 - g1 / roe,
            "payout2": payout(g2, roe), "ev_ni": ev_ni, "ev_ts": ev_ts, "ev_mi": ev_mi,
            "ev": ev, "group_ev_ebit": ev / v["ebit_group_fy26"],
        }
        anchors[k.upper()] = (ev + b["adj"]) * b["unit"]
    L, M, H = anchors["L"], anchors["M"], anchors["H"]
    A, B = cut_points(L, M, H)
    return {"tiers": tiers, "L": L, "M": M, "H": H, "A": A, "B": B, "disc": disc}


def group_ev_ebit_at(price_usd: float, v: dict, b: dict) -> float:
    """Whole-company EV/EBIT(FY26E) a USD/ADR price implies (A16 guardrail coordinate)."""
    ev = price_usd / b["unit"] - v["net_cash_eur"] - v["restructuring_eur"]
    return ev / v["ebit_group_fy26"]


def implied_ni27(target_usd: float, v: dict, b: dict, c: dict) -> tuple[float, float]:
    """NI FY2027E EBIT a price implies with TS / RAN / corp pinned at M and the
    NI multiple re-solved on the implied ROE (fixed point).  Returns (EBIT, PE)."""
    net = 1.0 - v["tax_rate"]
    rest = c["tiers"]["m"]["ev_ts"] + c["tiers"]["m"]["ev_mi"] + b["ev_corp"]
    ev_ni = target_usd / b["unit"] - b["adj"] - rest
    ni, pe = b["ni27"]["m"], c["tiers"]["m"]["pe"]
    for _ in range(60):
        pe = two_stage_pe(b["g1"], int(v["n_g1"]), v["g2_ni"], ni * net / b["equity_ni"], v["r_perp"])
        ni = ev_ni / (net * pe * c["disc"])
    return ni, pe


def fmt3(c: dict) -> str:
    return f"{c['L']:.2f} / {c['M']:.2f} / {c['H']:.2f}"


# ---------------------------------------------------------------- main

def main() -> None:
    text = FRAMEWORK.read_text(encoding="utf-8")
    if FORMULA_ID not in text:
        sys.exit(f"FATAL: formula_id {FORMULA_ID} missing from {FRAMEWORK.name}")

    v = parse_inputs(text)
    missing = check_missing(v, REQUIRED)
    if missing:
        sys.exit(f"FATAL: {missing[0]} in {FRAMEWORK.name}")
    stated = parse_stated(text)
    b = bridge(v)
    c = compute(v, b)
    bn = 1e9
    price = v["price"]
    checks: list[tuple[bool, str]] = []

    # 1. segment identity + guidance envelope + RAN H residual (framework §3 校验 1)
    drift = b["legs_sum_fy26"] - v["ebit_group_fy26"]
    checks.append((abs(drift) <= EBIT_TOL,
                   f"segment EBIT identity: legs {b['legs_sum_fy26'] / bn:.4f}bn == group "
                   f"{v['ebit_group_fy26'] / bn:.4f}bn (drift {drift / 1e6:+.1f}M)"))
    checks.append((v["guide_ebit_low"] <= v["ebit_group_fy26"] <= v["guide_ebit_high"],
                   f"group EBIT {v['ebit_group_fy26'] / bn:.2f}bn inside FY26 guidance "
                   f"[{v['guide_ebit_low'] / bn:.1f}, {v['guide_ebit_high'] / bn:.1f}]bn"))
    checks.append((abs(v["ebit_mi_core_h"] - b["mi_core_h_expected"]) <= EBIT_TOL,
                   f"ebit_mi_core_h {v['ebit_mi_core_h'] / bn:.3f}bn == guidance-top residual "
                   f"{b['mi_core_h_expected'] / bn:.3f}bn (A6)"))

    # 1b. optical-comms axis mount (OE shipment ladder)
    axis_errs = check_optical_oe_mount((v["oe_l"], v["oe_m"], v["oe_h"]))
    checks.append((not axis_errs, "optical OE L/M/H match _AXIS.optical-comms.md"
                   + (f": {axis_errs}" if axis_errs else "")))

    # 2. numerator ladders / multiple ladders (校验 2)
    for name, vals in (
        ("eps27", tuple(v[f"eps27_{k}_usd"] for k in TIERS)),
        ("ni27", tuple(b["ni27"][k] for k in TIERS)),
        ("ebit_mi_core", tuple(v[f"ebit_mi_core_{k}"] for k in TIERS)),
        ("ev_ebit_ts", tuple(v[f"ev_ebit_ts_{k}"] for k in TIERS)),
    ):
        errs = ladder(name, *vals)
        checks.append((not errs, errs[0] if errs else f"{name} ladder l < m < h"))
    # 2b. shared annuity ladder: every rung must equal QCOM's QTL rung (A13)
    peer = parse_inputs(PEER.read_text(encoding="utf-8"))
    drifts = [f"{ours}={v[ours]:g} vs QCOM.{theirs}={peer[theirs]:g}" if theirs in peer
              else f"QCOM.US missing {theirs}"
              for ours, theirs in SHARED_LADDER.items()
              if theirs not in peer or abs(v[ours] - peer[theirs]) > 1e-9]
    checks.append((not drifts, "shared annuity ladder ev_ebit_ts_l/m/h == QCOM.US QTL ladder"
                   + (f": drift {drifts}" if drifts else
                      f" ({v['ev_ebit_ts_l']:g} / {v['ev_ebit_ts_m']:g} / {v['ev_ebit_ts_h']:g})")))
    checks.append((v["n_disc_ni"] >= 0 and v["n_g1"] >= 1,
                   f"n_disc_ni {v['n_disc_ni']:g} >= 0, n_g1 {v['n_g1']:g} >= 1"))
    checks.append((v["ts_margin"] > 0 and v["ebit_mi_core_m"] > 0 and v["ebit_corp_fy26"] < 0,
                   "ts_margin > 0, MI-core residual > 0, corporate unallocated is a cost"))

    # 3. perpetual-growth 口径 (校验 3)
    r_errs = check_r(v["r_perp"], "r_perp")
    checks.append((not r_errs and abs(v["r_perp"] - R_OPERATING) < 1e-9,
                   f"r_perp {v['r_perp']:.0%} is the operating tier (换档属仓库级框架纠正)"))
    g_errs = check_g_cap(v["g2_ni"], "g2_ni")
    checks.append((not g_errs, g_errs[0] if g_errs else f"g2_ni {v['g2_ni']:.2%} <= cap {G_CAP:.0%}"))
    checks.append((v["r_perp"] - v["g2_ni"] >= 0.02 - 1e-9,
                   f"r - g2 = {v['r_perp'] - v['g2_ni']:.2%} >= 2%"))
    n_errs = check_transition_years(int(v["n_g1"]), CONSENSUS_YEARS_BEYOND_FY27, "n_g1")
    checks.append((not n_errs, n_errs[0] if n_errs else
                   f"n_g1 {int(v['n_g1'])} <= consensus years beyond FY27 ({CONSENSUS_YEARS_BEYOND_FY27}: 2028E points)"))
    for k in TIERS:
        p2 = c["tiers"][k]["payout2"]
        checks.append((0.0 < p2 <= 1.0, f"stage-2 payout {k.upper()} = {p2:.3f} in (0, 1]"))

    # 4. guardrail — 裁决顺序 ③: L must not price the group below its own realised trough
    trough = group_ev_ebit_at(v["price_trough_usd"], v, b)
    l_implied = group_ev_ebit_at(c["L"], v, b)
    checks.append((l_implied >= trough - 1e-9,
                   f"guardrail (③): L-implied group EV/EBIT {l_implied:.2f}x >= realised trough "
                   f"{trough:.2f}x (price {v['price_trough_usd']} on 2025-09-12)"))

    # 5. anchors / Outputs (校验 5)
    checks.append((c["L"] < c["M"] < c["H"],
                   f"L < M < H ({c['L']:.2f} < {c['M']:.2f} < {c['H']:.2f})"))
    for key in ("L", "M", "H", "A", "B"):
        checks.append((abs(stated[key] - c[key]) <= TOL,
                       f"stated {key}={stated[key]} matches computed {c[key]:.4f}"))
    expected_bounds = {round(c[k], 2) for k in ("L", "A", "B", "H")}
    checks.append((stated["table_nums"] == expected_bounds,
                   f"zone table bounds {sorted(stated['table_nums'])} == {sorted(expected_bounds)}"))
    checks.append((set(stated["legs"]) == {"L", "M", "H"},
                   f"leg table rows {sorted(stated['legs'])} == ['H', 'L', 'M']"))
    closing_ps = (b["ev_corp"] + b["adj"]) * b["unit"]
    for k in TIERS:
        row = stated["legs"].get(k.upper())
        if row is None:
            continue
        t = c["tiers"][k]
        want = (t["ev_ni"] * b["unit"], t["ev_ts"] * b["unit"], t["ev_mi"] * b["unit"],
                closing_ps, c[k.upper()])
        for name, got, exp in zip(("NI", "授权", "RAN", "闭合项", "合计"), row, want):
            checks.append((abs(got - exp) <= TOL,
                           f"leg table {k.upper()}/{name}: stated {got} vs computed {exp:.4f}"))
    z = zone_of(price, c["L"], c["M"], c["H"])
    checks.append((z == stated["zone"],
                   f"zone at price {price}: computed `{z}` == stated `{stated['zone']}`"))
    # Candidate band (A7c): same formula, only the H-tier g1 swapped for the
    # single-house JPM high scenario; L′ / M′ copy the base.
    cand = compute(v, b, g1_by_tier={"h": b["g1_cand"]})
    cand_vals = (c["L"], c["M"], cand["H"])
    checks.append((cand_vals[0] < cand_vals[1] < cand_vals[2],
                   f"candidate L′ < M′ < H′ ({cand_vals[0]:.2f} < {cand_vals[1]:.2f} < {cand_vals[2]:.2f})"))
    for name, got, exp in zip(("L′", "M′", "H′"), stated["cand"], cand_vals):
        checks.append((abs(got - exp) <= TOL, f"candidate {name}: stated {got} vs computed {exp:.4f}"))

    # 6. flat-@M ladder (A2e-2c) and g2 evidence-range zone stability (校验 6)
    flat = compute(v, b, pin_pe=c["tiers"]["m"]["pe"],
                   ts_mult={k: v["ev_ebit_ts_m"] for k in TIERS})
    checks.append((flat["L"] < flat["M"] < flat["H"],
                   f"flat-@M ladder (NI PE_M {c['tiers']['m']['pe']:.2f}x, TS {v['ev_ebit_ts_m']:g}x, RAN flat): "
                   f"{fmt3(flat)} still L < M < H"))
    for g2_edge in G2_EVIDENCE_RANGE:
        ce = compute(v, b, g2=g2_edge)
        ze = zone_of(price, ce["L"], ce["M"], ce["H"])
        checks.append((ze == z, f"g2 evidence edge {g2_edge:.2%}: zone `{ze}` == base `{z}`"))

    # 7. A2e-7a: no probability field may sit in Inputs
    leaked = [k for k in v if k == "p" or k.startswith("p_")]
    checks.append((not leaked, "no p_* field in Inputs" + (f": {leaked}" if leaked else "")))

    # ------------------------------------------------------------ report
    print(f"framework : {FRAMEWORK.name}   formula_id={FORMULA_ID}")
    print(f"segments  : NI(FY26E) {v['ebit_ni_fy26'] / bn:.3f} + TS {b['ebit_ts'] / bn:.3f} + MI-core "
          f"{v['ebit_mi_core_m'] / bn:.3f} + PB {v['ebit_pb_fy26'] / bn:.3f} + corp "
          f"{v['ebit_corp_fy26'] / bn:+.3f} = {b['legs_sum_fy26'] / bn:.3f}bn EUR")
    print("NI bridge : eps27 USD " + " / ".join(f"{v[f'eps27_{k}_usd']:.3f}" for k in TIERS)
          + " -> group EBIT27 " + " / ".join(f"{b['ebit_grp27'][k] / bn:.2f}" for k in TIERS)
          + " -> NI27 " + " / ".join(f"{b['ni27'][k] / bn:.3f}" for k in TIERS) + "bn"
          + f"  | others@FY26E {(b['ebit_grp27']['m'] - b['ni27']['m']) / bn:.2f}bn")
    print(f"NI Gordon : equity_ni {b['equity_ni'] / bn:.3f}bn = IC {v['ic_group_eur'] / bn:.2f} x "
          f"{v['ni_rev_share']:.1%} | g1 {b['g1']:+.2%} (n={int(v['n_g1'])}, 2028E 4-house mean "
          f"{sum(v[f] for f in EPS28_POINTS) / len(EPS28_POINTS):.4f} EUR) | g2 {v['g2_ni']:.1%} | "
          f"r {v['r_perp']:.0%} | df {c['disc']:.4f} ({v['n_disc_ni']:g}y)")
    for k in TIERS:
        t = c["tiers"][k]
        print(f"  {k.upper()}: ROE {t['roe']:6.2%}  PE {t['pe']:5.2f}x  EV/EBIT-eq {t['evx']:5.2f}x  "
              f"payout1 {t['payout1']:+.2f} payout2 {t['payout2']:.2f}  | NI {t['ev_ni'] * b['unit']:.3f} "
              f"TS {t['ev_ts'] * b['unit']:.3f} RAN {t['ev_mi'] * b['unit']:.3f} close {closing_ps:.3f} "
              f"-> {c[k.upper()]:.4f} USD | NI/EV {t['ev_ni'] / t['ev']:.1%} | group EV/EBIT {t['group_ev_ebit']:.2f}x")
    # 表1 reports the NI leg on the post-transition FY2028 numerator (A2e-3): the
    # FY27-basis PE above folds (1 + g1) into the multiple; divided out it is the
    # steady-state Gordon discounted one year, which is what the cell quotes.
    print("NI 表1    : FY28 NOPAT USD/ADR x FY28-basis multiple (PE / EV/EBIT-eq): "
          + " | ".join(
              f"{k.upper()} {b['ni27'][k] * (1.0 - v['tax_rate']) * (1.0 + b['g1']) * b['unit']:.4f} x "
              f"{c['tiers'][k]['pe'] / (1.0 + b['g1']):.2f}x / {c['tiers'][k]['evx'] / (1.0 + b['g1']):.2f}x"
              for k in TIERS))
    print(f"anchors   : L {c['L']:.2f} · M {c['M']:.2f} · H {c['H']:.2f}  (A {c['A']:.2f} · B {c['B']:.2f})"
          f"  zone@{price} = {z}  (P/H {price / c['H'] - 1:+.1%})")
    print(f"candidate : (2028E·JPM单家高情景, g1_H {b['g1_cand']:+.1%}, payout1 "
          f"{cand['tiers']['h']['payout1']:+.2f}, PE {cand['tiers']['h']['pe']:.2f}x) "
          f"L′ {cand_vals[0]:.2f} · M′ {cand_vals[1]:.2f} · H′ {cand_vals[2]:.2f}  "
          f"zone@{price} = {zone_of(price, *cand_vals)}")

    # A2e-5 decomposition per leg: NI / RAN ladders live in the numerator, TS in
    # its annuity ladder — they must not be read as one ratio.
    nl, nm, nh = (b["ni27"][k] for k in TIERS)
    pl, pm, ph = (c["tiers"][k]["pe"] for k in TIERS)
    print(f"decomp    : L/M {c['L'] / c['M']:.3f} | H/M {c['H'] / c['M']:.3f} | width {(c['H'] - c['L']) / (2 * c['M']):.3f}"
          f" | V_opt/M 0.000\n"
          f"            NI num {nl / nm:.2f}/{nh / nm:.2f} x pe {pl / pm:.2f}/{ph / pm:.2f}"
          f"  TS num 1.00 x pe {v['ev_ebit_ts_l'] / v['ev_ebit_ts_m']:.2f}/{v['ev_ebit_ts_h'] / v['ev_ebit_ts_m']:.2f}"
          f"  RAN num {v['ebit_mi_core_l'] / v['ebit_mi_core_m']:.2f}/{v['ebit_mi_core_h'] / v['ebit_mi_core_m']:.2f} x pe 1.00")
    print(f"flat-@M   : {fmt3(flat)}   (A2e-2c)")
    print(f"guardrail : L-implied group EV/EBIT {l_implied:.2f}x vs trough {trough:.2f}x (③) | "
          f"M {c['tiers']['m']['group_ev_ebit']:.2f}x  H {c['tiers']['h']['group_ev_ebit']:.2f}x")
    g_street, ok_street = implied_g(30.0 / (1.0 - v["tax_rate"]), c["tiers"]["m"]["roe"], v["r_perp"])
    print(f"cross     : street Optical+IP 30x EV/EBIT = {30.0 / (1.0 - v['tax_rate']):.1f}x PE -> implied g "
          f"{g_street:+.2%} (well_conditioned={ok_street}) | perpetual-only PE_M (no g1) "
          f"{perpetual_pe(v['g2_ni'], c['tiers']['m']['roe'], v['r_perp']):.2f}x")

    print("\nimplied NI FY2027E EBIT (TS/RAN/corp at M, NI multiple re-solved on implied ROE):")
    span = nh - nl
    for label, px in (("price", price), ("B", c["B"]), ("H", c["H"]),
                      ("sell-side TP mean 14.96", 14.96), ("52w high 16.85", 16.85)):
        ni, pe = implied_ni27(px, v, b, c)
        print(f"  {label:<24} ${px:6.2f} -> {ni / bn:5.2f}bn EUR  (PE {pe:.1f}x, position in [L,H] {(ni - nl) / span:+.2f})")

    print("\ng2 leverage (valuation-rules「g2 的杠杆 MUST 显式」; evidence range collapsed on the cap):")
    for g2 in (v["g2_ni"], v["g2_ni"] - G2_SENSITIVITY_PP, v["g2_ni"] - 2 * G2_SENSITIVITY_PP):
        cg = compute(v, b, g2=g2)
        tag = "current" if abs(g2 - v["g2_ni"]) < 1e-12 else f"{(g2 - v['g2_ni']) * 100:+.0f}pp"
        print(f"  g2 {g2:.1%} ({tag:7}): {fmt3(cg)}  A/B {cg['A']:.2f} / {cg['B']:.2f}"
              f"  zone@{price} = {zone_of(price, cg['L'], cg['M'], cg['H'])}")

    print("\nsensitivity:")
    # A2e-3 对照带: the extra one-year discount retired on 2026-09-14 (it would
    # now double-count the t=1 placement inside two_stage_pe).
    c2 = compute(v, b, disc_years=1)
    print(f"  NI extra 1y discount (retired policy, 对照带): {fmt3(c2)}  zone = {zone_of(price, c2['L'], c2['M'], c2['H'])}")
    for mult in (v["ev_ebit_mi"] - 1, v["ev_ebit_mi"] + 1):
        c2 = compute(v, b, ran_mult=mult)
        print(f"  RAN flat {mult:g}x: {fmt3(c2)}  zone = {zone_of(price, c2['L'], c2['M'], c2['H'])}")
    old_ts = {"l": 10.0, "m": 14.45, "h": 18.9}
    c2 = compute(v, b, ts_mult=old_ts)
    c3 = compute(v, b, ts_mult=old_ts, g2=v["g2_ni"] - G2_SENSITIVITY_PP)
    print(f"  TS prior ladder 10/14.45/18.9 (unsourced midpoint, retired): {fmt3(c2)}  zone = {zone_of(price, c2['L'], c2['M'], c2['H'])}"
          f"  | at g2 -1pp: {fmt3(c3)} zone = {zone_of(price, c3['L'], c3['M'], c3['H'])}")
    for m in (0.60, v["ts_margin"], 0.78):
        v2 = dict(v, ts_margin=m, ebit_mi_core_m=v["ebit_group_fy26"] - v["ebit_ni_fy26"]
                  - v["ts_sales_rr"] * m - v["ebit_pb_fy26"] - v["ebit_corp_fy26"])
        c2 = compute(v2, bridge(v2))
        print(f"  ts_margin {m:.2f} (MI-core M absorbs): M {c2['M']:.2f}")
    for share in (v["ni_rev_share"] - 0.10, v["ni_rev_share"] + 0.10):
        v2 = dict(v, ni_rev_share=share)
        c2 = compute(v2, bridge(v2))
        print(f"  ni_rev_share {share:.3f} (A7a ±10pp): {fmt3(c2)}  zone = {zone_of(price, c2['L'], c2['M'], c2['H'])}")
    for fx in (1.14,):
        v2 = dict(v, fx_eur_usd=fx)
        c2 = compute(v2, bridge(v2))
        print(f"  fx_eur_usd {fx:.4f}: {fmt3(c2)}  zone = {zone_of(price, c2['L'], c2['M'], c2['H'])}")
    v2 = dict(v, shares=5.8019e9)
    c2 = compute(v2, bridge(v2))
    print(f"  diluted shares 5.8019e9: {fmt3(c2)}")
    c2 = compute(v, b, ni_evebit_flat=30.0)
    print(f"  street NI 30x EV/EBIT flat (BofA, cross only): {fmt3(c2)}  zone = {zone_of(price, c2['L'], c2['M'], c2['H'])}")
    # No g1 at all: FY27 NOPAT straight into perpetual_pe (next-period base), the
    # reading A7b quotes for "what the 2028E points are worth".
    perp = {k: perpetual_pe(v["g2_ni"], c["tiers"][k]["roe"], v["r_perp"]) for k in TIERS}
    perp_vals = {
        k.upper(): (b["ni27"][k] * (1.0 - v["tax_rate"]) * perp[k] * c["disc"]
                    + c["tiers"][k]["ev_ts"] + c["tiers"][k]["ev_mi"] + b["ev_corp"] + b["adj"]) * b["unit"]
        for k in TIERS
    }
    print(f"  no g1 (perpetual_pe on FY27 NOPAT, PE "
          + " / ".join(f"{perp[k]:.2f}" for k in TIERS)
          + f"x): {perp_vals['L']:.2f} / {perp_vals['M']:.2f} / {perp_vals['H']:.2f}")

    print("\nchecks:")
    failed = False
    for ok, label in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        failed |= not ok
    if failed:
        sys.exit(1)
    print("OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
