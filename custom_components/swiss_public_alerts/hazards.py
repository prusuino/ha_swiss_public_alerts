"""Client for the natural hazard levels published on www.naturgefahren.ch.

The federal Natural Hazards Portal (naturgefahren.ch / natural-hazards.ch)
publishes the current danger levels of all federal specialist agencies
(MeteoSwiss, FOEN, SLF, SED) as a versioned JSON product:

    /product/output/versions.json                       -> current version
    /product/output/versioned/danger/v3/version__<v>/<lang>/dangers.json

Each hazard entry carries a warning level (0-5) and a list of region ids.
Locations are matched to regions via a bundled snapshot of the portal's
own location dataset (see hazard_locations.json), where each place (postal
code) lists its region ids per warning system.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import (
    DEFAULT_TIMEOUT,
    HAZARDS_BASE_URL,
    HAZARDS_DANGER_PATH,
    HAZARDS_PRODUCT_KEY,
    HAZARDS_VERSIONS_URL,
    HAZARD_TYPES,
)

LOCATIONS_FILE = Path(__file__).parent / "hazard_locations.json"

# Which region-id list of a location applies to which hazard type. Hazards
# not listed here (all weather processes) use the "warn" (MeteoSwiss) regions.
_REGION_SYSTEMS = {
    "avalanches": ("slf",),
    "forestfire": ("forestfire",),
    "flood": ("hydro", "rivers", "lakes"),
    "drought": ("hydro",),
}
_DEFAULT_SYSTEM = ("warn",)


class HazardsApiError(Exception):
    """Raised when the hazards product cannot be fetched or parsed."""


@dataclass(frozen=True)
class HazardLocation:
    """One place from the portal's location dataset with its region ids."""

    location_id: str
    plz: str
    name: str
    regions: dict[str, tuple[int, ...]]

    def region_ids(self, hazard_type: str) -> set[int]:
        """Region ids of this location relevant for the given hazard type."""
        systems = _REGION_SYSTEMS.get(hazard_type, _DEFAULT_SYSTEM)
        return {rid for system in systems for rid in self.regions.get(system, ())}


@dataclass(frozen=True)
class HazardState:
    """Aggregated danger state of one hazard type at one location."""

    hazard_type: str
    level: int
    outlook_level: int | None
    description: str
    web_link_text: str
    expires: int | None

    @property
    def expires_iso(self) -> str | None:
        if self.expires is None:
            return None
        from datetime import datetime, timezone

        return datetime.fromtimestamp(self.expires, tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class HazardsData:
    """Parsed danger levels for the configured location."""

    states: dict[str, HazardState]
    version: str
    timestamp: int | None

    @property
    def max_level(self) -> int:
        return max((s.level for s in self.states.values()), default=0)


def load_locations() -> list[dict]:
    """Load the bundled location dataset (executor only, blocking I/O)."""
    with LOCATIONS_FILE.open(encoding="utf-8") as f:
        return json.load(f)["locations"]


def find_location(locations: list[dict], plz: str) -> HazardLocation | None:
    """Find a place by postal code; prefers the main entry (id = plz + '00')."""
    plz = plz.strip()
    matches = [loc for loc in locations if loc.get("plz") == plz]
    if not matches:
        return None
    main = next((loc for loc in matches if loc.get("id") == f"{plz}00"), matches[0])
    return HazardLocation(
        location_id=main.get("id") or "",
        plz=plz,
        name=main.get("name") or plz,
        regions={
            key: tuple(main.get(key) or ())
            for key in ("warn", "forestfire", "hydro", "slf", "rivers", "lakes")
        },
    )


class HazardsClient:
    """Async client for the versioned dangers product of naturgefahren.ch."""

    def __init__(self, session: ClientSession, language: str, location: HazardLocation) -> None:
        self._session = session
        self.language = language
        self.location = location
        self._cached_version: str | None = None
        self._cached_raw: dict | None = None
        self._cached_language: str | None = None

    async def _get_json(self, url: str) -> dict:
        try:
            async with self._session.get(
                url, timeout=ClientTimeout(total=DEFAULT_TIMEOUT)
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except (ClientError, TimeoutError) as err:
            raise HazardsApiError(f"Error fetching {url}: {err}") from err

    async def async_fetch(self) -> HazardsData:
        """Fetch the current danger levels for the configured location."""
        versions = await self._get_json(HAZARDS_VERSIONS_URL)
        version = versions.get(HAZARDS_PRODUCT_KEY) if isinstance(versions, dict) else None
        if not version:
            raise HazardsApiError("Dangers product version not found in versions.json")

        if (
            self._cached_raw is None
            or version != self._cached_version
            or self.language != self._cached_language
        ):
            url = (
                f"{HAZARDS_BASE_URL}{HAZARDS_DANGER_PATH}version__{version}/"
                f"{self.language}/dangers.json"
            )
            raw = await self._get_json(url)
            if not isinstance(raw, dict) or "hazards" not in raw:
                raise HazardsApiError("Unexpected dangers.json structure")
            self._cached_raw = raw
            self._cached_version = version
            self._cached_language = self.language

        return self._parse(self._cached_raw, version)

    def _parse(self, raw: dict, version: str) -> HazardsData:
        now = time.time()
        states: dict[str, HazardState] = {}
        hazards = raw.get("hazards") or {}
        for hazard_type in HAZARD_TYPES:
            best: dict | None = None
            outlook_level: int | None = None
            region_ids = self.location.region_ids(hazard_type)
            for entry in hazards.get(hazard_type) or []:
                if not isinstance(entry, dict):
                    continue
                expires = entry.get("expires")
                if isinstance(expires, (int, float)) and expires < now:
                    continue
                if not region_ids & {a for a in entry.get("areas") or [] if isinstance(a, int)}:
                    continue
                level = entry.get("warnlevel")
                if not isinstance(level, int):
                    continue
                if entry.get("is_outlook"):
                    if outlook_level is None or level > outlook_level:
                        outlook_level = level
                elif best is None or level > best.get("warnlevel", 0):
                    best = entry
            states[hazard_type] = HazardState(
                hazard_type=hazard_type,
                level=best.get("warnlevel", 0) if best else 0,
                outlook_level=outlook_level,
                description=(best or {}).get("description") or "",
                web_link_text=(best or {}).get("webLinkText") or "",
                expires=(best or {}).get("expires"),
            )

        config = raw.get("config") or {}
        timestamp = config.get("timestamp")
        return HazardsData(
            states=states,
            version=version,
            timestamp=timestamp if isinstance(timestamp, int) else None,
        )
