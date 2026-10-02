"""Calendar targets and submission deadlines for advance-scheduled editions."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


SUBMISSION_MARGIN = timedelta(minutes=5)


def local_time(now: datetime, cfg: dict, value: str) -> datetime:
    local = now.astimezone(ZoneInfo(cfg['timezone']))
    hour, minute = map(int, value.split(':'))
    return local.replace(hour=hour, minute=minute, second=0, microsecond=0)


def target_time(now: datetime, cfg: dict) -> datetime:
    """Today's configured send time, with its calendar date's UTC offset."""
    return local_time(now, cfg, cfg['send_time'])


def production_target(now: datetime, cfg: dict) -> datetime:
    """Evening prepares tomorrow; overnight/morning recovers today's edition.

    Do not roll a missed morning forward to another day or skip weekend dates
    here: the caller must skip Saturday/Sunday targets, including Friday night.
    """
    target = target_time(now, cfg)
    if now >= local_time(now, cfg, cfg['preparation_start_time']):
        target += timedelta(days=1)
    return target


def require_submission_window(now: datetime, target: datetime) -> None:
    deadline = target - SUBMISSION_MARGIN
    if now >= deadline:
        raise RuntimeError(
            f"Production submission deadline {deadline.isoformat(timespec='seconds')} "
            f"was reached (now {now.isoformat(timespec='seconds')}). "
            "No late production email was requested."
        )


def monitoring_window(now: datetime, target: datetime, cfg: dict) -> bool:
    """Keep success heartbeats in the existing morning Healthchecks interval."""
    local = now.astimezone(ZoneInfo(cfg['timezone']))
    return (local.date() == target.astimezone(local.tzinfo).date()
            and now >= local_time(now, cfg, cfg['monitor_confirmation_time']))
