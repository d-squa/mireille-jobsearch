"""
Shared HTTP retry helper.

Every connector (Jooble, Greenhouse, Lever, Ashby, and any future
source) needs the same retry/backoff behaviour on network failures
and 5xx responses. Factored out here rather than duplicated per
connector.
"""
from __future__ import annotations

import time

import requests

from exceptions import SourceError
from utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_MAX_RETRIES = 3
_DEFAULT_BACKOFF_SECONDS = 2


def fetch_json_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    source_name: str,
    json: dict | None = None,
    params: dict | None = None,
    auth: tuple[str, str] | None = None,
    timeout: int = 10,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    backoff_seconds: int = _DEFAULT_BACKOFF_SECONDS,
) -> dict | list:
    """Make an HTTP request, retrying on network errors and 5xx/4xx
    failures with linear backoff. Returns the parsed JSON body.

    Raises:
        SourceError: if every attempt fails.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = session.request(
                method, url, json=json, params=params, auth=auth, timeout=timeout
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            logger.warning(
                "%s request failed (attempt %d/%d) for %s: %s",
                source_name,
                attempt,
                max_retries,
                url,
                exc,
            )
            if attempt < max_retries:
                time.sleep(backoff_seconds * attempt)

    raise SourceError(f"{source_name} request failed for {url}: {last_error}")
