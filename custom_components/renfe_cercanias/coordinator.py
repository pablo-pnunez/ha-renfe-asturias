"""Coordinadores de actualización de datos para Renfe Cercanías."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    Departure,
    RenfeApiError,
    TrainPosition,
    async_get_departures,
    async_get_fleet,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class RenfeFleetCoordinator(DataUpdateCoordinator[list[TrainPosition]]):
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

    async def _async_update_data(self) -> list[TrainPosition]:
        try:
            return await async_get_fleet(self._session)
        except RenfeApiError as err:
            raise UpdateFailed(str(err)) from err

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
        for tren in self.data:
            if tren.trip_id == trip_id:
                return tren
        return None


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
