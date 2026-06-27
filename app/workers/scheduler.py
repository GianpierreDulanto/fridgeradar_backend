"""
Background scheduler for periodic tasks.

Currently runs:
  - alert_service.scan_and_generate() every `SCAN_INTERVAL_MINUTES` minutes

The scheduler is started in app.main:start_scheduler() during the FastAPI
lifespan event and shut down cleanly on app shutdown.

Toggle via env: ENABLE_SCHEDULER=true (default) | false. In dev you may
want to disable it and call POST /api/alerts/run-preview manually instead.
"""

import logging
import os
from contextlib import suppress

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.database import SessionLocal
from app.services.alert_service import AlertService

logger = logging.getLogger(__name__)

SCAN_INTERVAL_MINUTES = int(os.environ.get("SCAN_INTERVAL_MINUTES", "60"))
ENABLE_SCHEDULER = os.environ.get("ENABLE_SCHEDULER", "true").lower() in ("1", "true", "yes")

_scheduler: BackgroundScheduler | None = None


def _run_scan() -> None:
    """Open a short-lived DB session and trigger a scan across all households."""
    db = SessionLocal()
    try:
        service = AlertService(db)
        result = service.scan_and_generate(household_id=None, current_user=None)
        logger.info(
            "scheduler: scan_and_generate created=%s", result.get("created"),
        )
    except Exception:
        logger.exception("scheduler: scan_and_generate failed")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler | None:
    """Idempotent. Returns the scheduler instance or None if disabled."""
    global _scheduler
    if not ENABLE_SCHEDULER:
        logger.info("scheduler: disabled (ENABLE_SCHEDULER=false)")
        return None
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        _run_scan,
        trigger=IntervalTrigger(minutes=SCAN_INTERVAL_MINUTES),
        id="alert_scan",
        name="Scan inventory and generate alerts",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "scheduler: started, alert scan every %s minutes", SCAN_INTERVAL_MINUTES,
    )
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        with suppress(Exception):
            _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler: stopped")
