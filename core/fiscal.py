"""Fiscal year and quarter from a month-day year-end.

The fiscal year is the calendar year of the next year-end. The year-end
day itself still belongs to that year. Quarter 1 starts the next day.
Each quarter is three calendar months, counting the start month, and ends
on the last day of the third.
"""

import datetime as dt
import re


_YEAR_END = re.compile(r"^(\d{1,2})-(\d{1,2})$")


def parse_year_end(value):
    """`(month, day)` from `03-31`. 29 Feb is allowed and clamps off a leap year."""
    text = str(value or "").strip()
    match = _YEAR_END.match(text)
    if not match:
        raise ValueError(
            f"metrics.year_end must be a month-day such as 03-31, not {value!r}.")
    month, day = int(match.group(1)), int(match.group(2))
    if month == 2 and day == 29:
        return 2, 29
    try:
        dt.date(2025, month, day)
    except ValueError:
        raise ValueError(
            f"metrics.year_end must be a real month-day such as 03-31, not {value!r}."
        ) from None
    return month, day


def canonical(value):
    """`03-31`, zero-padded."""
    month, day = parse_year_end(value)
    return f"{month:02d}-{day:02d}"


def _leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _last_day(year, month):
    if month == 12:
        return dt.date(year, 12, 31)
    return dt.date(year, month + 1, 1) - dt.timedelta(days=1)


def _shift_month(year, month, count):
    index = year * 12 + (month - 1) + count
    return index // 12, index % 12 + 1


def year_end_date(year, year_end):
    """The year-end in `year`. 29 Feb falls on 28 Feb when the year is not a leap year."""
    month, day = parse_year_end(year_end)
    if month == 2 and day == 29 and not _leap(year):
        day = 28
    return dt.date(year, month, day)


def next_year_end(day, year_end):
    """The year-end that closes the fiscal year containing `day`."""
    this = year_end_date(day.year, year_end)
    if day <= this:
        return this
    return year_end_date(day.year + 1, year_end)


def fiscal_year(day, year_end):
    """The year of the next year-end. On the year-end, that year."""
    return next_year_end(day, year_end).year


def fiscal_start(year, year_end):
    """The day after the previous year-end. Quarter 1 starts here."""
    return year_end_date(year - 1, year_end) + dt.timedelta(days=1)


def quarter_end(start):
    """Last day of the third calendar month, counting `start`'s month as the first."""
    year, month = _shift_month(start.year, start.month, 2)
    return _last_day(year, month)


def quarters(year, year_end):
    """The four quarters of fiscal `year`, oldest first.

    The fourth quarter ends on the year-end, so a year-end that is not a
    month-end still closes the year.
    """
    close = year_end_date(year, year_end)
    start = fiscal_start(year, year_end)
    found = []
    for quarter in range(1, 5):
        end = quarter_end(start)
        if quarter == 4 or end > close:
            end = close
        found.append({
            "year": year,
            "quarter": quarter,
            "start": start,
            "end": end,
        })
        if end >= close:
            break
        start = end + dt.timedelta(days=1)
    return found


def period_containing(day, year_end):
    """The quarter that contains `day`."""
    year = fiscal_year(day, year_end)
    for period in quarters(year, year_end):
        if period["start"] <= day <= period["end"]:
            return period
    raise ValueError(f"{day.isoformat()} is not inside {year_tag(year)}.")


def format_day(day, with_year=False):
    text = f"{day.day} {day.strftime('%b')}"
    if with_year:
        text += f" {day.year}"
    return text


def year_tag(year):
    """`F27` for fiscal 2027. The two digits are the year of the next year-end."""
    return f"F{int(year) % 100:02d}"


def period_label(period):
    return f"{year_tag(period['year'])} Q{period['quarter']}"


def period_phrase(period):
    """`F27 Q3 (1 Oct – 31 Dec 2026)`."""
    start = format_day(period["start"], with_year=period["start"].year != period["end"].year)
    end = format_day(period["end"], with_year=True)
    return f"{period_label(period)} ({start} – {end})"


def span_label(start, end, year_end):
    """`F27 Q3`, `F27 Q2–Q3`, or `F27 Q4 – F28 Q1`."""
    first = period_containing(start, year_end)
    last = period_containing(end, year_end)
    if first["year"] == last["year"] and first["quarter"] == last["quarter"]:
        return period_label(first)
    if first["year"] == last["year"]:
        return f"{year_tag(first['year'])} Q{first['quarter']}–Q{last['quarter']}"
    return f"{period_label(first)} – {period_label(last)}"
