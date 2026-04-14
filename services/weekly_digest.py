from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.database import supabase


@dataclass
class WeeklyDigestSummary:
    week_start: dt.date
    week_end: dt.date
    income_total: float
    expense_total: float
    net_total: float
    transaction_count: int
    top_categories: list[tuple[str, float]]
    daily_expenses: list[tuple[str, float]]
    highest_expense: dict | None
    insight: str


def week_key_for_date(day: dt.date) -> str:
    iso_year, iso_week, _ = day.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _week_bounds(reference_day: dt.date) -> tuple[dt.date, dt.date]:
    week_start = reference_day - dt.timedelta(days=reference_day.weekday())
    week_end = week_start + dt.timedelta(days=6)
    return week_start, week_end


def _parse_row_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def _currency_symbol(code: str | None) -> str:
    mapping = {
        "USD": "$",
        "AUD": "$",
        "CAD": "$",
        "NZD": "$",
        "EUR": "EUR ",
        "GBP": "GBP ",
        "INR": "INR ",
        "JPY": "JPY ",
        "SGD": "S$",
    }
    normalized = (code or "AUD").upper().strip()
    return mapping.get(normalized, f"{normalized} ")


def _build_insight(
    income_total: float,
    expense_total: float,
    top_categories: list[tuple[str, float]],
    transaction_count: int,
) -> str:
    if transaction_count == 0:
        return "No transactions were recorded this week. Add entries to get personalized trends."

    if expense_total <= 0:
        return "Great control this week — no expense outflow was recorded."

    if income_total <= 0:
        return "No income was recorded this week, so spend came fully from existing balance."

    savings_rate = (income_total - expense_total) / income_total
    top_name, top_value = top_categories[0] if top_categories else ("Other", 0.0)
    top_share = (top_value / expense_total) if expense_total > 0 else 0.0

    if savings_rate < 0:
        return (
            f"You spent more than you earned this week. {top_name} made up "
            f"{top_share * 100:.0f}% of all expenses."
        )
    if top_share >= 0.45:
        return (
            f"Your spending is concentrated in {top_name} ({top_share * 100:.0f}% of weekly expenses). "
            "Review that category first for quick savings."
        )
    if savings_rate >= 0.25:
        return "Solid week — you kept at least 25% of income as net savings."
    return "Your spending stayed below income this week, with room to improve category balance."


def build_weekly_digest_summary(
    user_id: str,
    reference_day: dt.date | None = None,
) -> WeeklyDigestSummary:
    day = reference_day or dt.datetime.now(dt.timezone.utc).date()
    week_start, week_end = _week_bounds(day)

    rows = (
        supabase.table("transactions")
        .select("date", "amount", "type", "category", "description", "notes")
        .eq("user_id", user_id)
        .gte("date", week_start.isoformat())
        .lte("date", week_end.isoformat())
        .execute()
        .data
    ) or []

    income_total = 0.0
    expense_total = 0.0
    by_category: dict[str, float] = {}
    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    by_day = {label: 0.0 for label in day_labels}
    highest_expense = None

    for row in rows:
        amount = float(row.get("amount") or 0)
        tx_type = (row.get("type") or "").strip().lower()
        tx_date = _parse_row_date(row.get("date"))

        if tx_type in {"income", "credit"}:
            income_total += amount
            continue

        expense_total += amount
        category = (row.get("category") or "Other").strip() or "Other"
        by_category[category] = by_category.get(category, 0.0) + amount

        if tx_date is not None and week_start <= tx_date <= week_end:
            by_day[day_labels[tx_date.weekday()]] += amount

        if highest_expense is None or amount > highest_expense["amount"]:
            highest_expense = {
                "amount": amount,
                "category": category,
                "date": row.get("date"),
                "description": (row.get("notes") or row.get("description") or "").strip(),
            }

    top_categories = sorted(by_category.items(), key=lambda item: item[1], reverse=True)[:5]
    daily_expenses = [(label, by_day[label]) for label in day_labels]
    net_total = income_total - expense_total

    insight = _build_insight(income_total, expense_total, top_categories, len(rows))

    return WeeklyDigestSummary(
        week_start=week_start,
        week_end=week_end,
        income_total=income_total,
        expense_total=expense_total,
        net_total=net_total,
        transaction_count=len(rows),
        top_categories=top_categories,
        daily_expenses=daily_expenses,
        highest_expense=highest_expense,
        insight=insight,
    )


def _daily_expense_svg(daily_expenses: list[tuple[str, float]]) -> str:
    max_value = max((value for _, value in daily_expenses), default=0.0)
    safe_max = max(max_value, 1.0)

    width = 520
    height = 180
    left = 36
    right = 16
    top = 12
    bottom = 32
    chart_width = width - left - right
    chart_height = height - top - bottom
    col_width = chart_width / max(len(daily_expenses), 1)

    bars = []
    labels = []
    for idx, (label, value) in enumerate(daily_expenses):
        bar_height = (value / safe_max) * chart_height
        x = left + idx * col_width + 6
        y = top + (chart_height - bar_height)
        bar_w = max(col_width - 12, 10)
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_height:.1f}" rx="5" fill="#F57C45" />'
        )
        labels.append(
            f'<text x="{(x + bar_w / 2):.1f}" y="{(height - 10):.1f}" text-anchor="middle" font-size="11" fill="#666">{label}</text>'
        )

    axis = (
        f'<line x1="{left}" y1="{top + chart_height}" x2="{width - right}" y2="{top + chart_height}" '
        'stroke="#E0E0E0" stroke-width="1" />'
    )

    return (
        f'<svg width="100%" viewBox="0 0 {width} {height}" role="img" aria-label="Daily expense chart">'
        f"{axis}{''.join(bars)}{''.join(labels)}"
        "</svg>"
    )


def _category_rows_html(
    top_categories: list[tuple[str, float]],
    currency_symbol: str,
) -> str:
    total = sum(value for _, value in top_categories)
    if total <= 0 or not top_categories:
        return '<p style="margin:0;color:#666;">No expense categories recorded this week.</p>'

    rows = []
    for name, value in top_categories:
        pct = (value / total) * 100
        rows.append(
            "<div style=\"margin-bottom:10px;\">"
            f"<div style=\"font-size:13px;font-weight:600;color:#333;\">{name}"
            f" <span style=\"color:#666;font-weight:500;\">{currency_symbol}{value:.2f} ({pct:.0f}%)</span></div>"
            "<div style=\"margin-top:4px;background:#F3F3F3;border-radius:8px;height:8px;overflow:hidden;\">"
            f"<div style=\"width:{pct:.1f}%;height:8px;background:#FBC34A;\"></div>"
            "</div>"
            "</div>"
        )
    return "".join(rows)


def build_weekly_digest_email(
    user_name: str | None,
    currency_code: str | None,
    summary: WeeklyDigestSummary,
) -> dict[str, str]:
    name = (user_name or "there").strip() or "there"
    currency_symbol = _currency_symbol(currency_code)

    subject = (
        f"Your weekly money report ({summary.week_start.strftime('%d %b')}"
        f" - {summary.week_end.strftime('%d %b')})"
    )

    top_line = (
        f"Income {currency_symbol}{summary.income_total:.2f}, "
        f"Expenses {currency_symbol}{summary.expense_total:.2f}, "
        f"Net {currency_symbol}{summary.net_total:.2f}."
    )

    highest = summary.highest_expense
    highest_line = (
        "No expense transactions recorded this week."
        if not highest
        else (
            f"Largest expense: {highest['category']} {currency_symbol}{highest['amount']:.2f}"
            f" on {str(highest.get('date') or '')[:10]}."
        )
    )

    plain = (
        f"Hi {name},\n\n"
        f"Weekly report for {summary.week_start.isoformat()} to {summary.week_end.isoformat()}\n"
        f"{top_line}\n"
        f"Transactions: {summary.transaction_count}\n"
        f"Insight: {summary.insight}\n"
        f"{highest_line}\n\n"
        "Top categories:\n"
        + (
            "\n".join(
                f"- {cat}: {currency_symbol}{value:.2f}"
                for cat, value in summary.top_categories
            )
            if summary.top_categories
            else "- No expense categories this week"
        )
    )

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background:#F6F7FB; margin:0; padding:24px; color:#222;">
        <div style="max-width:680px; margin:0 auto; background:#fff; border-radius:14px; overflow:hidden; border:1px solid #ECECEC;">
          <div style="padding:18px 20px; background:linear-gradient(90deg,#FFD87A,#F57C45);">
            <h2 style="margin:0; font-size:22px; color:#2A2A2A;">Weekly Money Report</h2>
            <p style="margin:6px 0 0 0; color:#3E3E3E; font-size:13px;">{summary.week_start.strftime('%d %b %Y')} - {summary.week_end.strftime('%d %b %Y')}</p>
          </div>

          <div style="padding:18px 20px;">
            <p style="margin:0 0 14px 0;">Hi {name}, here is your weekly snapshot.</p>

            <div style="display:flex; gap:10px; flex-wrap:wrap; margin-bottom:14px;">
              <div style="flex:1 1 180px; background:#EFF7EF; border-radius:10px; padding:10px;">
                <div style="font-size:12px; color:#4B6A4B;">Income</div>
                <div style="font-size:20px; font-weight:700; color:#2E7D32;">{currency_symbol}{summary.income_total:.2f}</div>
              </div>
              <div style="flex:1 1 180px; background:#FFF2E9; border-radius:10px; padding:10px;">
                <div style="font-size:12px; color:#8A5A33;">Expenses</div>
                <div style="font-size:20px; font-weight:700; color:#F57C45;">{currency_symbol}{summary.expense_total:.2f}</div>
              </div>
              <div style="flex:1 1 180px; background:#EEF3FF; border-radius:10px; padding:10px;">
                <div style="font-size:12px; color:#35507A;">Net</div>
                <div style="font-size:20px; font-weight:700; color:{'#2E7D32' if summary.net_total >= 0 else '#C62828'};">{currency_symbol}{summary.net_total:.2f}</div>
              </div>
            </div>

            <div style="margin-bottom:14px;">
              <h3 style="margin:0 0 8px 0; font-size:15px;">Daily Expenses Graph</h3>
              {_daily_expense_svg(summary.daily_expenses)}
            </div>

            <div style="margin-bottom:14px;">
              <h3 style="margin:0 0 8px 0; font-size:15px;">Top Spending Categories</h3>
              {_category_rows_html(summary.top_categories, currency_symbol)}
            </div>

            <div style="background:#F8FAFD; border-radius:10px; padding:12px; margin-bottom:12px; border:1px solid #E9EEF6;">
              <div style="font-size:13px; font-weight:700; margin-bottom:5px;">Basic understanding</div>
              <div style="font-size:14px; color:#37474F;">{summary.insight}</div>
            </div>

            <p style="margin:0; color:#666; font-size:13px;">{highest_line}</p>
          </div>
        </div>
      </body>
    </html>
    """

    return {"subject": subject, "plain": plain, "html": html}


def should_send_weekly_digest_now(
    settings_row: dict,
    now_utc: dt.datetime | None = None,
) -> tuple[bool, str]:
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    timezone_name = (settings_row.get("timezone") or "UTC").strip()
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")

    local_now = now.astimezone(zone)
    week_key = week_key_for_date(local_now.date())

    if settings_row.get("last_sent_week") == week_key:
        return False, week_key

    weekday = int(settings_row.get("weekday", 0))
    hour = int(settings_row.get("hour", 18))
    minute = int(settings_row.get("minute", 0))

    if local_now.weekday() != weekday:
        return False, week_key

    now_minutes = local_now.hour * 60 + local_now.minute
    target_minutes = hour * 60 + minute
    if now_minutes < target_minutes:
        return False, week_key

    return True, week_key
