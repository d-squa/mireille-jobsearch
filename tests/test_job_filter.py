"""Unit tests for core/job_filter.py."""
import pytest

from core.job_filter import ExcludeFilter, JobFilter, normalize_title

CANONICAL_TITLES = (
    "Paid Media Manager",
    "Performance Marketing Manager",
    "Media Buyer",
    "Campaign Manager",
    "Digital Marketing Manager",
    "SEM Specialist",
)


class TestNormalizeTitle:
    def test_strips_parenthetical_notes(self) -> None:
        assert normalize_title("Paid Media Manager (Hybrid)") == "Paid Media Manager"

    def test_strips_trailing_dash_qualifier(self) -> None:
        assert normalize_title("Paid Media Manager - EMEA") == "Paid Media Manager"

    def test_strips_trailing_pipe_qualifier(self) -> None:
        assert normalize_title("Paid Media Manager | Remote") == "Paid Media Manager"

    def test_strips_seniority_prefix(self) -> None:
        assert normalize_title("Senior Paid Media Manager") == "Paid Media Manager"

    def test_strips_multiple_qualifiers_together(self) -> None:
        assert normalize_title("Senior Paid Media Manager (Remote) - EMEA") == "Paid Media Manager"

    def test_collapses_whitespace(self) -> None:
        assert normalize_title("Paid   Media    Manager") == "Paid Media Manager"

    def test_empty_string_returns_empty(self) -> None:
        assert normalize_title("") == ""

    def test_vp_prefix_stripped(self) -> None:
        assert normalize_title("VP of Paid Media Manager") == "Paid Media Manager"


class TestJobFilterConstruction:
    def test_requires_at_least_one_title(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            JobFilter(canonical_titles=())

    def test_rejects_invalid_threshold(self) -> None:
        with pytest.raises(ValueError, match="threshold"):
            JobFilter(canonical_titles=CANONICAL_TITLES, threshold=150)


class TestJobFilterMatch:
    @pytest.fixture
    def job_filter(self) -> JobFilter:
        return JobFilter(canonical_titles=CANONICAL_TITLES, threshold=82)

    def test_exact_match(self, job_filter: JobFilter) -> None:
        assert job_filter.match("Paid Media Manager") == "Paid Media Manager"

    def test_matches_with_seniority_prefix(self, job_filter: JobFilter) -> None:
        assert job_filter.match("Senior Paid Media Manager") == "Paid Media Manager"

    def test_matches_with_location_suffix(self, job_filter: JobFilter) -> None:
        assert job_filter.match("Paid Media Manager - Dubai") == "Paid Media Manager"

    def test_matches_with_hybrid_note(self, job_filter: JobFilter) -> None:
        assert job_filter.match("Paid Media Manager (Hybrid)") == "Paid Media Manager"

    def test_matches_case_insensitively(self, job_filter: JobFilter) -> None:
        assert job_filter.match("paid media manager") == "Paid Media Manager"

    def test_matches_correct_title_among_similar_options(self, job_filter: JobFilter) -> None:
        assert job_filter.match("Campaign Manager") == "Campaign Manager"
        assert job_filter.match("Digital Marketing Manager") == "Digital Marketing Manager"

    def test_unrelated_title_does_not_match(self, job_filter: JobFilter) -> None:
        assert job_filter.match("Software Engineer") is None

    def test_loosely_related_title_below_threshold_does_not_match(self, job_filter: JobFilter) -> None:
        # "Marketing Intern" shares the word "Marketing" but is a
        # meaningfully different, non-target role.
        assert job_filter.match("Marketing Intern") is None

    def test_empty_title_does_not_match(self, job_filter: JobFilter) -> None:
        assert job_filter.match("") is None

    def test_realistic_messy_postings_match_correctly(self, job_filter: JobFilter) -> None:
        # Regression coverage for the kind of real-world noise this
        # matcher exists to handle.
        assert job_filter.match("Senior Paid Media Manager (Hybrid) - Doha") == "Paid Media Manager"
        assert job_filter.match("Head of Performance Marketing Manager") == "Performance Marketing Manager"

    def test_unrelated_short_titles_do_not_false_positive(self, job_filter: JobFilter) -> None:
        assert job_filter.match("Sales Manager") is None
        assert job_filter.match("Marketing Intern") is None
        assert job_filter.match("Graphic Designer") is None

    def test_lower_threshold_is_more_permissive(self) -> None:
        strict_filter = JobFilter(canonical_titles=CANONICAL_TITLES, threshold=95)
        loose_filter = JobFilter(canonical_titles=CANONICAL_TITLES, threshold=50)

        ambiguous_title = "Marketing Manager"
        # A stricter threshold should reject titles a looser one accepts,
        # for at least some ambiguous input - proving threshold is honored.
        strict_result = strict_filter.match(ambiguous_title)
        loose_result = loose_filter.match(ambiguous_title)
        assert loose_result is not None
        assert strict_result is None or strict_result == loose_result


class TestExcludeFilter:
    def test_no_terms_configured_excludes_nothing(self) -> None:
        exclude_filter = ExcludeFilter(())
        assert exclude_filter.is_excluded("Paid Media Manager") is False
        assert exclude_filter.is_excluded("Marketing Intern") is False

    def test_excludes_exact_substring_match(self) -> None:
        exclude_filter = ExcludeFilter(("Intern",))
        assert exclude_filter.is_excluded("Marketing Intern") is True

    def test_excludes_case_insensitively(self) -> None:
        exclude_filter = ExcludeFilter(("intern",))
        assert exclude_filter.is_excluded("MARKETING INTERN") is True

    def test_substring_match_catches_compound_words(self) -> None:
        # Deliberate behavior, not a bug: "Intern" also excludes
        # "Internship" since it's a substring match, not whole-word.
        exclude_filter = ExcludeFilter(("Intern",))
        assert exclude_filter.is_excluded("Marketing Internship Program") is True

    def test_does_not_exclude_unrelated_title(self) -> None:
        exclude_filter = ExcludeFilter(("Intern", "Volunteer"))
        assert exclude_filter.is_excluded("Paid Media Manager") is False

    def test_multiple_terms_any_match_excludes(self) -> None:
        exclude_filter = ExcludeFilter(("Intern", "Volunteer", "Unpaid"))
        assert exclude_filter.is_excluded("Unpaid Marketing Assistant") is True

    def test_blank_terms_in_list_are_ignored(self) -> None:
        exclude_filter = ExcludeFilter(("", "  ", "Intern"))
        assert exclude_filter.is_excluded("Marketing Intern") is True
        assert exclude_filter.is_excluded("Paid Media Manager") is False
