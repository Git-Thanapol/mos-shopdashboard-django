"""Materialized-view refresh hook. The matview itself is created in phase 4;
until then refresh is a no-op so ingest can already call it."""
import logging

from django.db import connection

logger = logging.getLogger(__name__)

FACT_DAILY = "analytics_fact_daily"


def refresh_facts():
    with connection.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", [FACT_DAILY])
        if cur.fetchone()[0] is None:
            logger.info("matview %s does not exist yet; skipping refresh", FACT_DAILY)
            return
        cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {FACT_DAILY}")
