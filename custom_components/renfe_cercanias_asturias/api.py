"""Cliente HTTP para los datos abiertos en tiempo real de Renfe Cercanías."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp

from .const import HTTP_HEADERS, URL_FLOTA, URL_SALIDAS

_LOGGER = logging.getLogger(__name__)

MADRID_TZ = ZoneInfo("Europe/Madrid")

_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class RenfeApiError(Exception):
    """Error al comunicarse con los servicios de Renfe."""


def _parse_datetime(value: str | None, fmt: str) -> datetime | None:
    """Parsea una fecha de Renfe asumiendo la zona horaria de Madrid."""
    if not value:
        return None
    try:
        return datetime.strptime(value, fmt).replace(tzinfo=MADRID_TZ)
    except ValueError:
        _LOGGER.debug("No se pudo parsear la fecha %r con formato %r", value, fmt)
        return None


def _parse_int(value: str | int | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_float(value: float | str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class Departure:
    """Una salida programada/real desde una estación."""

    tren_id: str
    trip_id: str
    linea: str
    destino_codigo: str
    destino_nombre: str
    hora_salida: datetime | None
    hora_salida_planificada: datetime | None
    retraso_min: int | None
    via: str | None
    accesible: bool
    latitud: float | None
    longitud: float | None


@dataclass(slots=True)
class TrainPosition:
    """Posición en tiempo real de un tren circulando."""

    trip_id: str
    tren_id: str
    linea: str
    nucleo: str
    origen_codigo: str
    destino_codigo: str
    estacion_actual_codigo: str
    estacion_siguiente_codigo: str
    hora_llegada_siguiente: datetime | None
    retraso_min: int | None
    porcentaje_avance: str | None
    latitud: float
    longitud: float
    accesible: bool
    via: str | None


async def _fetch_json(session: aiohttp.ClientSession, url: str) -> dict | list:
    try:
        async with session.get(
            url, headers=HTTP_HEADERS, timeout=_REQUEST_TIMEOUT
        ) as response:
            if response.status != 200:
                raise RenfeApiError(
                    f"Respuesta inesperada de Renfe ({response.status}) en {url}"
                )
            return await response.json(content_type=None)
    except asyncio.TimeoutError as err:
        raise RenfeApiError(f"Tiempo de espera agotado al consultar {url}") from err
    except aiohttp.ClientError as err:
        raise RenfeApiError(f"Error de conexión al consultar {url}") from err


async def async_get_departures(
    session: aiohttp.ClientSession, station_code: str
) -> list[Departure]:
    """Obtiene las próximas salidas de una estación."""
    url = URL_SALIDAS.format(codigo=station_code)
    raw = await _fetch_json(session, url)

    salidas_raw = raw.get("estacion", {}).get("salidas", []) if isinstance(raw, dict) else []

    departures: list[Departure] = []
    for item in salidas_raw:
        loc = item.get("localizacion") or {}
        departures.append(
            Departure(
                tren_id=str(item.get("trenId", "")),
                trip_id=str(item.get("tripId", "")),
                linea=str(item.get("linea", "")),
                destino_codigo=str(item.get("destino", "")),
                destino_nombre=str(item.get("destinoNombre", "")),
                hora_salida=_parse_datetime(
                    item.get("horaSalida"), "%d-%m-%Y %H:%M:%S"
                ),
                hora_salida_planificada=_parse_datetime(
                    item.get("horaSalidaPlanificada"), "%d-%m-%Y %H:%M:%S"
                ),
                retraso_min=_parse_int(item.get("retrasoMin")),
                via=item.get("via") or None,
                accesible=str(item.get("accesible")) in ("1", "2"),
                latitud=_parse_float(loc.get("latitud")),
                longitud=_parse_float(loc.get("longitud")),
            )
        )

    departures.sort(
        key=lambda dep: dep.hora_salida or datetime.max.replace(tzinfo=MADRID_TZ)
    )
    return departures


async def async_get_fleet(
    session: aiohttp.ClientSession, nucleo: str | None = None
) -> list[TrainPosition]:
    """Obtiene la posición en tiempo real de todos los trenes en circulación.

    Si se indica `nucleo`, filtra solo los trenes de ese núcleo (p.ej. "20" = Asturias).
    """
    raw = await _fetch_json(session, URL_FLOTA)
    trenes_raw = raw.get("trenes", []) if isinstance(raw, dict) else []

    positions: list[TrainPosition] = []
    for item in trenes_raw:
        if nucleo is not None and str(item.get("nucleo")) != nucleo:
            continue

        lat = _parse_float(item.get("latitud"))
        lon = _parse_float(item.get("longitud"))
        if lat is None or lon is None:
            continue

        positions.append(
            TrainPosition(
                trip_id=str(item.get("tripId", "")),
                tren_id=str(item.get("codTren", "")),
                linea=str(item.get("codLinea", "")),
                nucleo=str(item.get("nucleo", "")),
                origen_codigo=str(item.get("codEstOrig", "")),
                destino_codigo=str(item.get("codEstDest", "")),
                estacion_actual_codigo=str(item.get("codEstAct", "")),
                estacion_siguiente_codigo=str(item.get("codEstSig", "")),
                hora_llegada_siguiente=_parse_datetime(
                    item.get("horaLlegadaSigEst"), "%Y-%m-%dT%H:%M:%S"
                ),
                retraso_min=_parse_int(item.get("retrasoMin")),
                porcentaje_avance=item.get("porAvanc"),
                latitud=lat,
                longitud=lon,
                accesible=bool(item.get("accesible")),
                via=item.get("via") or None,
            )
        )
    return positions
