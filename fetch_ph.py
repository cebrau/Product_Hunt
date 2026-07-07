"""抓取 Product Hunt 每日 featured 排行,寫入 SQLite。

用法:
    python fetch_ph.py                          # 抓「昨天」(PH 太平洋時區)
    python fetch_ph.py --date 2026-06-01        # 抓指定日期
    python fetch_ph.py --from 2026-06-01 --to 2026-06-30   # 回補區間
"""
import argparse
import os
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

PH_TZ = ZoneInfo("America/Los_Angeles")

API_URL = "https://api.producthunt.com/v2/api/graphql"
DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "data", "producthunt.db")
RETRY_DELAYS = [15, 60, 180]   # 429/5xx 重試前等待秒數
BACKFILL_PAUSE = 5             # 回補多天時每天間隔秒數

QUERY = """
query DailyPosts($postedAfter: DateTime!, $postedBefore: DateTime!, $after: String) {
  posts(postedAfter: $postedAfter, postedBefore: $postedBefore,
        featured: true, order: RANKING, first: 20, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        name
        tagline
        url
        website
        votesCount
        commentsCount
        topics(first: 10) { edges { node { name } } }
      }
    }
  }
}
"""

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


def graphql_request(token, variables):
    """單次 GraphQL 呼叫;429/5xx 依 RETRY_DELAYS 重試。"""
    for delay in [0] + RETRY_DELAYS:
        if delay:
            print(f"  等待 {delay}s 後重試...", flush=True)
            time.sleep(delay)
        resp = requests.post(
            API_URL,
            json={"query": QUERY, "variables": variables},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code == 429 or resp.status_code >= 500:
            print(f"  API 回應 {resp.status_code}", flush=True)
            continue
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("errors"):
            raise SystemExit(f"GraphQL 錯誤: {payload['errors']}")
        return payload["data"]
    raise SystemExit("重試多次仍失敗(rate limit 或伺服器錯誤)")


def fetch_day_posts(token, day):
    """抓取單一 PH 日的全部 featured posts(自動翻頁)。"""
    posted_after, posted_before = ph_day_bounds(day)
    posts, cursor = [], None
    while True:
        data = graphql_request(token, {
            "postedAfter": posted_after,
            "postedBefore": posted_before,
            "after": cursor,
        })
        page = data["posts"]
        posts.extend(edge["node"] for edge in page["edges"])
        if not page["pageInfo"]["hasNextPage"]:
            return posts
        cursor = page["pageInfo"]["endCursor"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="抓取 Product Hunt 每日排行")
    parser.add_argument("--date", help="抓指定日期 YYYY-MM-DD")
    parser.add_argument("--from", dest="from_date", help="回補起日 YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", help="回補迄日 YYYY-MM-DD")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 檔案路徑")
    args = parser.parse_args(argv)

    token = os.environ.get("PH_API_TOKEN")
    if not token:
        raise SystemExit("缺少環境變數 PH_API_TOKEN(Product Hunt Developer Token)")

    days = resolve_target_dates(args)
    conn = open_db(args.db)
    try:
        for i, day in enumerate(days):
            if i:
                time.sleep(BACKFILL_PAUSE)
            print(f"抓取 {day} ...", flush=True)
            posts = fetch_day_posts(token, day)
            if not posts:
                raise SystemExit(f"{day} 抓到 0 筆,異常中止(featured 榜不應為空)")
            fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            upsert_rows(conn, rows_from_posts(day.isoformat(), posts, fetched_at))
            print(f"  已寫入 {len(posts)} 筆")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
