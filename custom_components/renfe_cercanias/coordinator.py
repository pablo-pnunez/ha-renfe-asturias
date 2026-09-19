"""Coordinadores de actualización de datos para Renfe Cercanías."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    Departure,
    RenfeApiError,
    ServiceAlert,
    TrainPosition,
    VehicleStatus,
    async_get_alerts,
    async_get_departures,
    async_get_fleet,
    async_get_vehicle_statuses,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class FleetSnapshot:
    """Combina la flota clásica con el estado GTFS-RT (más preciso) de cada tren."""

    trains: list[TrainPosition]
    statuses: dict[str, VehicleStatus]


class RenfeFleetCoordinator(DataUpdateCoordinator[FleetSnapshot]):
    """Coordinador compartido con la posición de todos los trenes de Cercanías de España.

    Se comparte entre todas las rutas favoritas, sin importar su región: el
    `tripId` de un tren es único a nivel nacional, así que no hace falta
    filtrar por núcleo para poder localizarlo.
    """

    def __init__(self, hass: HomeAssistant, scan_interval: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_fleet",
            update_interval=timedelta(seconds=scan_interval),
        )
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> FleetSnapshot:
        try:
            trains, statuses = await asyncio.gather(
                async_get_fleet(self._session),
                async_get_vehicle_statuses(self._session),
            )
        except RenfeApiError as err:
            raise UpdateFailed(str(err)) from err

        return FleetSnapshot(
            trains=trains,
            statuses={status.trip_id: status for status in statuses},
        )

    def get_train_by_trip_id(self, trip_id: str) -> TrainPosition | None:
        """Devuelve el tren en circulación con el `tripId` indicado.

        El `tripId` identifica un viaje concreto de un tren y es el único
        vínculo fiable entre una salida (origen/destino elegidos por el
        usuario, que pueden ser paradas intermedias del trayecto real del
        tren) y su posición GPS en la flota, cuyo origen/destino son siempre
        los extremos completos de la línea.
        """
        if not self.data or not trip_id:
            return None
        for tren in self.data.trains:
            if tren.trip_id == trip_id:
                return tren
        return None

    def get_status_by_trip_id(self, trip_id: str) -> VehicleStatus | None:
        """Devuelve el estado GTFS-RT (`currentStatus`) del tren, si se conoce."""
        if not self.data or not trip_id:
            return None
        return self.data.statuses.get(trip_id)


class RenfeAlertsCoordinator(DataUpdateCoordinator[list[ServiceAlert]]):
    """Coordinador compartido con los avisos de servicio (GTFS-RT alerts)."""

    def __init__(self, hass: HomeAssistant, scan_interval: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_alerts",
            update_interval=timedelta(seconds=scan_interval),
        )
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self) -> list[ServiceAlert]:
        try:
            return await async_get_alerts(self._session)
        except RenfeApiError as err:
            raise UpdateFailed(str(err)) from err

    def get_alerts_for_stop(self, station_code: str) -> list[ServiceAlert]:
        """Avisos que mencionan explícitamente esta estación."""
        return [
            alert for alert in (self.data or []) if station_code in alert.stop_ids
        ]

    def get_alerts_for_routes(self, route_ids: set[str]) -> list[ServiceAlert]:
        """Avisos que mencionan cualquiera de estos `routeId` (una línea)."""
        if not route_ids:
            return []
        return [
            alert
            for alert in (self.data or [])
            if route_ids.intersection(alert.route_ids)
        ]


class RenfeStopCoordinator(DataUpdateCoordinator[list[Departure]]):
    """Coordinador con las próximas salidas de una estación."""

    def __init__(
        self,
        hass: HomeAssistant,
        station_code: str,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{station_code}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self._session = async_get_clientsession(hass)
        self.station_code = station_code

    async def _async_update_data(self) -> list[Departure]:
        try:
            return await async_get_departures(self._session, self.station_code)
        except RenfeApiError as err:
            raise UpdateFailed(str(err)) from err
