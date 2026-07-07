# Product Hunt 每日熱門排行抓取 — 設計文件

日期:2026-07-07
狀態:已與使用者確認

## 目標

每天自動抓取 Product Hunt 當日全部 featured 產品的排行,長期累積成資料庫,供日後趨勢分析使用。

## 需求摘要

- **資料範圍**:每日全部 featured 產品(通常 20〜50 筆)
- **欄位**:日期、名次、產品名稱、tagline、票數、評論數、topics、產品連結
- **資料來源**:Product Hunt 官方 GraphQL API v2(非網頁爬取)
- **儲存**:SQLite 單一檔案,commit 進 git repo
- **排程**:GitHub Actions 每日自動執行,不依賴本機開機
- **回補能力**:API 可查歷史日期,排程中斷後可補齊任意日期

## 方案選擇

採用「純 Python 腳本」方案:單一腳本呼叫 API 寫入 SQLite,由 GitHub Actions 排程。
否決方案:Scrapy 框架(對單次 API 呼叫過重)、每日 JSON 快照(多一層流程,API 可回補故不需快照當保險)。

## 專案結構

```
Product_Hunt/
├── fetch_ph.py              # 主腳本(唯一的程式)
├── requirements.txt         # requests(執行)、pytest(測試)
├── data/
│   └── producthunt.db       # SQLite 資料庫(commit 進 repo)
├── .github/workflows/
│   └── daily.yml            # GitHub Actions 排程
├── tests/
│   └── test_fetch_ph.py     # pytest 單元測試
├── docs/superpowers/specs/  # 設計文件
└── README.md                # 使用說明(含 token 申請步驟)
```

## 資料庫 Schema

一張主表,以(日期, 產品 ID)為主鍵,重跑同一天採 upsert 覆蓋更新,不會重複插入:

```sql
CREATE TABLE daily_rankings (
    date           TEXT NOT NULL,   -- PH 當日(太平洋時間),如 '2026-07-07'
    rank           INTEGER NOT NULL,
    product_id     TEXT NOT NULL,   -- PH 的產品 ID
    name           TEXT NOT NULL,
    tagline        TEXT,
    votes_count    INTEGER,
    comments_count INTEGER,
    topics         TEXT,            -- 逗號分隔,如 'AI,Productivity'
    ph_url         TEXT,            -- Product Hunt 產品頁連結
    website        TEXT,            -- 產品官網
    fetched_at     TEXT,            -- 抓取時間戳(UTC ISO8601)
    PRIMARY KEY (date, product_id)
);
```

資料表由腳本啟動時自動建立(`CREATE TABLE IF NOT EXISTS`)。

## 抓取邏輯(fetch_ph.py)

- 端點:`https://api.producthunt.com/v2/api/graphql`,以 `Authorization: Bearer <token>` 認證,token 從環境變數 `PH_API_TOKEN` 讀取。
- 查詢:`posts`,以 `postedAfter` / `postedBefore` 界定目標日、`featured: true`、`order: RANKING` 排序,分頁(cursor)抓取當日全部;名次 = 排序後的順位(1 起算)。
- 每筆取:`id, name, tagline, url, website, votesCount, commentsCount, topics`。
- **時區**:Product Hunt 的「一天」以美國太平洋時間(America/Los_Angeles,自動處理 PST/PDT)為準,日期邊界據此換算成 UTC 時間戳傳給 API。
- **CLI 介面**:
  - `python fetch_ph.py` — 抓「昨天」(PH 時區),榜已收盤、名次固定
  - `python fetch_ph.py --date 2026-06-01` — 抓指定日
  - `python fetch_ph.py --from 2026-06-01 --to 2026-06-30` — 回補區間(逐日呼叫,尊重 API rate limit,必要時 sleep)
- 程式結構:「解析 API 回應 → 資料列」抽成純函式,與 HTTP、DB 寫入分離,便於測試。

## GitHub Actions(daily.yml)

- **排程**:每天 `08:30 UTC`(台灣 16:30)。此時 PH 的「昨天」已收盤至少 1.5 小時,資料完整。
- **流程**:checkout → setup Python → `pip install -r requirements.txt` → `python fetch_ph.py` → 若 `data/producthunt.db` 有變動則 commit + push。
- **認證**:token 存在 repo Secrets(`PH_API_TOKEN`),workflow 以環境變數注入。
- **手動觸發**:保留 `workflow_dispatch`,並提供可選的日期(或區間)輸入參數,供網頁上補抓。

## 錯誤處理

- API 錯誤、網路失敗、token 無效:腳本印出錯誤並以非零碼結束;GitHub Actions 顯示失敗,GitHub 寄失敗通知信給使用者。
- 抓到 0 筆:視為異常、報錯結束(featured 榜不會是空的),避免靜默寫入空資料。
- Rate limit(HTTP 429 或 API 額度回應):等待後重試,重試數次仍失敗則報錯。
- 重跑安全:upsert 主鍵設計保證任何日期重抓皆冪等。

## 測試

- pytest 單元測試,不打真實 API:
  - API 回應 JSON → 資料列的解析正確性(含 topics 攤平、名次編號)
  - upsert:同日重複寫入不產生重複列、欄位被更新
  - 日期邊界:指定日期 → PST/PDT 正確換算成 UTC 區間(涵蓋日光節約切換日)
- 端到端:以真實 token 手動執行一次,驗證 API 呼叫與完整流程。

## 使用者待辦

1. 到 https://www.producthunt.com/v2/oauth/applications 註冊 application,取得 **Developer Token**。
2. 建立 GitHub repo 並 push 本專案。
3. 在 repo Settings → Secrets and variables → Actions 新增 `PH_API_TOKEN`。

詳細步驟寫在 README。
