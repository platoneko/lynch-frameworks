# 标的与轴索引

> 由 `scripts/gen_index.py` 从 `frameworks/*.md` 与 `frameworks/axes/*.md` 题头生成；勿手改。
> 轴的稳定引用写逻辑 id `` `_AXIS.<名>` ``；文件在 `axes/<名>.md`。

## 美股

- [AEHR.US](./AEHR.US.md)
- [ALB.US](./ALB.US.md)
- [AVGO.US](./AVGO.US.md)
- [BE.US](./BE.US.md)
- [COHR.US](./COHR.US.md)
- [GFS.US](./GFS.US.md)
- [GLW.US](./GLW.US.md)
- [GOOG.US](./GOOG.US.md)
- [INTC.US](./INTC.US.md)
- [LITE.US](./LITE.US.md)
- [MRVL.US](./MRVL.US.md)
- [NOK.US](./NOK.US.md)
- [NVDA.US](./NVDA.US.md)
- [ORCL.US](./ORCL.US.md)
- [QCOM.US](./QCOM.US.md)
- [SOFI.US](./SOFI.US.md)
- [TSEM.US](./TSEM.US.md)
- [TSM.US](./TSM.US.md)
- [WOLF.US](./WOLF.US.md)

## 港股

- [0189.HK](./0189.HK.md) — 东岳集团
- [0700.HK](./0700.HK.md) — 腾讯控股
- [0728.HK](./0728.HK.md) — 中国电信
- [0857.HK](./0857.HK.md) — 中国石油股份
- [0883.HK](./0883.HK.md) — 中国海洋石油
- [1072.HK](./1072.HK.md) — 东方电气
- [1378.HK](./1378.HK.md) — 中国宏桥
- [1766.HK](./1766.HK.md) — 中国中车
- [1772.HK](./1772.HK.md) — 赣锋锂业
- [1810.HK](./1810.HK.md) — 小米集团
- [1898.HK](./1898.HK.md) — 中煤能源
- [2631.HK](./2631.HK.md) — 天岳先进
- [6655.HK](./6655.HK.md) — 华新建材
- [9696.HK](./9696.HK.md) — 天齐锂业
- [9988.HK](./9988.HK.md) — 阿里巴巴集团

## A股

- [000100.SZ](./000100.SZ.md) — TCL科技
- [000338.SZ](./000338.SZ.md) — 潍柴动力
- [000543.SZ](./000543.SZ.md) — 皖能电力
- [000725.SZ](./000725.SZ.md) — 京东方A
- [000792.SZ](./000792.SZ.md) — 盐湖股份
- [000933.SZ](./000933.SZ.md) — 神火股份
- [002532.SZ](./002532.SZ.md) — 天山铝业
- [002895.SZ](./002895.SZ.md) — 川恒股份
- [002897.SZ](./002897.SZ.md) — 意华股份
- [159263.SZ](./159263.SZ.md) — 易方达国证价值100ETF
- [159307.SZ](./159307.SZ.md) — 博时中证红利低波100ETF
- [300014.SZ](./300014.SZ.md) — 亿纬锂能
- [300750.SZ](./300750.SZ.md) — 宁德时代
- [513530.SH](./513530.SH.md) — 华泰柏瑞中证港股通高股息投资ETF(QDII)
- [520900.SH](./520900.SH.md) — 广发中证国新港股通央企红利ETF
- [600011.SH](./600011.SH.md) — 华能国际
- [600036.SH](./600036.SH.md) — 招商银行
- [600096.SH](./600096.SH.md) — 云天化
- [600309.SH](./600309.SH.md) — 万华化学
- [600499.SH](./600499.SH.md) — 科达制造
- [601600.SH](./601600.SH.md) — 中国铝业
- [601899.SH](./601899.SH.md) — 紫金矿业
- [603799.SH](./603799.SH.md) — 华友钴业
- [603871.SH](./603871.SH.md) — 嘉友国际
- [603993.SH](./603993.SH.md) — 洛阳钼业

## 共享情景轴

- [`_AXIS.africa-corridor`](./axes/africa-corridor.md) — 非洲建材与矿业通道情景轴 · 挂载票：`6655.HK` · `600499.SH` · `603871.SH`
- [`_AXIS.ai-capex`](./axes/ai-capex.md) — AI 资本开支情景轴 · 挂载票（需求方）：COHR.US · GLW.US · LITE.US · AEHR.US ｜ 挂载票（**构成方**）：GOOG.US · ORCL.US
- [`_AXIS.brent-oil`](./axes/brent-oil.md) — 布伦特原油 USD 价格情景轴（霍尔木兹中断后的 2027 油价 regime） · 挂载票：0857.HK · 0883.HK（后者主尺为 DDM——valuation-rules「DDM 主尺例外」，分子仍由本轴桥出，见 §3）
- [`_AXIS.coal-price`](./axes/coal-price.md) — 秦皇岛 5500 动力煤价格情景轴（长协 regime 下的煤价周期位置） · 挂载票：1（`000543.SZ` 皖能电力，电厂侧；候选：`1898.HK` 中煤能源 · `600011.SH` 华能国际；`513530.SH` / `520900.SH` 内的神华 / 中煤切片）
- [`_AXIS.cowos-capacity`](./axes/cowos-capacity.md) — CoWoS 产能与配额情景轴 · 挂载票：NVDA.US · AVGO.US · TSM.US
- [`_AXIS.fed-path-aluminium`](./axes/fed-path-aluminium.md) — 电解铝价差情景轴（利率路径 × 铝供应潮） · 挂载票：1378.HK · 601600.SH · 002532.SZ · 000933.SZ
- [`_AXIS.fed-path-gold-copper`](./axes/fed-path-gold-copper.md) — 金铜 USD 价格情景轴（美联储利率路径） · 挂载票：601899.SH · 603993.SH · 603799.SH（仅铜腿）
- [`_AXIS.lithium-carbonate`](./axes/lithium-carbonate.md) — 电池级碳酸锂 CNY 价格情景轴 · 挂载票：601899.SH · 9696.HK · 000792.SZ · ALB.US · 1772.HK · 600499.SH
- [`_AXIS.optical-comms`](./axes/optical-comms.md) — 光通信 / CPO·NPO 光引擎出货情景轴 · 挂载票：NOK.US · LITE.US · COHR.US · AVGO.US · TSM.US
- [`_AXIS.phosphate-chain`](./axes/phosphate-chain.md) — 磷产业链价格情景轴（国内磷肥定价管理松紧） · 挂载票：002895.SZ · 600096.SH
- [`_AXIS.southbound-repricing`](./axes/southbound-repricing.md) — 南向定价权情景轴 · 挂载票：`000338.SZ` · `600036.SH` · `6655.HK` · `1766.HK` · `1072.HK` · `600011.SH`
