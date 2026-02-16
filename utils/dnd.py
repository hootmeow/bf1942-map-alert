import datetime


def is_in_dnd(record, now_utc: datetime.datetime) -> bool:
    """Check if a subscription/watchlist record is currently in DND.

    ``record`` must have keys ``start_hour_utc``, ``end_hour_utc``, and
    ``weekdays_utc``.  Returns ``False`` when no DND rule is set (i.e.
    ``start_hour_utc`` is ``None``).
    """
    if record['start_hour_utc'] is None:
        return False

    current_hour = now_utc.hour
    current_weekday = now_utc.weekday()

    is_dnd_day = current_weekday in record['weekdays_utc']

    start_h = record['start_hour_utc']
    end_h = record['end_hour_utc']

    if start_h <= end_h:
        is_dnd_hour = start_h <= current_hour < end_h
    else:
        is_dnd_hour = current_hour >= start_h or current_hour < end_h

    return is_dnd_day and is_dnd_hour
