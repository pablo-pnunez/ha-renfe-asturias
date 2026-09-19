"""Ubicación en tiempo real del tren de una ruta favorita."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RenfeEntryData
from .api import Departure, TrainPosition, VehicleStatus
from .const import (
    ATTRIBUTION,
    CONF_DESTINATION,
    CONF_ORIGIN,
    CONF_ROUTE_ID,
    DOMAIN,
    VEHICLE_STATUS_IN_TRANSIT,
    VEHICLE_STATUS_INCOMING,
    VEHICLE_STATUS_STOPPED,
)
from .coordinator import RenfeFleetCoordinator, RenfeStopCoordinator
from .entity import build_device_info
from .route_patterns import (
    PatternStop,
    get_pattern,
    get_route_segment,
    get_travel_time_min,
)
from .stations import get_station_name, get_stations_by_code

NOT_RUNNING = "sin_circular"

# % de avance asumido cuando el GTFS-RT indica que el tren está llegando a
# la parada (no da un porcentaje exacto, pero "llegando" implica ya casi al
# final del tramo).
INCOMING_PROGRESS_PCT = 90.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en línea recta (km) entre dos coordenadas."""
    earth_radius_km = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * earth_radius_km * math.asin(math.sqrt(a))


def _parse_legacy_progress(value: str | None) -> float | None:
    """Intenta interpretar el campo `porAvanc` (sin documentar) del visor clásico."""
    if not value:
        return None
    try:
        return max(0.0, min(100.0, float(value)))
    except ValueError:
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crea el device_tracker del tren para esta ruta favorita."""
    entry_data: RenfeEntryData = hass.data[DOMAIN][entry.entry_id]
    if entry_data.fleet_coordinator is None:
        return

    async_add_entities(
        [
            RenfeRouteTrainTracker(
                entry_data.fleet_coordinator, entry_data.stop_coordinator, entry
            )
        ]
    )


class RenfeRouteTrainTracker(CoordinatorEntity[RenfeFleetCoordinator], TrackerEntity):
    """Representa la posición GPS del tren que cubre una ruta favorita.

    La ruta favorita se define por una estación de origen (donde se consultan
    las salidas) y un destino. El vínculo con la posición GPS del tren en la
    flota se hace a través del `tripId` de la próxima salida hacia ese
    destino, ya que el origen/destino de un tren en la flota son siempre los
    extremos completos de su línea y no coinciden necesariamente con las
    paradas elegidas por el usuario.

    Además expone el itinerario completo de paradas entre origen y destino
    (obtenido del GTFS oficial de Renfe) y el índice de la estación actual y
    siguiente dentro de ese itinerario, pensado para que una tarjeta Lovelace
    pueda dibujar la ruta completa con la posición del tren en tiempo real.
    """

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True
    _attr_translation_key = "train_position"
    _attr_icon = "mdi:train"

    def __init__(
        self,
        fleet_coordinator: RenfeFleetCoordinator,
        stop_coordinator: RenfeStopCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(fleet_coordinator)
        self._stop_coordinator = stop_coordinator
        self._origin = entry.data[CONF_ORIGIN]
        self._destination = entry.data[CONF_DESTINATION]
        self._route_id: str = entry.data.get(CONF_ROUTE_ID, "")
        self._attr_unique_id = (
            f"route_{self._origin}_{self._destination}_train_position"
        )
        self._attr_device_info = build_device_info(entry)
        pattern = get_pattern(self._route_id)
        self._paradas: list[PatternStop] = (
            get_route_segment(self._route_id, self._origin, self._destination) or []
        )
        self._color: str | None = pattern["color"] if pattern else None
        self._linea: str = pattern["linea"] if pattern else ""

        self._offsets: dict[str, int] = (
            {p["codigo"]: p["offset_min"] for p in pattern["paradas"]}
            if pattern
            else {}
        )
        self._origin_offset: int | None = self._offsets.get(self._origin)
        self._destination_offset: int | None = self._offsets.get(self._destination)

    async def async_added_to_hass(self) -> None:
        """Refresca también cuando cambian las salidas (próximo tripId)."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._stop_coordinator.async_add_listener(
                self._handle_coordinator_update
            )
        )

    @property
    def state(self) -> str | None:
        # Tanto la propiedad location_name como el atributo
        # _attr_location_name están deprecados en TrackerEntity; para fijar
        # un estado explícito cuando no hay tren activo se sobrescribe el
        # estado final directamente, delegando en la clase base (lat/lon
        # frente a zonas) el resto de casos.
        if self._train is None:
            return NOT_RUNNING
        return super().state

    @property
    def _current_departure(self) -> Departure | None:
        # No se puede vincular el tren comparando `destino_codigo` con
        # nuestro destino: muchas rutas favoritas terminan en una parada
        # intermedia del trayecto real del tren (p.ej. la línea C2 de
        # Asturias es San Juan de Nieva↔El Entrego y Oviedo es una parada
        # intermedia, nunca el destino final declarado). En su lugar se
        # comprueba la línea y que el tren vaya en la dirección correcta:
        # su destino final debe llegar, como mínimo, hasta la parada que
        # elegimos como destino (offset GTFS mayor o igual al nuestro).
        #
        # El GTFS oficial de Renfe no siempre modela el trayecto completo de
        # una línea como una sola ruta (esa misma C2, en el GTFS estático,
        # no llega más allá de Oviedo aunque el servicio real continúe hasta
        # San Juan de Nieva); si el destino real del tren ni siquiera
        # aparece en nuestro patrón, se asume que el trayecto se extiende
        # más allá de lo que el GTFS cubre y que igualmente pasa por nuestro
        # destino, en vez de descartarlo.
        if self._destination_offset is None:
            return None

        for departure in self._stop_coordinator.data or []:
            if departure.linea != self._linea:
                continue
            dest_offset = self._offsets.get(departure.destino_codigo)
            if dest_offset is None or dest_offset >= self._destination_offset:
                return departure
        return None

    @property
    def _train(self) -> TrainPosition | None:
        # La lista de "próximas salidas" de la estación deja de incluir un
        # tren en cuanto sale de origen, así que un tren que ya lleva un
        # buen tramo recorrido no se encuentra por ahí. Se busca primero
        # directamente en la flota completa: cualquier tren de nuestra
        # línea cuya posición actual (estación actual o siguiente) esté
        # dentro de nuestro tramo y avance en la dirección correcta. Esto
        # cubre tanto un tren recién salido como uno ya en tránsito
        # avanzado.
        for train in (self.coordinator.data.trains if self.coordinator.data else []):
            if train.linea == self._linea and self._matches_direction(train):
                return train

        # Si ningún tren de la flota está todavía en nuestro tramo, se cae
        # al tripId de la próxima salida prevista (por si ya circula pero
        # con datos de posición aún no actualizados).
        departure = self._current_departure
        return (
            self.coordinator.get_train_by_trip_id(departure.trip_id)
            if departure
            else None
        )

    def _matches_direction(self, train: TrainPosition) -> bool:
        idx_actual = self._segment_index(train.estacion_actual_codigo)
        idx_siguiente = self._segment_index(train.estacion_siguiente_codigo)
        if idx_actual is not None and idx_siguiente is not None:
            return idx_siguiente >= idx_actual
        return idx_actual is not None or idx_siguiente is not None

    @property
    def _hora_salida_origen(self) -> datetime | None:
        departure = self._current_departure
        if departure is not None:
            return departure.hora_salida

        # El tren ya circula pero ya no aparece en "próximas salidas": se
        # estima la hora de salida del origen a partir de la ETA a la
        # siguiente parada, retrocediendo los minutos programados (GTFS)
        # entre el origen y esa parada.
        train = self._train
        if train is None or train.hora_llegada_siguiente is None:
            return None
        idx_siguiente = self._segment_index(train.estacion_siguiente_codigo)
        if idx_siguiente is None or not self._paradas:
            return None
        delta_min = self._paradas[idx_siguiente]["offset_min"] - self._paradas[0]["offset_min"]
        return train.hora_llegada_siguiente - timedelta(minutes=delta_min)

    @property
    def _hora_llegada_destino(self) -> datetime | None:
        hora_salida = self._hora_salida_origen
        if hora_salida is None:
            return None
        travel_min = get_travel_time_min(
            self._route_id, self._origin, self._destination
        )
        if travel_min is None:
            return None
        return hora_salida + timedelta(minutes=travel_min)

    def _paradas_con_hora(self) -> list[dict]:
        """Itinerario del tramo con la hora estimada de paso por cada parada.

        La hora se calcula a partir de la hora de salida real/estimada del
        origen más los minutos programados (GTFS) entre paradas; es una
        estimación (asume que el recorrido sigue el horario programado desde
        ese punto), no una predicción en tiempo real por parada.
        """
        if not self._paradas:
            return []

        hora_salida = self._hora_salida_origen
        offset_origen = self._paradas[0]["offset_min"]

        paradas_con_hora = []
        for parada in self._paradas:
            hora_estimada = None
            if hora_salida is not None:
                delta = parada["offset_min"] - offset_origen
                hora_estimada = (hora_salida + timedelta(minutes=delta)).isoformat()
            paradas_con_hora.append(
                {
                    "codigo": parada["codigo"],
                    "nombre": parada["nombre"],
                    "hora_estimada": hora_estimada,
                }
            )
        return paradas_con_hora

    def _segment_index(self, station_code: str) -> int | None:
        for index, parada in enumerate(self._paradas):
            if parada["codigo"] == station_code:
                return index
        return None

    def _compute_progress_pct(self, train: TrainPosition) -> float | None:
        """Calcula el % de avance (0-100) entre la estación actual y la siguiente.

        Usa el `currentStatus` GTFS-RT (`vehicle_positions.json`), un dato
        estandarizado y mucho más fiable que el campo `porAvanc` (sin
        documentar) del visor clásico de Renfe: si el tren está parado, el
        avance es 0%; si está en tránsito, se calcula geométricamente la
        proporción recorrida entre ambas paradas a partir de sus
        coordenadas. Si no hay estado GTFS-RT disponible para este viaje, se
        recurre al campo clásico como último recurso.
        """
        status: VehicleStatus | None = self.coordinator.get_status_by_trip_id(
            train.trip_id
        )
        if status is not None:
            if status.current_status == VEHICLE_STATUS_STOPPED:
                return 0.0
            if status.current_status == VEHICLE_STATUS_INCOMING:
                return INCOMING_PROGRESS_PCT
            if status.current_status == VEHICLE_STATUS_IN_TRANSIT:
                geo_pct = self._geometric_progress_pct(train)
                if geo_pct is not None:
                    return geo_pct

        return _parse_legacy_progress(train.porcentaje_avance)

    def _geometric_progress_pct(self, train: TrainPosition) -> float | None:
        idx_actual = self._segment_index(train.estacion_actual_codigo)
        idx_siguiente = self._segment_index(train.estacion_siguiente_codigo)
        if idx_actual is None or idx_siguiente is None:
            return None

        stations = get_stations_by_code()
        actual = stations.get(self._paradas[idx_actual]["codigo"])
        siguiente = stations.get(self._paradas[idx_siguiente]["codigo"])
        if not actual or not siguiente:
            return None

        total_km = _haversine_km(actual["lat"], actual["lon"], siguiente["lat"], siguiente["lon"])
        if total_km <= 0:
            return None

        recorrido_km = _haversine_km(
            actual["lat"], actual["lon"], train.latitud, train.longitud
        )
        return max(0.0, min(100.0, recorrido_km / total_km * 100))

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        train = self._train
        return train.latitud if train else None

    @property
    def longitude(self) -> float | None:
        train = self._train
        return train.longitud if train else None

    @property
    def extra_state_attributes(self) -> dict:
        hora_salida_origen = self._hora_salida_origen
        hora_llegada_destino = self._hora_llegada_destino
        attrs: dict = {
            "paradas": self._paradas_con_hora(),
            "color": self._color,
            "linea": self._linea,
            "origen": get_station_name(self._origin),
            "destino": get_station_name(self._destination),
            "hora_salida_origen": hora_salida_origen.isoformat()
            if hora_salida_origen
            else None,
            "hora_llegada_destino": hora_llegada_destino.isoformat()
            if hora_llegada_destino
            else None,
        }

        train = self._train
        if train is None:
            attrs["en_circulacion"] = False
            attrs["indice_estacion_actual"] = None
            attrs["indice_estacion_siguiente"] = None
            return attrs

        status = self.coordinator.get_status_by_trip_id(train.trip_id)
        attrs.update(
            {
                "en_circulacion": True,
                "tren_id": train.tren_id,
                "estacion_actual": get_station_name(train.estacion_actual_codigo),
                "estacion_siguiente": get_station_name(
                    train.estacion_siguiente_codigo
                ),
                "indice_estacion_actual": self._segment_index(
                    train.estacion_actual_codigo
                ),
                "indice_estacion_siguiente": self._segment_index(
                    train.estacion_siguiente_codigo
                ),
                "hora_llegada_siguiente": train.hora_llegada_siguiente.isoformat()
                if train.hora_llegada_siguiente
                else None,
                "retraso_min": train.retraso_min,
                "porcentaje_avance": self._compute_progress_pct(train),
                "estado_gtfs_rt": status.current_status if status else None,
                "via": train.via,
                "accesible": train.accesible,
            }
        )
        return attrs
