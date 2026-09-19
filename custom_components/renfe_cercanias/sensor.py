"""Sensores de próximas salidas y avisos de servicio para paradas y rutas favoritas."""
from __future__ import annotations

from datetime import datetime, timedelta

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
from .route_patterns import get_pattern, get_route_ids_for_line, get_travel_time_min
from .stations import get_station_name


def _departure_attrs(
    departure: Departure,
    origin_code: str,
    destination_code: str | None = None,
    destination_name: str | None = None,
) -> dict:
    """Atributos de una salida real.

    Para una parada favorita, `destination_code`/`destination_name` se dejan
    en blanco y se usa el destino final real del tren. Para una ruta
    favorita a una parada intermedia (p.ej. la línea C2 de Asturias es San
    Juan de Nieva↔El Entrego y Oviedo es una parada intermedia, nunca el
    destino final declarado), el llamador los fija a la parada elegida por
    el usuario, para que la hora de llegada estimada sea la de esa parada y
    no la del final de trayecto real del tren.
    """
    dest_code = destination_code or departure.destino_codigo
    dest_name = destination_name or departure.destino_nombre

    hora_llegada_estimada = None
    if departure.hora_salida is not None:
        travel_min = get_travel_time_min(departure.route_id, origin_code, dest_code)
        if travel_min is not None:
            hora_llegada_estimada = (
                departure.hora_salida + timedelta(minutes=travel_min)
            ).isoformat()

    return {
        "linea": departure.linea,
        "destino": dest_name,
        "destino_codigo": dest_code,
        "hora_salida": departure.hora_salida.isoformat()
        if departure.hora_salida
        else None,
        "hora_salida_planificada": departure.hora_salida_planificada.isoformat()
        if departure.hora_salida_planificada
        else None,
        "hora_llegada_estimada": hora_llegada_estimada,
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
        self._station_code = entry.data[CONF_STATION]
        self._attr_unique_id = f"stop_{self._station_code}_next_departure"

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
        attrs: dict = {
            "salidas": [
                _departure_attrs(dep, self._station_code) for dep in departures
            ]
        }
        if first is not None:
            attrs.update(_departure_attrs(first, self._station_code))
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
        self._origin = entry.data.get(CONF_ORIGIN)
        self._attr_unique_id = f"route_{self._origin}_{destination}_next_departure"

        route_id = entry.data.get(CONF_ROUTE_ID, "")
        pattern = get_pattern(route_id)
        self._linea = pattern["linea"] if pattern else ""
        # Offsets del patrón de referencia elegido al configurar la ruta; se
        # usa siempre este mismo patrón (no el de cada salida real) para que
        # las comparaciones sean consistentes entre sí.
        self._offsets: dict[str, int] = (
            {p["codigo"]: p["offset_min"] for p in pattern["paradas"]}
            if pattern
            else {}
        )
        self._destination_offset = self._offsets.get(destination)

    @property
    def _departures(self) -> list[Departure]:
        # No se filtra por destino_codigo exacto: muchas rutas favoritas
        # terminan en una parada intermedia del trayecto real del tren (ver
        # nota en device_tracker.RenfeRouteTrainTracker._current_departure).
        # Basta con que la línea coincida y el tren llegue, como mínimo,
        # hasta nuestra parada de destino (offset GTFS mayor o igual, dentro
        # de nuestro propio patrón de referencia).
        if self._destination_offset is None:
            return []
        result = []
        for dep in self.coordinator.data or []:
            if dep.linea != self._linea:
                continue
            dest_offset = self._offsets.get(dep.destino_codigo)
            if dest_offset is not None and dest_offset >= self._destination_offset:
                result.append(dep)
        return result

    @property
    def native_value(self) -> datetime | None:
        departures = self._departures
        return departures[0].hora_salida if departures else None

    @property
    def extra_state_attributes(self) -> dict:
        destination_name = get_station_name(self._destination)
        departures = self._departures[: self._num_departures]
        first = departures[0] if departures else None
        attrs: dict = {
            "destino": destination_name,
            "salidas": [
                _departure_attrs(dep, self._origin, self._destination, destination_name)
                for dep in departures
            ],
        }
        if first is not None:
            attrs.update(
                _departure_attrs(
                    first, self._origin, self._destination, destination_name
                )
            )
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
