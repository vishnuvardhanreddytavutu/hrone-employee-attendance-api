
from datetime import datetime
from zoneinfo import ZoneInfo
from app.main import (
    compute_late_minutes,
    compute_overtime,
    compute_work_hours,
    round_half_up,
)

IST = ZoneInfo("Asia/Kolkata")


def local_time(value):
    return datetime.fromisoformat(value).replace(tzinfo=IST)


def test_late_minutes_grace_boundary():
    assert compute_late_minutes(local_time("2026-10-12T09:40:00"), "09:30") == 0
    assert compute_late_minutes(local_time("2026-10-12T09:40:01"), "09:30") == 10
    assert compute_late_minutes(local_time("2026-10-12T10:15:59"), "09:30") == 45


def test_round_half_up():
    assert round_half_up(4.444) == 4.44
    assert round_half_up(4.445) == 4.45
    assert round_half_up(7.125) == 7.13


def test_work_hours():
    start = local_time("2026-10-12T09:30:00")
    end = local_time("2026-10-12T14:00:00")
    assert compute_work_hours(start, end) == 4.5
def test_overtime_below_30_minute_threshold():
    punch_in = local_time("2026-10-13T09:50:00")
    punch_out = local_time("2026-10-13T18:50:00")

    assert compute_overtime(
        punch_out, "09:30", "18:30", punch_in
    ) == 0