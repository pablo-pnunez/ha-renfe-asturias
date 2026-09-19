"""Itinerarios (orden de paradas) de cada línea, extraídos del GTFS oficial de Renfe.

`route_patterns.json` se genera offline a partir del feed GTFS estático de
Cercanías (fomento_transit.zip) y contiene, para cada `route_id` (línea +
sentido, el mismo identificador que Renfe expone como `routeId` en las
salidas en tiempo real), la secuencia completa y ordenada de estaciones de
un viaje representativo de esa línea.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

_PATTERNS_FILE = Path(__file__).parent / "route_patterns.json"


class PatternStop(TypedDict):
    """Una parada dentro de un itinerario de línea."""

    codigo: str
    nombre: str


class RoutePattern(TypedDict):
    """Itinerario completo de una línea en un sentido concreto."""

    linea: str
    nucleo: str
    paradas: list[PatternStop]
    color: str | None


@lru_cache(maxsize=1)
def _all_patterns() -> dict[str, RoutePattern]:
    with _PATTERNS_FILE.open(encoding="utf-8") as file:
        return json.load(file)


def get_pattern(route_id: str) -> RoutePattern | None:
    """Devuelve el itinerario completo de un `route_id`, si se conoce."""
    return _all_patterns().get(route_id)


def get_route_segment(
    route_id: str, origin_code: str, destination_code: str
) -> list[PatternStop] | None:
    """Devuelve el tramo de paradas entre origen y destino, ambos incluidos.

    Devuelve `None` si no se conoce el itinerario de `route_id`, o si el
    origen/destino no aparecen en él en ese orden.
    """
    pattern = get_pattern(route_id)
    if pattern is None:
        return None

    paradas = pattern["paradas"]
    codigos = [parada["codigo"] for parada in paradas]

    try:
        origin_idx = codigos.index(origin_code)
        destination_idx = codigos.index(destination_code)
    except ValueError:
        return None

    if origin_idx > destination_idx:
        return None

    return paradas[origin_idx : destination_idx + 1]


def get_route_color(route_id: str) -> str | None:
    """Devuelve el color oficial (hex) de la línea, si se conoce."""
    pattern = get_pattern(route_id)
    return pattern["color"] if pattern else None


def preload() -> None:
    """Fuerza la carga (y cacheado) del fichero de patrones.

    Pensado para llamarse una vez desde un executor al arrancar la
    integración, para que las lecturas posteriores desde el bucle de
    eventos usen la caché en memoria y no bloqueen con E/S de disco.
    """
    _all_patterns()
