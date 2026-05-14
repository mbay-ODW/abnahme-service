"""Compute night-zone hours (20:00-06:00) for a time window.

Examples:
    night_hours("05:50", "12:50")   -> 0.1667   (10 min before 06:00)
    night_hours("18:00", "22:00")   -> 2.0      (20:00-22:00)
    night_hours("22:00", "06:00")   -> 8.0      (full overnight shift)
"""

from datetime import datetime, timedelta


def _to_dt(hhmm: str, base: datetime) -> datetime:
    h, m = hhmm.replace(".", ":").split(":")
    return base.replace(hour=int(h), minute=int(m), second=0, microsecond=0)


def night_hours(start: str, end: str) -> float:
    """Return the share of [start, end] that falls into 20:00–06:00.

    Times are HH:MM. If end < start, the window is assumed to cross midnight.
    Returns hours as a float (decimal hours, 1.5 = 1h30min).
    """
    base = datetime(2000, 1, 1)
    s = _to_dt(start, base)
    e = _to_dt(end, base)
    if e <= s:
        e += timedelta(days=1)

    # Night intervals to consider: [00:00, 06:00) and [20:00, 24:00) for each
    # covered day, plus the following day's early-morning [00:00, 06:00).
    night_total = timedelta(0)
    night_windows = [
        (base, base.replace(hour=6)),
        (base.replace(hour=20), base + timedelta(days=1)),
        (base + timedelta(days=1), (base + timedelta(days=1)).replace(hour=6)),
        ((base + timedelta(days=1)).replace(hour=20),
         (base + timedelta(days=2))),
    ]
    for w_start, w_end in night_windows:
        overlap_start = max(s, w_start)
        overlap_end = min(e, w_end)
        if overlap_end > overlap_start:
            night_total += overlap_end - overlap_start
    return night_total.total_seconds() / 3600.0


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python night_hours.py HH:MM HH:MM")
        sys.exit(1)
    h = night_hours(sys.argv[1], sys.argv[2])
    print(f"{h:.4f} h ({round(h*60)} min) within 20:00-06:00")
