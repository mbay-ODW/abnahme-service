"""Check if a date is a German federal public holiday.

Covers the bundesweit gesetzliche Feiertage:
- Neujahr (01.01.)
- Karfreitag (Easter Sunday - 2 Tage)
- Ostermontag (Easter + 1)
- Tag der Arbeit (01.05.)
- Christi Himmelfahrt (Easter + 39)
- Pfingstmontag (Easter + 50)
- Tag der deutschen Einheit (03.10.)
- 1. Weihnachtstag (25.12.)
- 2. Weihnachtstag (26.12.)

Use:
    python check_holiday.py 2026-04-11        # -> Saturday, no holiday
    python check_holiday.py 2026-04-06        # -> Easter Monday
"""

from datetime import date, timedelta
import sys


def easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm for Easter Sunday."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def german_holidays(year: int) -> dict:
    """Return {date: name} for all federal German holidays in the year."""
    easter = easter_sunday(year)
    return {
        date(year, 1, 1): "Neujahr",
        easter - timedelta(days=2): "Karfreitag",
        easter + timedelta(days=1): "Ostermontag",
        date(year, 5, 1): "Tag der Arbeit",
        easter + timedelta(days=39): "Christi Himmelfahrt",
        easter + timedelta(days=50): "Pfingstmontag",
        date(year, 10, 3): "Tag der dt. Einheit",
        date(year, 12, 25): "1. Weihnachtstag",
        date(year, 12, 26): "2. Weihnachtstag",
    }


def classify(d: date) -> dict:
    """Return a dict with weekday, is_sunday, is_holiday (+name)."""
    weekday_names_de = [
        "Montag", "Dienstag", "Mittwoch", "Donnerstag",
        "Freitag", "Samstag", "Sonntag",
    ]
    hols = german_holidays(d.year)
    return {
        "date": d.isoformat(),
        "weekday": weekday_names_de[d.weekday()],
        "is_saturday": d.weekday() == 5,
        "is_sunday": d.weekday() == 6,
        "is_holiday": d in hols,
        "holiday_name": hols.get(d, ""),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python check_holiday.py YYYY-MM-DD")
        sys.exit(1)
    target = date.fromisoformat(sys.argv[1])
    info = classify(target)
    print(f"{info['date']} ({info['weekday']})")
    if info["is_sunday"]:
        print("  → Sonntag (Sonntagszuschlag möglich)")
    if info["is_saturday"]:
        print("  → Samstag (kein Zuschlag, außer Nacht)")
    if info["is_holiday"]:
        print(f"  → FEIERTAG: {info['holiday_name']} (Feiertagszuschlag)")
    if not (info["is_sunday"] or info["is_holiday"]):
        print("  → regulärer Werktag")
