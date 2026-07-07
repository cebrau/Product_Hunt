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
