"""Sensores de próximas salidas para paradas y rutas favoritas."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RenfeEntryData
from .api import Departure
from .const import (
    CONF_DESTINATION,
    CONF_ENTRY_TYPE,
    CONF_NUM_DEPARTURES,
    CONF_ORIGIN,
    CONF_STATION,
    DEFAULT_NUM_DEPARTURES,
    DOMAIN,
    ENTRY_TYPE_ROUTE,
)
from .entity import RenfeStopEntity
from .stations import get_station_name


def _departure_attrs(departure: Departure) -> dict:
    return {
        "linea": departure.linea,
        "destino": departure.destino_nombre,
        "destino_codigo": departure.destino_codigo,
        "hora_salida": departure.hora_salida.isoformat()
        if departure.hora_salida
        else None,
        "hora_salida_planificada": departure.hora_salida_planificada.isoformat()
        if departure.hora_salida_planificada
        else None,
        "retraso_min": departure.retraso_min,
        "via": departure.via,
        "accesible": departure.accesible,
        "tren_id": departure.tren_id,
    }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea el sensor de próximas salidas para esta entrada."""
    entry_data: RenfeEntryData = hass.data[DOMAIN][entry.entry_id]
    num_departures = entry.options.get(CONF_NUM_DEPARTURES, DEFAULT_NUM_DEPARTURES)

    if entry.data[CONF_ENTRY_TYPE] == ENTRY_TYPE_ROUTE:
        async_add_entities(
            [
                RenfeRouteDepartureSensor(
                    entry_data.stop_coordinator,
                    entry,
                    destination=entry.data[CONF_DESTINATION],
                    num_departures=num_departures,
                )
            ]
        )
    else:
        async_add_entities(
            [
                RenfeStopDepartureSensor(
                    entry_data.stop_coordinator,
                    entry,
                    num_departures=num_departures,
                )
            ]
        )


class RenfeStopDepartureSensor(RenfeStopEntity, SensorEntity):
    """Próxima salida desde una parada favorita, con todas las líneas."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "next_departure"
    _attr_icon = "mdi:train"

    def __init__(self, coordinator, entry: ConfigEntry, num_departures: int) -> None:
        super().__init__(coordinator, entry)
        self._num_departures = num_departures
        station_code = entry.data[CONF_STATION]
        self._attr_unique_id = f"stop_{station_code}_next_departure"

    @property
    def _departures(self) -> list[Departure]:
        return self.coordinator.data or []

    @property
    def native_value(self) -> datetime | None:
        departures = self._departures
        return departures[0].hora_salida if departures else None

    @property
    def extra_state_attributes(self) -> dict:
        departures = self._departures[: self._num_departures]
        first = departures[0] if departures else None
        attrs: dict = {"salidas": [_departure_attrs(dep) for dep in departures]}
        if first is not None:
            attrs.update(_departure_attrs(first))
        return attrs


class RenfeRouteDepartureSensor(RenfeStopEntity, SensorEntity):
    """Próxima salida de una ruta favorita (origen -> destino concreto)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "next_departure"
    _attr_icon = "mdi:train-car"

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        destination: str,
        num_departures: int,
    ) -> None:
        super().__init__(coordinator, entry)
        self._destination = destination
        self._num_departures = num_departures
        origin = entry.data.get(CONF_ORIGIN)
        self._attr_unique_id = f"route_{origin}_{destination}_next_departure"

    @property
    def _departures(self) -> list[Departure]:
        return [
            dep
            for dep in (self.coordinator.data or [])
            if dep.destino_codigo == self._destination
        ]

    @property
    def native_value(self) -> datetime | None:
        departures = self._departures
        return departures[0].hora_salida if departures else None

    @property
    def extra_state_attributes(self) -> dict:
        departures = self._departures[: self._num_departures]
        first = departures[0] if departures else None
        attrs: dict = {
            "destino": get_station_name(self._destination),
            "salidas": [_departure_attrs(dep) for dep in departures],
        }
        if first is not None:
            attrs.update(_departure_attrs(first))
        return attrs
