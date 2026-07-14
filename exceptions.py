"""
Shared exception hierarchy.

SourceError is raised by connectors (sources/) for recoverable,
per-source failures - a timeout, a bad response, an auth error.
The orchestrator (Milestone 4) catches these per-source so one
failing connector doesn't take down the whole daily run.

ConfigError (in config.py) is intentionally kept separate: it's fatal
and should stop the process at startup, not be caught mid-run.
"""
from __future__ import annotations


class SourceError(Exception):
    """A single job source failed to fetch or parse results.

    Raised with enough context (source name + underlying cause) that
    the orchestrator can log it into RunStats.errors and move on to
    the next source.
    """
