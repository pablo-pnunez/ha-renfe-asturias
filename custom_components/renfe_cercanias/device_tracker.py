"""Ubicación en tiempo real del tren de una ruta favorita."""
from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RenfeEntryData
from .api import TrainPosition
from .const import ATTRIBUTION, CONF_DESTINATION, CONF_ORIGIN, CONF_ROUTE_ID, DOMAIN
from .coordinator import RenfeFleetCoordinator, RenfeStopCoordinator
from .entity import build_device_info
from .route_patterns import PatternStop, get_pattern, get_route_segment
from .stations import get_station_name

NOT_RUNNING = "sin_circular"


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

    async def async_added_to_hass(self) -> None:
        """Refresca también cuando cambian las salidas (próximo tripId)."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._stop_coordinator.async_add_listener(
                self._handle_coordinator_update
            )
        )

    @property
    def _current_trip_id(self) -> str | None:
        for departure in self._stop_coordinator.data or []:
            if departure.destino_codigo == self._destination:
                return departure.trip_id
        return None

    @property
    def _train(self) -> TrainPosition | None:
        trip_id = self._current_trip_id
        return self.coordinator.get_train_by_trip_id(trip_id) if trip_id else None

    def _segment_index(self, station_code: str) -> int | None:
        for index, parada in enumerate(self._paradas):
            if parada["codigo"] == station_code:
                return index
        return None

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
    def location_name(self) -> str | None:
        # Si no hay ningún tren activo en esta ruta ahora mismo, fijamos un
        # estado explícito en vez de dejar la posición en blanco.
        return None if self._train else NOT_RUNNING

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {
            "paradas": self._paradas,
            "color": self._color,
            "linea": self._linea,
            "origen": get_station_name(self._origin),
            "destino": get_station_name(self._destination),
        }

        train = self._train
        if train is None:
            attrs["en_circulacion"] = False
            attrs["indice_estacion_actual"] = None
            attrs["indice_estacion_siguiente"] = None
            return attrs

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
                "porcentaje_avance": train.porcentaje_avance,
                "via": train.via,
                "accesible": train.accesible,
            }
        )
        return attrs
