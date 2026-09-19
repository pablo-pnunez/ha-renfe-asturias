"""Integración Renfe Cercanías: paradas y rutas favoritas."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_ENTRY_TYPE,
    CONF_FLEET_SCAN_INTERVAL,
    CONF_ORIGIN,
    CONF_STATION,
    CONF_STOPS_SCAN_INTERVAL,
    DEFAULT_FLEET_SCAN_INTERVAL,
    DEFAULT_STOPS_SCAN_INTERVAL,
    DOMAIN,
    ENTRY_TYPE_ROUTE,
    ENTRY_TYPE_STOP,
    FLEET_COORDINATOR,
)
from .coordinator import RenfeFleetCoordinator, RenfeStopCoordinator
from .route_patterns import preload as preload_route_patterns
from .stations import preload as preload_stations

_LOGGER = logging.getLogger(__name__)

FRONTEND_SCRIPT_URL = f"/{DOMAIN}/renfe-route-card.js"
FRONTEND_SCRIPT_PATH = Path(__file__).parent / "www" / "renfe-route-card.js"
FRONTEND_REGISTERED_FLAG = "_frontend_registered"
CACHES_WARMED_FLAG = "_caches_warmed"


async def _async_warm_caches(hass: HomeAssistant) -> None:
    """Precarga (en un executor) los catálogos embebidos en JSON.

    stations.py y route_patterns.py cachean su contenido en memoria con
    lru_cache, pero la primera lectura hace E/S de disco síncrona; si esa
    primera llamada ocurriera desde el bucle de eventos (p.ej. durante el
    config flow), Home Assistant la detecta como bloqueante. Al forzarla
    aquí, en un hilo del executor, las llamadas posteriores solo leen la
    caché ya calentada.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(CACHES_WARMED_FLAG):
        return
    domain_data[CACHES_WARMED_FLAG] = True

    await hass.async_add_executor_job(preload_stations)
    await hass.async_add_executor_job(preload_route_patterns)


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Sirve la tarjeta Lovelace y la registra como recurso, si es posible.

    Es un patrón best-effort: si la API interna de recursos de Lovelace
    cambia entre versiones de Home Assistant, el fallo se registra mediante
    log y no bloquea la carga de la integración; el usuario siempre puede
    añadir el recurso manualmente (ver README).
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(FRONTEND_REGISTERED_FLAG):
        return
    domain_data[FRONTEND_REGISTERED_FLAG] = True

    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_SCRIPT_URL, str(FRONTEND_SCRIPT_PATH), True)]
        )
    except Exception:  # noqa: BLE001 - registro best-effort, no debe romper el setup
        _LOGGER.debug(
            "No se pudo registrar la ruta estática de la tarjeta (¿ya registrada?)",
            exc_info=True,
        )

    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None) if lovelace else None
    if resources is None:
        _LOGGER.debug(
            "Lovelace en modo YAML o no disponible aún: añade el recurso "
            "%s manualmente si quieres usar la tarjeta renfe-route-card",
            FRONTEND_SCRIPT_URL,
        )
        return

    try:
        already_added = any(
            item.get("url") == FRONTEND_SCRIPT_URL for item in resources.async_items()
        )
        if not already_added:
            await resources.async_create_item(
                {"res_type": "module", "url": FRONTEND_SCRIPT_URL}
            )
    except Exception:  # noqa: BLE001 - registro best-effort, no debe romper el setup
        _LOGGER.debug(
            "No se pudo registrar automáticamente el recurso de Lovelace",
            exc_info=True,
        )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Configuración a nivel de componente: registra la tarjeta del frontend."""
    await _async_warm_caches(hass)
    await _async_register_frontend(hass)
    return True


@dataclass
class RenfeEntryData:
    """Datos en tiempo de ejecución asociados a una config entry."""

    stop_coordinator: RenfeStopCoordinator
    fleet_coordinator: RenfeFleetCoordinator | None


def _platforms_for_entry(entry: ConfigEntry) -> list[Platform]:
    if entry.data[CONF_ENTRY_TYPE] == ENTRY_TYPE_ROUTE:
        return [Platform.SENSOR, Platform.DEVICE_TRACKER]
    return [Platform.SENSOR]


async def _async_get_fleet_coordinator(
    hass: HomeAssistant, scan_interval: int
) -> RenfeFleetCoordinator:
    """Devuelve el coordinador de flota compartido, creándolo si hace falta.

    `async_config_entry_first_refresh` solo puede llamarse una vez por
    coordinador (queda ligado a la config entry que lo crea); por eso el
    primer refresco se hace aquí, justo al crearlo, y nunca se repite para
    las siguientes rutas favoritas que reutilizan el mismo coordinador.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    coordinator: RenfeFleetCoordinator | None = domain_data.get(FLEET_COORDINATOR)
    if coordinator is None:
        coordinator = RenfeFleetCoordinator(hass, scan_interval)
        await coordinator.async_config_entry_first_refresh()
        domain_data[FLEET_COORDINATOR] = coordinator
    return coordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura una entrada (parada o ruta favorita) a partir del config flow."""
    await _async_warm_caches(hass)
    await _async_register_frontend(hass)

    entry_type = entry.data[CONF_ENTRY_TYPE]

    stops_interval = entry.options.get(
        CONF_STOPS_SCAN_INTERVAL, DEFAULT_STOPS_SCAN_INTERVAL
    )
    fleet_interval = entry.options.get(
        CONF_FLEET_SCAN_INTERVAL, DEFAULT_FLEET_SCAN_INTERVAL
    )

    station_code = (
        entry.data[CONF_STATION]
        if entry_type == ENTRY_TYPE_STOP
        else entry.data[CONF_ORIGIN]
    )

    stop_coordinator = RenfeStopCoordinator(hass, station_code, stops_interval)
    await stop_coordinator.async_config_entry_first_refresh()

    fleet_coordinator: RenfeFleetCoordinator | None = None
    if entry_type == ENTRY_TYPE_ROUTE:
        fleet_coordinator = await _async_get_fleet_coordinator(hass, fleet_interval)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = RenfeEntryData(
        stop_coordinator=stop_coordinator,
        fleet_coordinator=fleet_coordinator,
    )

    await hass.config_entries.async_forward_entry_setups(
        entry, _platforms_for_entry(entry)
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recarga la entrada cuando cambian las opciones."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Descarga una entrada de configuración."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, _platforms_for_entry(entry)
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)

        remaining_routes = [
            other
            for other in hass.config_entries.async_entries(DOMAIN)
            if other.entry_id != entry.entry_id
            and other.data[CONF_ENTRY_TYPE] == ENTRY_TYPE_ROUTE
        ]
        if not remaining_routes:
            hass.data[DOMAIN].pop(FLEET_COORDINATOR, None)

    return unloaded
