"""Flujo de configuración de Renfe Cercanías."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import RenfeApiError, async_get_departures
from .const import (
    CONF_ALERTS_SCAN_INTERVAL,
    CONF_DESTINATION,
    CONF_ENTRY_TYPE,
    CONF_FLEET_SCAN_INTERVAL,
    CONF_NUCLEO,
    CONF_NUM_DEPARTURES,
    CONF_ORIGIN,
    CONF_ROUTE_ID,
    CONF_STATION,
    CONF_STOPS_SCAN_INTERVAL,
    DEFAULT_ALERTS_SCAN_INTERVAL,
    DEFAULT_FLEET_SCAN_INTERVAL,
    DEFAULT_NUM_DEPARTURES,
    DEFAULT_STOPS_SCAN_INTERVAL,
    DOMAIN,
    ENTRY_TYPE_ROUTE,
    ENTRY_TYPE_STOP,
    MIN_ALERTS_SCAN_INTERVAL,
    MIN_FLEET_SCAN_INTERVAL,
    MIN_STOPS_SCAN_INTERVAL,
)
from .stations import get_nucleos, get_stations, get_stations_by_code


def _nucleo_options() -> list[SelectOptionDict]:
    return [
        SelectOptionDict(value=nucleo["codigo"], label=nucleo["nombre"])
        for nucleo in get_nucleos()
    ]


def _station_options(nucleo: str) -> list[SelectOptionDict]:
    return [
        SelectOptionDict(value=station["codigo"], label=station["nombre"])
        for station in get_stations(nucleo)
    ]


class RenfeCercaniasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Flujo de configuración para paradas y rutas favoritas de Cercanías."""

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._nucleo: str | None = None
        self._route_origin: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Punto de entrada: elegir entre parada o ruta favorita."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[ENTRY_TYPE_STOP, ENTRY_TYPE_ROUTE],
        )

    # -- Parada favorita ---------------------------------------------------

    async def async_step_stop(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Primer paso de una parada favorita: elegir la región/núcleo."""
        if user_input is not None:
            self._nucleo = user_input[CONF_NUCLEO]
            return await self.async_step_stop_station()

        schema = vol.Schema(
            {
                vol.Required(CONF_NUCLEO): SelectSelector(
                    SelectSelectorConfig(
                        options=_nucleo_options(), mode=SelectSelectorMode.DROPDOWN
                    )
                ),
            }
        )
        return self.async_show_form(step_id="stop", data_schema=schema)

    async def async_step_stop_station(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Segundo paso: elegir la estación dentro de la región elegida."""
        assert self._nucleo is not None

        if user_input is not None:
            station_code = user_input[CONF_STATION]
            await self.async_set_unique_id(f"{ENTRY_TYPE_STOP}_{station_code}")
            self._abort_if_unique_id_configured()

            station = get_stations_by_code().get(station_code)
            title = station["nombre"] if station else station_code
            return self.async_create_entry(
                title=title,
                data={
                    CONF_ENTRY_TYPE: ENTRY_TYPE_STOP,
                    CONF_STATION: station_code,
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_STATION): SelectSelector(
                    SelectSelectorConfig(
                        options=_station_options(self._nucleo),
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="stop_station", data_schema=schema)

    # -- Ruta favorita -------------------------------------------------------

    async def async_step_route(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Primer paso de una ruta favorita: elegir la región/núcleo."""
        if user_input is not None:
            self._nucleo = user_input[CONF_NUCLEO]
            return await self.async_step_route_origin()

        schema = vol.Schema(
            {
                vol.Required(CONF_NUCLEO): SelectSelector(
                    SelectSelectorConfig(
                        options=_nucleo_options(), mode=SelectSelectorMode.DROPDOWN
                    )
                ),
            }
        )
        return self.async_show_form(step_id="route", data_schema=schema)

    async def async_step_route_origin(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Segundo paso: elegir la estación de origen dentro de la región."""
        assert self._nucleo is not None

        if user_input is not None:
            self._route_origin = user_input[CONF_ORIGIN]
            return await self.async_step_route_destination()

        schema = vol.Schema(
            {
                vol.Required(CONF_ORIGIN): SelectSelector(
                    SelectSelectorConfig(
                        options=_station_options(self._nucleo),
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="route_origin", data_schema=schema)

    async def async_step_route_destination(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Último paso: elegir destino entre los trenes que salen de ese origen.

        El destino se limita a los que realmente aparecen como fin de trayecto
        en las salidas en tiempo real del origen elegido, para garantizar que
        la ruta pueda mostrar tanto horario como ubicación del tren en el mapa.
        También se guarda el `route_id` (línea + sentido) de esa salida, que
        es lo que permite luego reconstruir el itinerario completo de paradas.
        """
        errors: dict[str, str] = {}
        origin = self._route_origin
        assert origin is not None

        try:
            departures = await async_get_departures(
                async_get_clientsession(self.hass), origin
            )
        except RenfeApiError:
            errors["base"] = "cannot_connect"
            departures = []

        # Un mismo destino puede aparecer en salidas con route_id distinto
        # (p.ej. variantes de la misma línea); nos quedamos con el primero.
        destinations: dict[str, tuple[str, str]] = {}
        for dep in departures:
            if not dep.destino_codigo or dep.destino_codigo == origin:
                continue
            destinations.setdefault(
                dep.destino_codigo, (dep.destino_nombre, dep.route_id)
            )

        if not destinations and not errors:
            errors["base"] = "no_destinations"

        if user_input is not None and not errors:
            destination = user_input[CONF_DESTINATION]
            dest_name, route_id = destinations[destination]

            await self.async_set_unique_id(
                f"{ENTRY_TYPE_ROUTE}_{origin}_{destination}"
            )
            self._abort_if_unique_id_configured()

            origin_name = get_stations_by_code().get(origin, {}).get("nombre", origin)
            return self.async_create_entry(
                title=f"{origin_name} → {dest_name}",
                data={
                    CONF_ENTRY_TYPE: ENTRY_TYPE_ROUTE,
                    CONF_ORIGIN: origin,
                    CONF_DESTINATION: destination,
                    CONF_ROUTE_ID: route_id,
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_DESTINATION): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=codigo, label=nombre)
                            for codigo, (nombre, _route_id) in sorted(
                                destinations.items(), key=lambda kv: kv[1][0]
                            )
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="route_destination",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "origin": get_stations_by_code().get(origin, {}).get("nombre", origin)
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> RenfeCercaniasOptionsFlow:
        """Devuelve el flujo de opciones."""
        return RenfeCercaniasOptionsFlow(config_entry)


class RenfeCercaniasOptionsFlow(OptionsFlow):
    """Opciones: nº de salidas a mostrar e intervalos de actualización."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_NUM_DEPARTURES,
                    default=options.get(
                        CONF_NUM_DEPARTURES, DEFAULT_NUM_DEPARTURES
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=10, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_STOPS_SCAN_INTERVAL,
                    default=options.get(
                        CONF_STOPS_SCAN_INTERVAL, DEFAULT_STOPS_SCAN_INTERVAL
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_STOPS_SCAN_INTERVAL,
                        max=900,
                        step=10,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Optional(
                    CONF_FLEET_SCAN_INTERVAL,
                    default=options.get(
                        CONF_FLEET_SCAN_INTERVAL, DEFAULT_FLEET_SCAN_INTERVAL
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_FLEET_SCAN_INTERVAL,
                        max=300,
                        step=5,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Optional(
                    CONF_ALERTS_SCAN_INTERVAL,
                    default=options.get(
                        CONF_ALERTS_SCAN_INTERVAL, DEFAULT_ALERTS_SCAN_INTERVAL
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_ALERTS_SCAN_INTERVAL,
                        max=1800,
                        step=30,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
