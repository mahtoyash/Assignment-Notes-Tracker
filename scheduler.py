"""
Background Scheduling Engine for GSM Assignment Alert System
Uses APScheduler to trigger autonomous GSM phone calls at configured weekday & weekend timestamps.
"""

import logging
from typing import Dict, Any, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import config
import telephony

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global Background Scheduler instance
_scheduler: Optional[BackgroundScheduler] = None


def scheduled_alert_job():
    """Scheduled task executed at fixed daily intervals to alert all students."""
    logger.info("Scheduled Alert Job triggered! Initiating GSM batch call queue...")
    try:
        results = telephony.process_batch_alert_queue(trigger_type="scheduled")
        logger.info(f"Scheduled alert job completed. {len(results)} call(s) dispatched.")
    except Exception as e:
        logger.error(f"Error executing scheduled alert job: {e}")


def init_scheduler() -> BackgroundScheduler:
    """Initializes and registers cron jobs for weekdays and weekends."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler

    scheduler = BackgroundScheduler(daemon=True)

    # 1. Register Weekday Triggers (Mon-Fri)
    for idx, item in enumerate(config.WEEKDAY_SCHEDULE):
        job_id = f"weekday_job_{idx}_{item['hour']}_{item['minute']}"
        scheduler.add_job(
            scheduled_alert_job,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=item["hour"],
                minute=item["minute"]
            ),
            id=job_id,
            name=f"Weekday Reminder ({item['label']})",
            replace_existing=True
        )
        logger.info(f"Registered {job_id} at {item['label']} (Mon-Fri)")

    # 2. Register Weekend Triggers (Sat-Sun)
    for idx, item in enumerate(config.WEEKEND_SCHEDULE):
        job_id = f"weekend_job_{idx}_{item['hour']}_{item['minute']}"
        scheduler.add_job(
            scheduled_alert_job,
            trigger=CronTrigger(
                day_of_week="sat,sun",
                hour=item["hour"],
                minute=item["minute"]
            ),
            id=job_id,
            name=f"Weekend Reminder ({item['label']})",
            replace_existing=True
        )
        logger.info(f"Registered {job_id} at {item['label']} (Sat-Sun)")

    _scheduler = scheduler
    return scheduler


def start_scheduler():
    """Starts the background scheduler daemon."""
    scheduler = init_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler background alert engine started successfully.")


def stop_scheduler():
    """Shuts down the background scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")


def get_scheduler_status() -> Dict[str, Any]:
    """Returns the current state and next fire times of registered alert jobs."""
    global _scheduler
    if not _scheduler or not _scheduler.running:
        return {
            "running": False,
            "jobs_count": 0,
            "next_run_time": "Scheduler inactive",
            "jobs": []
        }

    jobs_info = []
    earliest_next_run = None

    for job in _scheduler.get_jobs():
        next_run = job.next_run_time
        if next_run:
            if earliest_next_run is None or next_run < earliest_next_run:
                earliest_next_run = next_run

        jobs_info.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": next_run.strftime("%Y-%m-%d %I:%M %p") if next_run else "Paused"
        })

    return {
        "running": True,
        "jobs_count": len(jobs_info),
        "next_run_time": earliest_next_run.strftime("%a, %d %b %I:%M %p") if earliest_next_run else "None scheduled",
        "jobs": jobs_info
    }
