# 输出口径

## forecasts.csv

- `origin_date`：预测基准日，即输入中的最后一个完整交易日。
- `origin_close`：基准日真实收盘点位。
- `target_date`：目标交易日。
- `horizon`：从基准日起第几个交易日。
- `median_close`：30条路径预测收盘的中位数。
- `p10_close` / `p90_close`：路径分布的10%与90%分位数。
- `p25_close` / `p75_close`：路径分布的25%与75%分位数。
- `p_up`：预测收盘高于 `origin_close` 的路径占比。
- `signal`：按冻结阈值生成的选择性方向信号。
- `actual_close`：目标日真实收盘；尚未发生时为空。
- `absolute_error`：`abs(median_close - actual_close)`（未校正的原始误差）。
- `actual_up`：真实收盘是否高于基准收盘。
- `direction_correct`：预测方向（`p_up>=0.5`）与真实方向是否一致；不确定信号为空。

## 统计校正列（"反思环节"）

用历史 1 日预测的真实误差做事后的展示层偏差修正，only 调点位、不碰方向信号。
每个 `origin_date` 生成时算一次，写死在该批次的所有 horizon 行里（不随之后新样本回填而改变）：

- `calibration_bias`：生成本次预测时，历史已结算 1 日预测的平均相对误差
  `mean((actual_close - median_close) / origin_close)`。
- `calibration_samples`：算这个 bias 时用了多少个已结算样本。
- `calibration_active`：`calibration_samples >= 30` 才为真；否则本行的
  `calibrated_*` 与原始值完全相同（校正未生效）。
- `calibrated_median_close` / `calibrated_p10_close` / `calibrated_p25_close` /
  `calibrated_p75_close` / `calibrated_p90_close`：原始值整体平移
  `calibration_bias * origin_close` 后的点位（校正生效时）。
- `calibrated_absolute_error` / `calibrated_direction_correct`：用校正后中位数
  重新计算的误差/方向命中，回填时机与 `absolute_error`/`direction_correct` 相同。

`p_up` / `signal` 永远来自未校正的原始路径分布——方向信号继续用冻结阈值判断，
统计校正不影响涨跌方向的判定，只影响点位预测本身展示成什么数字。

## 评价原则

优先评价 `horizon=1`，避免把不同期限混在同一个准确率中。至少同时报告覆盖率和方向准确率，因为选择性预测会放弃不确定样本。点位误差使用 MAE，并与“下一日等于当前收盘”的朴素基准比较。样本较少时报告样本数，不据此下稳定结论。

模型路径分位数来自有限的30条随机路径，未经覆盖率校准；它描述模型内部不确定性，不保证真实值以相同比例落入区间。
