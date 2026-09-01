"""
Weekly BOM formula refresh (Phase 3 cron entrypoint).

Runs OUT-OF-PROCESS from the live API — invoked by a systemd timer on Saturday morning:

    /opt/goldfinger/Backend/.venv/bin/python -m app.scripts.refresh_boms

It re-fetches every assembly currently in the bom_formula cache from NetSuite, paced to
respect rate limits, using the exact same BOMService.refresh_all_bom_formulas() that the
admin "Refresh formulas" button uses. A Postgres advisory lock inside that method makes it
mutually exclusive with a concurrent admin-triggered run, so this needs no auth and no HTTP.

Inventory is never touched here — only the persisted formulas. Exit code is non-zero if the
refresh could not run at all (init/lock failure), 0 otherwise (per-item errors are logged and
summarized, not fatal).
"""
import asyncio
import logging
import sys

from app.database.connection import init_db, close_db
from app.services.service_registry import get_bom_service

# Standalone process: log to stdout/stderr; the systemd unit captures it into the journal
# (and/or a file via StandardOutput=append:). INFO so the paced progress is visible here even
# though the live app runs at WARNING.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("bom_refresh_cron")


async def _run() -> int:
    await init_db()
    try:
        logger.info("[cron] weekly BOM formula refresh starting")
        summary = await get_bom_service().refresh_all_bom_formulas()
        if summary.get("skipped"):
            logger.warning("[cron] refresh skipped: %s", summary.get("reason"))
        else:
            logger.info(
                "[cron] refresh done: %d/%d refreshed, %d errors, %.1fs",
                summary.get("refreshed", 0),
                summary.get("total", 0),
                summary.get("errors", 0),
                summary.get("seconds", 0.0),
            )
        return 0
    finally:
        await close_db()


def main() -> None:
    try:
        sys.exit(asyncio.run(_run()))
    except Exception:
        logger.exception("[cron] BOM refresh failed to run")
        sys.exit(1)


if __name__ == "__main__":
    main()
