import datetime as dt

from services.weekly_digest import (
    WeeklyDigestSummary,
    build_weekly_digest_email,
    should_send_weekly_digest_now,
)


def test_build_weekly_digest_email_contains_insight_and_graph_markup():
    summary = WeeklyDigestSummary(
        week_start=dt.date(2026, 4, 6),
        week_end=dt.date(2026, 4, 12),
        income_total=1200.0,
        expense_total=650.0,
        net_total=550.0,
        transaction_count=12,
        top_categories=[("Food", 250.0), ("Transport", 120.0)],
        daily_expenses=[("Mon", 100.0), ("Tue", 80.0), ("Wed", 60.0), ("Thu", 90.0), ("Fri", 140.0), ("Sat", 110.0), ("Sun", 70.0)],
        highest_expense={"amount": 140.0, "category": "Food", "date": "2026-04-10", "description": "Dinner"},
        insight="Your spending stayed below income this week.",
    )

    email = build_weekly_digest_email("Alex", "AUD", summary)

    assert "Weekly Money Report" in email["html"]
    assert "Daily Expenses Graph" in email["html"]
    assert "Basic understanding" in email["html"]
    assert "Your spending stayed below income this week." in email["plain"]


def test_should_send_weekly_digest_now_respects_week_guard():
    settings = {
        "enabled": True,
        "weekday": 0,
        "hour": 9,
        "minute": 0,
        "timezone": "UTC",
        "last_sent_week": "2026-W15",
    }
    now = dt.datetime(2026, 4, 6, 10, 0, tzinfo=dt.timezone.utc)

    should_send, week_key = should_send_weekly_digest_now(settings, now)

    assert week_key == "2026-W15"
    assert should_send is False


def test_should_send_weekly_digest_now_allows_send_after_scheduled_time():
    settings = {
        "enabled": True,
        "weekday": 0,
        "hour": 9,
        "minute": 30,
        "timezone": "UTC",
        "last_sent_week": None,
    }
    now = dt.datetime(2026, 4, 6, 10, 0, tzinfo=dt.timezone.utc)

    should_send, week_key = should_send_weekly_digest_now(settings, now)

    assert week_key == "2026-W15"
    assert should_send is True
