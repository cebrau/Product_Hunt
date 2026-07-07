"""抓取 Product Hunt 每日 featured 排行,寫入 SQLite。

用法:
    python fetch_ph.py                          # 抓「昨天」(PH 太平洋時區)
    python fetch_ph.py --date 2026-06-01        # 抓指定日期
    python fetch_ph.py --from 2026-06-01 --to 2026-06-30   # 回補區間
"""
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PH_TZ = ZoneInfo("America/Los_Angeles")

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_rankings (
    date           TEXT NOT NULL,
    rank           INTEGER NOT NULL,
    product_id     TEXT NOT NULL,
    name           TEXT NOT NULL,
    tagline        TEXT,
    votes_count    INTEGER,
    comments_count INTEGER,
    topics         TEXT,
    ph_url         TEXT,
    website        TEXT,
    fetched_at     TEXT,
    PRIMARY KEY (date, product_id)
)
"""

UPSERT_SQL = """
INSERT INTO daily_rankings
    (date, rank, product_id, name, tagline, votes_count,
     comments_count, topics, ph_url, website, fetched_at)
VALUES
    (:date, :rank, :product_id, :name, :tagline, :votes_count,
     :comments_count, :topics, :ph_url, :website, :fetched_at)
ON CONFLICT(date, product_id) DO UPDATE SET
    rank = excluded.rank,
    name = excluded.name,
    tagline = excluded.tagline,
    votes_count = excluded.votes_count,
    comments_count = excluded.comments_count,
    topics = excluded.topics,
    ph_url = excluded.ph_url,
    website = excluded.website,
    fetched_at = excluded.fetched_at
"""


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


def open_db(path):
    """開啟(必要時建立)資料庫並確保 schema 存在。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)
    return conn


def upsert_rows(conn, rows):
    conn.executemany(UPSERT_SQL, rows)
    conn.commit()


def resolve_target_dates(args, today=None):
    """由 CLI 參數決定要抓的日期列表;預設抓 PH 時區的「昨天」。"""
    if args.date:
        return [date.fromisoformat(args.date)]
    if args.from_date or args.to_date:
        if not (args.from_date and args.to_date):
            raise SystemExit("--from 與 --to 必須同時提供")
        start = date.fromisoformat(args.from_date)
        end = date.fromisoformat(args.to_date)
        if start > end:
            raise SystemExit("--from 不可晚於 --to")
        return [start + timedelta(days=i) for i in range((end - start).days + 1)]
    if today is None:
        today = datetime.now(PH_TZ).date()
    return [today - timedelta(days=1)]
