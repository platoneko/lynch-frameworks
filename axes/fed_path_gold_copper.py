"""历史金铜共享情景草稿；只提供共同数据，不确认或发布任何个股估值。"""

from datetime import date
from math import isfinite

# 原轴题头研究日期为 2026-09-23，2026-09-25 的事件复核未改三档；
# 这两个日期用于识别历史来源，不说明新计算已完成来源复核。
HISTORICAL_LAST_REVIEW_DATE = "2026-09-25"
# 伦金美元/盎司：L=2026-06-30 加息预期下实测低点，汇丰 95352；
# M=2026H1 紫金实现价反推，H=花旗/美银/汇丰等 2027 年预测簇，
# Wisburg 101558、101483、104106、95352，2026-08 至 09。
GOLD_USD_PER_OUNCE = {"L": 3942.0, "M": 4693.0, "H": 5000.0}

# 伦铜美元/吨：L=2025H1 LME 实测均价，M=2026H1 LME 均价，
# 均由两家公司的中报引用；H=美银 2027E 上沿，Wisburg 101471，
# 同簇另有花旗与 JPM 15,000 美元/吨，资料日期为 2026-08 至 09。
COPPER_USD_PER_TONNE = {"L": 9431.05, "M": 13083.97, "H": 15250.0}
_PRICE_UNITS = {"gold": "USD_PER_TROY_OUNCE", "copper": "USD_PER_METRIC_TONNE"}

# 原轴依次将 L/M/H 命名为加息、维持、降息但不衰退；它们与铝轴
# 题头采用同一宏观命名。铝轴另一张 2×2 表对 L 的“利率维持”描述
# 存在历史张力，不能只因标签一致就声称该差异已解决。
MACRO_PATH = {"L": "rate_hike", "M": "rate_hold", "H": "rate_cut_without_recession"}

# 原研究各价格的观察或预测期间不同；这些是历史标注，不自动证明
# 新计算所用来源及期间。研究者更新价格时应重新核对并同步本标注。
_HISTORICAL_PRICE_PERIODS = {
    "gold": {"L": "2026-06-30", "M": "2026-H1", "H": "2027"},
    "copper": {"L": "2025-H1", "M": "2026-H1", "H": "2027"},
}

# 2026-09-13 杰富瑞《铜：缺失的吨位》（Wisburg 105401）：2025–2030E
# 全球铜需求年复合增长 2.6%。这是轴的共同参考，不是金铜价格增长，
# 也不自动作为任何股票的永续增长率；2026-06 IEA 长期参考约 1.5%。
DEMAND_GROWTH_REFERENCE = 0.026

# 原研究 2026-09-14 对 25 家金铜生产商做同日横截面反推，中位 2.76%；
# 铜 10 家中位 5.25%，金 15 家中位 -0.04%。为避免不同单位、极点和
# 业务范围扭曲样本，排除伦敦 GBp 计价、IVN 极点附近、TECK 回报接近
# 折现率、BHP/RIO 综合矿业及两家挂载票。原始私人样本能否重建仍待核；
# 后来的个股实际采用值为 2.5%，2.76% 只作历史印证，不由本轴自动采用。

# 2026-09-19 的历史卖方共识位置：2027 金花旗/美银/汇丰 5,000 美元，
# 铜瑞银 13,779 至美银 15,250 美元；该位置不是实时共识。数据缺失时
# 允许设置为 None，消费方应显示未标注或待更新，不得回退解析本文。
HISTORICAL_CONSENSUS = {"band": "M-H", "as_of": "2026-09-19"}
AXIS_ID = "fed-path-gold-copper"

# 历史敏感情景不是新预测：JPM 2026-09-11 关税套利结束后 12,000
# 美元/吨；摩根士丹利同日/09-18 的 12,600 仅为交叉参考。
TARIFF_CLEARANCE_COPPER_USD_PER_TONNE = 12000.0
TARIFF_CLEARANCE_CROSSCHECK_USD_PER_TONNE = 12600.0

# 旧轴的衰退对照曾记录紫金 28.39、洛钼 9.79 元；后者以 2026-10-25
# 钴业务与少数股东口径计算，此前为 10.42。紫金/洛钼金毛利占比约
# 42%/4%，两项对照相对各自旧 L 档约高 30%/7%。更早的 30.50、
# 15.10/13.09 使用 2026-09-21 前的当期稳态分子：当时紫金三档为
# 22.65/33.09/38.64、洛钼为 9.32/16.77/21.83；这些只是历史记录，
# 不能用作当前估值或作为自动重算的基准。

# 原轴头寸分类：华友仅引用铜腿、只向中/高档传导；其低档仍与轴铜价
# 核对，但低档利润使用自身实绩。银价按金价三档等比例缩放，不构造
# 独立银价梯；招金只挂金。若锚点改年，收益分子要由各票重新审阅。
# 紫金与洛钼虽共同使用金铜梯，项目资本、销量、成本和所得税各自持有。
_STOCK_SCOPES = {
    "601899.SH": ("priced", ("gold", "copper")),
    "603993.SH": ("priced", ("gold", "copper")),
    "1787.HK": ("priced", ("gold",)),
    "603799.SH": ("reference", ("copper",)),
}
_REFERENCE_GROWTH_USERS = ("601899.SH", "603993.SH", "1787.HK")
_STOCK_PRICE_FIELD_PREFIXES = {
    "601899.SH": {"gold": "lme_au", "copper": "lme_cu"},
    "603993.SH": {"gold": "lme_au", "copper": "p_cu"},
    "1787.HK": {"gold": "lme_au"},
    "603799.SH": {"copper": "p_cu"},
}

# 铝价差业务依赖铜价 H/M 上行幅度来校验铝价上行幅度；这是跨轴
# 约束，不把这些票错误标为金铜轴定档挂载。双方价格比由消费者计算，
# 不能固化为第二份独立数值，也不能以金铜轴替代铝轴的价格或期限。
_ALUMINIUM_CROSS_AXIS = ("000933.SZ", "002532.SZ", "601600.SH", "1378.HK")


def _checked_macro_path():
    # The old axis fixes each tier's world, not merely the set of labels.
    # A deliberate change to that research decision requires revisiting this
    # rule and affected consumers; it does not resolve the aluminium L issue.
    expected = {"L": "rate_hike", "M": "rate_hold", "H": "rate_cut_without_recession"}
    if not isinstance(MACRO_PATH, dict) or MACRO_PATH != expected:
        raise ValueError("gold-copper axis needs the declared L/M/H macro mapping")
    return dict(MACRO_PATH)


def axis_metadata():
    """Historical axis identity for a future unified metadata consumer."""
    consensus = HISTORICAL_CONSENSUS
    if consensus is not None:
        if (not isinstance(consensus, dict) or set(consensus) != {"band", "as_of"}
                or not isinstance(consensus["band"], str)
                or consensus["band"] not in {"L", "M", "H", "L-M", "M-H", "<L", ">H"}
                or not isinstance(consensus["as_of"], str) or not consensus["as_of"]):
            raise ValueError("invalid historical consensus metadata")
        try:
            if date.fromisoformat(consensus["as_of"]).isoformat() != consensus["as_of"]:
                raise ValueError("invalid historical consensus date")
        except ValueError as exc:
            raise ValueError("invalid historical consensus date") from exc
        consensus = dict(consensus)
    return {"axis_id": AXIS_ID, "logical_id": f"_AXIS.{AXIS_ID}", 'title': '金铜 USD 价格情景轴（美联储利率路径）', 'label': '金铜价格', "axis_type": "shared_scenario_axis",
            "macro_path": _checked_macro_path(),
            "priced_mounts": [ticker for ticker, (role, _) in _STOCK_SCOPES.items() if role == "priced"],
            "reference_mounts": [ticker for ticker, (role, _) in _STOCK_SCOPES.items() if role == "reference"],
            "historical_consensus": consensus, "historical_last_review_as_of": HISTORICAL_LAST_REVIEW_DATE}


def _checked_prices(metal):
    if metal not in ("gold", "copper"):
        raise ValueError(f"{metal}: unsupported gold-copper metal")
    values = GOLD_USD_PER_OUNCE if metal == "gold" else COPPER_USD_PER_TONNE
    if not isinstance(values, dict) or set(values) != {"L", "M", "H"}:
        raise ValueError(f"{metal}: expected exactly L, M and H prices")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or v <= 0
           for v in values.values()):
        raise ValueError(f"{metal}: prices must be finite and positive")
    if not values["L"] < values["M"] < values["H"]:
        raise ValueError(f"{metal}: prices must increase L < M < H")
    return dict(values)


def _ticker_metadata(role):
    metadata = axis_metadata()
    metadata["role"] = role
    # The old axis only assigns its historical consensus to priced mounts.
    if role != "priced":
        metadata["historical_consensus"] = None
    return metadata


def inputs(ticker):
    """Return this consumer's declared historical prices and reference growth."""
    if ticker in _ALUMINIUM_CROSS_AXIS:
        return {"role": "cross_axis_constraint", "prices": {"copper": _checked_prices("copper")},
                "units": {"copper": _PRICE_UNITS["copper"]},
                "macro_path": _checked_macro_path(),
                "historical_price_periods": {"copper": dict(_HISTORICAL_PRICE_PERIODS["copper"])},
                "axis_metadata": _ticker_metadata("cross_axis_constraint"),
                "comparison_scenarios": {},
                "historical_last_review_as_of": HISTORICAL_LAST_REVIEW_DATE}
    if ticker not in _STOCK_SCOPES:
        raise ValueError(f"{ticker}: not a declared gold-copper consumer")
    role, metals = _STOCK_SCOPES[ticker]
    result = {"role": role, "prices": {metal: _checked_prices(metal) for metal in metals},
              "units": {metal: _PRICE_UNITS[metal] for metal in metals},
              "macro_path": _checked_macro_path(),
              "historical_price_periods": {metal: dict(_HISTORICAL_PRICE_PERIODS[metal]) for metal in metals},
              "historical_last_review_as_of": HISTORICAL_LAST_REVIEW_DATE}
    if ticker in _REFERENCE_GROWTH_USERS:
        if (isinstance(DEMAND_GROWTH_REFERENCE, bool) or
                not isinstance(DEMAND_GROWTH_REFERENCE, (int, float)) or
                not isfinite(DEMAND_GROWTH_REFERENCE)):
            raise ValueError("gold-copper demand growth reference must be finite")
        result["axis_g2_aucu"] = DEMAND_GROWTH_REFERENCE
    # Each alias is derived from the same snapshot; a stock's adopted g2 is
    # intentionally absent. The unified runner passes only inputs(), not the
    # axis module itself, to each consumer.
    result["stock_fields"] = {
        f"{prefix}_{tier.lower()}": result["prices"][metal][tier]
        for metal, prefix in _STOCK_PRICE_FIELD_PREFIXES[ticker].items()
        for tier in ("L", "M", "H")
    }
    if "axis_g2_aucu" in result:
        result["stock_fields"]["axis_g2_aucu"] = result["axis_g2_aucu"]
    result["axis_metadata"] = _ticker_metadata(role)
    # These are scenario inputs only. Whether or how to calculate a comparison
    # belongs to the stock; they are never appended to the base anchors here.
    result["comparison_scenarios"] = comparison_scenarios(ticker)["scenarios"]
    return result


def comparison_scenarios(ticker):
    """Return only the ticker's historical comparison inputs, never base rungs."""
    if ticker not in _STOCK_SCOPES:
        raise ValueError(f"{ticker}: no declared gold-copper comparison scope")
    _checked_macro_path()
    units = {metal: _PRICE_UNITS[metal] for metal in _STOCK_SCOPES[ticker][1]}
    if ticker == "1787.HK":
        # Gold benefits in the old narrative, but no complete numerical
        # comparison was specified for this company.
        return {"ticker": ticker, "units": units, "scenarios": {}}
    gold = _checked_prices("gold") if ticker in ("601899.SH", "603993.SH") else None
    copper = _checked_prices("copper")
    independent = (TARIFF_CLEARANCE_COPPER_USD_PER_TONNE,
                   TARIFF_CLEARANCE_CROSSCHECK_USD_PER_TONNE)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or v <= 0
           for v in independent):
        raise ValueError("tariff-clearance reference prices must be finite and positive")
    scenarios = {}
    if ticker in ("601899.SH", "603993.SH"):
        # Each company retains its own L-tier production achievement and all
        # other L-tier conditions; only the market prices change.
        scenarios["recession_rate_cut"] = {
            "prices": {"gold": gold["H"], "copper": copper["L"]},
            "macro_case": "rate_cut_recession",
            "reference_tier": "L", "achievement_tier": "L", "non_price_basis": "company_L",
            "comparison_only": True,
        }
    if ticker in ("601899.SH", "603993.SH", "603799.SH"):
        # All of the company's M-tier conditions remain fixed; only copper
        # changes.  Availability here does not override any stock's BLOCKED.
        prices = {"copper": independent[0]}
        if gold is not None:
            prices["gold"] = gold["M"]
        scenarios["tariff_clearance"] = {
            "prices": prices,
            "macro_case": "rate_hold",
            "copper_crosscheck": independent[1], "reference_tier": "M",
            "non_price_basis": "company_M", "changed_price": "copper", "comparison_only": True,
        }
    return {"ticker": ticker, "units": units, "scenarios": scenarios}
