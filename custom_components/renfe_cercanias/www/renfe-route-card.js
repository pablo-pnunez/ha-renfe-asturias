/**
 * Tarjeta Lovelace para Renfe Cercanías: visualización lineal de una ruta
 * favorita con todas sus paradas y la posición en directo del tren.
 *
 * Configuración YAML mínima:
 *   type: custom:renfe-route-card
 *   entity: device_tracker.cercanias_oviedo_aviles_tren
 */

const STOP_WIDTH = 64; // px reservados por parada en la pista

class RenfeRouteCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Debes indicar 'entity' (el device_tracker de la ruta)");
    }
    this._config = config;
    this._built = false;
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

    this._render(stateObj);
  }

  getCardSize() {
    return 3;
  }

  static getStubConfig() {
    return { entity: "" };
  }

  _buildSkeleton() {
    const card = document.createElement("ha-card");
    card.innerHTML = `
      <style>
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
        }
        .renfe-status {
          margin-left: auto;
          font-size: 0.85rem;
          color: var(--secondary-text-color);
          white-space: nowrap;
        }
        .renfe-status.delay {
          color: var(--error-color, #db4437);
          font-weight: 500;
        }
        .renfe-track-wrap {
          overflow-x: auto;
          padding: 28px 16px 40px 16px;
        }
        .renfe-track {
          position: relative;
          height: 4px;
        }
        .renfe-line {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 4px;
          border-radius: 2px;
          background: var(--divider-color, #e0e0e0);
        }
        .renfe-stop {
          position: absolute;
          top: -5px;
          transform: translateX(-50%);
        }
        .renfe-stop-dot {
          width: 14px;
          height: 14px;
          border-radius: 50%;
          background: var(--card-background-color, white);
          border: 3px solid var(--divider-color, #9e9e9e);
          box-sizing: border-box;
        }
        .renfe-stop-label {
          position: absolute;
          top: 20px;
          left: 7px;
          font-size: 0.72rem;
          color: var(--secondary-text-color);
          white-space: nowrap;
          transform-origin: top left;
          transform: rotate(45deg);
        }
        .renfe-indicator {
          position: absolute;
          top: -9px;
          transform: translateX(-50%);
          width: 22px;
          height: 22px;
          border-radius: 50%;
          background: var(--card-background-color, white);
          border: 4px solid var(--primary-color);
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

    this._dotEl.style.background = color;
    this._titleEl.textContent =
      this._config.title ||
      (linea ? `${linea} · ${origen} → ${destino}` : `${origen} → ${destino}`);

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
    const trackWidth = Math.max(100, (n - 1) * STOP_WIDTH);

    let stopsHtml = "";
    for (let i = 0; i < n; i++) {
      const leftPct = n > 1 ? (i / (n - 1)) * 100 : 0;
      stopsHtml += `
        <div class="renfe-stop" style="left:${leftPct}%">
          <div class="renfe-stop-dot" style="border-color:${color}"></div>
          <div class="renfe-stop-label">${this._escape(paradas[i].nombre)}</div>
        </div>`;
    }

    const ratio = this._computePositionRatio(attrs);
    let indicatorHtml = "";
    if (ratio !== null) {
      indicatorHtml = `<div class="renfe-indicator" style="left:${
        ratio * 100
      }%;border-color:${color}"></div>`;
    }

    this._bodyEl.innerHTML = `
      <div class="renfe-track-wrap">
        <div class="renfe-track" style="min-width:${trackWidth}px">
          <div class="renfe-line" style="background:${color}55"></div>
          ${stopsHtml}
          ${indicatorHtml}
        </div>
      </div>
    `;
  }

  _computePositionRatio(attrs) {
    const idxActual = attrs.indice_estacion_actual;
    const idxSiguiente = attrs.indice_estacion_siguiente;
    const n = (attrs.paradas || []).length;

    if (!attrs.en_circulacion || idxActual === null || idxActual === undefined) {
      return null;
    }
    if (n <= 1) return 0;

    let target = idxActual;
    if (
      idxSiguiente !== null &&
      idxSiguiente !== undefined &&
      idxSiguiente !== idxActual
    ) {
      const raw = parseFloat(attrs.porcentaje_avance);
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
