"""抓取 Product Hunt 每日 featured 排行,寫入 SQLite。

用法:
    python fetch_ph.py                          # 抓「昨天」(PH 太平洋時區)
    python fetch_ph.py --date 2026-06-01        # 抓指定日期
    python fetch_ph.py --from 2026-06-01 --to 2026-06-30   # 回補區間
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PH_TZ = ZoneInfo("America/Los_Angeles")


def _utc_iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ph_day_bounds(day):
    """回傳該 PH 日(太平洋時區)的 [起, 迄) UTC ISO8601 字串。"""
    start = datetime(day.year, day.month, day.day, tzinfo=PH_TZ)
    nxt = day + timedelta(days=1)
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=PH_TZ)
    return _utc_iso(start), _utc_iso(end)
