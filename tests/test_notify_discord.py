from unittest.mock import MagicMock, patch

import fetch_ph
from notify_discord import (
    DESCRIPTION_LIMIT,
    PH_COLOR,
    WEBHOOK_USERNAME,
    build_embed,
    load_day_rows,
    send_daily_top,
)


def _make_rows(count: int, day: str = "2026-11-26") -> list[dict]:
    return [
        {
            "date": day,
            "rank": i,
            "product_id": f"p-{i}",
            "name": f"Product {i}",
            "tagline": f"Tagline for product {i}",
            "votes_count": 500 - i * 10,
            "comments_count": 30 - i,
            "topics": "AI,Developer Tools",
            "ph_url": f"https://www.producthunt.com/products/product-{i}",
            "website": f"https://www.producthunt.com/r/CODE{i}",
            "fetched_at": "2026-11-27T18:21:48Z",
        }
        for i in range(1, count + 1)
    ]


def test_build_embed_includes_source_markers_and_fields():
    row = _make_rows(1)[0]
    embed = build_embed(row, "2026-11-26")

    assert embed["title"] == "#1 Product 1"
    assert embed["url"] == "https://www.producthunt.com/products/product-1"
    assert embed["description"] == "Tagline for product 1"
    assert embed["color"] == PH_COLOR
    assert embed["footer"] == {"text": "來源：Product Hunt • 2026-11-26"}

    fields = {f["name"]: f for f in embed["fields"]}
    assert fields["票數"]["value"] == "▲ 490"
    assert fields["評論數"]["value"] == "💬 29"
    assert fields["官網"]["value"] == "[前往官網](https://www.producthunt.com/r/CODE1)"
    assert fields["主題"]["value"] == "AI, Developer Tools"
    assert fields["主題"]["inline"] is False


def test_build_embed_truncates_long_tagline_and_handles_missing_optional_fields():
    row = {
        "rank": 2,
        "name": "Minimal",
        "tagline": "x" * (DESCRIPTION_LIMIT + 50),
        "votes_count": 100,
        "comments_count": None,
        "topics": "",
        "ph_url": None,
        "website": None,
    }
    embed = build_embed(row, "2026-11-26")

    assert len(embed["description"]) == DESCRIPTION_LIMIT + 1
    assert embed["description"].endswith("…")
    assert "url" not in embed
    assert [f["name"] for f in embed["fields"]] == ["票數"]


def test_send_daily_top_skips_when_webhook_missing():
    with patch("notify_discord.requests.post") as mock_post:
        sent = send_daily_top(None, "2026-11-26", _make_rows(15), top_n=10)

    assert sent == 0
    mock_post.assert_not_called()


def test_send_daily_top_limits_to_top_10_and_sets_source_identity():
    resp = MagicMock(status_code=204)
    with patch("notify_discord.requests.post", return_value=resp) as mock_post:
        sent = send_daily_top(
            "https://discord.com/api/webhooks/test/token",
            "2026-11-26",
            _make_rows(25),
            top_n=10,
            sleep=lambda _: None,
        )

    assert sent == 10
    assert mock_post.call_count == 1
    payload = mock_post.call_args.kwargs["json"]
    assert payload["username"] == WEBHOOK_USERNAME
    assert "[Product Hunt]" in payload["content"]
    assert "2026-11-26" in payload["content"]
    assert "Top 10" in payload["content"]
    assert "共 25 筆" in payload["content"]
    assert len(payload["embeds"]) == 10
    assert payload["embeds"][0]["title"] == "#1 Product 1"
    assert payload["embeds"][-1]["title"] == "#10 Product 10"


def test_send_daily_top_retries_once_on_429():
    rate_limited = MagicMock(status_code=429)
    rate_limited.json.return_value = {"retry_after": 1.5}
    ok = MagicMock(status_code=204)
    slept = []

    with patch("notify_discord.requests.post", side_effect=[rate_limited, ok]) as mock_post:
        sent = send_daily_top(
            "https://discord.com/api/webhooks/test/token",
            "2026-11-26",
            _make_rows(3),
            top_n=10,
            sleep=slept.append,
        )

    assert sent == 3
    assert mock_post.call_count == 2
    assert slept == [1.5]


def test_load_day_rows_reads_latest_day_from_sqlite(tmp_path):
    db = str(tmp_path / "ph.db")
    conn = fetch_ph.open_db(db)
    fetch_ph.upsert_rows(conn, _make_rows(2, day="2026-11-25"))
    fetch_ph.upsert_rows(conn, _make_rows(3, day="2026-11-26"))
    conn.close()

    day, rows = load_day_rows(db)
    assert day == "2026-11-26"
    assert len(rows) == 3
    assert [r["rank"] for r in rows] == [1, 2, 3]


def test_fetch_ph_skips_notify_on_backfill(tmp_path, monkeypatch):
    db = str(tmp_path / "ph.db")
    monkeypatch.setenv("PH_API_TOKEN", "dummy-token")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test/token")

    fake_posts = [
        {
            "id": "p1",
            "name": "Demo",
            "tagline": "Test",
            "url": "https://www.producthunt.com/posts/demo",
            "website": "https://demo.example",
            "votesCount": 100,
            "commentsCount": 5,
            "topics": {"edges": [{"node": {"name": "AI"}}]},
        }
    ]

    with patch.object(fetch_ph, "fetch_day_posts", return_value=fake_posts), \
         patch.object(fetch_ph, "BACKFILL_PAUSE", 0), \
         patch.object(fetch_ph, "send_daily_top") as mock_send:
        fetch_ph.main(["--from", "2026-11-25", "--to", "2026-11-26", "--db", db])

    mock_send.assert_not_called()


def test_fetch_ph_notifies_on_single_date(tmp_path, monkeypatch):
    db = str(tmp_path / "ph.db")
    monkeypatch.setenv("PH_API_TOKEN", "dummy-token")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test/token")

    fake_posts = [
        {
            "id": "p1",
            "name": "Demo",
            "tagline": "Test",
            "url": "https://www.producthunt.com/posts/demo",
            "website": "https://demo.example",
            "votesCount": 100,
            "commentsCount": 5,
            "topics": {"edges": [{"node": {"name": "AI"}}]},
        }
    ]

    with patch.object(fetch_ph, "fetch_day_posts", return_value=fake_posts), \
         patch.object(fetch_ph, "send_daily_top", return_value=1) as mock_send:
        fetch_ph.main(["--date", "2026-11-26", "--db", db])

    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert call_args.args[0] == "https://discord.com/api/webhooks/test/token"
    assert call_args.args[1] == "2026-11-26"
    assert call_args.kwargs["top_n"] == 10
