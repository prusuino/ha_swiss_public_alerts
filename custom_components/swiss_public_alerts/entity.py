"""Base entity for the Swiss Public Alerts integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import AlertswissCoordinator
from .const import ATTRIBUTION, DOMAIN, MANUFACTURER


class AlertswissEntity(CoordinatorEntity[AlertswissCoordinator]):
    """Common base with device and attribution."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: AlertswissCoordinator, suffix: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name="Alertswiss",
            manufacturer=MANUFACTURER,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.alert.swiss/",
        )
