# Product Hunt 每日熱門排行抓取 — 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每天用 Product Hunt 官方 GraphQL API 抓取當日全部 featured 產品排行,寫入 SQLite,由 GitHub Actions 每日排程並 commit 回 repo。

**Architecture:** 單一 Python 腳本 `fetch_ph.py`:純函式(日期邊界換算、API 回應解析、CLI 日期解析)與副作用層(HTTP、SQLite)分離。GitHub Actions 每日 08:30 UTC 執行並把更新後的 `.db` push 回 repo。

**Tech Stack:** Python 3.12(stdlib `sqlite3`、`zoneinfo`)、requests、pytest、GitHub Actions。

**Spec:** `docs/superpowers/specs/2026-07-07-producthunt-daily-ranking-design.md`

---

## 檔案結構

| 檔案 | 職責 |
|---|---|
| `fetch_ph.py` | 唯一程式:CLI、API 呼叫、解析、SQLite 寫入 |
| `tests/test_fetch_ph.py` | 純函式與 DB upsert 的單元測試(不打真實 API) |
| `requirements.txt` | requests、pytest |
| `.github/workflows/daily.yml` | 每日排程 + 手動觸發 + commit 資料庫 |
| `data/producthunt.db` | SQLite 資料庫(首次執行時自動建立) |
| `README.md` | 使用說明、token 申請、GitHub 設定步驟 |

---

### Task 1: 專案骨架

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `data/.gitkeep`

- [ ] **Step 1: 建立 requirements.txt**

```
requests>=2.31
pytest>=8.0
```

- [ ] **Step 2: 建立 .gitignore**

```
__pycache__/
*.pyc
.pytest_cache/
.venv/
```

- [ ] **Step 3: 建立 data/.gitkeep(空檔案)並安裝依賴**

Run: `pip install -r requirements.txt`
Expected: 成功安裝 requests 與 pytest

- [ ] **Step 4: Commit**

```bash
git add requirements.txt .gitignore data/.gitkeep
git commit -m "chore: project skeleton"
```

---

### Task 2: 日期邊界換算 `ph_day_bounds`

Product Hunt 的「一天」以 America/Los_Angeles 為準,要把日曆日換成 UTC 的 [起, 迄) ISO8601 字串。

**Files:**
- Create: `fetch_ph.py`
- Create: `tests/test_fetch_ph.py`

- [ ] **Step 1: 寫失敗測試**

`tests/test_fetch_ph.py`:

```python
from datetime import date

from fetch_ph import ph_day_bounds


def test_ph_day_bounds_winter_pst():
    # 冬令 PST = UTC-8
    start, end = ph_day_bounds(date(2026, 1, 15))
    assert start == "2026-01-15T08:00:00Z"
    assert end == "2026-01-16T08:00:00Z"


def test_ph_day_bounds_summer_pdt():
    # 夏令 PDT = UTC-7
    start, end = ph_day_bounds(date(2026, 7, 7))
    assert start == "2026-07-07T07:00:00Z"
    assert end == "2026-07-08T07:00:00Z"


def test_ph_day_bounds_dst_transition():
    # 2026-03-08 是美國春季轉換日:起點還是 PST,隔日零點已是 PDT
    start, end = ph_day_bounds(date(2026, 3, 8))
    assert start == "2026-03-08T08:00:00Z"
    assert end == "2026-03-09T07:00:00Z"
```

- [ ] **Step 2: 執行測試,確認失敗**

Run: `python -m pytest tests/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fetch_ph'`

- [ ] **Step 3: 建立 `fetch_ph.py`,實作 `ph_day_bounds`**

```python
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
```

- [ ] **Step 4: 執行測試,確認通過**

Run: `python -m pytest tests/ -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add fetch_ph.py tests/test_fetch_ph.py
git commit -m "feat: PH day to UTC bounds conversion"
```

---

### Task 3: API 回應解析 `rows_from_posts`

把 API 回傳的 post node 列表轉成資料列 dict,依序編名次、攤平 topics。

**Files:**
- Modify: `fetch_ph.py`
- Modify: `tests/test_fetch_ph.py`

- [ ] **Step 1: 寫失敗測試(附在 tests/test_fetch_ph.py 末尾)**

```python
from fetch_ph import rows_from_posts

SAMPLE_POSTS = [
    {
        "id": "post-1",
        "name": "SuperApp",
        "tagline": "The best app",
        "url": "https://www.producthunt.com/posts/superapp",
        "website": "https://superapp.com",
        "votesCount": 512,
        "commentsCount": 44,
        "topics": {"edges": [{"node": {"name": "AI"}},
                             {"node": {"name": "Productivity"}}]},
    },
    {
        "id": "post-2",
        "name": "MiniTool",
        "tagline": None,
        "url": "https://www.producthunt.com/posts/minitool",
        "website": None,
        "votesCount": 300,
        "commentsCount": 10,
        "topics": {"edges": []},
    },
]


def test_rows_from_posts_ranks_and_flattens():
    rows = rows_from_posts("2026-07-06", SAMPLE_POSTS, "2026-07-07T08:30:00Z")
    assert len(rows) == 2
    first, second = rows
    assert first["date"] == "2026-07-06"
    assert first["rank"] == 1
    assert first["product_id"] == "post-1"
    assert first["name"] == "SuperApp"
    assert first["topics"] == "AI,Productivity"
    assert first["votes_count"] == 512
    assert first["comments_count"] == 44
    assert first["ph_url"] == "https://www.producthunt.com/posts/superapp"
    assert first["website"] == "https://superapp.com"
    assert first["fetched_at"] == "2026-07-07T08:30:00Z"
    assert second["rank"] == 2
    assert second["topics"] == ""
    assert second["tagline"] is None
```

- [ ] **Step 2: 執行測試,確認失敗**

Run: `python -m pytest tests/ -v`
Expected: FAIL — `ImportError: cannot import name 'rows_from_posts'`

- [ ] **Step 3: 實作(附在 fetch_ph.py)**

```python
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
```

- [ ] **Step 4: 執行測試,確認通過**

Run: `python -m pytest tests/ -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add fetch_ph.py tests/test_fetch_ph.py
git commit -m "feat: parse API posts into ranked rows"
```

---

### Task 4: SQLite schema 與 upsert

**Files:**
- Modify: `fetch_ph.py`
- Modify: `tests/test_fetch_ph.py`

- [ ] **Step 1: 寫失敗測試(附在 tests/test_fetch_ph.py 末尾)**

```python
from fetch_ph import open_db, upsert_rows


def _sample_rows(votes=512):
    return rows_from_posts("2026-07-06", [
        {**SAMPLE_POSTS[0], "votesCount": votes},
        SAMPLE_POSTS[1],
    ], "2026-07-07T08:30:00Z")


def test_upsert_is_idempotent(tmp_path):
    db = str(tmp_path / "test.db")
    conn = open_db(db)
    upsert_rows(conn, _sample_rows(votes=512))
    upsert_rows(conn, _sample_rows(votes=600))  # 同日重抓,票數更新
    count, = conn.execute("SELECT COUNT(*) FROM daily_rankings").fetchone()
    assert count == 2
    votes, = conn.execute(
        "SELECT votes_count FROM daily_rankings WHERE product_id='post-1'"
    ).fetchone()
    assert votes == 600
    conn.close()
```

- [ ] **Step 2: 執行測試,確認失敗**

Run: `python -m pytest tests/ -v`
Expected: FAIL — `ImportError: cannot import name 'open_db'`

- [ ] **Step 3: 實作(附在 fetch_ph.py;`import os`、`import sqlite3` 加到檔頭)**

```python
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


def open_db(path):
    """開啟(必要時建立)資料庫並確保 schema 存在。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)
    return conn


def upsert_rows(conn, rows):
    conn.executemany(UPSERT_SQL, rows)
    conn.commit()
```

- [ ] **Step 4: 執行測試,確認通過**

Run: `python -m pytest tests/ -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add fetch_ph.py tests/test_fetch_ph.py
git commit -m "feat: SQLite schema and idempotent upsert"
```

---

### Task 5: CLI 日期解析 `resolve_target_dates`

**Files:**
- Modify: `fetch_ph.py`
- Modify: `tests/test_fetch_ph.py`

- [ ] **Step 1: 寫失敗測試(附在 tests/test_fetch_ph.py 末尾)**

```python
import argparse

import pytest

from fetch_ph import resolve_target_dates


def _args(**kw):
    return argparse.Namespace(date=None, from_date=None, to_date=None, **kw)


def test_default_is_yesterday_ph_time():
    days = resolve_target_dates(_args(), today=date(2026, 7, 7))
    assert days == [date(2026, 7, 6)]


def test_single_date():
    days = resolve_target_dates(_args(date="2026-06-01"))
    assert days == [date(2026, 6, 1)]


def test_range():
    days = resolve_target_dates(_args(from_date="2026-06-01", to_date="2026-06-03"))
    assert days == [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]


def test_range_requires_both_ends():
    with pytest.raises(SystemExit):
        resolve_target_dates(_args(from_date="2026-06-01"))


def test_range_order_validated():
    with pytest.raises(SystemExit):
        resolve_target_dates(_args(from_date="2026-06-03", to_date="2026-06-01"))
```

注意:`_args(date="2026-06-01")` 這種寫法會與預設的 `date=None` 重複給值而報 TypeError,所以 `_args` 要寫成先建 dict 再覆蓋:

```python
def _args(**kw):
    base = {"date": None, "from_date": None, "to_date": None}
    base.update(kw)
    return argparse.Namespace(**base)
```

(用上面這個版本,不要用最初那個。)

- [ ] **Step 2: 執行測試,確認失敗**

Run: `python -m pytest tests/ -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_target_dates'`

- [ ] **Step 3: 實作(附在 fetch_ph.py)**

```python
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
```

- [ ] **Step 4: 執行測試,確認通過**

Run: `python -m pytest tests/ -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add fetch_ph.py tests/test_fetch_ph.py
git commit -m "feat: CLI date resolution with backfill range"
```

---

### Task 6: HTTP 層與 main(API 呼叫、分頁、重試)

副作用層,不寫單元測試;以「缺 token 時報錯」煙霧測試 + 全套 pytest 驗證沒弄壞純函式。真實 API 呼叫留到 Task 9 端到端驗證。

**Files:**
- Modify: `fetch_ph.py`

- [ ] **Step 1: 實作 HTTP 層與 main(附在 fetch_ph.py;檔頭補 `import argparse, sys, time`、`import requests`)**

```python
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
```

- [ ] **Step 2: 煙霧測試(不打 API)**

Run: `python fetch_ph.py --date 2026-07-06`(不設 PH_API_TOKEN)
Expected: 印出「缺少環境變數 PH_API_TOKEN...」,exit code 非 0

Run: `python -m pytest tests/ -v`
Expected: 10 passed

- [ ] **Step 3: Commit**

```bash
git add fetch_ph.py
git commit -m "feat: GraphQL fetch with pagination, retry, and CLI main"
```

---

### Task 7: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/daily.yml`

- [ ] **Step 1: 建立 workflow**

```yaml
name: Daily Product Hunt rankings

on:
  schedule:
    - cron: "30 8 * * *"   # 08:30 UTC = 台灣 16:30;PH 的「昨天」已收盤
  workflow_dispatch:
    inputs:
      date:
        description: "抓指定日期 YYYY-MM-DD(留空 = 昨天)"
        required: false
      from:
        description: "回補起日 YYYY-MM-DD(需搭配 to)"
        required: false
      to:
        description: "回補迄日 YYYY-MM-DD(需搭配 from)"
        required: false

permissions:
  contents: write

jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - run: pip install -r requirements.txt

      - name: Fetch rankings
        env:
          PH_API_TOKEN: ${{ secrets.PH_API_TOKEN }}
          INPUT_DATE: ${{ inputs.date }}
          INPUT_FROM: ${{ inputs.from }}
          INPUT_TO: ${{ inputs.to }}
        run: |
          ARGS=""
          if [ -n "$INPUT_DATE" ]; then ARGS="--date $INPUT_DATE"; fi
          if [ -n "$INPUT_FROM" ]; then ARGS="--from $INPUT_FROM --to $INPUT_TO"; fi
          python fetch_ph.py $ARGS

      - name: Commit database
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/producthunt.db
          if git diff --cached --quiet; then
            echo "No changes"
          else
            git commit -m "data: update rankings ($(date -u +%F))"
            git push
          fi
```

- [ ] **Step 2: 驗證 YAML 語法**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/daily.yml', encoding='utf-8')); print('OK')"`
(若無 pyyaml 先 `pip install pyyaml`)
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/daily.yml
git commit -m "ci: daily fetch workflow with manual backfill"
```

---

### Task 8: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: 撰寫 README**

內容必須包含(用繁體中文):
1. 專案簡介:每天抓 PH featured 排行進 SQLite
2. Token 申請步驟:登入 producthunt.com → https://www.producthunt.com/v2/oauth/applications → Add an application(名稱隨意,Redirect URI 填 `https://localhost`)→ 建立後複製 **Developer Token**
3. 本機執行:`pip install -r requirements.txt`、設 `PH_API_TOKEN` 環境變數(PowerShell:`$env:PH_API_TOKEN = "..."`)、三種 CLI 用法
4. GitHub 自動化設定:建 repo → push → Settings → Secrets and variables → Actions → New repository secret,名稱 `PH_API_TOKEN` → Actions 頁籤手動跑一次 workflow 驗證
5. 資料表 schema 說明與查詢範例(如 `sqlite3 data/producthunt.db "SELECT * FROM daily_rankings WHERE date='2026-07-06' ORDER BY rank"`)

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: usage and setup guide"
```

---

### Task 9: 端到端驗證(需要真實 token)

**前置:** 使用者已取得 PH Developer Token。沒有 token 時此任務暫停,由使用者完成後再驗證。

- [ ] **Step 1: 本機以真實 token 跑一次**

Run(PowerShell):
```powershell
$env:PH_API_TOKEN = "<你的 token>"
python fetch_ph.py --date 2026-07-05
```
Expected: 印出「抓取 2026-07-05 ...」「已寫入 N 筆」(N 通常 20〜50)

- [ ] **Step 2: 檢查資料**

Run: `python -c "import sqlite3; c = sqlite3.connect('data/producthunt.db'); [print(r) for r in c.execute('SELECT date, rank, name, votes_count FROM daily_rankings ORDER BY rank LIMIT 5')]"`
Expected: 前 5 名產品,名次 1〜5、票數遞減

- [ ] **Step 3: Commit 首批資料**

```bash
git add data/producthunt.db
git commit -m "data: first fetch"
```

---

## 自我檢查(已執行)

- Spec 覆蓋:欄位 ✓(Task 3/4)、時區 ✓(Task 2)、回補 ✓(Task 5)、重試與 0 筆防護 ✓(Task 6)、排程與手動觸發 ✓(Task 7)、README 待辦 ✓(Task 8)、端到端 ✓(Task 9)
- 無佔位符;各任務間函式名稱與簽名一致(`ph_day_bounds`、`rows_from_posts`、`open_db`、`upsert_rows`、`resolve_target_dates`、`fetch_day_posts`)
