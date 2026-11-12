"""原非洲共同参考只约定各档长期增长，不提供利润或具名项目。"""

# 原轴 2026-10-04：世界银行撒哈拉以南非洲美元现价 GDP 按年均汇率
# 换算为人民币。2010–2025 和 2014–2025 年年增 3.17% / 2.83%，
# 取中档 3%；2004–2025 年 4.90%，取高档 5%；低档 0% 低于最差十年。
# 公开项目仍归各票，不能再用永续增长重复计入。
GROWTH = {"l": 0.0, "m": 0.03, "h": 0.05}
MOUNTS = {"6655.HK": "ovs", "600499.SH": "afr", "603871.SH": "afr"}


def inputs(ticker):
    if ticker not in MOUNTS:
        raise ValueError(f"{ticker}: not an Africa axis mount")
    if set(GROWTH) != {"l", "m", "h"} or not GROWTH["l"] < GROWTH["m"] < GROWTH["h"]:
        raise ValueError("Africa growth rungs invalid")
    return {
        **{f"g2_{MOUNTS[ticker]}_{tier}": value for tier, value in GROWTH.items()},
        "axis_metadata": {
            "axis_id": "africa-corridor",
            "logical_id": "_AXIS.africa-corridor",
            "axis_type": "shared_scenario_axis",
            "title": "非洲建材与矿业通道情景轴",
            "label": "非洲建材与矿业通道",
            "role": "priced",
            "priced_mounts": list(MOUNTS),
            "reference_mounts": [],
            "historical_last_review_as_of": "2026-10-04",
            "historical_consensus": None,
        },
    }
