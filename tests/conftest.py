"""Shared notes for the Swiss Public Alerts tests.

Tests that need a Home Assistant instance request `hass` and
`enable_custom_integrations`; the Alertswiss and hazard feeds are patched
per test, or through the `feeds` fixture for a whole entry. The bundled
location dataset is read as shipped.
"""
from __future__ import annotations

import pytest

from .common import Feeds


@pytest.fixture
def feeds(enable_custom_integrations):
    """Both feeds faked for the length of a test."""
    fake = Feeds()
    alertswiss, hazards = fake.patches()
    with alertswiss, hazards:
        yield fake
