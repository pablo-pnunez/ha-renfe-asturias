"""Constantes para la integración Renfe Cercanías."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "renfe_cercanias"

URL_SALIDAS: Final = (
    "https://tiempo-real.renfe.com/renfe-json-cutter/write/salidas/estacion/{codigo}.json"
)
URL_FLOTA: Final = "https://tiempo-real.renfe.com/renfe-visor/flota.json"

# Feeds GTFS-Realtime oficiales (https://gtfsrt.renfe.com)
URL_VEHICLE_POSITIONS: Final = "https://gtfsrt.renfe.com/vehicle_positions.json"
URL_ALERTS: Final = "https://gtfsrt.renfe.com/alerts.json"

VEHICLE_STATUS_STOPPED: Final = "STOPPED_AT"
VEHICLE_STATUS_INCOMING: Final = "INCOMING_AT"
VEHICLE_STATUS_IN_TRANSIT: Final = "IN_TRANSIT_TO"

HTTP_HEADERS: Final = {
    "Accept": "application/json",
    "Accept-Language": "es,en-US;q=0.9,en;q=0.8",
    "Origin": "https://www.renfe.com",
    "Referer": "https://www.renfe.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Tipos de entrada de configuración
ENTRY_TYPE_STOP: Final = "stop"
ENTRY_TYPE_ROUTE: Final = "route"

CONF_ENTRY_TYPE: Final = "entry_type"
CONF_NUCLEO: Final = "nucleo"
CONF_STATION: Final = "station"
CONF_ORIGIN: Final = "origin"
CONF_DESTINATION: Final = "destination"
CONF_ROUTE_ID: Final = "route_id"

CONF_NUM_DEPARTURES: Final = "num_departures"
CONF_STOPS_SCAN_INTERVAL: Final = "stops_scan_interval"
CONF_FLEET_SCAN_INTERVAL: Final = "fleet_scan_interval"
CONF_ALERTS_SCAN_INTERVAL: Final = "alerts_scan_interval"

DEFAULT_NUM_DEPARTURES: Final = 5
DEFAULT_STOPS_SCAN_INTERVAL: Final = 60
DEFAULT_FLEET_SCAN_INTERVAL: Final = 30
DEFAULT_ALERTS_SCAN_INTERVAL: Final = 300

MIN_STOPS_SCAN_INTERVAL: Final = 30
MIN_FLEET_SCAN_INTERVAL: Final = 20
MIN_ALERTS_SCAN_INTERVAL: Final = 60

FLEET_COORDINATOR: Final = "fleet_coordinator"
ALERTS_COORDINATOR: Final = "alerts_coordinator"

ATTRIBUTION: Final = "Datos: Renfe (tiempo-real.renfe.com)"

MANUFACTURER: Final = "Renfe"
