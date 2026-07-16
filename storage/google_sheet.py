"""
Google Sheets export.

Appends qualified leads to a Google Sheet using a service account.
Deliberately append-only: existing rows are never touched, so any
manual edits to the Status column (e.g. sales marking a lead
"Contacted") survive forever. Which leads still need exporting is
tracked in SQLite (leads.exported_at, see storage/database.py) rather
than by re-reading the whole sheet each run - cheaper and simpler,
and the sheet is never the source of truth for what's been sent.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Sequence

import gspread
from google.oauth2.service_account import Credentials

from utils.logger import get_logger

logger = get_logger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_HEADER = ["Score", "Company", "Job Title", "Salary", "Location", "Work Mode", "Country", "Source", "Job URL", "Date Found", "Status"]
_DEFAULT_WORKSHEET_NAME = "Leads"


class GoogleSheetError(Exception):
    """Raised when authentication, opening the sheet, or writing to it
    fails. Callers should treat this as recoverable: leads stay
    unexported in the DB and will be retried next run."""


def _describe_exception(exc: Exception) -> str:
    """Build a diagnostic string from an exception, robust to exception
    types whose str() is empty or unhelpful.

    Observed in production: a failure logged as "Could not open Google
    Sheet '***': " with nothing after the colon - str(exc) was empty,
    and the sheet ID itself is a GitHub Actions secret so it's redacted
    to '***' in logs regardless. Always including the exception type
    name, and falling back to repr() when str() is blank, means a
    masked secret in the message never leaves zero diagnostic info.
    """
    text = str(exc).strip() or repr(exc)
    status_code = None
    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)

    parts = [type(exc).__name__]
    if status_code is not None:
        parts.append(f"HTTP {status_code}")
    parts.append(text)
    return " | ".join(parts)


class GoogleSheetExporter:
    """Appends leads to a Google Sheet, creating the header row and
    worksheet on first use if needed."""

    def __init__(
        self,
        sheet_id: str,
        service_account_file: Path | None = None,
        worksheet_name: str = _DEFAULT_WORKSHEET_NAME,
        client: gspread.Client | None = None,
    ) -> None:
        if not sheet_id:
            raise ValueError("GoogleSheetExporter requires a non-empty sheet_id")
        self._sheet_id = sheet_id
        self._worksheet_name = worksheet_name
        self._client = client or self._build_client(service_account_file)
        self._worksheet: gspread.Worksheet | None = None

    @staticmethod
    def _build_client(service_account_file: Path | None) -> gspread.Client:
        if service_account_file is None:
            raise ValueError("service_account_file is required when no client is injected")
        try:
            credentials = Credentials.from_service_account_file(
                str(service_account_file), scopes=_SCOPES
            )
        except (OSError, ValueError) as exc:
            raise GoogleSheetError(
                f"Could not load Google service account credentials from "
                f"{service_account_file}: {exc}"
            ) from exc
        return gspread.authorize(credentials)

    def _get_worksheet(self) -> gspread.Worksheet:
        """Open the target worksheet, creating it (and the header row)
        on first use. Cached after the first successful call."""
        if self._worksheet is not None:
            return self._worksheet

        try:
            spreadsheet = self._client.open_by_key(self._sheet_id)
        except Exception as exc:
            # Deliberately broad: auth failures (google.auth.exceptions.
            # RefreshError), network errors, and gspread's own APIError
            # all need to land here. A single narrower except type isn't
            # enough - this method touches the network via three
            # different layers (google-auth, requests, gspread) and any
            # of them can fail independently. This must never crash the
            # daily run; export failures are always recoverable.
            raise GoogleSheetError(
                f"Could not open Google Sheet (id redacted if secret): {_describe_exception(exc)}"
            ) from exc

        try:
            worksheet = spreadsheet.worksheet(self._worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            logger.info("Worksheet %r not found, creating it", self._worksheet_name)
            try:
                worksheet = spreadsheet.add_worksheet(
                    title=self._worksheet_name, rows=1000, cols=len(_HEADER)
                )
                worksheet.append_row(_HEADER)
            except Exception as exc:
                raise GoogleSheetError(
                    f"Could not create worksheet {self._worksheet_name!r}: {_describe_exception(exc)}"
                ) from exc
        except Exception as exc:
            raise GoogleSheetError(
                f"Could not open worksheet {self._worksheet_name!r}: {_describe_exception(exc)}"
            ) from exc
        else:
            try:
                first_row = worksheet.row_values(1)
                if first_row != _HEADER:
                    if not first_row:
                        logger.info(
                            "Worksheet %r has no header, writing one", self._worksheet_name
                        )
                    else:
                        # The important case: a header exists but doesn't
                        # match what we're about to write - typically
                        # because the column set changed (e.g. a new
                        # column was inserted) since this sheet was
                        # first created. Overwriting the header alone
                        # does NOT fix the alignment of existing data
                        # rows below it - those were appended under the
                        # OLD column layout and will now read against
                        # the wrong labels. This must never happen
                        # silently again.
                        logger.warning(
                            "Worksheet %r header does not match expected columns. "
                            "Found: %r. Expected: %r. Overwriting the header, but "
                            "existing data rows below may now be misaligned - if "
                            "this sheet has old data in it, clear the data rows "
                            "and use the Reset Export Status workflow to re-send "
                            "everything cleanly under the new column layout.",
                            self._worksheet_name,
                            first_row,
                            _HEADER,
                        )
                    worksheet.update("A1", [_HEADER])
            except Exception as exc:
                raise GoogleSheetError(f"Could not read/write header row: {_describe_exception(exc)}") from exc

        self._worksheet = worksheet
        return worksheet

    def export_leads(self, leads: Sequence[sqlite3.Row]) -> list[str]:
        """Append the given leads as new rows. Returns the job_hash of
        every lead successfully written, so the caller can mark them
        exported in the database.

        Raises:
            GoogleSheetError: if the sheet can't be opened or written
                to. Callers should catch this, log it, and continue -
                leads simply stay unexported and get retried next run.
        """
        if not leads:
            return []

        worksheet = self._get_worksheet()
        rows = [self._lead_to_row(lead) for lead in leads]

        try:
            worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        except Exception as exc:
            raise GoogleSheetError(f"Failed to append {len(rows)} lead(s) to Google Sheet: {_describe_exception(exc)}") from exc

        logger.info("Exported %d lead(s) to Google Sheet", len(rows))
        return [lead["job_hash"] for lead in leads]

    @staticmethod
    def _lead_to_row(lead: sqlite3.Row) -> list[object]:
        """Map a leads table row to a sheet row in the fixed column
        order: Score, Company, Job Title, Salary, Location, Work Mode,
        Country, Source, Job URL, Date Found, Status."""
        found_at = lead["found_at"] or ""
        date_found = found_at.split("T")[0] if "T" in found_at else found_at
        return [
            lead["score"],
            lead["company"],
            lead["job_title"],
            lead["salary"] or "Not specified",
            lead["location"],
            lead["work_mode"] or "Not specified",
            lead["country"],
            lead["source"],
            lead["job_url"],
            date_found,
            lead["status"],
        ]
