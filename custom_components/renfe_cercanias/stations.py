"""Catálogo (embebido) de estaciones y núcleos de Cercanías Renfe."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypedDict


class Station(TypedDict):
    """Datos de una estación."""

    codigo: str
    nombre: str
    nucleo: str
    lineas: list[str]
    lat: float
    lon: float
    accesible: bool


class Nucleo(TypedDict):
    """Un núcleo/región de Cercanías (p.ej. Madrid, Asturias...)."""

    codigo: str
    nombre: str


_STATIONS_FILE = Path(__file__).parent / "stations.json"
_NUCLEOS_FILE = Path(__file__).parent / "nucleos.json"


@lru_cache(maxsize=1)
def get_all_stations() -> list[Station]:
    """Devuelve el catálogo completo de estaciones, ordenado por nombre."""
    with _STATIONS_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def get_stations(nucleo: str | None = None) -> list[Station]:
    """Devuelve las estaciones, opcionalmente filtradas por núcleo/región."""
    stations = get_all_stations()
    if nucleo is None:
        return stations
    return [station for station in stations if station["nucleo"] == nucleo]


@lru_cache(maxsize=1)
def get_stations_by_code() -> dict[str, Station]:
    """Devuelve el catálogo de estaciones indexado por código."""
    return {station["codigo"]: station for station in get_all_stations()}


def get_station_name(codigo: str) -> str:
    """Devuelve el nombre de una estación a partir de su código."""
    station = get_stations_by_code().get(codigo)
    return station["nombre"] if station else codigo


@lru_cache(maxsize=1)
def get_nucleos() -> list[Nucleo]:
    """Devuelve la lista de núcleos/regiones de Cercanías, ordenada por nombre."""
    with _NUCLEOS_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def get_nucleo_name(codigo: str) -> str:
    """Devuelve el nombre de un núcleo a partir de su código."""
    for nucleo in get_nucleos():
        if nucleo["codigo"] == codigo:
            return nucleo["nombre"]
    return codigo
