"""Connectivity sensor: off when AlarmeringDroid has not answered for a minute (alarms will not arrive)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import V2000ConfigEntry
from .const import signal_status
from .poller import V2000Poller
from .sensor import device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: V2000ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([V2000Verbinding(entry.entry_id, entry.runtime_data)])


class V2000Verbinding(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "verbinding"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, entry_id: str, poller: V2000Poller) -> None:
        self._poller = poller
        self._signal = signal_status(entry_id)
        self._attr_unique_id = f"{entry_id}_verbinding"
        self._attr_device_info = device_info(entry_id)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, self._signal, self._update))

    @property
    def available(self) -> bool:
        return self._poller.connected is not None

    @property
    def is_on(self) -> bool | None:
        return self._poller.connected

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        p = self._poller
        return {
            "poll_interval_s": p.interval,
            "laatste_fout": p.last_error,
            "sinds": p.status_since.isoformat() if p.status_since else None,
        }

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()
