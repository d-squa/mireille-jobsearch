"""
RunStats model.

A single structured object accumulated by the orchestrator during a
run and emitted as the final log summary: jobs checked, matched,
ignored, inserted, errors, and execution time.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RunStats:
    """Mutable counters for a single pipeline run.

    Not frozen, since the orchestrator increments these fields as the
    run progresses through each stage.
    """

    jobs_checked: int = 0
    jobs_matched: int = 0
    jobs_ignored: int = 0
    jobs_excluded: int = 0
    jobs_duplicate: int = 0
    jobs_inserted: int = 0
    errors: list[str] = field(default_factory=list)
    _start_time: float = field(default_factory=time.monotonic, repr=False)
    _end_time: float | None = field(default=None, repr=False)

    def record_error(self, message: str) -> None:
        """Record an error without stopping the run."""
        self.errors.append(message)

    def finish(self) -> None:
        """Mark the run as complete for duration calculation."""
        self._end_time = time.monotonic()

    @property
    def duration_seconds(self) -> float:
        end = self._end_time if self._end_time is not None else time.monotonic()
        return round(end - self._start_time, 2)

    def summary(self) -> str:
        """Human-readable one-block summary for the end-of-run log line."""
        return (
            f"Jobs checked: {self.jobs_checked} | "
            f"Matched: {self.jobs_matched} | "
            f"Excluded: {self.jobs_excluded} | "
            f"Ignored: {self.jobs_ignored} | "
            f"Duplicates: {self.jobs_duplicate} | "
            f"Inserted: {self.jobs_inserted} | "
            f"Errors: {len(self.errors)} | "
            f"Duration: {self.duration_seconds}s"
        )
