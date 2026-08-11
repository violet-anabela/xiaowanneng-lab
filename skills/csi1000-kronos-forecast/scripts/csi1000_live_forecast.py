#!/usr/bin/env python3
"""Update the CSI 1000 rolling Kronos forecast ledger and charts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import akshare as ak
import exchange_calendars as xcals
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch


FEATURES = ["open", "high", "low", "close", "volume", "amount"]
PRICE_FEATURES = ["open", "high", "low", "close"]

# 统计校正（"反思环节"）：用历史 1 日预测的真实误差做事后的展示层偏差修正。
# 只在"历史该样本已结算"这一前提下计算 bias，天然不会用到未来信息（walk-forward）。
# 样本不足 MIN_CALIBRATION_SAMPLES 时不生效（calibrated_* 与原始值相同），避免小样本把噪声
# 当成系统性偏差去校正。只调点位（median/p10/p25/p75/p90），不碰 p_up/signal——
# 方向信号继续用冻结阈值判断，见 SKILL.md。
MIN_CALIBRATION_SAMPLES = 30
CN_COLUMNS = {
    "日期": "timestamps",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
    "成交金额": "amount",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kronos-dir", type=Path, default=Path(".runtime/Kronos"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("outputs/reports/csi1000-live")
    )
    parser.add_argument("--lookback", type=int, default=40)
    parser.add_argument("--pred-len", type=int, default=12)
    parser.add_argument("--paths", type=int, default=30)
    parser.add_argument("--temperature", type=float, default=0.4)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--device", default=None)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def fetch_completed_bars() -> pd.DataFrame:
    now = pd.Timestamp.now(tz="Asia/Shanghai")
    raw = ak.stock_zh_index_hist_csindex(
        symbol="000852", start_date="20150101", end_date=now.strftime("%Y%m%d")
    )
    df = raw.rename(columns=CN_COLUMNS)
    df["timestamps"] = pd.to_datetime(df["timestamps"])
    df = df[["timestamps", *FEATURES]].sort_values("timestamps")
    df = df.dropna().drop_duplicates(subset=["timestamps"], keep="last")
    repeated = df[FEATURES].eq(df[FEATURES].shift()).all(axis=1)
    df = df.loc[~repeated].reset_index(drop=True)

    # Never use an unfinished same-day bar before the Shanghai market has closed.
    if (
        not df.empty
        and df.iloc[-1]["timestamps"].date() == now.date()
        and (now.hour, now.minute) < (15, 15)
    ):
        df = df.iloc[:-1].reset_index(drop=True)
    if df.empty:
        raise RuntimeError("No completed CSI 1000 bars returned by data source")
    return df


def future_sessions(last_date: pd.Timestamp, count: int) -> pd.DatetimeIndex:
    calendar = xcals.get_calendar("XSHG")
    session = calendar.date_to_session(last_date, direction="previous")
    return calendar.sessions_window(session, count + 1)[1:]


def load_ledger(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"origin_date": str, "target_date": str})


def fill_actuals(ledger: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    if ledger.empty:
        return ledger
    actual_map = {
        row.timestamps.date().isoformat(): float(row.close)
        for row in bars.itertuples(index=False)
    }
    ledger = ledger.copy()
    ledger["actual_close"] = ledger["target_date"].map(actual_map)
    ledger["absolute_error"] = (ledger["median_close"] - ledger["actual_close"]).abs()
    actual_return = ledger["actual_close"] / ledger["origin_close"] - 1
    ledger["actual_direction"] = np.where(
        ledger["actual_close"].isna(), "", np.where(actual_return > 0, "up", "down")
    )
    predicted_up = ledger["p_up"] >= 0.5
    ledger["direction_correct"] = np.where(
        ledger["actual_close"].isna(),
        np.nan,
        predicted_up == (actual_return > 0),
    )
    # 校正后误差（仅当该行已经算过校正列才补，旧行/校正未生效的行两者应相等）。
    if "calibrated_median_close" in ledger.columns:
        ledger["calibrated_absolute_error"] = (
            ledger["calibrated_median_close"] - ledger["actual_close"]
        ).abs()
        calibrated_predicted_up = ledger["calibrated_median_close"] >= ledger["origin_close"]
        ledger["calibrated_direction_correct"] = np.where(
            ledger["actual_close"].isna(),
            np.nan,
            calibrated_predicted_up == (actual_return > 0),
        )
    return ledger


def compute_calibration_bias(ledger: pd.DataFrame) -> tuple[float, int]:
    """从已结算的 1 日预测里算历史平均相对误差（反思环节的核心）。

    只读取传入时刻已经存在于账本里的结算数据——调用方必须在把"今天"这批新预测
    并入账本之前调用本函数，这样天然是 walk-forward 的，不会用到未来信息。
    返回 (mean_relative_error, sample_count)；样本为空时 bias=0。
    """
    if ledger.empty:
        return 0.0, 0
    settled = ledger[(ledger["horizon"] == 1) & ledger["actual_close"].notna()]
    if settled.empty:
        return 0.0, 0
    rel_err = (settled["actual_close"] - settled["median_close"]) / settled["origin_close"]
    return float(rel_err.mean()), int(len(settled))


def apply_calibration(summary: pd.DataFrame, bias: float, sample_count: int) -> pd.DataFrame:
    """把历史平均偏差整体平移到本次预测的点位上（展示层校正，不改路径分布形状）。

    样本不足 MIN_CALIBRATION_SAMPLES 时 calibrated_* 直接等于原始值（不生效）。
    不触碰 p_up/signal：方向信号继续由未校正的原始路径分布决定。
    """
    active = sample_count >= MIN_CALIBRATION_SAMPLES
    shift = (bias * summary["origin_close"]) if active else 0.0
    summary = summary.copy()
    summary["calibration_bias"] = bias
    summary["calibration_samples"] = sample_count
    summary["calibration_active"] = active
    for col in ("median_close", "p10_close", "p25_close", "p75_close", "p90_close"):
        summary[f"calibrated_{col}"] = summary[col] + shift
    return summary


def generate_paths(
    args: argparse.Namespace, bars: pd.DataFrame, dates: pd.DatetimeIndex
) -> np.ndarray:
    sys.path.insert(0, str(args.kronos_dir.resolve()))
    from model import Kronos, KronosPredictor, KronosTokenizer

    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-base")
    predictor = KronosPredictor(
        model,
        tokenizer,
        device=args.device,
        max_context=args.lookback,
    )
    history = bars.iloc[-args.lookback :].copy()
    x_df = history[FEATURES].reset_index(drop=True)
    x_timestamp = history["timestamps"].reset_index(drop=True)
    y_timestamp = pd.Series(dates)

    origin_key = history.iloc[-1]["timestamps"].date().isoformat()
    seed = int(hashlib.sha256(origin_key.encode()).hexdigest()[:8], 16)
    np.random.seed(seed)
    torch.manual_seed(seed)

    all_paths = []
    for path_id in range(args.paths):
        prediction = predictor.predict(
            df=x_df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=args.pred_len,
            T=args.temperature,
            top_p=args.top_p,
            sample_count=1,
            verbose=False,
        )
        values = prediction[FEATURES].to_numpy(dtype=np.float64)
        all_paths.append(values)
        print(f"generated path {path_id + 1}/{args.paths}", flush=True)
    return np.stack(all_paths, axis=0)


def summarize_paths(
    paths: np.ndarray,
    dates: pd.DatetimeIndex,
    origin_date: str,
    origin_close: float,
    args: argparse.Namespace,
) -> pd.DataFrame:
    rows = []
    close_paths = paths[:, :, FEATURES.index("close")]
    for step, target_date in enumerate(dates, start=1):
        closes = close_paths[:, step - 1]
        p_up = float((closes > origin_close).mean())
        confidence = max(p_up, 1 - p_up)
        if p_up >= 0.9:
            signal = "high-confidence up"
        elif p_up <= 0.1:
            signal = "high-confidence down"
        else:
            signal = "uncertain"
        rows.append(
            {
                "origin_date": origin_date,
                "target_date": target_date.date().isoformat(),
                "horizon": step,
                "origin_close": origin_close,
                "median_close": float(np.median(closes)),
                "mean_close": float(closes.mean()),
                "p10_close": float(np.quantile(closes, 0.10)),
                "p25_close": float(np.quantile(closes, 0.25)),
                "p75_close": float(np.quantile(closes, 0.75)),
                "p90_close": float(np.quantile(closes, 0.90)),
                "p_up": p_up,
                "model_confidence": confidence,
                "signal": signal,
                "paths": args.paths,
                "temperature": args.temperature,
                "top_p": args.top_p,
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
        )
    return pd.DataFrame(rows)


def save_raw_paths(
    paths: np.ndarray, dates: pd.DatetimeIndex, origin_date: str, path: Path
) -> None:
    rows = []
    for path_id in range(paths.shape[0]):
        for step, target_date in enumerate(dates, start=1):
            row = {
                "origin_date": origin_date,
                "path_id": path_id + 1,
                "target_date": target_date.date().isoformat(),
                "horizon": step,
            }
            row.update(dict(zip(FEATURES, paths[path_id, step - 1])))
            rows.append(row)
    pd.DataFrame(rows).to_csv(path, index=False)


def plot_latest(
    bars: pd.DataFrame, latest: pd.DataFrame, ledger: pd.DataFrame, output: Path
) -> None:
    history = bars.iloc[-60:]
    hist_dates = pd.to_datetime(history["timestamps"])
    future_dates = pd.to_datetime(latest["target_date"])
    origin_date = pd.Timestamp(latest.iloc[0]["origin_date"])
    origin_close = float(latest.iloc[0]["origin_close"])
    forecast_dates = pd.DatetimeIndex([origin_date]).append(pd.DatetimeIndex(future_dates))
    raw_values = np.r_[origin_close, latest["median_close"].to_numpy()]
    calibrated_values = np.r_[origin_close, latest["calibrated_median_close"].to_numpy()]
    calibration_active = bool(latest.iloc[0]["calibration_active"])
    fig, ax = plt.subplots(figsize=(12, 6.5))
    ax.plot(hist_dates, history["close"], color="#2563eb", lw=2, label="Historical close")
    # Anchor the forecast line at the last observed close so the transition is
    # visually continuous; uncertainty bands still begin on the first forecast day.
    ax.plot(
        forecast_dates,
        calibrated_values,
        color="#111827",
        lw=2.2,
        label="Forecast median (calibrated)" if calibration_active else "Forecast median",
    )
    if calibration_active:
        # 只有校正真的生效时才画原始线做对照，否则两条线重合，纯属视觉噪音。
        ax.plot(
            forecast_dates,
            raw_values,
            color="#9ca3af",
            lw=1.4,
            ls="--",
            label="Forecast median (raw, uncalibrated)",
        )
    ax.fill_between(
        future_dates,
        latest["calibrated_p10_close"].to_numpy(),
        latest["calibrated_p90_close"].to_numpy(),
        color="#93c5fd",
        alpha=0.30,
        label="10%-90% path band",
    )
    ax.fill_between(
        future_dates,
        latest["calibrated_p25_close"].to_numpy(),
        latest["calibrated_p75_close"].to_numpy(),
        color="#3b82f6",
        alpha=0.28,
        label="25%-75% path band",
    )
    realized = latest.dropna(subset=["actual_close"])
    if not realized.empty:
        ax.plot(
            pd.to_datetime(realized["target_date"]),
            realized["actual_close"],
            color="#dc2626",
            marker="o",
            lw=2,
            label="Realized close",
        )
    ax.axvline(origin_date, color="#6b7280", ls="--", lw=1.2)
    ax.axhline(latest.iloc[0]["origin_close"], color="#9ca3af", ls=":", lw=1)
    ax.set_title(f"CSI 1000 rolling forecast from {origin_date.date().isoformat()}")
    ax.set_ylabel("Index level")
    ax.grid(alpha=0.2)
    ax.legend(loc="best")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def plot_evaluation(ledger: pd.DataFrame, output: Path) -> None:
    """复盘图：这是"反思环节"最直接的可视化——同一张图对比未校正 / 已校正预测
    与真实值的差距，看统计校正到底有没有把预测拉准。"""
    step1 = ledger[(ledger["horizon"] == 1) & ledger["actual_close"].notna()].copy()
    fig, ax = plt.subplots(figsize=(12, 5.5))
    if step1.empty:
        ax.text(0.5, 0.5, "No realized one-day forecasts yet", ha="center", va="center")
        ax.set_axis_off()
    else:
        dates = pd.to_datetime(step1["target_date"])
        has_calibration = "calibrated_median_close" in step1.columns
        ax.plot(dates, step1["actual_close"], color="#dc2626", marker="o", lw=2, label="Actual")
        if has_calibration and step1["calibration_active"].fillna(False).any():
            ax.plot(
                dates,
                step1["calibrated_median_close"],
                color="#111827",
                marker="o",
                lw=2,
                label="Forecast median (calibrated)",
            )
            ax.plot(
                dates,
                step1["median_close"],
                color="#9ca3af",
                marker=".",
                lw=1.2,
                ls="--",
                label="Forecast median (raw)",
            )
        else:
            ax.plot(dates, step1["median_close"], color="#111827", marker="o", label="Forecast median")
        ax.fill_between(
            dates,
            step1["p10_close"].to_numpy(),
            step1["p90_close"].to_numpy(),
            color="#93c5fd",
            alpha=0.30,
            label="10%-90% band",
        )
        ax.grid(alpha=0.2)
        ax.legend(loc="best")
        ax.set_ylabel("Index level")
        ax.set_title("Realized one-day forecasts")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def write_dashboard(ledger: pd.DataFrame, output_dir: Path) -> None:
    latest_origin = ledger["origin_date"].max()
    latest = ledger[ledger["origin_date"] == latest_origin].sort_values("horizon")
    first = latest.iloc[0]
    next_session = first["target_date"]
    first_up = float(first["p_up"])
    first_down = 1.0 - first_up
    first_direction = "偏上涨" if first_up > 0.5 else "偏下跌" if first_down > 0.5 else "方向均衡"
    calibration_active = bool(first["calibration_active"])
    first_median = float(first["calibrated_median_close"])
    first_p10 = float(first["calibrated_p10_close"])
    first_p90 = float(first["calibrated_p90_close"])
    first_return = float(first_median / first["origin_close"] - 1.0)
    if first_return > 0.02:
        first_strength = "强烈上涨"
    elif first_return < -0.02:
        first_strength = "强烈下跌"
    elif first_return > 0:
        first_strength = "温和上涨"
    elif first_return < 0:
        first_strength = "温和下跌"
    else:
        first_strength = "基本持平"
    signal_labels = {
        "high-confidence up": "高一致度上涨",
        "high-confidence down": "高一致度下跌",
        "uncertain": "不确定",
    }
    step1_realized = ledger[(ledger["horizon"] == 1) & ledger["actual_close"].notna()]
    high_conf = step1_realized[
        (step1_realized["p_up"] <= 0.1) | (step1_realized["p_up"] >= 0.9)
    ]
    overall_acc = (
        float(step1_realized["direction_correct"].astype(float).mean())
        if len(step1_realized)
        else None
    )
    high_acc = (
        float(high_conf["direction_correct"].astype(float).mean())
        if len(high_conf)
        else None
    )
    calibrated_overall_acc = (
        float(step1_realized["calibrated_direction_correct"].astype(float).mean())
        if len(step1_realized)
        else None
    )
    raw_mae = float(step1_realized["absolute_error"].mean()) if len(step1_realized) else None
    calibrated_mae = (
        float(step1_realized["calibrated_absolute_error"].mean()) if len(step1_realized) else None
    )
    calibration_line = (
        f"- 反思环节：已用 {int(first['calibration_samples'])} 个结算样本做统计校正，"
        f"历史平均偏差 {float(first['calibration_bias']):+.3%}"
        if calibration_active
        else f"- 反思环节：结算样本仅 {int(first['calibration_samples'])} 个（需满 {MIN_CALIBRATION_SAMPLES} 个才启用统计校正），当前展示未校正的原始预测"
    )
    lines = [
        "# 中证1000每日滚动预测",
        "",
        f"- 最新完整行情：{latest_origin}，收盘 {first['origin_close']:.2f}",
        f"- 下一交易日（{next_session}）中心点位：{first_median:.2f}",
        f"- 预测涨跌幅：{first_return:+.2%}，强弱判断：{first_strength}",
        f"- 下一交易日（{next_session}）80%路径区间：{first_p10:.2f} ～ {first_p90:.2f}",
        f"- 下一交易日（{next_session}）上涨路径：{first_up:.1%}（{int(round(first_up * first['paths']))}/{int(first['paths'])}）",
        f"- 下一交易日（{next_session}）下跌路径：{first_down:.1%}（{int(first['paths']) - int(round(first_up * first['paths']))}/{int(first['paths'])}）",
        f"- 模型方向：{first_direction}；方向一致度：{max(first_up, first_down):.1%}",
        f"- 模型信号：{signal_labels.get(first['signal'], first['signal'])}",
        calibration_line,
        "- 说明：方向一致度是30条模型路径中多数方向的占比，不是已校准的真实置信概率；"
        "统计校正只调点位展示，不影响方向信号判定。",
        "",
        "![最新预测扇形图](latest-forecast.png)",
        "",
        "## 已实现预测效果",
        "",
        f"- 已回填的一日预测：{len(step1_realized)}次",
        f"- 全部一日方向准确率：{'尚无数据' if overall_acc is None else f'{overall_acc:.2%}'}"
        + (
            ""
            if calibrated_overall_acc is None or calibrated_overall_acc == overall_acc
            else f"（校正后 {calibrated_overall_acc:.2%}）"
        ),
        f"- 高一致度判断：{len(high_conf)}次",
        f"- 高一致度判断准确率：{'尚无数据' if high_acc is None else f'{high_acc:.2%}'}",
        f"- 点位平均绝对误差：{'尚无数据' if raw_mae is None else f'{raw_mae:.2f}'}"
        + (
            ""
            if calibrated_mae is None or calibrated_mae == raw_mae
            else f"（校正后 {calibrated_mae:.2f}）"
        ),
        "",
        "![预测与真实值](evaluation-history.png)",
        "",
        "## 最新12日预测表",
        "",
        "| 日期 | 中位点位 | 预测涨跌幅 | 强弱 | 10%-90%区间 | 上涨 | 下跌 | 方向一致度 | 信号 | 真实值 |",
        "|---|---:|---:|---|---:|---:|---:|---:|---|---:|",
    ]
    for row in latest.itertuples(index=False):
        actual = "—" if pd.isna(row.actual_close) else f"{row.actual_close:.2f}"
        median = row.calibrated_median_close
        p10, p90 = row.calibrated_p10_close, row.calibrated_p90_close
        predicted_return = median / row.origin_close - 1.0
        if predicted_return > 0.02:
            strength = "强烈上涨"
        elif predicted_return < -0.02:
            strength = "强烈下跌"
        elif predicted_return > 0:
            strength = "温和上涨"
        elif predicted_return < 0:
            strength = "温和下跌"
        else:
            strength = "基本持平"
        lines.append(
            f"| {row.target_date} | {median:.2f} | {predicted_return:+.2%} | {strength} | {p10:.2f}～{p90:.2f} | {row.p_up:.1%} | {1.0 - row.p_up:.1%} | {max(row.p_up, 1.0 - row.p_up):.1%} | {signal_labels.get(row.signal, row.signal)} | {actual} |"
        )
    (output_dir / "dashboard.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_interactive_dashboard(
    ledger: pd.DataFrame, bars: pd.DataFrame, output_dir: Path
) -> None:
    latest_origin = ledger["origin_date"].max()
    latest = ledger[ledger["origin_date"] == latest_origin].sort_values("horizon")
    first = latest.iloc[0]
    step1 = ledger[ledger["horizon"] == 1].sort_values("target_date")
    settled = step1[step1["actual_close"].notna()]
    high = settled[(settled["p_up"] <= 0.1) | (settled["p_up"] >= 0.9)]

    def records(frame: pd.DataFrame, columns: list[str]) -> list[dict]:
        clean = frame[columns].copy()
        # datetime 列（如 K 线 timestamps）转日期字符串，否则无法 JSON 序列化
        for col in columns:
            if pd.api.types.is_datetime64_any_dtype(clean[col]):
                clean[col] = clean[col].dt.strftime("%Y-%m-%d")
        clean = clean.replace({np.nan: None})
        return clean.to_dict(orient="records")

    payload = {
        "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "originDate": latest_origin,
        "originClose": round(float(first["origin_close"]), 2),
        "targetDate": str(first["target_date"]),
        "nextMedian": round(float(first["calibrated_median_close"]), 2),
        "nextP10": round(float(first["calibrated_p10_close"]), 2),
        "nextP90": round(float(first["calibrated_p90_close"]), 2),
        "nextUp": round(float(first["p_up"]), 6),
        "calibrationActive": bool(first["calibration_active"]),
        "calibrationSamples": int(first["calibration_samples"]),
        "calibrationBias": round(float(first["calibration_bias"]), 6),
        "settledCount": int(len(settled)),
        "directionAccuracy": (
            round(float(settled["direction_correct"].astype(float).mean()), 6)
            if len(settled)
            else None
        ),
        "highCount": int(len(high)),
        "highAccuracy": (
            round(float(high["direction_correct"].astype(float).mean()), 6)
            if len(high)
            else None
        ),
        "history": records(bars.iloc[-90:], ["timestamps", "close"]),
        "forecast": records(
            latest,
            [
                "target_date",
                "median_close",
                "p10_close",
                "p90_close",
                "calibrated_median_close",
                "calibrated_p10_close",
                "calibrated_p90_close",
                "p_up",
                "actual_close",
            ],
        ),
    }
    template_path = Path(__file__).with_name("templates") / "csi1000-dashboard.html"
    template = template_path.read_text(encoding="utf-8")
    html = template.replace(
        "__DATA_JSON__",
        # default=str 兜底：任何漏网的非原生类型（Timestamp/numpy 标量）转字符串而不是崩溃
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
    )
    (output_dir / "dashboard.html").write_text(html, encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = args.output_dir / "forecasts.csv"
    bars_path = args.output_dir / "latest-bars.csv"
    bars = fetch_completed_bars()
    bars.to_csv(bars_path, index=False)
    ledger = fill_actuals(load_ledger(ledger_path), bars)
    # 反思环节：在把"今天"这批新预测并入账本之前，先从已有历史算校正偏差——
    # 天然 walk-forward，不会用到本次预测尚不存在的未来信息。
    bias, bias_n = compute_calibration_bias(ledger)
    print(
        f"calibration: bias={bias:+.4%} of index level, samples={bias_n}, "
        f"active={bias_n >= MIN_CALIBRATION_SAMPLES}",
        flush=True,
    )

    origin = bars.iloc[-1]["timestamps"].date().isoformat()
    already_generated = not ledger.empty and origin in set(ledger["origin_date"])
    if args.force or not already_generated:
        dates = future_sessions(bars.iloc[-1]["timestamps"], args.pred_len)
        paths = generate_paths(args, bars, dates)
        summary = summarize_paths(
            paths,
            dates,
            origin_date=origin,
            origin_close=float(bars.iloc[-1]["close"]),
            args=args,
        )
        summary = apply_calibration(summary, bias, bias_n)
        if not ledger.empty:
            ledger = ledger[ledger["origin_date"] != origin]
        ledger = pd.concat([ledger, summary], ignore_index=True)
        save_raw_paths(paths, dates, origin, args.output_dir / "latest-paths.csv")
    else:
        print(f"forecast for {origin} already exists; only refreshing actuals")

    ledger = fill_actuals(ledger, bars).sort_values(["origin_date", "horizon"])
    # 日期列统一为 YYYY-MM-DD 字符串：新建的记录里是 Timestamp、从 CSV 重载的是字符串，
    # 不归一会导致 JSON 序列化崩溃和 markdown 表格里带 00:00:00。
    for col in ("origin_date", "target_date"):
        ledger[col] = ledger[col].astype(str).str.slice(0, 10)
    ledger.to_csv(ledger_path, index=False)
    latest = ledger[ledger["origin_date"] == ledger["origin_date"].max()].copy()
    plot_latest(bars, latest, ledger, args.output_dir / "latest-forecast.png")
    plot_evaluation(ledger, args.output_dir / "evaluation-history.png")
    write_dashboard(ledger, args.output_dir)
    write_interactive_dashboard(ledger, bars, args.output_dir)

    metadata = {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "latest_completed_bar": origin,
        "forecast_created": bool(args.force or not already_generated),
        "ledger_rows": len(ledger),
        "forecast_origins": int(ledger["origin_date"].nunique()),
    }
    (args.output_dir / "status.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
