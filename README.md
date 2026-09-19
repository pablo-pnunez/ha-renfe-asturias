# Renfe Cercanías para Home Assistant

Integración personalizada (custom component) para Home Assistant que muestra horarios en
tiempo real y ubicación GPS de los trenes de **cualquier red de Cercanías Renfe de
España**, a partir de los mismos datos abiertos que alimentan el visor oficial
[tiempo-real.renfe.com](https://tiempo-real.renfe.com), más el feed [GTFS oficial de
Cercanías](https://data.renfe.com) para conocer el itinerario completo de cada línea.

Incluye 15 redes/núcleos: Madrid, Asturias, Sevilla, Cádiz, Málaga, Valencia,
Murcia/Alicante, Cartagena, Ferrol, León, Rodalies de Catalunya, Bilbao, San Sebastián,
Cantabria y Zaragoza.

## Funcionalidades

- **Paradas favoritas**: elige una región y luego cualquiera de sus estaciones → sensor
  con la próxima salida (todas las líneas) y los datos de las siguientes salidas (línea,
  destino, hora, retraso, vía, accesibilidad).
- **Rutas favoritas** (origen → destino): además del sensor de próxima salida para ese
  trayecto concreto, se crea una entidad `device_tracker` que sitúa el tren en el mapa de
  Home Assistant mientras está circulando, con línea, retraso, próxima parada y % de
  avance como atributos. El % de avance se calcula con el `currentStatus` GTFS-RT oficial
  (parado / llegando / en tránsito) y, cuando el tren está en tránsito, con la posición
  geométrica real entre ambas paradas. También expone el itinerario completo de paradas
  de la ruta (orden real, extraído del GTFS oficial) y el índice de la parada
  actual/siguiente dentro de ese itinerario, pensado para dashboards. También expone la
  hora de salida real del origen, la hora estimada de llegada al destino y la hora
  estimada de paso por cada parada intermedia (calculadas a partir de los tiempos de
  recorrido programados del GTFS, sumados a la hora de salida real).
- **Avisos de servicio**: cada parada y ruta favorita tiene un sensor con el número de
  incidencias activas de Renfe que le afectan (obras, cambios de recorrido, ascensores
  averiados...) y su texto completo como atributo.
- **Tarjeta Lovelace incluida** (`renfe-route-card`): visualización lineal de una ruta
  favorita con todas sus paradas y un indicador que se mueve en directo según la posición
  del tren. Se registra automáticamente como recurso del frontend al instalar.
- Todo se configura desde la interfaz (config flow), sin tocar YAML.
- Opciones configurables: número de próximas salidas a mostrar e intervalos de
  actualización de horarios, posición GPS y avisos de servicio.

## Instalación

### Vía HACS (repositorio personalizado)

1. HACS → Integraciones → menú (⋮) → *Repositorios personalizados*.
2. Añade la URL de este repositorio con categoría **Integración**.
3. Busca "Renfe Cercanías" en HACS e instálala.
4. Reinicia Home Assistant.

### Manual

1. Copia la carpeta `custom_components/renfe_cercanias` dentro de
   `<config>/custom_components/` de tu instalación de Home Assistant.
2. Reinicia Home Assistant.

## Configuración

Ajustes → Dispositivos y servicios → Añadir integración → "Renfe Cercanías".

- **Parada favorita**: elige primero la región (núcleo) y luego la estación.
- **Ruta favorita**: elige la región, luego el origen; el destino se rellena con los
  trenes que realmente salen de esa estación en ese momento, para garantizar que la ruta
  tenga datos de horario y de posición.

Puedes repetir el proceso para añadir tantas paradas y rutas como quieras, de cualquier
región, combinadas libremente. Cada una se puede eliminar o configurar (número de
salidas, intervalos) de forma independiente.

## Tarjeta "ruta en directo"

Al instalar la integración se registra automáticamente el recurso Lovelace
`renfe-route-card`. Si tu instalación usa el modo de dashboards "storage" (el habitual),
no hace falta ningún paso adicional; añade la tarjeta desde el editor de tarjetas o con
YAML:

```yaml
type: custom:renfe-route-card
entity: device_tracker.cercanias_oviedo_aviles_tren
```

Si tu Lovelace está en modo YAML puro, o el registro automático no funcionase en tu
versión de Home Assistant, añade el recurso a mano en Ajustes → Panel de control →
Recursos: `/renfe_cercanias/renfe-route-card.js` (tipo módulo JavaScript).

## Icono de la integración

El icono y logo se sirven directamente desde `custom_components/renfe_cercanias/brand/`
gracias a la [Brands Proxy API](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api)
introducida en Home Assistant 2026.3: no requiere ningún PR externo ni configuración
adicional. En versiones de Home Assistant anteriores a la 2026.3 no se mostrará (se verá
el icono genérico de integración personalizada).

## Fuentes de datos

Todos los datos provienen de fuentes públicas de Renfe:

- Catálogo de estaciones y núcleos: `https://tiempo-real.renfe.com/data/estaciones.geojson`
  (usado para generar el catálogo embebido `stations.json` / `nucleos.json`).
- Salidas en tiempo real de una estación:
  `https://tiempo-real.renfe.com/renfe-json-cutter/write/salidas/estacion/<código>.json`.
- Posición GPS de todos los trenes en circulación de toda España:
  `https://tiempo-real.renfe.com/renfe-visor/flota.json`.
- Itinerario completo de cada línea (orden de paradas y color oficial): feed
  [GTFS estático de Cercanías](http://data.renfe.com) (`fomento_transit.zip`), usado para
  generar el catálogo embebido `route_patterns.json`.
- Estado GTFS-Realtime oficial (`https://gtfsrt.renfe.com`): `vehicle_positions.json`
  aporta el `currentStatus` de cada tren (parado / llegando / en tránsito), usado para
  calcular con precisión el % de avance; `alerts.json` aporta los avisos de servicio.

## Limitaciones conocidas

- Los catálogos de estaciones, núcleos e itinerarios de línea están embebidos
  (`stations.json`, `nucleos.json`, `route_patterns.json`); si Renfe cambia su red
  (nuevas estaciones, líneas) habrá que regenerarlos.
- La posición GPS de una ruta solo aparece mientras hay un tren circulando en ese
  trayecto concreto (identificado por su `tripId`); fuera de servicio, la entidad indica
  `sin_circular`.
- El registro automático de la tarjeta en Lovelace usa una API interna no pública de Home
  Assistant; si en tu versión no funciona, añádela a mano (ver arriba).
- Son datos no oficiales de Renfe, sujetos a cambios sin previo aviso por su parte.

## Créditos

Datos: Renfe ([tiempo-real.renfe.com](https://tiempo-real.renfe.com),
[data.renfe.com](http://data.renfe.com)). Este proyecto no está afiliado ni respaldado
por Renfe.
