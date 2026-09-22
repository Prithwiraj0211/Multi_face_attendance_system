from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

def to_local_datetime(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Convert a datetime object from UTC to the local machine timezone.
    If the datetime is naive (typical for SQLite records), it is treated as UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()

def format_local_timestamp(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a stored UTC datetime into the local timezone string."""
    if not dt:
        return ""
    local_dt = to_local_datetime(dt)
    return local_dt.strftime(fmt)

def get_local_day_utc_bounds(date_str: Optional[str] = None) -> Tuple[datetime, datetime]:
    """
    Given a local date string 'YYYY-MM-DD' (or today's local date if None),
    compute the start and end datetime bounds in UTC for database queries.
    This guarantees that filtering by local calendar date correctly matches
    all timestamps recorded during that local day regardless of server timezone.
    """
    if date_str:
        try:
            local_date = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD")
    else:
        local_date = datetime.now().date()

    start_local = datetime(local_date.year, local_date.month, local_date.day, 0, 0, 0).astimezone()
    end_local = start_local + timedelta(days=1)

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    return start_utc, end_utc
