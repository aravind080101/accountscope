"""Refresh watched accounts that are due, then exit. For cron, e.g. daily at 7am:

    0 7 * * *  cd /path/to/accountscope && .venv/bin/python -m backend.watch
"""
from . import alerts, db, pipeline

if __name__ == "__main__":
    db.init()
    n = alerts.refresh_due(pipeline.run)
    print(f"Refreshed {n} watched account(s)")
