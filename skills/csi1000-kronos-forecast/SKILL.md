---
name: csi1000-kronos-forecast
version: 1.0.0
description: 运行并解读中证1000（000852）的 Kronos 滚动预测系统。当用户要求更新当日预测、预测下一交易日、查看点位预测或蒙特卡洛路径区间、回填真实收盘、检查方向准确率、回顾预测历史、诊断每日自动化，或解读看板与账本时使用。
---

# 中证1000 Kronos 滚动预测

用打包在本技能内的预测程序维护一份**追加式预测账本**：每天生成新预测、回填旧预测的真实结果，绝不用新预测覆盖历史记录。

## 环境准备（首次使用）

本技能自带主程序（`scripts/csi1000_live_forecast.py`），但需要两样外部依赖：

```bash
# 1. Python 3.10+ 虚拟环境 + 依赖
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Kronos 模型代码（官方仓库，clone 到任意位置）
git clone https://github.com/shiyu-coder/Kronos.git
```

模型权重（Kronos-base 及其 tokenizer）由 huggingface_hub 在首次运行时自动下载缓存；
之后可加 `HF_HUB_OFFLINE=1` 离线复用缓存。行情数据来自 akshare，运行时需要联网。

国内网络访问 huggingface.co 常年不稳定，若下载卡住或超时，设置环境变量
`HF_ENDPOINT=https://hf-mirror.com` 后重试（huggingface_hub 官方支持的国内镜像，
内容与接口和官方站一致）。hf-mirror.com 单线程直连较慢，配合装好 `hf_transfer`
包后设 `HF_HUB_ENABLE_HF_TRANSFER=1` 可开多线程分块下载，明显提速。

任何一项缺失时停下来说明缺什么；不要静默换用别的模型或数据源。

## 更新预测

```bash
python scripts/csi1000_live_forecast.py \
  --kronos-dir /path/to/Kronos \
  --output-dir outputs/csi1000-live
```

程序必须保持以下语义（改代码时也不许破坏）：

1. 仅使用最新**完整**日线；收盘前不得把当日未完成行情作为输入。
2. 先回填旧预测的真实收盘、误差和方向命中，再生成新预测。
3. 同一 `origin_date` 已存在时只刷新真实值，不重复追加。
4. 使用 Kronos-base、40 日回看、未来 12 个交易日、30 条独立路径、`temperature=0.4`、`top_p=0.9`。
5. 以 `p_up <= 0.1` 为高置信度下跌、`p_up >= 0.9` 为高置信度上涨，其余为不确定。
6. 反思环节：生成新预测前，先用历史已结算的 1 日预测算平均相对误差（walk-forward，
   不用到本次预测还不存在的未来信息），据此对**点位预测**做展示层校正（写入
   `calibrated_*` 列）；样本不足 30 个时不生效。这一步永远不碰 `p_up`/`signal`——
   方向信号继续由未校正的原始路径分布和冻结阈值决定。

## 读取结果

输出目录下按需读取：

| 文件 | 内容 |
|---|---|
| `status.json` | 本次运行状态、是否创建了新预测 |
| `dashboard.md` | 最新预测摘要和未来点位表 |
| `dashboard.html` | 交互式看板（悬停查看日期、点位、路径区间、方向比例） |
| `forecasts.csv` | 全部历史预测、真实值与误差（账本本体） |
| `latest-forecast.png` | 历史走势 + 预测中位数 + 路径区间 |
| `evaluation-history.png` | 已结算预测与真实值对比 |
| `latest-paths.csv` | 30 条原始采样路径 |

字段定义与统计口径见 [references/output-schema.md](references/output-schema.md)，
仅在分析准确率、排查字段或修改输出时读取。

## 汇报结果

先报告最新完整行情日与目标交易日，再依次报告：

- 基准收盘点位；
- 下一交易日预测中位点位（`calibrated_median_close`）及相对涨跌幅；
- 涨跌强弱：预测涨跌幅超过 2% 为强烈，否则为温和；
- 10%–90% 路径区间（`calibrated_p10_close` ～ `calibrated_p90_close`）；
- 上涨与下跌路径数、各自占比，以及多数方向的模型一致度（来自未校正的 `p_up`）；
- 高置信度上涨 / 高置信度下跌 / 不确定；
- 反思环节状态：`calibration_active` 为真时说明用了多少历史样本、平均偏差是多少；
  为假时如实说明样本不足（当前多少个、需要多少个）、展示的是未校正原始预测；
- 已结算的一日预测数量、方向准确率、MAE；校正生效时同时报告校正前后的对比；
  样本不足时明确说不足。

措辞纪律：把多数路径占比称为"模型方向一致度"，把预测区间称为"模型路径区间"；
不要说成经过校准的真实置信度或真实概率。反思环节的统计校正只调点位展示，
不要说成"模型变准了"或暗示影响了方向信号判定。不要把模型信号表述为投资建议。

## 修改与校验

修改程序后：先做语法检查，再完整跑一次并确认幂等性（重复运行同一天不追加重复记录）。
涉及图表的改动必须打开生成的 PNG 亲眼确认。
