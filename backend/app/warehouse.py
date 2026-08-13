"""个人数据仓库：全市场 A 股日线同步的后台调度（跑批脚本见 backend/warehouse/）。

纯背景任务，不对外暴露任何接口——现在还只是"攒数据"阶段，查询接口以后
再单独做。跑法：
- 存量历史没追平前，短间隔连续跑批（每次一批，见 stock_daily_sync.py）；
- 追平之后（脚本报告"nothing to sync"）退化成每天一次的增量更新，收盘后跑，
  等当天数据落定。
"""

import asyncio
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .settings import settings

TZ = ZoneInfo("Asia/Shanghai")


def _run_batch_blocking() -> tuple[int, str]:
    db_path = Path(settings.warehouse_dir) / "warehouse.db"
    cmd = [
        sys.executable,
        settings.warehouse_script,
        "--db",
        str(db_path),
        "--batch-size",
        str(settings.warehouse_batch_size),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30 * 60,  # 兜底：单批无论如何 30 分钟内结束
    )
    tail = (proc.stdout + "\n" + proc.stderr).strip()[-2000:]
    return proc.returncode, tail


async def run_batch_once() -> bool:
    """跑一批，返回这批是不是已经追平（没有真的同步任何东西）。"""
    try:
        code, tail = await asyncio.to_thread(_run_batch_blocking)
    except Exception as e:  # noqa: BLE001
        print(f"[warehouse] batch crashed: {type(e).__name__}: {e}", flush=True)
        return False
    if code != 0:
        print(f"[warehouse] batch failed rc={code}\n{tail}", flush=True)
        return False
    print(tail, flush=True)
    return "nothing to sync" in tail


def _next_daily_run(now: datetime) -> datetime:
    hour, minute = (int(x) for x in settings.warehouse_schedule.split(":", 1))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


async def scheduler_loop() -> None:
    while True:
        caught_up = await run_batch_once()
        if caught_up:
            now = datetime.now(TZ)
            nxt = _next_daily_run(now)
            wait = (nxt - now).total_seconds()
            print(f"[warehouse] caught up, next run at {nxt.isoformat()} (in {wait / 3600:.1f}h)", flush=True)
            await asyncio.sleep(wait)
        else:
            await asyncio.sleep(settings.warehouse_poll_interval)
