"""Sensores de próximas salidas y avisos de servicio para paradas y rutas favoritas."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RenfeEntryData
from .api import Departure, ServiceAlert
from .const import (
    ATTRIBUTION,
    CONF_DESTINATION,
    CONF_ENTRY_TYPE,
    CONF_NUM_DEPARTURES,
    CONF_ORIGIN,
    CONF_ROUTE_ID,
    CONF_STATION,
    DEFAULT_NUM_DEPARTURES,
    DOMAIN,
    ENTRY_TYPE_ROUTE,
    ENTRY_TYPE_STOP,
)
from .coordinator import RenfeAlertsCoordinator
from .entity import RenfeStopEntity, build_device_info
from .route_patterns import get_pattern, get_route_ids_for_line
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

    entities: list[SensorEntity] = []
    if entry.data[CONF_ENTRY_TYPE] == ENTRY_TYPE_ROUTE:
        entities.append(
            RenfeRouteDepartureSensor(
                entry_data.stop_coordinator,
                entry,
                destination=entry.data[CONF_DESTINATION],
                num_departures=num_departures,
            )
        )
    else:
        entities.append(
            RenfeStopDepartureSensor(
                entry_data.stop_coordinator,
                entry,
                num_departures=num_departures,
            )
        )

    entities.append(RenfeAlertsSensor(entry_data.alerts_coordinator, entry))
    async_add_entities(entities)


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


class RenfeAlertsSensor(CoordinatorEntity[RenfeAlertsCoordinator], SensorEntity):
    """Avisos de servicio (GTFS-RT) que afectan a una parada o ruta favorita.

    Para una parada se buscan avisos que mencionen explícitamente su código
    de estación; para una ruta, avisos de cualquiera de los `route_id`
    (ambos sentidos) de su misma línea, ya que Renfe suele publicarlos a
    nivel de línea completa.
    """

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_translation_key = "service_alerts"
    _attr_icon = "mdi:alert-circle-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "avisos"

    def __init__(
        self, coordinator: RenfeAlertsCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_device_info = build_device_info(entry)

        if entry.data[CONF_ENTRY_TYPE] == ENTRY_TYPE_STOP:
            station_code = entry.data[CONF_STATION]
            self._attr_unique_id = f"stop_{station_code}_service_alerts"
            self._station_code: str | None = station_code
            self._route_ids: set[str] = set()
        else:
            origin = entry.data[CONF_ORIGIN]
            destination = entry.data[CONF_DESTINATION]
            self._attr_unique_id = f"route_{origin}_{destination}_service_alerts"
            self._station_code = None
            route_id = entry.data.get(CONF_ROUTE_ID, "")
            pattern = get_pattern(route_id)
            self._route_ids = (
                get_route_ids_for_line(pattern["linea"], pattern["nucleo"])
                if pattern
                else set()
            )

    @property
    def _alerts(self) -> list[ServiceAlert]:
        if self._station_code is not None:
            return self.coordinator.get_alerts_for_stop(self._station_code)
        return self.coordinator.get_alerts_for_routes(self._route_ids)

    @property
    def native_value(self) -> int:
        return len(self._alerts)

    @property
    def extra_state_attributes(self) -> dict:
        return {"avisos": [alert.texto for alert in self._alerts]}
