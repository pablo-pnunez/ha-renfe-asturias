/**
 * Tarjeta Lovelace para Renfe Cercanías: visualización lineal de una ruta
 * favorita con todas sus paradas y la posición en directo del tren.
 *
 * Configuración YAML mínima:
 *   type: custom:renfe-route-card
 *   entity: device_tracker.cercanias_oviedo_aviles_tren
 *
 * La tarjeta siempre ocupa el ancho disponible (nunca requiere scroll
 * horizontal): mide su propio ancho con ResizeObserver y decide cuántas
 * etiquetas de parada caben sin solaparse, mostrando siempre origen,
 * destino y la parada actual/siguiente del tren cuando está circulando.
 * El tramo ya recorrido de la línea se pinta con el color de la línea; el
 * resto, en gris neutro.
 */

const MAX_LABEL_WIDTH_PX = 72; // debe coincidir con --renfe-label-max-width
const MIN_LABEL_SPACING_PX = 54; // >= huella horizontal de una etiqueta rotada 45º
const TRACK_RIGHT_PADDING_PX = 56; // hueco para que la última etiqueta no se corte
const TRACK_LEFT_PADDING_PX = 18;
const TRACK_BOTTOM_PADDING_PX = 80; // hueco vertical para la etiqueta rotada más larga

class RenfeRouteCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Debes indicar 'entity' (el device_tracker de la ruta)");
    }
    this._config = config;
    this._built = false;
    this._lastStateObj = null;
  }

  set hass(hass) {
    this._hass = hass;
    const stateObj = hass.states[this._config.entity];

    if (!this._built) {
      this._buildSkeleton();
      this._built = true;
    }

    if (!stateObj) {
      this._renderMissing();
      return;
    }

    this._lastStateObj = stateObj;
    this._render(stateObj);
  }

  connectedCallback() {
    if (this._resizeObserver || !this._built) return;
    this._resizeObserver = new ResizeObserver(() => this._onResize());
    this._resizeObserver.observe(this);
  }

  disconnectedCallback() {
    if (this._resizeObserver) {
      this._resizeObserver.disconnect();
      this._resizeObserver = null;
    }
  }

  _onResize() {
    if (this._resizeFrame) cancelAnimationFrame(this._resizeFrame);
    this._resizeFrame = requestAnimationFrame(() => {
      if (this._lastStateObj) this._render(this._lastStateObj);
    });
  }

  getCardSize() {
    return 4;
  }

  static getStubConfig() {
    return { entity: "" };
  }

  _buildSkeleton() {
    const card = document.createElement("ha-card");
    card.innerHTML = `
      <style>
        :host, ha-card {
          display: block;
          box-sizing: border-box;
        }
        * { box-sizing: border-box; }
        .renfe-header {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 16px 16px 0 16px;
        }
        .renfe-dot {
          width: 12px;
          height: 12px;
          border-radius: 50%;
          flex-shrink: 0;
        }
        .renfe-title {
          font-size: 1rem;
          font-weight: 500;
          color: var(--primary-text-color);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          min-width: 0;
        }
        .renfe-status {
          margin-left: auto;
          font-size: 0.85rem;
          color: var(--secondary-text-color);
          white-space: nowrap;
          flex-shrink: 0;
        }
        .renfe-status.delay {
          color: var(--error-color, #db4437);
          font-weight: 500;
        }
        .renfe-track-wrap {
          width: 100%;
          padding: 28px ${TRACK_RIGHT_PADDING_PX}px ${TRACK_BOTTOM_PADDING_PX}px ${TRACK_LEFT_PADDING_PX}px;
        }
        .renfe-track {
          position: relative;
          width: 100%;
          height: 4px;
        }
        .renfe-line {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 4px;
          border-radius: 2px;
          background: var(--divider-color, #9e9e9e);
          opacity: 0.5;
        }
        .renfe-line-progress {
          position: absolute;
          top: 0;
          left: 0;
          height: 4px;
          border-radius: 2px;
        }
        .renfe-stop {
          position: absolute;
          top: -4px;
        }
        .renfe-stop-dot {
          position: absolute;
          top: 0;
          left: 0;
          transform: translateX(-50%);
          width: 12px;
          height: 12px;
          border-radius: 50%;
          background: var(--card-background-color, white);
          border: 3px solid var(--divider-color, #9e9e9e);
        }
        .renfe-stop.reached .renfe-stop-dot {
          border-color: var(--renfe-line-color, var(--primary-color));
        }
        .renfe-stop.minor .renfe-stop-dot {
          width: 6px;
          height: 6px;
          border-width: 2px;
          top: 3px;
        }
        .renfe-stop-label {
          position: absolute;
          top: 14px;
          left: 6px;
          max-width: ${MAX_LABEL_WIDTH_PX}px;
          overflow: hidden;
          text-overflow: ellipsis;
          font-size: 0.72rem;
          color: var(--secondary-text-color);
          white-space: nowrap;
          transform-origin: top left;
          transform: rotate(45deg);
        }
        .renfe-indicator {
          position: absolute;
          top: 50%;
          left: 0;
          transform: translate(-50%, -50%);
          width: 20px;
          height: 20px;
          border-radius: 50%;
          background: var(--card-background-color, white);
          border: 4px solid var(--renfe-line-color, var(--primary-color));
          box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
          transition: left 2s linear;
          z-index: 3;
        }
        .renfe-empty {
          padding: 16px;
          color: var(--secondary-text-color);
          text-align: center;
          font-size: 0.9rem;
        }
      </style>
      <div class="renfe-header">
        <span class="renfe-dot"></span>
        <span class="renfe-title"></span>
        <span class="renfe-status"></span>
      </div>
      <div class="renfe-body"></div>
    `;
    this.innerHTML = "";
    this.appendChild(card);
    this._card = card;
    this._dotEl = card.querySelector(".renfe-dot");
    this._titleEl = card.querySelector(".renfe-title");
    this._statusEl = card.querySelector(".renfe-status");
    this._bodyEl = card.querySelector(".renfe-body");

    if (!this._resizeObserver && this.isConnected) {
      this._resizeObserver = new ResizeObserver(() => this._onResize());
      this._resizeObserver.observe(this);
    }
  }

  _renderMissing() {
    this._dotEl.style.background = "var(--disabled-text-color)";
    this._titleEl.textContent = this._config.entity;
    this._statusEl.textContent = "Entidad no encontrada";
    this._bodyEl.innerHTML = "";
  }

  _render(stateObj) {
    const attrs = stateObj.attributes || {};
    const paradas = attrs.paradas || [];
    const color = attrs.color || "var(--primary-color)";
    const linea = attrs.linea || "";
    const origen = attrs.origen || "";
    const destino = attrs.destino || "";
    const enCirculacion = !!attrs.en_circulacion;

    this._card.style.setProperty("--renfe-line-color", color);
    this._dotEl.style.background = color;
    this._titleEl.textContent =
      this._config.title ||
      (linea ? `${linea} · ${origen} → ${destino}` : `${origen} → ${destino}`);
    this._titleEl.title = this._titleEl.textContent;

    if (!enCirculacion) {
      this._statusEl.textContent = "Sin tren en circulación";
      this._statusEl.classList.remove("delay");
    } else {
      const retraso = attrs.retraso_min;
      if (typeof retraso === "number" && retraso > 0) {
        this._statusEl.textContent = `+${retraso} min`;
        this._statusEl.classList.add("delay");
      } else {
        this._statusEl.textContent = "En hora";
        this._statusEl.classList.remove("delay");
      }
    }

    if (!paradas.length) {
      this._bodyEl.innerHTML =
        '<div class="renfe-empty">No se conoce el itinerario de esta línea todavía.</div>';
      return;
    }

    const n = paradas.length;
    const idxActual = enCirculacion ? attrs.indice_estacion_actual : null;
    const idxSiguiente = enCirculacion ? attrs.indice_estacion_siguiente : null;

    const availableWidth = this.clientWidth || this._card.clientWidth || 300;
    const trackWidth = Math.max(
      0,
      availableWidth - TRACK_LEFT_PADDING_PX - TRACK_RIGHT_PADDING_PX
    );
    const labeledIndices = this._pickLabeledIndices(
      n,
      trackWidth,
      idxActual,
      idxSiguiente
    );

    const ratio = this._computePositionRatio(n, idxActual, idxSiguiente, attrs.porcentaje_avance);

    let stopsHtml = "";
    for (let i = 0; i < n; i++) {
      const leftPct = n > 1 ? (i / (n - 1)) * 100 : 0;
      const labeled = labeledIndices.has(i);
      const reached = ratio !== null && leftPct / 100 <= ratio + 1e-6;
      const label = labeled
        ? `<div class="renfe-stop-label" title="${this._escape(paradas[i].nombre)}">${this._escape(
            paradas[i].nombre
          )}</div>`
        : "";
      const classes = [
        "renfe-stop",
        labeled ? "" : "minor",
        reached ? "reached" : "",
      ]
        .filter(Boolean)
        .join(" ");
      stopsHtml += `
        <div class="${classes}" style="left:${leftPct}%">
          <div class="renfe-stop-dot"></div>
          ${label}
        </div>`;
    }

    let indicatorHtml = "";
    let progressHtml = "";
    if (ratio !== null) {
      indicatorHtml = `<div class="renfe-indicator" style="left:${ratio * 100}%"></div>`;
      progressHtml = `<div class="renfe-line-progress" style="width:${
        ratio * 100
      }%;background:var(--renfe-line-color)"></div>`;
    }

    this._bodyEl.innerHTML = `
      <div class="renfe-track-wrap">
        <div class="renfe-track">
          <div class="renfe-line"></div>
          ${progressHtml}
          ${stopsHtml}
          ${indicatorHtml}
        </div>
      </div>
    `;
  }

  /**
   * Decide qué índices de parada llevan etiqueta de texto, para que quepan
   * sin solaparse en el ancho real disponible. Siempre se etiquetan el
   * origen, el destino y (si hay tren circulando) la parada actual y la
   * siguiente; el resto se reparte de forma uniforme hasta llenar el hueco.
   */
  _pickLabeledIndices(n, trackWidthPx, idxActual, idxSiguiente) {
    const mustHave = new Set([0, n - 1]);
    if (idxActual !== null && idxActual !== undefined) mustHave.add(idxActual);
    if (idxSiguiente !== null && idxSiguiente !== undefined) mustHave.add(idxSiguiente);

    const maxLabels = Math.max(
      mustHave.size,
      Math.min(n, Math.floor(trackWidthPx / MIN_LABEL_SPACING_PX) + 1)
    );

    const indices = new Set(mustHave);
    if (maxLabels > indices.size && n > 2) {
      const remainingSlots = maxLabels - indices.size;
      const step = (n - 1) / (remainingSlots + 1);
      for (let k = 1; k <= remainingSlots; k++) {
        const idx = Math.round(step * k);
        if (idx > 0 && idx < n - 1) indices.add(idx);
      }
    }

    // Si ni siquiera caben todas las "obligatorias" (origen, destino, tren
    // actual/siguiente) con un mínimo de holgura -en una tarjeta muy
    // estrecha-, nos quedamos solo con origen y destino para evitar
    // amontonar el texto.
    const avgSpacingPx = trackWidthPx / Math.max(1, indices.size - 1 || 1);
    if (indices.size > 2 && avgSpacingPx < MIN_LABEL_SPACING_PX * 0.6) {
      return new Set([0, n - 1]);
    }
    return indices;
  }

  _computePositionRatio(n, idxActual, idxSiguiente, porcentajeAvance) {
    if (idxActual === null || idxActual === undefined) return null;
    if (n <= 1) return 0;

    let target = idxActual;
    if (
      idxSiguiente !== null &&
      idxSiguiente !== undefined &&
      idxSiguiente !== idxActual
    ) {
      const raw = parseFloat(porcentajeAvance);
      const pct = Number.isFinite(raw) ? Math.min(Math.max(raw, 0), 100) / 100 : 0;
      target = idxActual + (idxSiguiente - idxActual) * pct;
    }
    return Math.min(Math.max(target / (n - 1), 0), 1);
  }

  _escape(text) {
    const div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  }
}

customElements.define("renfe-route-card", RenfeRouteCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "renfe-route-card",
  name: "Renfe Cercanías - Ruta en directo",
  description:
    "Visualización lineal de una ruta favorita de Cercanías con la posición del tren en directo.",
});
