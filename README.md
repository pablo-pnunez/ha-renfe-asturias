# Renfe Cercanías Asturias para Home Assistant

Integración personalizada (custom component) para Home Assistant que muestra horarios en
tiempo real y ubicación GPS de los trenes de **Cercanías Renfe Asturias** (núcleo C-6),
a partir de los mismos datos abiertos que alimentan el visor oficial
[tiempo-real.renfe.com](https://tiempo-real.renfe.com).

No existía ninguna integración de Home Assistant que combinase horarios de una parada,
rutas favoritas origen→destino y posición en tiempo real del tren en un mapa; esta
integración cubre las tres cosas.

## Funcionalidades

- **Paradas favoritas**: elige cualquiera de las 149 estaciones de Cercanías Asturias y
  obtén un sensor con la próxima salida (todas las líneas) y los datos de las siguientes
  salidas (línea, destino, hora, retraso, vía, accesibilidad).
- **Rutas favoritas** (origen → destino): además del sensor de próxima salida para ese
  trayecto concreto, se crea una entidad `device_tracker` que sitúa el tren en el mapa de
  Home Assistant mientras está circulando, con línea, retraso, próxima parada y % de
  avance como atributos.
- Todo se configura desde la interfaz (config flow), sin tocar YAML.
- Opciones configurables: número de próximas salidas a mostrar e intervalos de
  actualización de horarios y de posición GPS.

## Instalación

### Vía HACS (repositorio personalizado)

1. HACS → Integraciones → menú (⋮) → *Repositorios personalizados*.
2. Añade la URL de este repositorio con categoría **Integración**.
3. Busca "Renfe Cercanías Asturias" en HACS e instálala.
4. Reinicia Home Assistant.

### Manual

1. Copia la carpeta `custom_components/renfe_cercanias_asturias` dentro de
   `<config>/custom_components/` de tu instalación de Home Assistant.
2. Reinicia Home Assistant.

## Configuración

Ajustes → Dispositivos y servicios → Añadir integración → "Renfe Cercanías Asturias".

- **Parada favorita**: elige una estación de la lista.
- **Ruta favorita**: elige primero el origen; el destino se rellena con los trenes que
  realmente salen de esa estación en ese momento, para garantizar que la ruta tenga datos
  de horario y de posición.

Puedes repetir el proceso para añadir tantas paradas y rutas como quieras. Cada una se
puede eliminar u configurar (número de salidas, intervalos) de forma independiente desde
la propia integración.

## Fuentes de datos

Todos los datos provienen de los endpoints públicos, sin autenticación, que usa la propia
web de Renfe:

- Catálogo de estaciones: `https://tiempo-real.renfe.com/data/estaciones.geojson`
  (se usó para generar el catálogo embebido de Asturias en `stations.json`).
- Salidas en tiempo real de una estación:
  `https://tiempo-real.renfe.com/renfe-json-cutter/write/salidas/estacion/<código>.json`.
- Posición GPS de todos los trenes en circulación:
  `https://tiempo-real.renfe.com/renfe-visor/flota.json` (se filtra por el núcleo de
  Asturias, código `20`).

## Limitaciones conocidas

- Solo cubre Cercanías Asturias (núcleo 20). El catálogo de estaciones está embebido en
  `stations.json`; si Renfe añade/renombra estaciones habrá que regenerarlo.
- La posición GPS de una ruta solo aparece mientras hay un tren circulando en ese
  trayecto concreto (identificado por su `tripId`); fuera de servicio, la entidad indica
  `sin_circular`.
- Son datos no oficiales de Renfe, sujetos a cambios sin previo aviso por su parte.

## Créditos

Datos: Renfe ([tiempo-real.renfe.com](https://tiempo-real.renfe.com)). Este proyecto no
está afiliado ni respaldado por Renfe.
