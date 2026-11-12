"""电池级碳酸锂共同情景；值、来源与原研究判断均保存在此。"""

# 单位：国内电池级碳酸锂含税现货，CNY/吨；轴研究更新至 2026-10-20。
# 2026-10-12 确定的换算：美元未税值乘 2026H1 均汇 6.8645 和税率
# 系数 1.13；人民币含税原值不换算。德银数据以同期历史读数对照后
# 判为含税美元口径，只乘汇率（2026-10-20）。这是历史换算口径。
# L：2028 供过于求情景的暂定底价。BMI/Fitch 2028 底价按当时口径
# 折为 11.3 万（2026-08-28），高盛折为 8.5 万（2026-10-06）；
# 10.3 万介于两者，等待第三个同一过剩情景的来源。原研究保留旧值，
# 没有把德银紧平衡世界的 2028 预测当成第三个过剩底价。
# M：9 月后发布的 2027 均价，高盛 10.6 万（10-06）、德银 11.8 万
# （10-15）、美银 12.0 万（10-01）、瑞银 12.0 万（09-23），按含税
# 口径汇集的中位 11.9 万；按 0.5 万元档取整为 12.0 万（2026-10-20）。
# H：2026 平台延续至 2027，参考高盛周报 14.0–15.8 万区间和 SMM
# 较早发布的 2027 年均价 15 万。2026-10-20 复核时现货已跌破平台，
# 原研究以供给中断承载此情景，并记录缺少下跌后新预测的风险。
RUNG_CNY_PER_TONNE = {"L": 103_000, "M": 120_000, "H": 150_000}
# 2026-09-14 的轴引用增长率：IEA 2026 年展望中 2025–2040 锂需求
# 超过 3 倍，SMM 经瑞银转述的 2026–2030 锂电需求年增约 20%；原研究
# 因两者均高于 6% 上限而截到 6%。这是被引用的上限值，不自动等于
# 任何票实际采用的增长率；来源日期分别为 2026-06 和 2026-08-17。
REFERENCED_G2 = 0.06
# 历史参考：2026-09-14 锂生产商 SQM、PLS、IGO、中矿四家良态反解
# 中位 2.35%。原轴历史文字与后续个股采用值存在差异，本值不自动采用。
PEER_G2 = 0.0235
# 用户 2026-10-16 确定 H 高价只维持一年，随后锂腿回 M；非锂腿
# 保留自身 H 情景。2026-10-18 盐湖锂腿、2026-10-19 紫金锂腿落盘。
H_DURATION_YEARS = 1
H_AFTER = "M"
H_SCOPE = "lithium"
# 原轴题头将 M 设为共识，L 标为两源夹逼暂定；非实时市场判断。
CONSENSUS = "M"
L_STATUS = "tentative"
PRICE_UNIT = "CNY/tonne, domestic battery-grade spot including tax"
RUNG_PERIODS = {"L": "2028 surplus", "M": "2027 consensus", "H": "2026 platform extended into 2027"}
# 依据原轴 2026-10-20 题头：五只定档挂载，紫金仅锂腿参照；
# 名单不表示可重算已归档票，也不构成结果确认。
MOUNTS = ("9696.HK", "000792.SZ", "ALB.US", "1772.HK", "600499.SH")
REFERENCES = ("601899.SH",)


def inputs(ticker):
    """Shared numerical inputs for the explicitly mounted ticker."""
    if ticker not in (*MOUNTS, *REFERENCES):
        raise ValueError(f"{ticker}: not a lithium axis mount")
    if set(RUNG_CNY_PER_TONNE) != {"L", "M", "H"}:
        raise ValueError("missing or unexpected lithium axis rungs")
    if not 0 < RUNG_CNY_PER_TONNE["L"] < RUNG_CNY_PER_TONNE["M"] < RUNG_CNY_PER_TONNE["H"]:
        raise ValueError("lithium axis rungs not ordered")
    if isinstance(H_DURATION_YEARS, bool) or not isinstance(H_DURATION_YEARS, int) or H_DURATION_YEARS < 1:
        raise ValueError("lithium H duration must be a positive whole number of years")
    if ticker != "600499.SH" and H_DURATION_YEARS != 1:
        raise ValueError("lithium H duration must be one year for these models")
    if H_AFTER != "M" or H_SCOPE != "lithium":
        raise ValueError("lithium H return or scope is incompatible with these models")
    if CONSENSUS != "M":
        raise ValueError("lithium consensus must be M for these models")
    result = {**{f"li2co3_{tier.lower()}": value for tier, value in RUNG_CNY_PER_TONNE.items()},
              "axis_g2_li": REFERENCED_G2}
    result['axis_metadata'] = {
        'axis_id': 'lithium-carbonate', 'logical_id': '_AXIS.lithium-carbonate',
        'title': '电池级碳酸锂 CNY 价格情景轴', 'label': '电池级碳酸锂价格', 'axis_type': 'shared_scenario_axis', 'role': 'priced' if ticker in MOUNTS else 'reference',
        'priced_mounts': list(MOUNTS), 'reference_mounts': list(REFERENCES),
        'historical_last_review_as_of': '2026-10-20',
        'historical_consensus': {'band':'M', 'as_of':'2026-10-15'} if ticker in MOUNTS else None,
    }
    if ticker == "600499.SH":
        result.update(h_duration_years=H_DURATION_YEARS, h_after=H_AFTER, h_scope=H_SCOPE)
    return result
