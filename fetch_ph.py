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


def rows_from_posts(day_iso, posts, fetched_at):
    """API post node 列表 → 資料列 dict 列表;rank 依輸入順序 1 起算。"""
    rows = []
    for rank, post in enumerate(posts, start=1):
        topic_names = [e["node"]["name"]
                       for e in post.get("topics", {}).get("edges", [])]
        rows.append({
            "date": day_iso,
            "rank": rank,
            "product_id": post["id"],
            "name": post["name"],
            "tagline": post.get("tagline"),
            "votes_count": post.get("votesCount"),
            "comments_count": post.get("commentsCount"),
            "topics": ",".join(topic_names),
            "ph_url": post.get("url"),
            "website": post.get("website"),
            "fetched_at": fetched_at,
        })
    return rows
