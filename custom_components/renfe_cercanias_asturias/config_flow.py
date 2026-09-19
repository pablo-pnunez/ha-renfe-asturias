"""Flujo de configuración de Renfe Cercanías Asturias."""
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
    CONF_DESTINATION,
    CONF_ENTRY_TYPE,
    CONF_FLEET_SCAN_INTERVAL,
    CONF_NUM_DEPARTURES,
    CONF_ORIGIN,
    CONF_STATION,
    CONF_STOPS_SCAN_INTERVAL,
    DEFAULT_FLEET_SCAN_INTERVAL,
    DEFAULT_NUM_DEPARTURES,
    DEFAULT_STOPS_SCAN_INTERVAL,
    DOMAIN,
    ENTRY_TYPE_ROUTE,
    ENTRY_TYPE_STOP,
    MIN_FLEET_SCAN_INTERVAL,
    MIN_STOPS_SCAN_INTERVAL,
)
from .stations import get_stations, get_stations_by_code


def _station_options() -> list[SelectOptionDict]:
    return [
        SelectOptionDict(value=station["codigo"], label=station["nombre"])
        for station in get_stations()
    ]


class RenfeCercaniasAsturiasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Flujo de configuración para paradas y rutas favoritas de Cercanías Asturias."""

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._route_origin: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Punto de entrada: elegir entre parada o ruta favorita."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[ENTRY_TYPE_STOP, ENTRY_TYPE_ROUTE],
        )

    async def async_step_stop(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Configura una parada favorita (horarios de salida)."""
        errors: dict[str, str] = {}

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
                        options=_station_options(),
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="stop", data_schema=schema, errors=errors
        )

    async def async_step_route(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Primer paso de una ruta favorita: elegir la estación de origen."""
        if user_input is not None:
            self._route_origin = user_input[CONF_ORIGIN]
            return await self.async_step_route_destination()

        schema = vol.Schema(
            {
                vol.Required(CONF_ORIGIN): SelectSelector(
                    SelectSelectorConfig(
                        options=_station_options(), mode=SelectSelectorMode.DROPDOWN
                    )
                ),
            }
        )
        return self.async_show_form(step_id="route", data_schema=schema)

    async def async_step_route_destination(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Segundo paso: elegir destino entre los trenes que salen de ese origen.

        El destino se limita a los que realmente aparecen como fin de trayecto
        en las salidas en tiempo real del origen elegido, para garantizar que
        la ruta pueda mostrar tanto horario como ubicación del tren en el mapa.
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

        destinations = {
            dep.destino_codigo: dep.destino_nombre
            for dep in departures
            if dep.destino_codigo and dep.destino_codigo != origin
        }

        if not destinations and not errors:
            errors["base"] = "no_destinations"

        if user_input is not None and not errors:
            destination = user_input[CONF_DESTINATION]

            await self.async_set_unique_id(
                f"{ENTRY_TYPE_ROUTE}_{origin}_{destination}"
            )
            self._abort_if_unique_id_configured()

            origin_name = get_stations_by_code().get(origin, {}).get("nombre", origin)
            dest_name = destinations.get(destination, destination)
            return self.async_create_entry(
                title=f"{origin_name} → {dest_name}",
                data={
                    CONF_ENTRY_TYPE: ENTRY_TYPE_ROUTE,
                    CONF_ORIGIN: origin,
                    CONF_DESTINATION: destination,
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_DESTINATION): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=codigo, label=nombre)
                            for codigo, nombre in sorted(
                                destinations.items(), key=lambda kv: kv[1]
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
    ) -> RenfeCercaniasAsturiasOptionsFlow:
        """Devuelve el flujo de opciones."""
        return RenfeCercaniasAsturiasOptionsFlow(config_entry)


class RenfeCercaniasAsturiasOptionsFlow(OptionsFlow):
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
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
