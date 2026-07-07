from datetime import date

from fetch_ph import ph_day_bounds, rows_from_posts

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
    upsert_rows(conn, _sample_rows(votes=600))
    count, = conn.execute("SELECT COUNT(*) FROM daily_rankings").fetchone()
    assert count == 2
    votes, = conn.execute(
        "SELECT votes_count FROM daily_rankings WHERE product_id='post-1'"
    ).fetchone()
    assert votes == 600
    conn.close()
