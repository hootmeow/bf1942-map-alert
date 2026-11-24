import datetime

import pytz


def in_window(hour: int, weekday: int, start_h: int, end_h: int, days) -> bool:
    """Whether (weekday, hour) falls in a quiet window that starts at start_h
    on each of ``days`` and runs until end_h.

    Overnight windows (start_h > end_h) belong to the day they start on, so
    the early-morning part is checked against the previous day. start_h ==
    end_h means the whole day.
    """
    if start_h == end_h:
        return weekday in days
    if start_h < end_h:
        return weekday in days and start_h <= hour < end_h
    if hour >= start_h:
        return weekday in days
    if hour < end_h:
        return (weekday - 1) % 7 in days
    return False


def is_in_dnd(record, now_utc: datetime.datetime) -> bool:
    """Check if a subscription/watchlist record is currently in DND.

    Uses the rule's local hours/days in the user's timezone when present
    (``start_hour_local``, ``end_hour_local``, ``weekdays_local``,
    ``dnd_timezone``), so DST and half-hour offsets are handled. Falls back
    to the legacy UTC columns. Returns ``False`` when no DND rule is set.
    """
    if record.get('start_hour_local') is not None and record.get('dnd_timezone'):
        try:
            tz = pytz.timezone(record['dnd_timezone'])
        except pytz.UnknownTimeZoneError:
            tz = pytz.utc
        now = now_utc.astimezone(tz)
        return in_window(now.hour, now.weekday(), record['start_hour_local'],
                         record['end_hour_local'], record['weekdays_local'])

    if record.get('start_hour_utc') is None:
        return False

    return in_window(now_utc.hour, now_utc.weekday(), record['start_hour_utc'],
                     record['end_hour_utc'], record['weekdays_utc'])
