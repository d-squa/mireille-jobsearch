"""Unit tests for core/work_mode.py."""
from core.work_mode import classify_work_mode


class TestClassifyWorkMode:
    def test_remote_keyword_labels_remote(self) -> None:
        assert classify_work_mode("Paid Media Manager - Remote") == "Remote"

    def test_hybrid_keyword_labels_hybrid(self) -> None:
        assert classify_work_mode("Paid Media Manager (Hybrid)") == "Hybrid"

    def test_onsite_keyword_labels_onsite(self) -> None:
        assert classify_work_mode("Paid Media Manager - Onsite") == "Onsite"

    def test_on_site_with_hyphen_labels_onsite(self) -> None:
        assert classify_work_mode("Paid Media Manager - On-Site") == "Onsite"

    def test_work_from_home_labels_remote(self) -> None:
        assert classify_work_mode("Paid Media Manager (Work From Home)") == "Remote"

    def test_wfh_abbreviation_labels_remote(self) -> None:
        assert classify_work_mode("Paid Media Manager - WFH available") == "Remote"

    def test_case_insensitive_matching(self) -> None:
        assert classify_work_mode("PAID MEDIA MANAGER - REMOTE") == "Remote"
        assert classify_work_mode("paid media manager - remote") == "Remote"

    def test_no_keyword_present_returns_none(self) -> None:
        assert classify_work_mode("Paid Media Manager") is None

    def test_does_not_default_to_onsite_when_unclear(self) -> None:
        # Silence isn't evidence - most job titles say nothing about
        # work mode at all, and that must not be assumed Onsite.
        assert classify_work_mode("Software Engineer") is None

    def test_hybrid_takes_priority_when_both_hybrid_and_remote_present(self) -> None:
        assert classify_work_mode("Hybrid/Remote options available") == "Hybrid"

    def test_checks_across_multiple_text_fields_combined(self) -> None:
        assert classify_work_mode("Paid Media Manager", "London", "This is a remote-first role.") == "Remote"

    def test_none_and_empty_strings_in_args_are_ignored(self) -> None:
        assert classify_work_mode(None, "", "Paid Media Manager - Remote") == "Remote"

    def test_all_none_or_empty_returns_none(self) -> None:
        assert classify_work_mode(None, "", None) is None

    def test_no_arguments_returns_none(self) -> None:
        assert classify_work_mode() is None

    def test_remote_as_substring_of_unrelated_word_still_matches(self) -> None:
        # Documents actual behavior (substring matching per the brief),
        # not an edge case guard - "remotely" contains "remote".
        assert classify_work_mode("Manage campaigns remotely from anywhere") == "Remote"
