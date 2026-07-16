"""Shared pytest fixtures for the whole test suite."""
import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_environ():
    """Snapshot and restore os.environ around every test.

    config._load_settings calls python-dotenv's load_dotenv(), which
    mutates os.environ directly - bypassing monkeypatch's tracking
    entirely. Without this fixture, a value set by one test's .env
    file can leak into every later test in the same pytest session
    (load_dotenv's default override=False means a leaked value even
    blocks a later test's own file from overwriting it), causing
    validation-order-dependent failures that have nothing to do with
    the test that actually fails.

    Applies to every test automatically (autouse=True), so no
    individual test needs to remember to clean up after itself.
    """
    original = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(original)
