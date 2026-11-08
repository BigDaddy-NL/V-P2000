"""V-P2000: fast P2000 alarms in Home Assistant via AlarmeringDroid.

Polls all configured capcodes in one request and fires the event
`v_p2000_alarm` for every new page (main melding or subitem) that contains
one of them. Trigger your automations on that event.
"""

from __future__ import annotations

import time
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_GROEPEN,
    CONF_GROEPEN_TEKST,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_ALARM,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .poller import V2000Poller

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

type V2000ConfigEntry = ConfigEntry[V2000Poller]

# Optional YAML, imported once into a config entry (UI setup is preferred).
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                ),
                vol.Required(CONF_GROEPEN): vol.Schema(
                    {cv.string: vol.All(cv.ensure_list, [cv.string])}
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

TEST_SCHEMA = vol.Schema(
    {
        vol.Required("melding"): cv.string,
        vol.Optional("groep"): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def _test_alarm(call: ServiceCall) -> None:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError("V-P2000 is niet ingesteld")
        groepen: list[dict[str, Any]] = entries[0].runtime_data.groepen
        wanted = call.data.get("groep")
        groep = next((g for g in groepen if wanted in (None, g["slug"], g["naam"])), None)
        if groep is None:
            raise ServiceValidationError(
                f"Onbekende groep '{wanted}'. Kies uit: {', '.join(g['slug'] for g in groepen)}"
            )
        melding = call.data["melding"]
        hass.bus.async_fire(
            EVENT_ALARM,
            {
                "groep": groep["slug"],
                "groep_naam": groep["naam"],
                "groepen": [groep["slug"]],
                "capcodes": list(groep["capcodes"]),
                "id": f"test-{int(time.time())}",
                "groep_id": "",
                "melding": melding,
                "tekstmelding": melding,
                "bron": "test",
            },
            context=call.context,
        )

    hass.services.async_register(DOMAIN, "test_alarm", _test_alarm, schema=TEST_SCHEMA)

    if DOMAIN in config:
        conf = config[DOMAIN]
        tekst = "\n".join(
            f"{naam}: {', '.join(str(c) for c in codes)}"
            for naam, codes in conf[CONF_GROEPEN].items()
        )
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data={CONF_GROEPEN_TEKST: tekst, CONF_SCAN_INTERVAL: conf[CONF_SCAN_INTERVAL]},
            )
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: V2000ConfigEntry) -> bool:
    poller = V2000Poller(
        hass,
        entry.entry_id,
        entry.options[CONF_GROEPEN],
        int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
    )
    entry.runtime_data = poller
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await poller.async_start()
    entry.async_on_unload(poller.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: V2000ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Forget the stored 'seen' ids when the integration is removed."""
    await Store(hass, 1, f"{DOMAIN}.seen").async_remove()


async def _async_reload(hass: HomeAssistant, entry: V2000ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
