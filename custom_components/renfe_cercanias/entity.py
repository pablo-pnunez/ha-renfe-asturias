"""Entidad base compartida por las plataformas de la integración."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTRIBUTION,
    CONF_DESTINATION,
    CONF_ENTRY_TYPE,
    CONF_ORIGIN,
    CONF_STATION,
    DOMAIN,
    ENTRY_TYPE_ROUTE,
    MANUFACTURER,
)
from .coordinator import RenfeStopCoordinator
from .stations import get_stations_by_code


def build_label(entry: ConfigEntry) -> str:
    """Nombre legible de una parada o ruta favorita, p.ej. para notificaciones."""
    stations = get_stations_by_code()

    if entry.data[CONF_ENTRY_TYPE] == ENTRY_TYPE_ROUTE:
        origin = entry.data[CONF_ORIGIN]
        destination = entry.data[CONF_DESTINATION]
        origin_name = stations.get(origin, {}).get("nombre", origin)
        dest_name = stations.get(destination, {}).get("nombre", destination)
        return f"{origin_name} → {dest_name}"

    station_code = entry.data[CONF_STATION]
    return stations.get(station_code, {}).get("nombre", station_code)


def build_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Construye el dispositivo asociado a una parada o ruta favorita."""
    label = build_label(entry)

    if entry.data[CONF_ENTRY_TYPE] == ENTRY_TYPE_ROUTE:
        origin = entry.data[CONF_ORIGIN]
        destination = entry.data[CONF_DESTINATION]
        return DeviceInfo(
            identifiers={(DOMAIN, f"route_{origin}_{destination}")},
            name=f"Cercanías {label}",
            manufacturer=MANUFACTURER,
            model="Ruta favorita",
        )

    station_code = entry.data[CONF_STATION]
    return DeviceInfo(
        identifiers={(DOMAIN, f"stop_{station_code}")},
        name=f"Cercanías {label}",
        manufacturer=MANUFACTURER,
        model="Parada favorita",
    )


class RenfeStopEntity(CoordinatorEntity[RenfeStopCoordinator]):
    """Entidad base ligada al coordinador de salidas de una estación."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: RenfeStopCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = build_device_info(entry)
