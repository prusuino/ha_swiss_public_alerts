"""Client for the Alertswiss public alert feed."""

from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass, field
from datetime import datetime

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import (
    ALERT_URL_TEMPLATE,
    CANTON_KEYWORDS,
    DEFAULT_TIMEOUT,
    FEED_URL_TEMPLATE,
    SEVERITY_UNKNOWN,
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v ]+")

EARTH_RADIUS_KM = 6371.0088

# Longest keywords first so e.g. "appenzell ausserrhoden" wins over "uri".
_CANTON_PATTERNS = [
    (re.compile(rf"\b{re.escape(kw)}\b"), code)
    for kw, code in sorted(CANTON_KEYWORDS.items(), key=lambda kv: -len(kv[0]))
]


def detect_canton(publisher: str | None) -> str | None:
    """Derive the two-letter canton code from a publisher name."""
    if not publisher:
        return None
    text = publisher.lower()
    for pattern, code in _CANTON_PATTERNS:
        if pattern.search(text):
            return code
    return None


class AlertswissApiError(Exception):
    """Raised when the Alertswiss feed cannot be fetched or parsed."""


def _clean_text(value: str | None) -> str:
    """Strip HTML tags and normalize whitespace."""
    if not value:
        return ""
    text = _TAG_RE.sub(" ", value)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _parse_published(reference: str | None) -> datetime | None:
    """Extract the ISO timestamp from the CAP reference field.

    The reference has the form "sender,identifier,2026-07-17T12:18:25+02:00";
    the localized "sent"/"publishDate" strings are not machine-readable.
    """
    if not reference:
        return None
    try:
        return datetime.fromisoformat(reference.rsplit(",", 1)[-1])
    except ValueError:
        return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points in kilometers."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _ring(pairs) -> tuple[tuple[float, float], ...]:
    """The (lat, lon) vertices of a coordinate list; unreadable pairs are skipped."""
    coords = []
    for pair in pairs or []:
        try:
            coords.append((float(pair[0]), float(pair[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return tuple(coords)


def _web_link(value: str | None) -> str | None:
    """A link as the feed gives it, made usable.

    Authorities often enter a bare host ("www.example.ch"); that gets https.
    Anything that is not a web address (mailto:, javascript:, text) is dropped.
    """
    link = (value or "").strip()
    if not link or any(c.isspace() for c in link):
        return None
    if re.match(r"^https?://", link, re.I):
        return link
    if re.match(r"^www\.[\w.-]+\.[a-z]{2,}(/.*)?$", link, re.I):
        return "https://" + link
    return None


def _point_in_polygon(lat: float, lon: float, polygon: tuple[tuple[float, float], ...]) -> bool:
    """Ray-casting point-in-polygon test on (lat, lon) vertex tuples."""
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


@dataclass(frozen=True)
class Alert:
    """One active Alertswiss alert."""

    identifier: str
    title: str
    description: str
    event: str
    severity: str
    publisher: str
    published: datetime | None
    link: str
    instructions: tuple[str, ...]
    area_descriptions: tuple[str, ...]
    nation_wide: bool
    all_clear: bool
    polygons: tuple[tuple[tuple[float, float], ...], ...] = field(repr=False)
    centroid: tuple[float, float] | None
    canton_code: str | None
    # Zones cut out of a polygon, one tuple of rings per entry of `polygons`.
    holes: tuple[tuple[tuple[tuple[float, float], ...], ...], ...] = field(default=(), repr=False)
    # Areas given as a circle: (lat, lon, radius in km).
    circles: tuple[tuple[float, float, float], ...] = field(default=(), repr=False)
    cantons: tuple[str, ...] = ()
    links: tuple[tuple[str, str], ...] = ()
    contact: str = ""
    machine_translated: bool = False

    def covers(self, lat: float, lon: float) -> bool:
        """Whether the given location lies inside any affected area.

        An area is a polygon, minus the zones the authority cut out of it,
        or a circle around a point.
        """
        if self.nation_wide:
            return True
        for index, poly in enumerate(self.polygons):
            if not _point_in_polygon(lat, lon, poly):
                continue
            holes = self.holes[index] if index < len(self.holes) else ()
            if not any(_point_in_polygon(lat, lon, hole) for hole in holes):
                return True
        return any(haversine_km(lat, lon, c_lat, c_lon) <= radius for c_lat, c_lon, radius in self.circles)

    def distance_km(self, lat: float, lon: float) -> float | None:
        """Distance from the given location to the alert area centroid."""
        if self.centroid is None:
            return None
        return haversine_km(lat, lon, self.centroid[0], self.centroid[1])

    @property
    def summary(self) -> dict:
        """Compact representation for entity attributes."""
        return {
            "identifier": self.identifier,
            "title": self.title,
            "event": self.event,
            "severity": self.severity,
            "publisher": self.publisher,
            "published": self.published.isoformat() if self.published else None,
            "areas": list(self.area_descriptions),
            "nation_wide": self.nation_wide,
            "canton_code": self.canton_code,
            "cantons": list(self.cantons),
            "link": self.link,
            "links": [{"href": href, "text": text} for href, text in self.links],
            "machine_translated": self.machine_translated,
        }


@dataclass(frozen=True)
class FeedData:
    """Parsed state of the Alertswiss feed."""

    alerts: tuple[Alert, ...]
    heartbeat_age_seconds: float | None


class AlertswissClient:
    """Minimal async client for the Alertswiss JSON feed."""

    def __init__(self, session: ClientSession, language: str) -> None:
        self._session = session
        self.language = language

    async def async_fetch(self) -> FeedData:
        """Fetch and parse the current feed."""
        url = FEED_URL_TEMPLATE.format(language=self.language)
        try:
            async with self._session.get(
                url, timeout=ClientTimeout(total=DEFAULT_TIMEOUT)
            ) as resp:
                resp.raise_for_status()
                raw = await resp.json(content_type=None)
        except (ClientError, TimeoutError) as err:
            raise AlertswissApiError(f"Error fetching Alertswiss feed: {err}") from err

        if not isinstance(raw, dict) or "alerts" not in raw:
            raise AlertswissApiError("Unexpected Alertswiss feed structure")

        heartbeat_ms = raw.get("heartbeatAgeInMillis")
        heartbeat = heartbeat_ms / 1000 if isinstance(heartbeat_ms, (int, float)) else None

        alerts = []
        for item in raw["alerts"]:
            alert = self._parse_alert(item)
            if alert is not None:
                alerts.append(alert)
        return FeedData(alerts=tuple(alerts), heartbeat_age_seconds=heartbeat)

    def _parse_alert(self, item: dict) -> Alert | None:
        """Parse one alert, skipping test alerts and malformed entries."""
        if not isinstance(item, dict):
            return None
        if item.get("testAlert") or item.get("technicalTestAlert"):
            return None
        identifier = item.get("identifier")
        if not identifier:
            return None

        polygons: list[tuple[tuple[float, float], ...]] = []
        holes: list[tuple[tuple[tuple[float, float], ...], ...]] = []
        circles: list[tuple[float, float, float]] = []
        cantons: list[str] = []
        area_descriptions: list[str] = []
        for area in item.get("areas") or []:
            if not isinstance(area, dict):
                continue
            desc = _clean_text((area.get("description") or {}).get("description"))
            if desc:
                area_descriptions.append(desc)
            for poly in area.get("polygons") or []:
                coords = _ring(poly.get("coordinates"))
                if len(coords) < 3:
                    continue
                polygons.append(coords)
                holes.append(tuple(
                    ring
                    for exclude in poly.get("excludes") or []
                    if len(ring := _ring((exclude or {}).get("coordinates"))) >= 3
                ))
            for circle in area.get("circles") or []:
                try:
                    center = circle["centerPosition"]
                    radius = float(circle["radius"])  # kilometres, as in CAP
                    circles.append((float(center[0]), float(center[1]), radius))
                except (KeyError, TypeError, ValueError, IndexError):
                    continue
            for region in area.get("regions") or []:
                code = str((region or {}).get("region") or "").strip().lower()
                if re.fullmatch(r"[a-z]{2}", code) and code not in cantons:
                    cantons.append(code)

        centroid = None
        vertices = [pt for poly in polygons for pt in poly] + [(c[0], c[1]) for c in circles]
        if vertices:
            centroid = (
                sum(p[0] for p in vertices) / len(vertices),
                sum(p[1] for p in vertices) / len(vertices),
            )

        instructions = tuple(
            text
            for entry in item.get("instructions") or []
            if (text := _clean_text(entry.get("text")))
        )

        publisher = _clean_text(item.get("publisherName"))
        links = tuple(
            (href, _clean_text(entry.get("text")) or href)
            for entry in item.get("links") or []
            if isinstance(entry, dict) and (href := _web_link(entry.get("href")))
        )
        # The canton as the feed names it for the area; the publisher's name
        # is the fallback for alerts without a region.
        if item.get("nationWide"):
            canton_code = "ch"
        elif len(cantons) == 1:
            canton_code = cantons[0]
        else:
            canton_code = detect_canton(publisher) or (cantons[0] if cantons else None)
        return Alert(
            identifier=identifier,
            title=_clean_text((item.get("title") or {}).get("title")) or identifier,
            description=_clean_text((item.get("description") or {}).get("description")),
            event=_clean_text(item.get("event")),
            severity=item.get("severity") or SEVERITY_UNKNOWN,
            publisher=publisher,
            published=_parse_published(item.get("reference")),
            link=_web_link(item.get("link"))
            or (links[0][0] if links else None)
            or ALERT_URL_TEMPLATE.format(language=self.language, identifier=identifier),
            instructions=instructions,
            area_descriptions=tuple(area_descriptions),
            nation_wide=bool(item.get("nationWide")),
            all_clear=bool(item.get("allClear")),
            polygons=tuple(polygons),
            centroid=centroid,
            canton_code=canton_code,
            holes=tuple(holes),
            circles=tuple(circles),
            cantons=tuple(cantons),
            links=links,
            contact=_clean_text((item.get("contact") or {}).get("contact")),
            machine_translated=bool(item.get("gtransOrigin")),
        )
