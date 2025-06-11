"""Device scheduling system for WaterBot."""
import logging
import threading
import time

import schedule

from .config import DEVICE_SCHEDULES, ENABLE_SCHEDULING
from .gpio import handler as gpio_handler

logger = logging.getLogger("scheduler")


class DeviceScheduler:
    """Handles scheduled device operations."""

    def __init__(self):
        """Initialize the device scheduler."""
        self.running = False
        self.scheduler_thread = None
        self.scheduled_jobs = []

    def setup_schedules(self):
        """Set up all scheduled tasks based on configuration."""
        # Clear existing schedules first
        schedule.clear()
        self.scheduled_jobs.clear()

        if not ENABLE_SCHEDULING:
            logger.info("Scheduling is disabled")
            return

        for device, actions in DEVICE_SCHEDULES.items():
            for action, times in actions.items():
                for time_str in times:
                    self._schedule_device_action(device, action, time_str)

        logger.info(f"Set up {len(self.scheduled_jobs)} scheduled tasks")

    def _schedule_device_action(self, device, action, time_str):
        """Schedule a single device action."""
        try:

            def job():
                logger.info(
                    f"Executing scheduled {action} for device '{device}' at {time_str}"
                )
                if action == "on":
                    success = gpio_handler.turn_on(device)
                elif action == "off":
                    success = gpio_handler.turn_off(device)
                else:
                    logger.error(f"Unknown action: {action}")
                    return

                if success:
                    logger.info(
                        f"Successfully executed scheduled {action} for "
                        f"device '{device}'"
                    )
                else:
                    logger.error(
                        f"Failed to execute scheduled {action} for device '{device}'"
                    )

            # Schedule the job
            scheduled_job = schedule.every().day.at(time_str).do(job)
            self.scheduled_jobs.append(
                {
                    "device": device,
                    "action": action,
                    "time": time_str,
                    "job": scheduled_job,
                }
            )

            logger.debug(f"Scheduled {action} for device '{device}' at {time_str}")

        except Exception as e:
            logger.error(
                f"Error scheduling {action} for device '{device}' at {time_str}: {e}"
            )

    def add_schedule(self, device, action, time_str):
        """Add a new schedule dynamically."""
        from .config import add_schedule as config_add_schedule

        if config_add_schedule(device, action, time_str):
            self._schedule_device_action(device, action, time_str)
            logger.info(f"Added schedule: {device} {action} at {time_str}")
            return True
        return False

    def remove_schedule(self, device, action, time_str):
        """Remove a schedule dynamically."""
        from .config import remove_schedule as config_remove_schedule

        # Find and cancel the job
        for job_info in self.scheduled_jobs[:]:
            if (
                job_info["device"] == device
                and job_info["action"] == action
                and job_info["time"] == time_str
            ):
                schedule.cancel_job(job_info["job"])
                self.scheduled_jobs.remove(job_info)
                logger.info(f"Removed scheduled job: {device} {action} at {time_str}")
                break

        # Remove from config
        return config_remove_schedule(device, action, time_str)

    def get_next_runs(self):
        """Get information about next scheduled runs."""
        next_runs = []
        for job_info in self.scheduled_jobs:
            job = job_info["job"]
            next_run = job.next_run
            if next_run:
                next_runs.append(
                    {
                        "device": job_info["device"],
                        "action": job_info["action"],
                        "time": job_info["time"],
                        "next_run": next_run.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

        # Sort by next run time
        next_runs.sort(key=lambda x: x["next_run"])
        return next_runs

    def start(self):
        """Start the scheduler."""
        if self.running:
            logger.warning("Scheduler is already running")
            return

        if not ENABLE_SCHEDULING:
            logger.info("Scheduling is disabled, not starting scheduler")
            return

        logger.info("Starting device scheduler")
        self.setup_schedules()
        self.running = True

        # Start scheduler thread
        self.scheduler_thread = threading.Thread(target=self._run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()

        logger.info("Device scheduler started")

    def _run_scheduler(self):
        """Run the scheduler in a separate thread."""
        logger.debug("Scheduler thread started")

        while self.running:
            try:
                schedule.run_pending()
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error in scheduler thread: {e}", exc_info=True)

        logger.debug("Scheduler thread stopped")

    def stop(self):
        """Stop the scheduler."""
        if not self.running:
            logger.warning("Scheduler is not running")
            return

        logger.info("Stopping device scheduler")
        self.running = False

        # Wait for scheduler thread to finish
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)

        # Clear all scheduled jobs
        schedule.clear()
        self.scheduled_jobs.clear()

        logger.info("Device scheduler stopped")


# Global scheduler instance
_scheduler = None


def get_scheduler():
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = DeviceScheduler()
    return _scheduler


def start_scheduler():
    """Start the global scheduler."""
    scheduler = get_scheduler()
    scheduler.start()


def stop_scheduler():
    """Stop the global scheduler."""
    scheduler = get_scheduler()
    scheduler.stop()


def add_schedule(device, action, time_str):
    """Add a schedule using the global scheduler."""
    scheduler = get_scheduler()
    return scheduler.add_schedule(device, action, time_str)


def remove_schedule(device, action, time_str):
    """Remove a schedule using the global scheduler."""
    scheduler = get_scheduler()
    return scheduler.remove_schedule(device, action, time_str)


def get_next_runs():
    """Get next scheduled runs using the global scheduler."""
    scheduler = get_scheduler()
    return scheduler.get_next_runs()
