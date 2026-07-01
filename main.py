import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from scheduler.signal_runner import run_signal_scan
from notifications.weekly_digest import send_weekly_digest
from monitoring.logger import log

if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scan_times = [
        (12, 20),
    ]
    for hour, minute in scan_times:
        scheduler.add_job(
            run_signal_scan,
            CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone="America/New_York"),
        )
    scheduler.add_job(
        send_weekly_digest,
        CronTrigger(day_of_week="fri", hour=16, minute=30, timezone="America/New_York"),
    )
    scheduler.start()
    log.info(
        "Freki scheduled — daily scan at 12:20 ET + weekly digest Fri 16:30 ET. Ctrl+C to stop."
    )
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)
        log.info("Scheduler stopped.")
