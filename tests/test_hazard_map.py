"""The maps of the natural hazards for dashboard cards: regions out of the
FOEN geodata, read on demand, kept, and bounded while the source is away."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from aiohttp import ClientError
from homeassistant.core import HomeAssistant

from custom_components.swiss_public_alerts import hazard_map
from custom_components.swiss_public_alerts.hazard_map import URLS, HazardMapError, HazardMaps, parse_map

from .common import Feeds, setup

SESSION = "custom_components.swiss_public_alerts.hazard_map.async_get_clientsession"
# a 10 km square in LV95 metres with a needless point on an edge
SQUARE = [[2600000, 1200000], [2605000, 1200010], [2610000, 1200000], [2610000, 1210000], [2600000, 1210000], [2600000, 1200000]]


def geojson(*features: tuple[str, list, dict]) -> bytes:
    return json.dumps({
        "creation_time": "24.11.2026 11:00",
        "features": [{"geometry": {"type": t, "coordinates": c}, "properties": p} for t, c, p in features],
    }).encode()


FIRE = geojson(("MultiPolygon", [[SQUARE]], {"level": 2, "name_de": "Aaretal", "name_en": "Aare valley", "title_de": "Mässige Gefahr"}))
FLOOD = geojson(
    ("MultiPolygon", [[SQUARE]], {"description": "<b>Al &amp; Stein</b>: Stufe 1", "ws-class": "Region.1", "text": "Gefahrenstufe 1"}),
    ("MultiLineString", [[[2600000, 1200000], [2620000, 1200000]]], {"description": "<b>Doubs</b>: Stufe 2", "ws-class": "River.2", "text": "Gefahrenstufe 2"}),
    ("Point", [2600000, 1200000], {}),
)
DROUGHT = geojson(("Polygon", [SQUARE], {"cdi-class": 4, "name_fr": "Haute-Argovie", "info_fr": "Très sec"}))


class Response:
    def __init__(self, status: int, body: bytes = b"", stamp: str | None = None) -> None:
        self.status, self._body = status, body
        self.headers = {"Last-Modified": stamp} if stamp else {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def read(self) -> bytes:
        return self._body


class Session:
    def __init__(self, *answers) -> None:
        self.answers, self.calls = list(answers), []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers or {}))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_regions_of_the_three_maps() -> None:
    (fire,) = parse_map(FIRE, "forestfire", "de")["regions"]
    assert (fire["name"], fire["level"], fire["text"]) == ("Aaretal", 2, "Mässige Gefahr")
    # LV95 kilometres, closed, without the needless point
    assert fire["rings"] == [[[2600.0, 1200.0], [2610.0, 1200.0], [2610.0, 1210.0], [2600.0, 1210.0], [2600.0, 1200.0]]]
    region, river = parse_map(FLOOD, "flood", "de")["regions"]  # the point is left out
    assert (region["name"], region["level"], region["lines"]) == ("Al & Stein", 1, [])
    assert (river["name"], river["level"], river["rings"]) == ("Doubs", 2, [])
    assert river["lines"] == [[[2600.0, 1200.0], [2620.0, 1200.0]]]
    (dry,) = parse_map(DROUGHT, "drought", "fr")["regions"]
    assert (dry["name"], dry["level"], dry["text"]) == ("Haute-Argovie", 4, "Très sec")
    assert parse_map(FLOOD, "flood", "de")["issued"] == "24.11.2026 11:00"


def test_levels_outside_the_scale_are_unknown() -> None:
    for level in (9, "2", None, True and "x"):
        (region,) = parse_map(geojson(("Polygon", [SQUARE], {"level": level})), "forestfire", "de")["regions"]
        assert region["level"] is None and region["name"] == ""
    (region,) = parse_map(geojson(("Polygon", [SQUARE], {"ws-class": "Region", "description": "no name"})), "flood", "de")["regions"]
    assert (region["name"], region["level"]) == ("", None)


@pytest.mark.parametrize("body", [b"not json", b"{}", b'{"features": []}', b'{"features": [1]}', b'{"features": [{"geometry": {"type": "Polygon", "coordinates": [[["a", "b"]]]}}]}'])
def test_files_that_make_no_sense(body: bytes) -> None:
    with pytest.raises(HazardMapError):
        parse_map(body, "forestfire", "de")


async def test_a_map_is_kept_and_asked_for_again(hass: HomeAssistant, freezer) -> None:
    session = Session(Response(200, FIRE, "Tue, 24 Nov 2026 12:00:25 GMT"), Response(304), Response(200, DROUGHT.replace(b"cdi-class", b"level")))
    maps = HazardMaps(hass)
    with patch(SESSION, return_value=session):
        first = await maps.async_get("forestfire", "de")
        freezer.tick(hazard_map.MAX_AGE - 1)
        assert await maps.async_get("forestfire", "de") is first and len(session.calls) == 1
        freezer.tick(2)
        assert await maps.async_get("forestfire", "de") is first  # not modified
        assert session.calls[1][1] == {"If-Modified-Since": "Tue, 24 Nov 2026 12:00:25 GMT"}
        freezer.tick(hazard_map.MAX_AGE + 1)
        assert (await maps.async_get("forestfire", "de"))["regions"][0]["level"] == 4
    assert session.calls[0][0] == URLS["forestfire"]


async def test_source_away(hass: HomeAssistant, freezer) -> None:
    session = Session(Response(503), Response(200, FIRE), ClientError(), TimeoutError())
    maps = HazardMaps(hass)
    with patch(SESSION, return_value=session):
        with pytest.raises(HazardMapError):
            await maps.async_get("forestfire", "de")
        with pytest.raises(HazardMapError):
            await maps.async_get("forestfire", "de")
        assert len(session.calls) == 1  # not asked again at once
        freezer.tick(hazard_map.RETRY_AFTER)
        kept = await maps.async_get("forestfire", "de")
        freezer.tick(hazard_map.MAX_AGE + 1)
        assert await maps.async_get("forestfire", "de") is kept  # the source is away: the last map
        assert session.calls[2][1] == {}  # no Last-Modified to ask with
        freezer.tick(hazard_map.KEEP)
        with pytest.raises(HazardMapError):
            await maps.async_get("forestfire", "de")


async def test_view(hass: HomeAssistant, feeds: Feeds, hass_client, hass_client_no_auth) -> None:
    await setup(hass, feeds)
    client = await hass_client()
    assert (await (await hass_client_no_auth()).get("/api/swiss_public_alerts/hazard_map")).status == 401
    answer = await client.get("/api/swiss_public_alerts/hazard_map")
    assert (await answer.json()) == {"kinds": ["forestfire", "flood", "drought"]}
    assert (await client.get("/api/swiss_public_alerts/hazard_map?kind=volcano")).status == 400
    session = Session(Response(200, FLOOD), Response(500))
    with patch(SESSION, return_value=session):
        answer = await client.get("/api/swiss_public_alerts/hazard_map?kind=flood&lang=rm")
        assert answer.status == 200 and len((await answer.json())["regions"]) == 2
        assert session.calls[0][0].endswith("_en.json")  # a language the source does not have
        assert (await client.get("/api/swiss_public_alerts/hazard_map?kind=drought&lang=de")).status == 503
    for entry in hass.config_entries.async_entries("swiss_public_alerts"):
        await hass.config_entries.async_unload(entry.entry_id)
    assert (await client.get("/api/swiss_public_alerts/hazard_map?kind=flood")).status == 503
