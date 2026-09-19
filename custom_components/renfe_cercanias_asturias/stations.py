"""Catálogo (embebido) de estaciones de Cercanías Asturias."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypedDict


class Station(TypedDict):
    """Datos de una estación."""

    codigo: str
    nombre: str
    lineas: list[str]
    lat: float
    lon: float
    accesible: bool


_STATIONS_FILE = Path(__file__).parent / "stations.json"


@lru_cache(maxsize=1)
def get_stations() -> list[Station]:
    """Devuelve el catálogo de estaciones de Asturias, ordenado por nombre."""
    with _STATIONS_FILE.open(encoding="utf-8") as file:
        return json.load(file)


@lru_cache(maxsize=1)
def get_stations_by_code() -> dict[str, Station]:
    """Devuelve el catálogo de estaciones indexado por código."""
    return {station["codigo"]: station for station in get_stations()}


def get_station_name(codigo: str) -> str:
    """Devuelve el nombre de una estación a partir de su código."""
    station = get_stations_by_code().get(codigo)
    return station["nombre"] if station else codigo
