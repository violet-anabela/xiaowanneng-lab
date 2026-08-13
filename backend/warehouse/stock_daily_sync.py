"""个人金融数据仓库：全市场 A 股日线同步（数据源 baostock，免费无需 token）。

设计要点：
- 只存"事实"：不复权原始成交价（baostock adjustflag=3），复权是分析时的派生
  选择，不是历史事实本身；以后要加复权序列可以另开一张表，不动这张。
- 范围只到股票（baostock type=1），不含指数/ETF/可转债——这几类以后要存
  再加，现在先把最大头的股票日线跑稳。
- 按批次跑，不追求一次性跑完全市场：股票名单几千只，一次全跑要很久，
  中途容器重启也不该丢进度。每次只处理落后最多的一批，进度记在
  sync_state 表里，下次接着跑；追平之后每天增量就只剩几千只各拉一天，
  很快。
- 调度（多久跑一批、追平后多久跑一次）不归这个脚本管，由
  backend/app/warehouse.py 的后台任务决定；这里只管"跑一批"。
"""

import argparse
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import baostock as bs

SCHEMA = """
CREATE TABLE IF NOT EXISTS stocks (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    list_date TEXT NOT NULL,
    delist_date TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_bars (
    code TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    amount REAL,
    turn REAL,
    pct_chg REAL,
    PRIMARY KEY (code, date)
);
CREATE TABLE IF NOT EXISTS sync_state (
    code TEXT PRIMARY KEY,
    last_date TEXT NOT NULL
);
"""

FIELDS = "date,code,open,high,low,close,volume,amount,turn,pctChg"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=300)
    return parser.parse_args()


def _to_float(value: str) -> float | None:
    return float(value) if value not in (None, "") else None


def _to_int(value: str) -> int | None:
    return int(value) if value not in (None, "") else None


def _next_day(iso_date: str) -> str:
    year, month, day = (int(x) for x in iso_date.split("-"))
    return (date(year, month, day) + timedelta(days=1)).isoformat()


def refresh_universe(conn: sqlite3.Connection) -> int:
    """股票名单本身会变（新股上市/老股退市），每次运行都刷新一遍——一次 API
    调用返回全量名单，很快，不算额外负担。"""
    rs = bs.query_stock_basic()
    if rs.error_code != "0":
        raise RuntimeError(f"query_stock_basic failed: {rs.error_msg}")
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    stocks = [r for r in rows if r[4] == "1"]  # type: 1=股票，排除指数/ETF/可转债/其它
    conn.executemany(
        """
        INSERT INTO stocks (code, name, list_date, delist_date, status)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            name = excluded.name,
            delist_date = excluded.delist_date,
            status = excluded.status
        """,
        [(r[0], r[1], r[2], r[3], r[5]) for r in stocks],
    )
    conn.commit()
    return len(stocks)


def pick_batch(
    conn: sqlite3.Connection, batch_size: int, today: str
) -> list[tuple[str, str, str, str]]:
    """挑一批还没追平的股票：没同步过的（从没跑过 / 新股）优先。

    "追平"对已退市股票是指同步到退市日，对在市股票是指同步到今天。
    """
    cur = conn.execute(
        """
        SELECT s.code, s.list_date, s.delist_date, COALESCE(w.last_date, '') AS last_date
        FROM stocks s
        LEFT JOIN sync_state w ON w.code = s.code
        WHERE COALESCE(w.last_date, '') <
              CASE WHEN s.delist_date != '' AND s.delist_date < ?
                   THEN s.delist_date ELSE ? END
        ORDER BY last_date ASC
        LIMIT ?
        """,
        (today, today, batch_size),
    )
    return cur.fetchall()


def sync_one(conn: sqlite3.Connection, code: str, start_date: str, end_date: str) -> None:
    rs = bs.query_history_k_data_plus(
        code, FIELDS, start_date=start_date, end_date=end_date, frequency="d", adjustflag="3"
    )
    if rs.error_code != "0":
        raise RuntimeError(f"{code}: {rs.error_msg}")
    rows = []
    last_date = None
    while rs.next():
        d = rs.get_row_data()  # date,code,open,high,low,close,volume,amount,turn,pctChg
        rows.append(
            (
                d[0],
                d[1],
                _to_float(d[2]),
                _to_float(d[3]),
                _to_float(d[4]),
                _to_float(d[5]),
                _to_int(d[6]),
                _to_float(d[7]),
                _to_float(d[8]),
                _to_float(d[9]),
            )
        )
        last_date = d[0]
    if rows:
        conn.executemany(
            """
            INSERT OR REPLACE INTO daily_bars
                (date, code, open, high, low, close, volume, amount, turn, pct_chg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    # 就算这段区间没有实际交易数据（刚上市、或者赶上假期），也要把进度推到
    # end_date，不然下次还会重复请求同一段空区间。
    conn.execute(
        """
        INSERT INTO sync_state (code, last_date) VALUES (?, ?)
        ON CONFLICT(code) DO UPDATE SET last_date = excluded.last_date
        """,
        (code, last_date or end_date),
    )
    conn.commit()


def main() -> None:
    args = parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)

    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"baostock login failed: {login.error_msg}")
    try:
        n = refresh_universe(conn)
        print(f"universe refreshed: {n} stocks", flush=True)

        today = date.today().isoformat()
        batch = pick_batch(conn, args.batch_size, today)
        if not batch:
            print("nothing to sync, all caught up", flush=True)
            return

        for code, list_date, delist_date, last_date in batch:
            start = _next_day(last_date) if last_date else list_date
            end = delist_date if delist_date else today
            if start > end:
                continue
            sync_one(conn, code, start, end)
            print(f"synced {code}: {start} ~ {end}", flush=True)
        print(f"batch done: {len(batch)} stocks", flush=True)
    finally:
        bs.logout()
        conn.close()


if __name__ == "__main__":
    main()
