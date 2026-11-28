"""Discord Webhook 推播模組：推送 Product Hunt 每日排行 Top N。

沒設定 DISCORD_WEBHOOK_URL 或推播失敗時只記錄訊息並降級跳過，不中斷抓取與入庫流程。

也可獨立從本機資料庫手動推播或測試版面：
    python notify_discord.py                   # 推資料庫中最新一天 Top 10
    python notify_discord.py --date 2026-11-26 # 推指定日期 Top 10
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from typing import Any, Mapping, Sequence

import requests

DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "producthunt.db"
)

# Discord 單則訊息最多 10 張 embed 卡片。
EMBEDS_PER_MESSAGE = 10
DESCRIPTION_LIMIT = 300
TOPICS_LIMIT = 200

# Product Hunt 品牌橘紅色，用於在共用頻道中與其他來源視覺區隔。
PH_COLOR = 0xDA552F
WEBHOOK_USERNAME = "Product Hunt 每日排行"


def _get(row: Mapping[str, Any] | sqlite3.Row, key: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(key, default)
    return row[key] if key in row.keys() else default


def _safe_markdown_url(url: str) -> str:
    return url.strip().replace("(", "%28").replace(")", "%29")


def build_embed(row: Mapping[str, Any] | sqlite3.Row, day_iso: str) -> dict[str, Any]:
    """將單筆 Product Hunt 排行資料轉成 Discord Embed 物件。"""
    rank = _get(row, "rank")
    name = (_get(row, "name") or "").strip()
    title = f"#{rank} {name}" if rank is not None else name

    tagline = (_get(row, "tagline") or "").strip()
    if len(tagline) > DESCRIPTION_LIMIT:
        tagline = tagline[:DESCRIPTION_LIMIT].rstrip() + "…"

    fields: list[dict[str, Any]] = []
    votes = _get(row, "votes_count")
    if votes is not None:
        fields.append({"name": "票數", "value": f"▲ {votes}", "inline": True})

    comments = _get(row, "comments_count")
    if comments is not None:
        fields.append({"name": "評論數", "value": f"💬 {comments}", "inline": True})

    website = (_get(row, "website") or "").strip()
    if website:
        fields.append(
            {
                "name": "官網",
                "value": f"[前往官網]({_safe_markdown_url(website)})",
                "inline": True,
            }
        )

    topics_raw = (_get(row, "topics") or "").strip()
    if topics_raw:
        topics = ", ".join(t.strip() for t in topics_raw.split(",") if t.strip())
        if len(topics) > TOPICS_LIMIT:
            topics = topics[:TOPICS_LIMIT].rstrip() + "…"
        if topics:
            fields.append({"name": "主題", "value": topics, "inline": False})

    embed: dict[str, Any] = {
        "title": title[:250],
        "description": tagline,
        "color": PH_COLOR,
        "fields": fields,
        "footer": {"text": f"來源：Product Hunt • {day_iso}"},
    }
    ph_url = (_get(row, "ph_url") or "").strip()
    if ph_url:
        embed["url"] = ph_url
    return embed


def send_daily_top(
    webhook_url: str | None,
    day_iso: str,
    rows: Sequence[Mapping[str, Any] | sqlite3.Row],
    top_n: int = 10,
    sleep=time.sleep,
) -> int:
    """推送單日 Product Hunt Top N 到 Discord，回傳實際送出的筆數。"""
    if not rows:
        return 0
    if not webhook_url:
        print("  未設定 DISCORD_WEBHOOK_URL，略過 Discord 推播", flush=True)
        return 0

    ordered = sorted(rows, key=lambda r: _get(r, "rank", 0))
    selected = ordered[:top_n] if top_n and top_n > 0 else ordered
    total_count = len(rows)

    sent = 0
    for start in range(0, len(selected), EMBEDS_PER_MESSAGE):
        chunk = selected[start : start + EMBEDS_PER_MESSAGE]
        if start == 0:
            content = (
                f"🚀 **[Product Hunt]** {day_iso} 每日排行 "
                f"Top {len(selected)}（當日共 {total_count} 筆上榜）"
            )
        else:
            content = (
                f"🚀 **[Product Hunt]** {day_iso} 每日排行"
                f"（續 #{start + 1}–#{start + len(chunk)}）"
            )

        payload = {
            "username": WEBHOOK_USERNAME,
            "content": content,
            "embeds": [build_embed(row, day_iso) for row in chunk],
        }

        try:
            response = requests.post(webhook_url, json=payload, timeout=30)
        except requests.RequestException as exc:
            print(f"  Discord 推播失敗：{exc}", flush=True)
            break

        if response.status_code == 429:
            try:
                retry_after = float(response.json().get("retry_after", 5))
            except (ValueError, TypeError):
                retry_after = 5.0
            print(f"  Discord 限流，等待 {retry_after:.1f} 秒後重試", flush=True)
            sleep(retry_after)
            try:
                response = requests.post(webhook_url, json=payload, timeout=30)
            except requests.RequestException as exc:
                print(f"  Discord 重試失敗：{exc}", flush=True)
                break

        if response.status_code >= 300:
            print(
                f"  Discord 回傳 {response.status_code}：{response.text[:200]}",
                flush=True,
            )
            break

        sent += len(chunk)
        if start + EMBEDS_PER_MESSAGE < len(selected):
            sleep(1)

    return sent


def load_day_rows(db_path: str, day_iso: str | None = None) -> tuple[str | None, list[sqlite3.Row]]:
    """從 SQLite 讀取指定日期（或最新日期）的排行資料。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if not day_iso:
            row = conn.execute("SELECT MAX(date) FROM daily_rankings").fetchone()
            day_iso = row[0] if row else None
        if not day_iso:
            return None, []
        rows = conn.execute(
            "SELECT * FROM daily_rankings WHERE date = ? ORDER BY rank ASC",
            (day_iso,),
        ).fetchall()
        return day_iso, rows
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="從本機 SQLite 推播 Product Hunt 排行到 Discord")
    parser.add_argument("--date", help="指定日期 YYYY-MM-DD（留空 = 資料庫最新一天）")
    parser.add_argument("--top", type=int, default=10, help="推送前幾名（預設 10）")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite 檔案路徑")
    args = parser.parse_args(argv)

    day_iso, rows = load_day_rows(args.db, args.date)
    if not day_iso or not rows:
        print(f"查無資料（date={args.date or '最新'}）")
        return 1

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    sent = send_daily_top(webhook_url, day_iso, rows, top_n=args.top)
    if sent:
        print(f"已推播 Product Hunt {day_iso} Top {sent} 到 Discord")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
