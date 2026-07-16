"""
Reset export status.

Use this after manually clearing rows from the Google Sheet, so the
existing leads in the database (which are never deleted just because
the sheet was cleared) get re-sent on the next pipeline run.

Run:
    python scripts/reset_export_status.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from config import get_settings
from storage.database import Database
from utils.logger import configure_logging, get_logger


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_file)
    logger = get_logger(__name__)

    with Database(settings.database_path) as database:
        database.initialize_schema()
        updated_count = database.reset_exported_status()

    logger.info(
        "Reset export status on %d lead(s) - they will be re-sent to "
        "Google Sheets on the next pipeline run.",
        updated_count,
    )


if __name__ == "__main__":
    main()
