# Product Hunt 每日熱門排行

每天自動抓取 [Product Hunt](https://www.producthunt.com) 當日全部 featured 產品排行(官方 GraphQL API,非網頁爬取),寫入 SQLite 長期累積,由 GitHub Actions 每日排程執行。

## 資料內容

`data/producthunt.db` 中的 `daily_rankings` 表,每天約 20〜50 筆:

| 欄位 | 說明 |
|---|---|
| `date` | Product Hunt 當日(美國太平洋時區),如 `2026-07-06` |
| `rank` | 當日名次(1 起算) |
| `product_id` | PH 產品 ID |
| `name` | 產品名稱 |
| `tagline` | 一句話簡介 |
| `votes_count` | 票數(upvotes) |
| `comments_count` | 評論數 |
| `topics` | 主題分類,逗號分隔,如 `AI,Productivity` |
| `ph_url` | Product Hunt 產品頁連結 |
| `website` | 產品官網 |
| `fetched_at` | 抓取時間(UTC) |

主鍵為 `(date, product_id)`,同一天重抓會更新而不會重複。

## 1. 申請 Product Hunt API Token

1. 登入 [producthunt.com](https://www.producthunt.com)
2. 前往 <https://www.producthunt.com/v2/oauth/applications>
3. 點 **Add an application**,名稱隨意(如 `daily-rankings`),Redirect URI 填 `https://localhost`
4. 建立後在 application 頁面複製 **Developer Token**(非商業用途免費)

## 2. 本機執行

```powershell
pip install -r requirements.txt
$env:PH_API_TOKEN = "你的 Developer Token"

python fetch_ph.py                            # 抓「昨天」(PH 時區),排程用
python fetch_ph.py --date 2026-06-01          # 抓指定日期
python fetch_ph.py --from 2026-06-01 --to 2026-06-30   # 回補一段區間
```

(Linux/macOS 設環境變數改用 `export PH_API_TOKEN=...`)

執行測試:

```
python -m pytest tests/
```

## 3. 設定 GitHub 每日自動抓取

1. 在 GitHub 建一個 repo(private 即可),把本專案 push 上去
2. Repo 頁面 → **Settings → Secrets and variables → Actions → New repository secret**
   - Name:`PH_API_TOKEN`
   - Secret:貼上你的 Developer Token
3. 到 **Actions** 頁籤,選 **Daily Product Hunt rankings** → **Run workflow** 手動跑一次驗證(可留空抓昨天,或填日期回補)
4. 之後每天 08:30 UTC(台灣 16:30)自動執行,抓「昨天」的完整排行並把更新後的資料庫 commit 回 repo

排程若某幾天失敗(GitHub 會寄通知信),用 Run workflow 填 `from`/`to` 補齊即可。

## 查詢範例

```bash
# 某天完整排行
sqlite3 data/producthunt.db "SELECT rank, name, votes_count FROM daily_rankings WHERE date='2026-07-06' ORDER BY rank"

# 最近 30 天最常上榜的主題
sqlite3 data/producthunt.db "SELECT topics, COUNT(*) FROM daily_rankings WHERE date >= date('now','-30 day') GROUP BY topics ORDER BY 2 DESC LIMIT 10"

# 匯出成 CSV
sqlite3 -header -csv data/producthunt.db "SELECT * FROM daily_rankings" > rankings.csv
```
