"""Unit tests for storage/google_sheet.py. Uses an injected mock
gspread.Client - no real Google API calls or credentials needed."""
from datetime import date
from unittest.mock import MagicMock

import gspread
import pytest

from models.job import Job
from storage.database import Database
from storage.google_sheet import GoogleSheetError, GoogleSheetExporter, _HEADER


def _job(**overrides: object) -> Job:
    defaults: dict[str, object] = dict(
        company="Acme Real Estate",
        job_title="Paid Media Manager",
        location="Doha, Qatar",
        country="Qatar",
        source="jooble",
        job_url="https://example.com/jobs/1",
        posted_date=date(2026, 7, 1),
        description="desc",
    )
    defaults.update(overrides)
    return Job(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def database() -> Database:
    db = Database(":memory:")
    db.initialize_schema()
    job = _job()
    db.mark_seen(job)
    db.insert_lead(job, score=100)
    yield db
    db.close()


def _mock_client_with_worksheet(header_present: bool = True) -> tuple[MagicMock, MagicMock]:
    """Build a mock gspread client whose open_by_key().worksheet()
    chain returns a controllable mock worksheet."""
    worksheet = MagicMock()
    worksheet.row_values.return_value = list(_HEADER) if header_present else []

    spreadsheet = MagicMock()
    spreadsheet.worksheet.return_value = worksheet

    client = MagicMock()
    client.open_by_key.return_value = spreadsheet
    return client, worksheet


class TestGoogleSheetExporterConstruction:
    def test_requires_sheet_id(self) -> None:
        with pytest.raises(ValueError, match="sheet_id"):
            GoogleSheetExporter(sheet_id="", client=MagicMock())

    def test_requires_service_account_file_when_no_client_injected(self) -> None:
        with pytest.raises(ValueError, match="service_account_file"):
            GoogleSheetExporter(sheet_id="abc123")


class TestExportLeads:
    def test_exports_leads_and_returns_hashes(self, database: Database) -> None:
        client, worksheet = _mock_client_with_worksheet()
        exporter = GoogleSheetExporter(sheet_id="abc123", client=client)

        leads = database.get_unexported_leads()
        exported_hashes = exporter.export_leads(leads)

        assert len(exported_hashes) == 1
        assert exported_hashes[0] == leads[0]["job_hash"]
        worksheet.append_rows.assert_called_once()

    def test_row_column_order_matches_spec(self, database: Database) -> None:
        client, worksheet = _mock_client_with_worksheet()
        exporter = GoogleSheetExporter(sheet_id="abc123", client=client)

        leads = database.get_unexported_leads()
        exporter.export_leads(leads)

        appended_rows = worksheet.append_rows.call_args[0][0]
        row = appended_rows[0]
        # Score, Company, Job Title, Salary, Location, Country, Source, Job URL, Date Found, Status
        assert row[0] == 100
        assert row[1] == "Acme Real Estate"
        assert row[2] == "Paid Media Manager"
        assert row[3] == "Not specified"  # no salary set on the fixture job
        assert row[4] == "Doha, Qatar"
        assert row[5] == "Qatar"
        assert row[6] == "jooble"
        assert row[7] == "https://example.com/jobs/1"
        assert row[9] == "New"

    def test_empty_leads_list_does_not_call_api(self) -> None:
        client, worksheet = _mock_client_with_worksheet()
        exporter = GoogleSheetExporter(sheet_id="abc123", client=client)

        result = exporter.export_leads([])

        assert result == []
        client.open_by_key.assert_not_called()

    def test_writes_header_when_worksheet_is_empty(self, database: Database) -> None:
        client, worksheet = _mock_client_with_worksheet(header_present=False)
        exporter = GoogleSheetExporter(sheet_id="abc123", client=client)

        exporter.export_leads(database.get_unexported_leads())

        worksheet.update.assert_called_once()
        args, _ = worksheet.update.call_args
        assert args[1] == [
            ["Score", "Company", "Job Title", "Salary", "Location", "Country",
             "Source", "Job URL", "Date Found", "Status"]
        ]

    def test_overwrites_stale_header_that_predates_a_column_change(self, database: Database) -> None:
        # Regression test for the actual production bug: a sheet
        # created before the Salary column was added had an old
        # 9-column header. Since only "is the header empty?" was
        # checked (not "does it match?"), new 10-column rows got
        # appended underneath the stale header, shifting every column
        # one to the right relative to its own label.
        worksheet = MagicMock()
        worksheet.row_values.return_value = [
            "Score", "Company", "Job Title", "Location", "Country",
            "Source", "Job URL", "Date Found", "Status",
        ]  # old header, missing "Salary"
        spreadsheet = MagicMock()
        spreadsheet.worksheet.return_value = worksheet
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet

        exporter = GoogleSheetExporter(sheet_id="abc123", client=client)
        exporter.export_leads(database.get_unexported_leads())

        worksheet.update.assert_called_once()
        args, _ = worksheet.update.call_args
        assert args[1] == [
            ["Score", "Company", "Job Title", "Salary", "Location", "Country",
             "Source", "Job URL", "Date Found", "Status"]
        ]

    def test_does_not_rewrite_header_when_already_present(self, database: Database) -> None:
        client, worksheet = _mock_client_with_worksheet(header_present=True)
        exporter = GoogleSheetExporter(sheet_id="abc123", client=client)

        exporter.export_leads(database.get_unexported_leads())

        worksheet.append_row.assert_not_called()
        worksheet.update.assert_not_called()

    def test_creates_worksheet_when_missing(self, database: Database) -> None:
        new_worksheet = MagicMock()
        spreadsheet = MagicMock()
        spreadsheet.worksheet.side_effect = gspread.exceptions.WorksheetNotFound("Leads")
        spreadsheet.add_worksheet.return_value = new_worksheet

        client = MagicMock()
        client.open_by_key.return_value = spreadsheet

        exporter = GoogleSheetExporter(sheet_id="abc123", client=client)
        exporter.export_leads(database.get_unexported_leads())

        spreadsheet.add_worksheet.assert_called_once()
        new_worksheet.append_row.assert_called_once()  # header written on creation
        new_worksheet.append_rows.assert_called_once()  # leads appended

    def test_worksheet_is_cached_across_calls(self, database: Database) -> None:
        client, worksheet = _mock_client_with_worksheet()
        exporter = GoogleSheetExporter(sheet_id="abc123", client=client)

        exporter.export_leads(database.get_unexported_leads())
        exporter.export_leads([])  # second call, empty - shouldn't reopen

        assert client.open_by_key.call_count == 1


class TestErrorHandling:
    def test_open_by_key_failure_raises_google_sheet_error(self, database: Database) -> None:
        client = MagicMock()
        client.open_by_key.side_effect = gspread.exceptions.APIError(
            MagicMock(json=lambda: {"error": {"code": 404, "message": "not found", "status": "NOT_FOUND"}})
        )
        exporter = GoogleSheetExporter(sheet_id="abc123", client=client)

        with pytest.raises(GoogleSheetError, match="Could not open"):
            exporter.export_leads(database.get_unexported_leads())

    def test_append_rows_failure_raises_google_sheet_error(self, database: Database) -> None:
        client, worksheet = _mock_client_with_worksheet()
        worksheet.append_rows.side_effect = gspread.exceptions.APIError(
            MagicMock(json=lambda: {"error": {"code": 429, "message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}})
        )
        exporter = GoogleSheetExporter(sheet_id="abc123", client=client)

        with pytest.raises(GoogleSheetError, match="Failed to append"):
            exporter.export_leads(database.get_unexported_leads())

    def test_leads_stay_unexported_in_db_after_export_failure(self, database: Database) -> None:
        client, worksheet = _mock_client_with_worksheet()
        worksheet.append_rows.side_effect = gspread.exceptions.APIError(
            MagicMock(json=lambda: {"error": {"code": 429, "message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}})
        )
        exporter = GoogleSheetExporter(sheet_id="abc123", client=client)

        leads = database.get_unexported_leads()
        with pytest.raises(GoogleSheetError):
            exporter.export_leads(leads)

        # Caller (main.py) only calls mark_exported with the returned
        # hashes - since export_leads raised, none were returned, so
        # the lead must still show up as unexported.
        assert len(database.get_unexported_leads()) == 1

    def test_non_gspread_exception_during_open_is_still_wrapped(self, database: Database) -> None:
        # Regression test: google.auth.exceptions.RefreshError (raised
        # during OAuth token refresh, e.g. on network failure) is NOT a
        # gspread.exceptions.APIError. A narrower except clause here
        # let this propagate uncaught and crash the whole run in
        # practice - this must never happen for an export failure.
        client = MagicMock()
        client.open_by_key.side_effect = RuntimeError("Host not in allowlist: oauth2.googleapis.com")
        exporter = GoogleSheetExporter(sheet_id="abc123", client=client)

        with pytest.raises(GoogleSheetError, match="Could not open"):
            exporter.export_leads(database.get_unexported_leads())

    def test_non_gspread_exception_during_append_is_still_wrapped(self, database: Database) -> None:
        client, worksheet = _mock_client_with_worksheet()
        worksheet.append_rows.side_effect = ConnectionError("network unreachable")
        exporter = GoogleSheetExporter(sheet_id="abc123", client=client)

        with pytest.raises(GoogleSheetError, match="Failed to append"):
            exporter.export_leads(database.get_unexported_leads())

    def test_exception_with_empty_str_still_produces_useful_message(self, database: Database) -> None:
        # Regression test: production logs showed "Could not open Google
        # Sheet '***': " with nothing after the colon - str(exc) was
        # empty. The error message must always carry the exception type
        # name at minimum, even when str(exc) gives nothing.
        class BlankException(Exception):
            def __str__(self) -> str:
                return ""

        client = MagicMock()
        client.open_by_key.side_effect = BlankException()
        exporter = GoogleSheetExporter(sheet_id="abc123", client=client)

        with pytest.raises(GoogleSheetError, match="BlankException") as exc_info:
            exporter.export_leads(database.get_unexported_leads())
        assert str(exc_info.value).strip() != "Could not open Google Sheet (id redacted if secret):"


class TestDateFormatting:
    def test_date_found_extracts_date_portion_from_iso_timestamp(self, database: Database) -> None:
        client, worksheet = _mock_client_with_worksheet()
        exporter = GoogleSheetExporter(sheet_id="abc123", client=client)

        leads = database.get_unexported_leads()
        exporter.export_leads(leads)

        row = worksheet.append_rows.call_args[0][0][0]
        date_found = row[8]
        assert len(date_found) == 10  # YYYY-MM-DD, no time component
        assert "T" not in date_found
