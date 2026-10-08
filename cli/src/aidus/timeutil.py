"""RFC 3339 helpers that work on Python 3.10 (no 'Z' or arbitrary fractions in fromisoformat)."""
import re
from datetime import datetime, timezone

_RFC3339 = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$")


def parse(value):
    """Parse an RFC 3339 timestamp into an aware datetime, or raise ValueError."""
    m = _RFC3339.match(value)
    if not m:
        raise ValueError(f"not an RFC 3339 timestamp: {value!r}")
    base, frac, offset = m.groups()
    frac = (frac or "0")[:6].ljust(6, "0")
    offset = "+00:00" if offset == "Z" else offset
    return datetime.fromisoformat(f"{base}.{frac}{offset}")


def now():
    """Current UTC time as RFC 3339 with microseconds."""
    return format_utc(datetime.now(timezone.utc))


def format_utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def utc_month(value):
    """'YYYY-MM' of a timestamp, in UTC (spec §2)."""
    return parse(value).astimezone(timezone.utc).strftime("%Y-%m")
