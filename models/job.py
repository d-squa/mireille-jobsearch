"""
Job model.

Every source connector (discovery or ATS) must normalize its raw
response into this exact shape. No connector-specific fields are
allowed to leak past the source layer - this is what lets core/,
storage/, and everything downstream stay source-agnostic.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Job:
    """A single, normalized job posting.

    Attributes:
        company: Company name as it appears in the posting.
        job_title: Raw job title as posted (not yet matched/scored).
        location: Human-readable location string (e.g. "Doha, Qatar").
        country: Best-effort country name or ISO code; "Unknown" if
            it could not be determined.
        source: Identifier of the connector that produced this job,
            e.g. "jooble", "adzuna", "greenhouse".
        job_url: Canonical URL to the posting. Used as part of the
            dedup key.
        posted_date: Date the job was posted, if the source provides
            it. None if unavailable.
        description: Raw or lightly-cleaned job description text.
        salary: Human-readable salary/compensation string, normalized
            per-source into a display string (currency and format vary
            by source, deliberately not forced into numeric min/max
            fields). None if the source doesn't expose salary data -
            Greenhouse and Lever never do; Jooble, Reed, Adzuna, and
            Ashby (with compensation enabled) do, when the employer
            chose to publish it.
    """

    company: str
    job_title: str
    location: str
    country: str
    source: str
    job_url: str
    posted_date: date | None
    description: str
    salary: str | None = None

    def dedup_hash(self) -> str:
        """Stable hash used as the dedup key across daily runs.

        Built from company + normalized title + location + source
        rather than job_url alone, since some ATS platforms reissue
        the same posting under a new URL after edits.
        """
        normalized_title = " ".join(self.job_title.lower().split())
        normalized_company = " ".join(self.company.lower().split())
        normalized_location = " ".join(self.location.lower().split())
        raw = f"{normalized_company}|{normalized_title}|{normalized_location}|{self.source}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
