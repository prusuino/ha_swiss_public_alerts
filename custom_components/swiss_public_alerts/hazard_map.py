"""Maps of the natural hazards for dashboard cards: the danger level of every
region for forest fire, flood and drought, in one authenticated request.

GET /api/swiss_public_alerts/hazard_map             -> the kinds on offer
GET /api/swiss_public_alerts/hazard_map?kind=flood&lang=de

The maps are the open geodata the Federal Office for the Environment FOEN
publishes on data.geo.admin.ch. Nothing is read until a card asks; a map is
kept for half an hour, and after that asked for with If-Modified-Since, so
an unchanged file is not transferred again. The outlines come in Swiss LV95
metres; they are simplified to about 150 m and sent as LV95 kilometres.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import math
import re
import time
from typing import Any

from aiohttp import ClientError, ClientTimeout

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_BASE = "https://data.geo.admin.ch"
URLS = {
    "forestfire": f"{_BASE}/ch.bafu.gefahren-waldbrand_warnung/gefahren-waldbrand_warnung/gefahren-waldbrand_warnung_2056.geojson",
    # one file per language
    "flood": f"{_BASE}/ch.bafu.hydroweb-warnkarte_national/ch.bafu.hydroweb-warnkarte_national_{{lang}}.json",
    "drought": f"{_BASE}/ch.bafu.trockenheitsindex/trockenheitsindex_0/trockenheitsindex_0_2056.json",
}
LANGUAGES = ("de", "fr", "it", "en")
MAX_AGE = 1800  # seconds a map is kept without asking
KEEP = 12 * 3600  # seconds a map is shown while the source does not answer
RETRY_AFTER = 300  # seconds after a failed read
TOLERANCE_KM = 0.15
_TIMEOUT = ClientTimeout(total=40)


class HazardMapError(Exception):
    """The map could not be read or made no sense."""


def _thin(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Douglas-Peucker on an open line."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (x1, y1), (x2, y2) = points[first], points[last]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        worst, index = 0.0, -1
        for i in range(first + 1, last):
            x, y = points[i]
            off = abs(dy * (x - x1) - dx * (y - y1)) / length if length else math.hypot(x - x1, y - y1)
            if off > worst:
                worst, index = off, i
        if worst > TOLERANCE_KM:
            keep[index] = True
            stack += [(first, index), (index, last)]
    return [p for p, k in zip(points, keep, strict=True) if k]


def _kilometres(points: list) -> list[tuple[float, float]]:
    return [(float(p[0]) / 1000, float(p[1]) / 1000) for p in points]


def _rounded(points: list[tuple[float, float]]) -> list[list[float]]:
    out: list[list[float]] = []
    for x, y in points:
        point = [round(x, 1), round(y, 1)]
        if not out or out[-1] != point:
            out.append(point)
    return out


def _ring(points: list) -> list[list[float]]:
    """A closed outline, simplified in two halves so that it stays closed."""
    line = _kilometres(points)
    half = len(line) // 2
    return _rounded(_thin(line[: half + 1])[:-1] + _thin(line[half:]))


def _shapes(geometry: dict | None) -> tuple[list, list]:
    """(outlines, lines) of a geometry; islands and cut-outs are outlines too
    and are drawn with the even-odd rule."""
    geometry = geometry or {}
    coordinates = geometry.get("coordinates") or []
    kind = geometry.get("type")
    if kind == "Polygon":
        coordinates = [coordinates]
    if kind in ("Polygon", "MultiPolygon"):
        rings = [_ring(ring) for polygon in coordinates for ring in polygon]
        return [ring for ring in rings if len(ring) >= 4], []
    if kind == "LineString":
        coordinates = [coordinates]
    if kind in ("LineString", "MultiLineString"):
        lines = [_rounded(_thin(_kilometres(line))) for line in coordinates]
        return [], [line for line in lines if len(line) >= 2]
    return [], []


def _region(kind: str, properties: dict, lang: str) -> tuple[str, int | None, str]:
    """(name, level, text) of a feature."""
    if kind == "forestfire":
        return properties.get(f"name_{lang}") or "", properties.get("level"), properties.get(f"title_{lang}") or ""
    if kind == "drought":
        return properties.get(f"name_{lang}") or "", properties.get("cdi-class"), properties.get(f"info_{lang}") or ""
    # flood: "<b>Doubs</b>: Gefahrenstufe 2: Mässige Hochwassergefahr", class "River.2"
    match = re.match(r"<b>(.*?)</b>", properties.get("description") or "")
    level = str(properties.get("ws-class") or "").rpartition(".")[2]
    return html.unescape(match.group(1)) if match else "", int(level) if level.isdigit() else None, properties.get("text") or ""


def parse_map(body: bytes, kind: str, lang: str) -> dict[str, Any]:
    """The regions of a map file. Runs in the executor."""
    try:
        data = json.loads(body)
        features = data["features"]
        regions = []
        for feature in features:
            rings, lines = _shapes(feature.get("geometry"))
            if not rings and not lines:
                continue
            name, level, text = _region(kind, feature.get("properties") or {}, lang)
            regions.append({
                "name": str(name),
                "level": level if isinstance(level, int) and 0 <= level <= 5 else None,
                "text": str(text),
                "rings": rings,
                "lines": lines,
            })
    except (ValueError, KeyError, TypeError, IndexError, AttributeError) as err:
        raise HazardMapError(f"{kind} map is not what was expected ({type(err).__name__})") from err
    if not regions:
        raise HazardMapError(f"{kind} map has no regions")
    return {"kind": kind, "language": lang, "issued": data.get("creation_time"), "regions": regions}


class HazardMaps:
    """The maps as last read, one store per Home Assistant."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._maps: dict[tuple[str, str], dict[str, Any]] = {}
        self._checked: dict[tuple[str, str], float] = {}
        self._failed: dict[tuple[str, str], float] = {}
        self._stamps: dict[tuple[str, str], str] = {}

    async def async_get(self, kind: str, lang: str) -> dict[str, Any]:
        key = (kind, lang)
        async with self._locks.setdefault(key, asyncio.Lock()):
            now = time.time()
            if key in self._maps and now - self._checked[key] < MAX_AGE:
                return self._maps[key]
            if now - self._failed.get(key, 0) >= RETRY_AFTER:
                try:
                    await self._read(key, now)
                    self._failed.pop(key, None)
                except HazardMapError as err:
                    self._failed[key] = now
                    _LOGGER.debug("Hazard map not read: %s", err)
            if key in self._maps and now - self._checked[key] < KEEP:
                return self._maps[key]
            raise HazardMapError(f"no {kind} map at the moment")

    async def _read(self, key: tuple[str, str], now: float) -> None:
        kind, lang = key
        headers = {}
        if key in self._maps and key in self._stamps:
            headers["If-Modified-Since"] = self._stamps[key]
        session = async_get_clientsession(self._hass)
        try:
            async with session.get(URLS[kind].format(lang=lang), headers=headers, timeout=_TIMEOUT) as resp:
                if resp.status == 304:
                    self._checked[key] = now
                    return
                if resp.status != 200:
                    raise HazardMapError(f"HTTP {resp.status} for the {kind} map")
                body = await resp.read()
                stamp = resp.headers.get("Last-Modified")
        except (ClientError, TimeoutError) as err:
            raise HazardMapError(f"{type(err).__name__} for the {kind} map") from err
        self._maps[key] = await self._hass.async_add_executor_job(parse_map, body, kind, lang)
        self._checked[key] = now
        if stamp:
            self._stamps[key] = stamp
        else:
            self._stamps.pop(key, None)


class HazardMapView(HomeAssistantView):
    """The danger level of every region, for a card."""

    url = f"/api/{DOMAIN}/hazard_map"
    name = f"api:{DOMAIN}:hazard_map"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._maps = HazardMaps(hass)

    async def get(self, request):
        hass: HomeAssistant = request.app[KEY_HASS]
        kind = request.query.get("kind")
        if kind is None:
            return self.json({"kinds": list(URLS)})
        if kind not in URLS:
            return self.json_message("Unknown kind of map", 400)
        if not hass.config_entries.async_loaded_entries(DOMAIN):
            return self.json_message("Swiss Public Alerts is not set up", 503)
        lang = request.query.get("lang") or hass.config.language
        if lang not in LANGUAGES:
            lang = "en"
        try:
            return self.json(await self._maps.async_get(kind, lang))
        except HazardMapError:
            return self.json_message("The map could not be fetched", 503)


def async_register_view(hass: HomeAssistant) -> None:
    """Register the view once per Home Assistant run."""
    key = f"{DOMAIN}_hazard_map_registered"
    if not hass.data.get(key):
        hass.http.register_view(HazardMapView(hass))
        hass.data[key] = True
