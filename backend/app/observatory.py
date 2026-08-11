"""观测站：中证1000 Kronos 每日预测的调度与只读文件 API。

设计要点：
- 预测跑在**子进程**里（与 csi1000-kronos-forecast Skill 同一份脚本）：
  torch/权重只在运行那几分钟占内存，进程退出后全部释放，主进程平时保持轻量。
- 追加式账本存 OBSERVATORY_DIR（生产环境挂持久卷到 /data），脚本本身幂等，
  同一交易日重复运行不会追加重复记录。
- 对外只暴露白名单文件的只读下载，不暴露任何触发执行的公开入口。
"""

import asyncio
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .settings import settings

TZ = ZoneInfo("Asia/Shanghai")

# 允许下载的产物白名单：文件名 -> MIME
ALLOWED_FILES = {
    "status.json": "application/json",
    "forecasts.csv": "text/csv; charset=utf-8",
    "latest-forecast.png": "image/png",
    "evaluation-history.png": "image/png",
    "dashboard.md": "text/markdown; charset=utf-8",
    "latest-paths.csv": "text/csv; charset=utf-8",
    # 历史日线（前端拿来画可交互图表的左半段，即"史实"部分）。
    "latest-bars.csv": "text/csv; charset=utf-8",
}

router = APIRouter(prefix="/v1/observatory")

_run_lock = asyncio.Lock()


def _run_forecast_blocking() -> tuple[int, str]:
    """在子进程中执行一次完整预测更新，返回 (returncode, 摘要日志)。"""
    out_dir = Path(settings.observatory_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        settings.observatory_script,
        "--kronos-dir",
        settings.kronos_dir,
        "--output-dir",
        str(out_dir),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30 * 60,  # 兜底：无论如何 30 分钟内结束
    )
    tail = (proc.stdout + "\n" + proc.stderr).strip()[-2000:]
    return proc.returncode, tail


async def run_forecast_once(reason: str) -> bool:
    """带互斥锁地跑一次预测。已在跑时直接跳过（幂等，无需排队）。"""
    if _run_lock.locked():
        print(f"[observatory] skip ({reason}): previous run still in progress")
        return False
    async with _run_lock:
        print(f"[observatory] run start ({reason})")
        try:
            code, tail = await asyncio.to_thread(_run_forecast_blocking)
        except Exception as e:  # noqa: BLE001
            print(f"[observatory] run crashed ({reason}): {type(e).__name__}: {e}")
            return False
        if code == 0:
            print(f"[observatory] run ok ({reason})")
            return True
        print(f"[observatory] run failed ({reason}) rc={code}\n{tail}")
        return False


def _next_run_time(now: datetime) -> datetime:
    """下一个调度时刻（每天 settings.observatory_schedule，Asia/Shanghai）。"""
    hour, minute = (int(x) for x in settings.observatory_schedule.split(":", 1))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


async def scheduler_loop() -> None:
    """每日定时跑；启动时若从未出过结果，先补跑一次让页面尽快有数据。

    周末/节假日照常触发也无妨：脚本只认最新完整交易日，无新数据时是幂等空跑。
    """
    if not Path(settings.observatory_dir, "status.json").exists():
        await run_forecast_once("bootstrap: no ledger yet")

    while True:
        now = datetime.now(TZ)
        nxt = _next_run_time(now)
        wait = (nxt - now).total_seconds()
        print(f"[observatory] next run at {nxt.isoformat()} (in {wait / 3600:.1f}h)")
        await asyncio.sleep(wait)
        await run_forecast_once(f"daily {settings.observatory_schedule}")


@router.get("/{filename}")
async def get_artifact(filename: str):
    mime = ALLOWED_FILES.get(filename)
    if mime is None:
        raise HTTPException(status_code=404, detail="Unknown artifact")
    path = Path(settings.observatory_dir) / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not generated yet")
    return FileResponse(
        path,
        media_type=mime,
        headers={"Cache-Control": "no-cache"},
    )
