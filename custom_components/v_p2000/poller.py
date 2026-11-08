"""AlarmeringDroid poller: one request for all capcodes, fires v_p2000_alarm per new page."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

import aiohttp

from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    API_URL,
    DOMAIN,
    EVENT_ALARM,
    MAX_BACKOFF,
    MAX_RETRY_AFTER,
    MAX_SEEN,
    OFFLINE_AFTER,
    RECENT_MINUTES,
    REQUEST_TIMEOUT,
    SLOW_FACTOR,
    USER_AGENT,
    signal_alarm,
    signal_status,
)
from .logic import api_capcode, find_matches, item_time

_LOGGER = logging.getLogger(__name__)


def build_url(groepen: list[dict[str, Any]]) -> str:
    codes = sorted({api_capcode(c) for g in groepen for c in g["capcodes"]})
    return API_URL + quote(json.dumps({"capcodes": codes}, separators=(",", ":")))


class _ApiError(Exception):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class V2000Poller:
    """Polls AlarmeringDroid on a fixed cadence, with backoff while it is failing."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, groepen: list[dict[str, Any]], interval: int
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.groepen = groepen
        self.interval = interval
        self.url = build_url(groepen)
        self.session = async_get_clientsession(hass)
        self.store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.seen")
        self.seen: dict[str, None] = {}  # insertion-ordered set of item ids
        self.primed = False
        self.failures = 0
        self.connected: bool | None = None
        self.last_error: str | None = None
        self.last_ok: datetime | None = None
        self.status_since: datetime | None = None
        self._started = time.monotonic()
        self._last_ok_mono: float | None = None
        self._unsub: CALLBACK_TYPE | None = None
        self._stopped = False
        self._job = HassJob(self._on_timer, f"{DOMAIN} poll", cancel_on_shutdown=True)

    async def async_start(self) -> None:
        stored = await self.store.async_load() or {}
        for iid in stored.get("seen", []):
            self.seen[str(iid)] = None
        _LOGGER.info(
            "V-P2000 gestart: %s groep(en), poll elke %ss, %s bekende meldingen",
            len(self.groepen),
            self.interval,
            len(self.seen),
        )
        self.hass.async_create_background_task(self._poll(), f"{DOMAIN} first poll")

    @callback
    def async_stop(self) -> None:
        self._stopped = True
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _schedule(self, delay: float) -> None:
        if self._stopped:
            return
        self._unsub = async_call_later(self.hass, max(delay, 0.5), self._job)

    @callback
    def _on_timer(self, _now: datetime) -> None:
        self._unsub = None
        self.hass.async_create_background_task(self._poll(), f"{DOMAIN} poll")

    async def _fetch(self) -> list[Any]:
        try:
            async with self.session.get(
                self.url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                allow_redirects=False,
            ) as resp:
                if resp.status in (429, 503):
                    retry = resp.headers.get("Retry-After", "")
                    raise _ApiError(
                        f"HTTP {resp.status}",
                        float(retry) if retry.isdigit() else None,
                    )
                if resp.status != 200:
                    raise _ApiError(f"HTTP {resp.status}")
                data = await resp.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise _ApiError(f"geen antwoord binnen {REQUEST_TIMEOUT}s") from err
        except (aiohttp.ClientError, ValueError) as err:
            raise _ApiError(str(err) or type(err).__name__) from err
        meldingen = data.get("meldingen") if isinstance(data, dict) else None
        if not isinstance(meldingen, list):
            raise _ApiError("onverwacht antwoord")
        return meldingen

    async def _poll(self) -> None:
        t0 = time.monotonic()
        delay: float = self.interval
        try:
            meldingen = await self._fetch()
        except _ApiError as err:
            self.failures += 1
            self.last_error = str(err)
            delay = min(self.interval * 2 ** min(self.failures - 1, 4), MAX_BACKOFF)
            if err.retry_after:
                delay = min(max(err.retry_after, delay), MAX_RETRY_AFTER)
            log = _LOGGER.warning if self.failures == 1 else _LOGGER.debug
            log("V-P2000: AlarmeringDroid fout (%s); volgende poging over %.0fs", err, delay)
        except Exception:  # never let the poll loop die
            self.failures += 1
            self.last_error = "interne fout"
            _LOGGER.exception("V-P2000: onverwachte fout tijdens poll")
        else:
            if self.failures:
                _LOGGER.warning("V-P2000: AlarmeringDroid weer bereikbaar na %s fout(en)", self.failures)
            self.failures = 0
            self._last_ok_mono = time.monotonic()
            self.last_ok = dt_util.utcnow()
            try:
                self._process(meldingen, round(time.monotonic() - t0, 2))
            except Exception:
                _LOGGER.exception("V-P2000: fout bij verwerken van meldingen")
            elapsed = time.monotonic() - t0
            delay = max(self.interval - elapsed, elapsed * SLOW_FACTOR)
        finally:
            self._update_status()
            self._schedule(delay)

    def _process(self, meldingen: list[Any], duur: float) -> None:
        now = dt_util.now()
        changed = False
        nieuw = 0
        for ev in find_matches(meldingen, self.groepen):
            if ev["id"] in self.seen:
                continue
            self.seen[ev["id"]] = None
            changed = True
            if not self.primed:
                t = item_time(ev, now)
                if t is None or now - t > timedelta(minutes=RECENT_MINUTES):
                    continue  # old melding, first seen after a (re)start
            nieuw += 1
            ev["request_duur_s"] = duur
            self.hass.bus.async_fire(EVENT_ALARM, ev)
            async_dispatcher_send(self.hass, signal_alarm(self.entry_id), ev)
            _LOGGER.warning(
                "V-P2000: ALARM %s id=%s (%s) %s", ev["groep_naam"], ev["id"], ev["tijd"], ev["melding"]
            )
        _LOGGER.debug("V-P2000: poll ok in %.2fs, %s meldingen, %s nieuw alarm", duur, len(meldingen), nieuw)
        self.primed = True
        if changed:
            while len(self.seen) > MAX_SEEN:
                self.seen.pop(next(iter(self.seen)))
            self.store.async_delay_save(lambda: {"seen": list(self.seen)}, 5)

    @callback
    def _update_status(self) -> None:
        ref = self._last_ok_mono if self._last_ok_mono is not None else self._started
        if self.failures == 0:
            connected = True
        elif time.monotonic() - ref >= OFFLINE_AFTER:
            connected = False
        else:
            connected = self.connected  # short hiccup: keep the current status
        if connected != self.connected:
            self.connected = connected
            self.status_since = dt_util.utcnow()
            if not connected:
                _LOGGER.error(
                    "V-P2000: al %ss geen verbinding met AlarmeringDroid (%s), alarmen komen niet door",
                    OFFLINE_AFTER,
                    self.last_error,
                )
            async_dispatcher_send(self.hass, signal_status(self.entry_id))
