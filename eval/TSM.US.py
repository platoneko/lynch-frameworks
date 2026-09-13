#!/usr/bin/env python3
"""TSM.US valuation eval — recompute anchors from frameworks/TSM.US.md.

formula_id: tsm_sotp_2028_two_stage_v4

2028E EPS bridge × Gordon multiples (L: perpetual g2; M/H: two-stage g1/n/g2),
B1 = max(CoWoS capacity×UV, adv EPS×PE), discount n_disc years; COUPE V_k
from _AXIS.optical-comms OE × $450 × share × npm × same-tier PE.

Run:  python3 eval/TSM.US.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.lib.axes import (  # noqa: E402
    check_cowos_supply,
    check_optical_narrow_attach,
    check_optical_oe_mount,
)
from eval.lib.gordon import check_r, perpetual_pe, two_stage_pe  # noqa: E402

FRAMEWORK = Path(__file__).resolve().parent.parent / "frameworks" / "TSM.US.md"
TOL = 0.15


def parse_inputs(md: str) -> dict[str, float]:
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
        if raw in ("待补", ""):
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


def main() -> int:
    md = FRAMEWORK.read_text(encoding="utf-8")
    inp = parse_inputs(md)
    required = [
        "price",
        "shares_adr",
        "eps_2027e",
        "growth_2028_l",
        "growth_2028_m",
        "growth_2028_h",
        "share_wafer",
        "share_adv",
        "share_other",
        "npm_2027e_l",
        "npm_2027e_m",
        "g1",
        "n_stage",
        "g2",
        "roe",
        "r",
        "n_disc",
        "r_disc",
        "cowos_wpm_l",
        "cowos_wpm_m",
        "cowos_wpm_h",
        "uv_per_10k_wpm",
        "oe_l",
        "oe_m",
        "oe_h",
        "asp_oe",
        "coupe_share_l",
        "coupe_share_m",
        "coupe_share_h",
        "npm_coupe",
    ]
    missing = [k for k in required if k not in inp]
    if missing:
        print("missing inputs:", ", ".join(missing), file=sys.stderr)
        return 1

    errors: list[str] = []
    errors.extend(check_r(inp["r"], "r"))
    errors.extend(check_r(inp["r_disc"], "r_disc"))

    share_sum = inp["share_wafer"] + inp["share_adv"] + inp["share_other"]
    if abs(share_sum - 1.0) > 1e-6:
        errors.append(f"shares sum {share_sum} != 1")

    # r - g1 critical band warning (still compute)
    if inp["r"] - inp["g1"] < 0.02 - 1e-12:
        errors.append(f"r-g1={inp['r']-inp['g1']:.4f} < 2% (ill-conditioned)")

    pe_l = perpetual_pe(inp["g2"], inp["roe"], inp["r"])
    pe_mh = two_stage_pe(
        inp["g1"], int(inp["n_stage"]), inp["g2"], inp["roe"], inp["r"]
    )
    df = (1.0 + inp["r_disc"]) ** (-inp["n_disc"])

    def eps_consol(tier: str) -> float:
        g = inp[f"growth_2028_{tier}"]
        e = inp["eps_2027e"] * g
        if tier == "l":
            e *= inp["npm_2027e_l"] / inp["npm_2027e_m"]
        return e

    def pe(tier: str) -> float:
        return pe_l if tier == "l" else pe_mh

    def capacity(wpm: float) -> float:
        return (wpm / 10000.0) * inp["uv_per_10k_wpm"] / inp["shares_adr"]

    legs: dict[str, dict[str, float]] = {}
    for tier in ("l", "m", "h"):
        e = eps_consol(tier)
        p = pe(tier)
        pa = e * inp["share_wafer"] * p
        floor = e * inp["share_adv"] * p
        cap = capacity(inp[f"cowos_wpm_{tier}"])
        pb1 = max(cap, floor)
        pb2 = e * inp["share_other"] * p
        und = pa + pb1 + pb2
        legs[tier] = {
            "eps": e,
            "pe": p,
            "Pa": pa,
            "Pb1": pb1,
            "Pb2": pb2,
            "cap": cap,
            "floor": floor,
            "X": und,
            "disc": und * df,
        }

    L, M, H = legs["l"]["disc"], legs["m"]["disc"], legs["h"]["disc"]
    if not (L < M < H):
        errors.append(f"invariant L<M<H failed: {L=:.4f} {M=:.4f} {H=:.4f}")

    A = (L + M) / 2
    B = (M + H) / 2
    z = zone_of(inp["price"], L, M, H)

    for err in check_optical_oe_mount((inp["oe_l"], inp["oe_m"], inp["oe_h"])):
        errors.append(f"optical axis: {err}")
    if abs(inp["asp_oe"] - 450.0) > 1e-9:
        errors.append(f"asp_oe={inp['asp_oe']} must be 450 (GS CPO OE BoM)")
    if not (inp["coupe_share_l"] < inp["coupe_share_m"] < inp["coupe_share_h"]):
        errors.append(
            f"coupe_share order: {inp['coupe_share_l']}/{inp['coupe_share_m']}/{inp['coupe_share_h']}"
        )
    if inp["coupe_share_h"] > 1.0 + 1e-12:
        errors.append(f"coupe_share_h={inp['coupe_share_h']} > 100%")

    coupe_rev = {
        t: inp[f"oe_{t}"] * inp["asp_oe"] * inp[f"coupe_share_{t}"]
        for t in ("l", "m", "h")
    }
    for err in check_optical_narrow_attach(
        {t.upper(): coupe_rev[t] for t in ("l", "m", "h")}
    ):
        errors.append(f"COUPE narrow: {err}")

    v_k = {
        t: (coupe_rev[t] * inp["npm_coupe"] / inp["shares_adr"]) * pe(t) * df
        for t in ("l", "m", "h")
    }

    out_sec = md.split("### Outputs", 1)[-1] if "### Outputs" in md else md
    leaked = [k for k in inp if k == "p" or k.startswith("p_")]
    if leaked:
        errors.append(f"p-class fields must not appear in Inputs: {leaked}")

    triples = re.findall(
        r"L = \*\*[0-9.]+\*\* · M = \*\*[0-9.]+\*\* · H = \*\*[0-9.]+\*\*", out_sec
    )
    if len(triples) != 1:
        errors.append(f"L/M/H triple must appear once in Outputs, found {len(triples)}")

    stated: dict[str, float] = {}
    m = re.search(
        r"L\s*=\s*\*\*([0-9.]+)\*\*\s*·\s*M\s*=\s*\*\*([0-9.]+)\*\*\s*·\s*H\s*=\s*\*\*([0-9.]+)\*\*",
        out_sec,
    )
    if m:
        stated["L"], stated["M"], stated["H"] = map(float, m.groups())
    m2 = re.search(
        r"A\s*=\s*\*\*([0-9.]+)\*\*\s*·\s*B\s*=\s*\*\*([0-9.]+)\*\*", out_sec
    )
    if m2:
        stated["A"], stated["Bcut"] = map(float, m2.groups())
    mz = re.search(r"zone\s*=\s*\*\*`([a-z_]+)`\*\*", out_sec)
    stated_zone = mz.group(1) if mz else None

    vt = re.search(
        r"V_L/V_M/V_H\\\)\s*=\s*\*\*([0-9.]+)\s*/\s*([0-9.]+)\s*/\s*([0-9.]+)\*\*",
        out_sec,
    )
    if vt is None:
        errors.append("V_L/V_M/V_H not stated")
    else:
        for name, got, exp in zip(
            ("V_L", "V_M", "V_H"),
            (float(x) for x in vt.groups()),
            (v_k["l"], v_k["m"], v_k["h"]),
        ):
            if abs(got - exp) > TOL:
                errors.append(f"{name}: stated {got} vs {exp:.4f}")

    zv = re.findall(
        r"\|\s*[LMH]\s*\|\s*[0-9.]+\s*\|\s*\*\*[0-9.]+×\*\*\s*\|\s*([0-9.]+)\s*\|\s*\*\*([0-9.]+)\*\*",
        out_sec,
    )
    if len(zv) != 3:
        errors.append(f"表3 must have 3 rows, found {len(zv)}")
    else:
        for (vk_s, adj_s), tier in zip(zv, ("l", "m", "h")):
            base = legs[tier]["disc"]
            if abs(float(vk_s) - v_k[tier]) > TOL:
                errors.append(f"表3 V_{tier}: {vk_s} vs {v_k[tier]:.4f}")
            if abs(float(adj_s) - (base + v_k[tier])) > TOL:
                errors.append(
                    f"表3 adj_{tier}: {adj_s} vs {base + v_k[tier]:.4f}"
                )

    print("recomputed:")
    print(f"  PE_L={pe_l:.4f}  PE_M/H={pe_mh:.4f}  df={df:.6f}")
    for t in ("l", "m", "h"):
        lg = legs[t]
        print(
            f"  {t}: eps={lg['eps']:.2f} pe={lg['pe']:.2f}  "
            f"wafer={lg['Pa']*df:.1f} B1={lg['Pb1']*df:.1f} "
            f"(max cap {lg['cap']:.1f}/floor {lg['floor']:.1f}) "
            f"B2={lg['Pb2']*df:.1f} sum={lg['disc']:.1f}"
        )
    print(f"  L/M/H = {L:.1f}/{M:.1f}/{H:.1f}")
    print(f"  A/B   = {A:.1f}/{B:.1f}")
    print(f"  zone  = {z} (price={inp['price']})")
    print(
        f"  COUPE V = {v_k['l']:.1f}/{v_k['m']:.1f}/{v_k['h']:.1f}  "
        f"zone+V = {L+v_k['l']:.1f}/{M+v_k['m']:.1f}/{H+v_k['h']:.1f}"
    )

    ok = True
    for err in errors:
        print(f"MISMATCH: {err}", file=sys.stderr)
        ok = False
    for err in check_cowos_supply(inp["cowos_wpm_m"]):
        print(f"MISMATCH axis: {err}", file=sys.stderr)
        ok = False
    for key, got in (("L", L), ("M", M), ("H", H), ("A", A), ("Bcut", B)):
        if key not in stated:
            print(f"mismatch {key}: not found in Outputs", file=sys.stderr)
            ok = False
            continue
        if abs(stated[key] - got) > TOL:
            print(
                f"mismatch {key}: stated={stated[key]} recomputed={got:.4f}",
                file=sys.stderr,
            )
            ok = False
    if stated_zone != z:
        print(f"mismatch zone: stated={stated_zone} recomputed={z}", file=sys.stderr)
        ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
