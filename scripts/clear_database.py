"""
Clear database.

Permanently deletes every lead, dedup record, and discovered company.
Irreversible. The next run treats every job every source returns as
brand new. Does NOT touch the Google Sheet - clear that separately if
you want a fully synced fresh start.

Requires the environment variable CONFIRM_CLEAR=yes to actually run,
as a safety gate against accidental triggering - see
.github/workflows/clear-database.yml, which sets this only after the
person manually types a confirmation phrase.

Run:
    CONFIRM_CLEAR=yes python scripts/clear_database.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings
from storage.database import Database
from utils.logger import configure_logging, get_logger


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_file)
    logger = get_logger(__name__)

    if os.environ.get("CONFIRM_CLEAR", "").strip().lower() != "yes":
        logger.error(
            "Refusing to clear the database: CONFIRM_CLEAR=yes was not set. "
            "This is a safety gate against accidental triggering."
        )
        return 1

    with Database(settings.database_path) as database:
        database.initialize_schema()
        counts = database.clear_all_data()

    logger.warning(
        "Database cleared. Deleted %d lead(s), %d dedup record(s), %d compan(y/ies). "
        "The next run will treat every job as brand new. The Google Sheet was NOT "
        "touched - clear its data rows separately if you want a fully fresh start.",
        counts["leads"],
        counts["jobs_seen"],
        counts["companies"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
