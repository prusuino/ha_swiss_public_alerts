"""Pure parsing: Alertswiss alerts, canton detection, coverage of a point,
the hazard location lookup and the natural-hazard danger levels."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

from custom_components.swiss_public_alerts.api import (
    AlertswissClient,
    _clean_text,
    _parse_published,
    _point_in_polygon,
    detect_canton,
    haversine_km,
)
from custom_components.swiss_public_alerts.hazards import HazardsClient, find_location, load_locations

SQUARE = [[46.0, 7.0], [46.0, 8.0], [47.0, 8.0], [47.0, 7.0]]
ITEM = {
    "identifier": "ch.alertswiss.123",
    "title": {"title": "<b>Hochwasser</b> Aare"},
    "description": {"description": "Pegel  steigt&nbsp;weiter."},
    "event": "Hochwasser",
    "severity": "moderate",
    "publisherName": "Kanton Bern, Amt für Bevölkerungsschutz",
    "reference": "sender,ch.alertswiss.123,2026-07-17T12:18:25+02:00",
    "instructions": [{"text": "Keller <i>meiden</i>."}, {"text": ""}],
    "areas": [{"description": {"description": "Bern und Umgebung"}, "polygons": [{"coordinates": SQUARE}, {"coordinates": [[1, 2]]}]}],
}


def _client():
    return AlertswissClient(MagicMock(), "de")


def test_alert_parsing_cleans_text_and_builds_geometry():
    alert = _client()._parse_alert(ITEM)
    assert alert.title == "Hochwasser Aare"
    assert alert.description == "Pegel steigt weiter."
    assert alert.instructions == ("Keller meiden .",)  # a tag becomes a space
    assert alert.area_descriptions == ("Bern und Umgebung",)
    assert len(alert.polygons) == 1  # the two-point polygon is dropped
    assert alert.centroid == (46.5, 7.5)
    assert alert.canton_code == "be"
    assert alert.published == datetime(2026, 7, 17, 12, 18, 25, tzinfo=timezone(__import__("datetime").timedelta(hours=2)))
    assert alert.covers(46.5, 7.5) is True
    assert alert.covers(47.5, 7.5) is False
    assert 0 < alert.distance_km(46.5, 7.6) < 10
    assert alert.summary["severity"] == "moderate" and alert.summary["canton_code"] == "be"
    assert alert.link.endswith("ch.alertswiss.123")


def test_test_alerts_and_broken_items_are_skipped():
    client = _client()
    assert client._parse_alert({**ITEM, "testAlert": True}) is None
    assert client._parse_alert({**ITEM, "technicalTestAlert": True}) is None
    assert client._parse_alert({"title": {"title": "no id"}}) is None
    assert client._parse_alert("garbage") is None


def test_nation_wide_alert_covers_everything():
    alert = _client()._parse_alert({"identifier": "x", "nationWide": True, "publisherName": "BABS", "severity": None})
    assert alert.nation_wide is True and alert.canton_code == "ch"
    assert alert.severity == "unknown"
    assert alert.covers(47.4, 8.5) is True
    assert alert.centroid is None and alert.distance_km(47.4, 8.5) is None
    assert alert.title == "x"  # falls back to the identifier


def test_text_and_time_helpers():
    assert _clean_text("  <p>Hallo</p>&amp; <br/>Welt  ") == "Hallo & Welt"
    assert _clean_text(None) == ""
    assert _parse_published("a,b,2026-07-17T12:18:25+02:00").year == 2026
    assert _parse_published("a,b,yesterday") is None
    assert _parse_published(None) is None
    assert detect_canton("Kanton Zürich") == "zh"
    assert detect_canton("Kantonspolizei Graubünden") == "gr"
    assert detect_canton("Unbekannt") is None
    assert detect_canton(None) is None
    assert _point_in_polygon(46.5, 7.5, tuple((a, b) for a, b in SQUARE)) is True
    assert _point_in_polygon(46.5, 7.5, ((46, 7), (47, 8))) is False
    assert round(haversine_km(46.948, 7.447, 47.377, 8.540)) == 95


def test_location_lookup_prefers_the_main_entry():
    locations = load_locations()
    zurich = find_location(locations, " 8001 ")
    assert zurich.name == "Zürich" and zurich.location_id == "800100"
    assert zurich.regions["warn"] == (143,)
    assert zurich.region_ids("wind") == {143}
    assert find_location(locations, "0000") is None


def test_hazard_levels_pick_the_worst_valid_entry_for_the_location():
    location = find_location(load_locations(), "8001")
    client = HazardsClient(MagicMock(), "de", location)
    future = int(time.time()) + 3600
    raw = {
        "config": {"timestamp": 1794000000},
        "hazards": {
            "wind": [
                {"warnlevel": 2, "areas": [143], "expires": future, "description": "Sturmböen", "webLinkText": "Mehr"},
                {"warnlevel": 4, "areas": [143], "expires": int(time.time()) - 10},  # expired
                {"warnlevel": 5, "areas": [999], "expires": future},  # another region
                {"warnlevel": 3, "areas": [143], "expires": future, "is_outlook": True},
                "garbage",
            ],
            "rain": [{"warnlevel": "high", "areas": [143]}],  # no numeric level
        },
    }
    data = client._parse(raw, "v1")
    wind = data.states["wind"]
    assert wind.level == 2 and wind.outlook_level == 3
    assert wind.description == "Sturmböen" and wind.expires == future
    assert wind.expires_iso.startswith("20")
    assert data.states["rain"].level == 0 and data.states["rain"].outlook_level is None
    assert data.states["earthquake"].level == 0
    assert data.max_level == 2
    assert data.timestamp == 1794000000 and data.version == "v1"
