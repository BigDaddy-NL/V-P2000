"""One timestamp sensor per group: when its last alarm came in, with the details as attributes."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import V2000ConfigEntry
from .const import DOMAIN, NAME, VERSION, signal_alarm


def device_info(entry_id: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name=NAME,
        manufacturer=NAME,
        model="P2000 via AlarmeringDroid",
        sw_version=VERSION,
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://beta.alarmeringdroid.nl",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: V2000ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(V2000GroepSensor(entry.entry_id, g) for g in entry.runtime_data.groepen)


class V2000GroepSensor(RestoreSensor):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:fire-alert"
    _attr_should_poll = False

    def __init__(self, entry_id: str, groep: dict[str, Any]) -> None:
        self._slug = groep["slug"]
        self._signal = signal_alarm(entry_id)
        self._attr_name = groep["naam"]
        self._attr_unique_id = f"{entry_id}_{groep['slug']}"
        self._attr_device_info = device_info(entry_id)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last.native_value
        if (state := await self.async_get_last_state()) is not None:
            self._attr_extra_state_attributes = dict(state.attributes)
        self.async_on_remove(async_dispatcher_connect(self.hass, self._signal, self._on_alarm))

    @callback
    def _on_alarm(self, ev: dict[str, Any]) -> None:
        if self._slug not in ev.get("groepen", []):
            return
        self._attr_native_value = dt_util.utcnow()
        self._attr_extra_state_attributes = dict(ev)
        self.async_write_ha_state()
