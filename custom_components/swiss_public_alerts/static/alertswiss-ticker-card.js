/* Alertswiss card suite — shipped by the Swiss Public Alerts integration and
 * served under /swiss_public_alerts/static/. Register the file once as a
 * Lovelace resource (JavaScript module); see the README.
 *
 *   alertswiss-ticker-card  scrolling one-line summary of active alerts
 *   alertswiss-alert-card   detail view of the alert affecting the home
 *   alertswiss-list-card    filterable list of all active alerts
 *
 * All cards provide a visual editor (getConfigElement) and follow the
 * Home Assistant frontend language (de/en/fr/it).
 */

const ALERTSWISS_CANTONS = [
  ['ag', 'Aargau'], ['ai', 'Appenzell Innerrhoden'], ['ar', 'Appenzell Ausserrhoden'],
  ['be', 'Bern'], ['bl', 'Basel-Landschaft'], ['bs', 'Basel-Stadt'], ['fr', 'Freiburg'],
  ['ge', 'Genf'], ['gl', 'Glarus'], ['gr', 'Graubünden'], ['ju', 'Jura'], ['lu', 'Luzern'],
  ['ne', 'Neuenburg'], ['nw', 'Nidwalden'], ['ow', 'Obwalden'], ['sg', 'St. Gallen'],
  ['sh', 'Schaffhausen'], ['so', 'Solothurn'], ['sz', 'Schwyz'], ['tg', 'Thurgau'],
  ['ti', 'Tessin'], ['ur', 'Uri'], ['vd', 'Waadt'], ['vs', 'Wallis'], ['zg', 'Zug'],
  ['zh', 'Zürich'],
];

const ALERTSWISS_SEVERITY_RANK = { unknown: 0, minor: 1, moderate: 2, severe: 3 };
const ALERTSWISS_SEVERITY_COLOR = {
  minor: '#2196f3', moderate: '#ff9800', severe: '#f44336', unknown: '#9e9e9e',
};
const ALERTSWISS_WAPPEN = '/swiss_public_alerts/static/wappen';

const ALERTSWISS_L10N = {
  de: {
    no_alerts: 'Keine aktiven Meldungen',
    none_home: 'Aktuell keine Behördenmeldungen für deinen Standort.',
    instructions: 'Verhaltensanweisungen',
    official: 'Zur offiziellen Meldung',
    published: 'Publiziert am',
    nationwide: 'landesweit',
    more_alerts: 'weitere Meldung(en)',
    severity: { minor: 'Information', moderate: 'Warnung', severe: 'Alarm', unknown: 'Unbekannt' },
  },
  en: {
    no_alerts: 'No active alerts',
    none_home: 'Currently no public alerts for your location.',
    instructions: 'Instructions',
    official: 'Official alert',
    published: 'Published',
    nationwide: 'nationwide',
    more_alerts: 'more alert(s)',
    severity: { minor: 'Information', moderate: 'Warning', severe: 'Alarm', unknown: 'Unknown' },
  },
  fr: {
    no_alerts: 'Aucune alerte active',
    none_home: "Actuellement aucune alerte officielle pour votre emplacement.",
    instructions: 'Consignes de comportement',
    official: "Vers l'alerte officielle",
    published: 'Publié le',
    nationwide: 'national',
    more_alerts: 'autre(s) alerte(s)',
    severity: { minor: 'Information', moderate: 'Avertissement', severe: 'Alarme', unknown: 'Inconnu' },
  },
  it: {
    no_alerts: 'Nessuna allerta attiva',
    none_home: 'Attualmente nessuna allerta ufficiale per la tua posizione.',
    instructions: 'Istruzioni di comportamento',
    official: "All'allerta ufficiale",
    published: 'Pubblicato il',
    nationwide: 'nazionale',
    more_alerts: 'altra/e allerta/e',
    severity: { minor: 'Informazione', moderate: 'Avviso', severe: 'Allarme', unknown: 'Sconosciuto' },
  },
};

function awLang(hass) {
  const lang = ((hass && hass.language) || 'en').split('-')[0];
  return ALERTSWISS_L10N[lang] || ALERTSWISS_L10N.en;
}

function awLangCode(hass) {
  const lang = ((hass && hass.language) || 'en').split('-')[0];
  return ALERTSWISS_L10N[lang] ? lang : 'en';
}

function awEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function awDate(iso, langCode) {
  try {
    return new Intl.DateTimeFormat(langCode === 'de' ? 'de-CH' : langCode, {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(new Date(iso));
  } catch (e) { return iso; }
}

function awRelative(iso, langCode) {
  try {
    const diff = (new Date(iso).getTime() - Date.now()) / 1000;
    const rtf = new Intl.RelativeTimeFormat(langCode, { numeric: 'auto' });
    const abs = Math.abs(diff);
    if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute');
    if (abs < 172800) return rtf.format(Math.round(diff / 3600), 'hour');
    return rtf.format(Math.round(diff / 86400), 'day');
  } catch (e) { return ''; }
}

function awDot(severity) {
  const color = ALERTSWISS_SEVERITY_COLOR[severity] || ALERTSWISS_SEVERITY_COLOR.unknown;
  return `<span class="dot" style="background:${color}"></span>`;
}

function awWappen(code, size) {
  return code
    ? `<img class="wappen" style="height:${size}px" src="${ALERTSWISS_WAPPEN}/${awEsc(code)}.png"/>`
    : '';
}

/* Shared alert filtering used by ticker and list card. */
function awFilter(alerts, config) {
  let list = alerts;
  if (Array.isArray(config.cantons) && config.cantons.length) {
    list = list.filter((a) => a.nation_wide || config.cantons.includes(a.canton_code));
  }
  if (config.max_distance_km > 0) {
    list = list.filter(
      (a) => a.nation_wide || (a.distance_km != null && a.distance_km <= config.max_distance_km)
    );
  }
  if (config.min_severity) {
    const min = ALERTSWISS_SEVERITY_RANK[config.min_severity] || 0;
    list = list.filter((a) => (ALERTSWISS_SEVERITY_RANK[a.severity] || 0) >= min);
  }
  return list;
}

/* Editor factory: one lightweight ha-form editor per card. */
function awEditorClass(schema, labels) {
  return class extends HTMLElement {
    setConfig(config) { this._config = config; this._render(); }
    set hass(hass) { this._hass = hass; this._render(); }
    _render() {
      if (!this._hass || !this._config) return;
      if (!this._form) {
        this._form = document.createElement('ha-form');
        this._form.addEventListener('value-changed', (ev) => {
          ev.stopPropagation();
          this.dispatchEvent(new CustomEvent('config-changed', {
            detail: { config: ev.detail.value }, bubbles: true, composed: true,
          }));
        });
        this.appendChild(this._form);
      }
      this._form.hass = this._hass;
      this._form.data = this._config;
      this._form.schema = schema;
      this._form.computeLabel = (s) => labels[s.name] || s.name;
    }
  };
}

const AW_FILTER_SCHEMA = [
  {
    name: 'cantons',
    selector: {
      select: {
        multiple: true, mode: 'dropdown',
        options: ALERTSWISS_CANTONS.map(([value, label]) => ({ value, label })),
      },
    },
  },
  { name: 'max_distance_km', selector: { number: { min: 0, max: 300, step: 5, mode: 'box', unit_of_measurement: 'km' } } },
  {
    name: 'min_severity',
    selector: {
      select: {
        mode: 'dropdown',
        options: [
          { value: 'minor', label: 'Information (minor)' },
          { value: 'moderate', label: 'Warnung (moderate)' },
          { value: 'severe', label: 'Alarm (severe)' },
        ],
      },
    },
  },
];

const AW_FILTER_LABELS = {
  cantons: 'Only these cantons (empty = all; nationwide always shown)',
  max_distance_km: 'Maximum distance from home (0 = no limit)',
  min_severity: 'Minimum severity',
};

function awStubEntity(hass, domain) {
  return Object.keys(hass.states).find(
    (id) => id.startsWith(domain + '.') && hass.states[id].attributes.alerts !== undefined
  ) || Object.keys(hass.states).find(
    (id) => id.startsWith(domain + '.') && hass.states[id].attributes.canton_code !== undefined
  ) || '';
}

/* ------------------------------------------------------------------ ticker */

class AlertswissTickerCard extends HTMLElement {
  static getConfigElement() { return document.createElement('alertswiss-ticker-card-editor'); }

  static getStubConfig(hass) { return { entity: awStubEntity(hass, 'sensor') }; }

  setConfig(config) {
    if (!config.entity) throw new Error('entity is required');
    this._config = config;
    this._key = null;
  }

  getCardSize() { return 1; }
  getGridOptions() { return { columns: 12, rows: 1 }; }

  set hass(hass) {
    this._hass = hass;
    const st = hass.states[this._config.entity];
    if (!st) return;
    if (!this.shadowRoot) this._build();
    const alerts = awFilter(st.attributes.alerts || [], this._config);
    const key = JSON.stringify(alerts.map((a) => a.identifier));
    if (key === this._key) return; /* avoid restarting the animation on every state write */
    this._key = key;
    this._render(alerts);
  }

  _build() {
    const r = this.attachShadow({ mode: 'open' });
    r.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 10px 0; overflow: hidden; }
        .wrap { overflow: hidden; white-space: nowrap; }
        .track { display: inline-block; white-space: nowrap; will-change: transform; }
        .item { display: inline-flex; align-items: center; gap: 7px; margin: 0 20px; font-size: .95rem; }
        .item img { height: 16px; }
        .sep { color: var(--secondary-text-color); }
        .empty { padding: 0 16px; color: var(--secondary-text-color); }
        @keyframes ticker { from { transform: translateX(0); } to { transform: translateX(-50%); } }
      </style>
      <ha-card><div class="wrap"><div class="track" id="track"></div></div></ha-card>`;
    this._track = r.getElementById('track');
  }

  _render(alerts) {
    if (!alerts.length) {
      this._track.style.animation = 'none';
      this._track.innerHTML =
        `<span class="empty">${awEsc(this._config.empty_text || awLang(this._hass).no_alerts)}</span>`;
      return;
    }
    const em = (s) => (s === 'severe' ? '🔴' : s === 'moderate' ? '🟠' : '🔵');
    const html = alerts.map((a) => {
      const label = [a.event, a.publisher].filter(Boolean).map((x) => awEsc(x)).join(' · ');
      return `<span class="item">${em(a.severity)} ${awWappen(a.canton_code, 16)}<span>${label}</span></span><span class="sep">+++</span>`;
    }).join('');
    /* content twice for a seamless loop */
    this._track.innerHTML = html + html;
    const secs = Math.max(20, alerts.length * (this._config.seconds_per_item || 4));
    this._track.style.animation = `ticker ${secs}s linear infinite`;
  }
}

/* -------------------------------------------------------------- alert card */

class AlertswissAlertCard extends HTMLElement {
  static getConfigElement() { return document.createElement('alertswiss-alert-card-editor'); }

  static getStubConfig(hass) { return { entity: awStubEntity(hass, 'binary_sensor') }; }

  setConfig(config) {
    if (!config.entity) throw new Error('entity is required');
    this._config = config;
    this._key = null;
    this._index = 0;
  }

  getCardSize() { return 5; }
  getGridOptions() { return { columns: 12 }; }

  set hass(hass) {
    this._hass = hass;
    const st = hass.states[this._config.entity];
    if (!st) return;
    if (!this.shadowRoot) this._build();
    const key = JSON.stringify(
      [st.state, (st.attributes.alerts || []).map((a) => a.identifier)]
    );
    if (key === this._key) return;
    this._key = key;
    this._index = 0; /* alert set changed — back to the most severe one */
    this._render(st);
  }

  _build() {
    const r = this.attachShadow({ mode: 'open' });
    r.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 16px; }
        .head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
        h2 { margin: 0 0 10px; font-size: 1.15rem; display: flex; align-items: center; gap: 10px; }
        .pager { display: flex; align-items: center; gap: 4px; flex: 0 0 auto; color: var(--secondary-text-color); font-size: .85rem; }
        .pager button { background: var(--secondary-background-color); color: var(--primary-text-color);
                        border: none; border-radius: 8px; width: 28px; height: 28px; cursor: pointer;
                        font-size: 1rem; line-height: 1; }
        .pager button:disabled { opacity: .35; cursor: default; }
        .meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 6px; }
        .meta .wappen { height: 22px; }
        .chip { border-radius: 12px; padding: 2px 10px; font-size: .8rem; font-weight: 600; color: #fff; }
        .pub { font-weight: 600; }
        .time { color: var(--secondary-text-color); font-size: .85rem; margin-bottom: 10px; }
        .desc { white-space: pre-line; margin-bottom: 10px; }
        .inst-title { font-weight: 600; margin-bottom: 4px; }
        ul { margin: 0 0 12px; padding-left: 20px; }
        li { margin-bottom: 4px; }
        a { color: var(--primary-color); }
        .empty { color: var(--secondary-text-color); }
        details { margin-top: 12px; border-top: 1px solid var(--divider-color); padding-top: 8px; }
        summary { cursor: pointer; color: var(--primary-color); font-size: .9rem; user-select: none; }
        .row { display: flex; align-items: center; gap: 10px; padding: 8px 0 0; }
        .dot { width: 10px; height: 10px; border-radius: 50%; flex: 0 0 auto; }
        .row .wappen { height: 18px; flex: 0 0 auto; }
        .row .t a { color: var(--primary-text-color); text-decoration: none; font-weight: 500; }
        .row .t a:hover { text-decoration: underline; }
        .row .sub { color: var(--secondary-text-color); font-size: .8rem; }
      </style>
      <ha-card><div id="body"></div></ha-card>`;
    this._body = r.getElementById('body');
  }

  _render(st) {
    const L = awLang(this._hass);
    const lc = awLangCode(this._hass);
    const c = this._config;

    if (st.state !== 'on') {
      this._body.innerHTML = `<div class="empty">✅ ${awEsc(c.empty_text || L.none_home)}</div>`;
      return;
    }

    /* All home alerts in full detail; fall back to the flat attributes of
       older integration versions that only carried the most severe alert. */
    const alerts = (st.attributes.alerts && st.attributes.alerts.length)
      ? st.attributes.alerts
      : [st.attributes];
    if (this._index >= alerts.length) this._index = 0;
    const a = alerts[this._index];

    const sevColor = ALERTSWISS_SEVERITY_COLOR[a.severity] || ALERTSWISS_SEVERITY_COLOR.unknown;
    const sevName = L.severity[a.severity] || a.severity;

    let pager = '';
    if (alerts.length > 1) {
      pager = `<div class="pager">
        <button id="prev" ${this._index === 0 ? 'disabled' : ''}>‹</button>
        <span>${this._index + 1}/${alerts.length}</span>
        <button id="next" ${this._index === alerts.length - 1 ? 'disabled' : ''}>›</button>
      </div>`;
    }

    let html = `<div class="head"><h2>⚠️ ${awEsc(a.title)}</h2>${pager}</div>`;
    html += `<div class="meta">${awWappen(a.canton_code, 22)}<span class="pub">${awEsc(a.publisher)}</span>`
      + `<span>· ${awEsc(a.event)}</span><span class="chip" style="background:${sevColor}">${awEsc(sevName)}</span></div>`;
    if (a.published) {
      html += `<div class="time">🕐 ${L.published} ${awEsc(awDate(a.published, lc))} (${awRelative(a.published, lc)})</div>`;
    }
    if (c.show_description !== false && a.description) {
      html += `<div class="desc">${awEsc(a.description)}</div>`;
    }
    if (c.show_instructions !== false && Array.isArray(a.instructions) && a.instructions.length) {
      html += `<div class="inst-title">${L.instructions}:</div><ul>`
        + a.instructions.map((i) => `<li>${awEsc(i)}</li>`).join('') + '</ul>';
    }
    if (a.link) {
      html += `<a href="${awEsc(a.link)}" target="_blank" rel="noreferrer">🔗 ${L.official}</a>`;
    }
    this._body.innerHTML = html;

    const prev = this._body.querySelector('#prev');
    const next = this._body.querySelector('#next');
    if (prev) prev.onclick = () => { this._index -= 1; this._render(st); };
    if (next) next.onclick = () => { this._index += 1; this._render(st); };
  }
}

/* --------------------------------------------------------------- list card */

class AlertswissListCard extends HTMLElement {
  static getConfigElement() { return document.createElement('alertswiss-list-card-editor'); }

  static getStubConfig(hass) { return { entity: awStubEntity(hass, 'sensor') }; }

  setConfig(config) {
    if (!config.entity) throw new Error('entity is required');
    this._config = config;
    this._key = null;
  }

  getCardSize() { return 6; }
  getGridOptions() { return { columns: 12 }; }

  set hass(hass) {
    this._hass = hass;
    const st = hass.states[this._config.entity];
    if (!st) return;
    if (!this.shadowRoot) this._build();
    let alerts = awFilter(st.attributes.alerts || [], this._config);
    if (this._config.max_items > 0) alerts = alerts.slice(0, this._config.max_items);
    const key = JSON.stringify(alerts.map((a) => a.identifier));
    if (key === this._key) return;
    this._key = key;
    this._render(alerts);
  }

  _build() {
    const r = this.attachShadow({ mode: 'open' });
    r.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 8px 16px; }
        .title { font-weight: 600; padding: 8px 0 4px; }
        .row { display: flex; align-items: center; gap: 10px; padding: 8px 0;
               border-bottom: 1px solid var(--divider-color); }
        .row:last-child { border-bottom: none; }
        .dot { width: 10px; height: 10px; border-radius: 50%; flex: 0 0 auto; }
        .wappen { height: 18px; flex: 0 0 auto; }
        .txt { min-width: 0; }
        .t a { color: var(--primary-text-color); text-decoration: none; font-weight: 500; }
        .t a:hover { text-decoration: underline; }
        .sub { color: var(--secondary-text-color); font-size: .8rem; }
        .empty { color: var(--secondary-text-color); padding: 12px 0; }
      </style>
      <ha-card><div id="title" class="title" hidden></div><div id="rows"></div></ha-card>`;
    this._title = r.getElementById('title');
    this._rows = r.getElementById('rows');
    if (this._config.title) { this._title.hidden = false; this._title.textContent = this._config.title; }
  }

  _render(alerts) {
    const L = awLang(this._hass);
    const lc = awLangCode(this._hass);
    const c = this._config;
    if (!alerts.length) {
      this._rows.innerHTML = `<div class="empty">✅ ${awEsc(c.empty_text || L.no_alerts)}</div>`;
      return;
    }
    this._rows.innerHTML = alerts.map((a) => {
      const sub = [
        awEsc(a.publisher),
        awEsc(a.event),
        a.nation_wide ? L.nationwide : null,
        c.show_time !== false && a.published ? `🕐 ${awEsc(awDate(a.published, lc))}` : null,
        c.show_distance && a.distance_km != null ? `${a.distance_km} km` : null,
      ].filter(Boolean).join(' · ');
      return `<div class="row">${awDot(a.severity)}${awWappen(a.canton_code, 18)}
        <div class="txt"><div class="t"><a href="${awEsc(a.link)}" target="_blank" rel="noreferrer">${awEsc(a.title)}</a></div>
        <div class="sub">${sub}</div></div></div>`;
    }).join('');
  }
}

/* ------------------------------------------------------------ registration */

const AlertswissTickerCardEditor = awEditorClass(
  [
    { name: 'entity', required: true, selector: { entity: { domain: 'sensor' } } },
    ...AW_FILTER_SCHEMA,
    { name: 'seconds_per_item', selector: { number: { min: 1, max: 30, mode: 'box' } } },
    { name: 'empty_text', selector: { text: {} } },
  ],
  {
    entity: 'Sensor (with "alerts" attribute)',
    ...AW_FILTER_LABELS,
    seconds_per_item: 'Seconds per alert (scroll speed)',
    empty_text: 'Text when there are no alerts',
  },
);

const AlertswissAlertCardEditor = awEditorClass(
  [
    { name: 'entity', required: true, selector: { entity: { domain: 'binary_sensor' } } },
    { name: 'show_description', selector: { boolean: {} } },
    { name: 'show_instructions', selector: { boolean: {} } },
    { name: 'empty_text', selector: { text: {} } },
  ],
  {
    entity: 'Binary sensor (home location affected)',
    show_description: 'Show description',
    show_instructions: 'Show instructions',
    empty_text: 'Text when there is no alert',
  },
);

const AlertswissListCardEditor = awEditorClass(
  [
    { name: 'entity', required: true, selector: { entity: { domain: 'sensor' } } },
    { name: 'title', selector: { text: {} } },
    ...AW_FILTER_SCHEMA,
    { name: 'max_items', selector: { number: { min: 0, max: 25, mode: 'box' } } },
    { name: 'show_time', selector: { boolean: {} } },
    { name: 'show_distance', selector: { boolean: {} } },
    { name: 'empty_text', selector: { text: {} } },
  ],
  {
    entity: 'Sensor (with "alerts" attribute)',
    title: 'Card title',
    ...AW_FILTER_LABELS,
    max_items: 'Maximum number of alerts (0 = all)',
    show_time: 'Show published time',
    show_distance: 'Show distance from home',
    empty_text: 'Text when there are no alerts',
  },
);

customElements.define('alertswiss-ticker-card-editor', AlertswissTickerCardEditor);
customElements.define('alertswiss-ticker-card', AlertswissTickerCard);
customElements.define('alertswiss-alert-card-editor', AlertswissAlertCardEditor);
customElements.define('alertswiss-alert-card', AlertswissAlertCard);
customElements.define('alertswiss-list-card-editor', AlertswissListCardEditor);
customElements.define('alertswiss-list-card', AlertswissListCard);

window.customCards = window.customCards || [];
window.customCards.push(
  {
    type: 'alertswiss-ticker-card',
    name: 'Alertswiss Ticker',
    description: 'Scrolling ticker with the active Alertswiss public alerts',
  },
  {
    type: 'alertswiss-alert-card',
    name: 'Alertswiss Alert',
    description: 'Details of the public alert affecting the home location',
  },
  {
    type: 'alertswiss-list-card',
    name: 'Alertswiss List',
    description: 'Filterable list of the active Alertswiss public alerts',
  },
);

/* ===================================================================== */
/* The strategy block below is wrapped in an IIFE: several of these       */
/* integrations ship the same core, and without the wrapper two of them   */
/* installed side by side would declare the same consts in one scope.     */
/* ===================================================================== */
(() => {
/* =====================================================================
 * Dashboard strategy core — shared building blocks
 * =====================================================================
 * A Lovelace dashboard strategy generates a dashboard in the browser at
 * render time. Nothing is written to .storage: the dashboard belongs to
 * the user, the integration only supplies the recipe.
 *
 * ⚠️ This block is duplicated into every integration that ships a
 * strategy. Each integration is its own HACS repository and must not
 * depend on another one being installed, so a shared file is not an
 * option. Keep the copies in sync and bump CORE_VERSION when the shared
 * part changes — it identifies which revision a copy was taken from.
 * ===================================================================== */

const CORE_VERSION = "1.1.1";

/* 1.1.1 - review follow-ups on the `strategy:` options
 *   (a) `map: false` only dropped the view with path "map". Where the map is
 *       a section inside another view (or a card in a panel view) it stayed
 *       visible. The option now also strips map cards out of every view: a
 *       section left with nothing but headings is dropped, and a view that
 *       ends up without any sections or cards is dropped as well.
 *   (b) The view flavour hardcoded max_columns: 2 and discarded the user's
 *       `max_columns`. It now uses the option when valid, else the value of
 *       the first sections view, else 2.
 *   (c) The view flavour copied only sections and cards, losing a view's
 *       `header` and `badges`. Both are carried over from the first view
 *       that has them. */

/* --- Registry access -------------------------------------------------
 * The registries are the only reliable way to find an integration's
 * entities: entity_id patterns are user-editable, unique_id is not.
 * Both calls are cheap and cached by the frontend for the render pass.
 */
async function loadRegistry(hass) {
  const [entities, devices] = await Promise.all([
    hass.callWS({ type: "config/entity_registry/list" }),
    hass.callWS({ type: "config/device_registry/list" }),
  ]);
  return { entities, devices };
}

/** All registry entries belonging to one integration (platform == domain). */
function entriesOfDomain(entities, domain) {
  return entities.filter((e) => e.platform === domain && !e.disabled_by);
}

/** Registry entries of one config entry, keyed by unique_id suffix.
 *  Mirrors the `f"{entry_id}_{suffix}"` convention the integrations use. */
function bySuffix(entities, configEntryId) {
  const out = {};
  const prefix = `${configEntryId}_`;
  for (const e of entities) {
    if (e.config_entry_id !== configEntryId) continue;
    if (typeof e.unique_id === "string" && e.unique_id.startsWith(prefix)) {
      out[e.unique_id.slice(prefix.length)] = e.entity_id;
    }
  }
  return out;
}

/** Group an integration's entities by the device they belong to.
 *  Returns [{device, entities:[registryEntry,...]}] sorted by device name. */
function groupByDevice(domainEntries, devices) {
  const byId = new Map(devices.map((d) => [d.id, d]));
  const groups = new Map();
  for (const e of domainEntries) {
    if (!e.device_id) continue;
    if (!groups.has(e.device_id)) groups.set(e.device_id, []);
    groups.get(e.device_id).push(e);
  }
  return [...groups.entries()]
    .map(([id, list]) => ({ device: byId.get(id), entities: list }))
    .filter((g) => g.device)
    .sort((a, b) => deviceName(a.device).localeCompare(deviceName(b.device)));
}

function deviceName(device) {
  return device.name_by_user || device.name || "";
}

/* --- Card helpers ---------------------------------------------------- */

const heading = (text, icon, badges) => {
  const card = { type: "heading", heading: text };
  if (icon) card.icon = icon;
  if (badges && badges.length) card.badges = badges;
  return card;
};

const grid = (cards, columnSpan) => {
  const section = { type: "grid", cards: cards.filter(Boolean) };
  if (columnSpan) section.column_span = columnSpan;
  return section;
};

const tile = (entity, extra = {}) => ({ type: "tile", entity, ...extra });

/** Map card fed from the integration's geo_location source.
 *  Deliberately uses geo_location_sources instead of an entity list: the
 *  markers are hidden entities, and the source keeps working when the
 *  set of markers changes between renders.
 *  labelAttribute writes the marker label into the source object, which is
 *  where the map card reads a geo-location source's label config from — the
 *  card-level label_mode only applies to `entities`. */
const mapCard = (domain, opts = {}) => ({
  type: "map",
  geo_location_sources: [
    opts.labelAttribute
      ? { source: domain, label_mode: "attribute", attribute: opts.labelAttribute }
      : domain,
  ],
  entities: opts.entities || ["zone.home"],
  default_zoom: opts.zoom ?? 8,
  theme_mode: "auto",
  grid_options: { columns: 12, rows: opts.rows ?? 6 },
});

/** Shown instead of an empty dashboard — an empty dashboard looks broken
 *  and gives the user nothing to act on. */
const emptyNotice = (text) => ({
  type: "markdown",
  content: text,
});

/* --- Localisation ----------------------------------------------------
 * Strategies run in the frontend, so hass.language is authoritative.
 * Falls back to English for any language the integration does not ship.
 */
function translator(strings, hass) {
  const lang = (hass.language || "en").split("-")[0];
  const table = strings[lang] || strings.en;
  return (key) => (table && table[key]) || (strings.en && strings.en[key]) || key;
}

/* --- Strategy base ---------------------------------------------------
 * Wraps the parts every strategy repeats: load registries, bail out
 * gracefully when the integration is not set up, and hand the concrete
 * strategy a prepared context.
 */

/* Options a user may put under `strategy:` in the raw configuration editor.
 * They are handled here in the core, so every integration supports the same
 * set without shipping its own option code:
 *
 *   map: false        drop the map: the full-screen map view as well as the
 *                     map cards inside section and panel views
 *   title: "..."      override the title
 *   max_columns: 3    column count of the generated section views (the view
 *                     flavour honours it too)
 *
 * Unknown keys are ignored on purpose - a strategy config is free-form, and a
 * typo should not take the dashboard down. */
const validColumns = (value) => {
  const cols = Number(value);
  return Number.isFinite(cols) && cols > 0 ? cols : undefined;
};

const isMapCard = (card) => Boolean(card) && card.type === "map";
const isHeadingCard = (card) => Boolean(card) && card.type === "heading";

/* Remove the map cards of one view. A section is dropped once only headings
 * remain - a heading merely labels the map that was just removed. Returns
 * null when nothing is left to show; views without a map card come back
 * untouched. */
const withoutMapCards = (view) => {
  let touched = false;
  const out = { ...view };
  if (Array.isArray(view.sections)) {
    out.sections = [];
    for (const section of view.sections) {
      const cards = Array.isArray(section.cards) ? section.cards : [];
      if (!cards.some(isMapCard)) {
        out.sections.push(section);
        continue;
      }
      touched = true;
      const rest = cards.filter((c) => !isMapCard(c));
      if (rest.some((c) => !isHeadingCard(c))) out.sections.push({ ...section, cards: rest });
    }
  }
  if (Array.isArray(view.cards) && view.cards.some(isMapCard)) {
    touched = true;
    out.cards = view.cards.filter((c) => !isMapCard(c));
  }
  if (!touched) return view;
  const empty = !(out.sections && out.sections.length) && !(out.cards && out.cards.length);
  return empty ? null : out;
};

const applyViewOptions = (views, config) => {
  const cfg = config || {};
  let out = views;
  if (cfg.map === false) {
    out = out
      .filter((v) => v.path !== "map")
      .map(withoutMapCards)
      .filter(Boolean);
  }
  const cols = validColumns(cfg.max_columns);
  if (cols) {
    out = out.map((v) => (v.type === "sections" ? { ...v, max_columns: cols } : v));
  }
  return out;
};

/* A view strategy must return exactly ONE view, while build() yields a list.
 * Section views are merged by concatenating their sections. A panel view (the
 * map) has no sections, so its cards become one full-width section instead -
 * that keeps the map visible rather than silently dropping it. */
const flattenToView = (views, title, icon, config) => {
  const sections = [];
  for (const v of views) {
    if (Array.isArray(v.sections) && v.sections.length) {
      sections.push(...v.sections);
    } else if (Array.isArray(v.cards) && v.cards.length) {
      sections.push(
        grid(
          v.cards.map((c) => ({
            ...c,
            grid_options: { columns: "full", rows: (c.grid_options || {}).rows ?? 8 },
          }))
        )
      );
    }
  }
  const sized = views.find((v) => v.type === "sections" && validColumns(v.max_columns));
  const view = {
    title,
    icon,
    type: "sections",
    max_columns: validColumns((config || {}).max_columns) ?? (sized ? validColumns(sized.max_columns) : 2),
    sections,
  };
  // header and badges live outside the sections and would be lost by the
  // merge above - keep the first ones the build produced.
  const withHeader = views.find((v) => v.header);
  if (withHeader) view.header = withHeader.header;
  const withBadges = views.find((v) => Array.isArray(v.badges) && v.badges.length);
  if (withBadges) view.badges = withBadges.badges;
  return view;
};

function defineDashboardStrategy(name, { domain, title, icon, build, strings, description }) {
  /* Shared by both strategy flavours: everything up to the finished view list. */
  const buildViews = async (config, hass) => {
    const t = translator(strings || {}, hass);
    let registry;
    try {
      registry = await loadRegistry(hass);
    } catch (err) {
      // Registry unreachable: render a readable message rather than
      // letting the dashboard fail with a blank screen.
      return [{ title: title, cards: [emptyNotice(`\u26a0\ufe0f ${err}`)] }];
    }
    const domainEntries = entriesOfDomain(registry.entities, domain);
    if (!domainEntries.length) {
      return [{ title: title, icon, cards: [emptyNotice(t("not_configured"))] }];
    }
    const views = await build({
      hass,
      config,
      t,
      domain,
      entities: domainEntries,
      devices: registry.devices,
      allEntities: registry.entities,
      helpers: { heading, grid, tile, mapCard, emptyNotice, bySuffix, groupByDevice, deviceName },
    });
    return applyViewOptions(views, config);
  };

  class Strategy extends HTMLElement {
    static async generate(config, hass) {
      const views = await buildViews(config, hass);
      return { title: (config && config.title) || title, views };
    }
  }

  /* The view flavour: fills a single view of a dashboard the user built
   * themselves, so adjusting the layout no longer requires "take control". */
  class ViewStrategy extends HTMLElement {
    static async generate(config, hass) {
      const views = await buildViews(config, hass);
      return flattenToView(views, (config && config.title) || title, icon, config);
    }
  }

  // getCreateSuggestions lets Home Assistant offer sensible defaults when the
  // strategy is picked from the "new dashboard" dialog.
  Strategy.getCreateSuggestions = () => ({ title, icon });

  customElements.define(`ll-strategy-dashboard-${name}`, Strategy);
  customElements.define(`ll-strategy-view-${name}`, ViewStrategy);

  // Announce the strategy to the frontend so it appears in the dashboard
  // creation dialog instead of having to be typed into the raw editor.
  window.customStrategies = window.customStrategies || [];
  if (!window.customStrategies.some((s) => s.type === name)) {
    window.customStrategies.push({
      type: name,
      strategyType: "dashboard",
      name: title,
      description: description || "",
    });
  }
  return Strategy;
}


/* =====================================================================
 * Dashboard strategy: Swiss Public Alerts (Alertswiss)
 * =====================================================================
 * Reproduces the dashboard that earlier versions created in the user's
 * Lovelace storage — but generated in the browser at render time, so
 * nothing is written to .storage and the user stays in control.
 *
 * Usage: create an empty dashboard, open the raw editor and use
 *
 *     strategy:
 *       type: custom:swiss-public-alerts
 *
 * Optional: `title:` overrides the dashboard title.
 * ===================================================================== */

const AW_STRINGS = {
  en: {
    view: "Alerts",
    header: "# Public alerts (Alertswiss)\nOfficial alerts published by the Swiss Federal Office for Civil Protection",
    home: "At home",
    map: "Map",
    all: "All alerts in Switzerland",
    hazards: "Natural hazard warnings",
    count: "Alert count",
    no_alerts: "No active alerts",
    not_configured:
      "### Swiss Public Alerts is not set up yet\nAdd the integration under **Settings → Devices & services** first — this dashboard fills itself automatically afterwards.",
  },
  de: {
    view: "Meldungen",
    header: "# Behördenmeldungen Alertswiss\nOffizielle Meldungen des Bundesamts für Bevölkerungsschutz",
    home: "Zuhause",
    map: "Karte",
    all: "Alle Meldungen Schweiz",
    hazards: "Naturgefahren",
    count: "Anzahl Meldungen",
    no_alerts: "Keine aktiven Meldungen",
    not_configured:
      "### Alertswiss ist noch nicht eingerichtet\nFüge die Integration zuerst unter **Einstellungen → Geräte & Dienste** hinzu — dieses Dashboard füllt sich danach von selbst.",
  },
  fr: {
    view: "Alertes",
    header: "# Alertes officielles Alertswiss\nAlertes publiées par l'Office fédéral de la protection de la population",
    home: "À la maison",
    map: "Carte",
    all: "Toutes les alertes en Suisse",
    hazards: "Dangers naturels",
    count: "Nombre d'alertes",
    no_alerts: "Aucune alerte active",
    not_configured:
      "### Alertswiss n'est pas encore configuré\nAjoutez d'abord l'intégration sous **Paramètres → Appareils et services**.",
  },
  it: {
    view: "Allerte",
    header: "# Allerte ufficiali Alertswiss\nAllerte pubblicate dall'Ufficio federale della protezione della popolazione",
    home: "A casa",
    map: "Mappa",
    all: "Tutte le allerte in Svizzera",
    hazards: "Pericoli naturali",
    count: "Numero di allerte",
    no_alerts: "Nessuna allerta attiva",
    not_configured:
      "### Alertswiss non è ancora configurato\nAggiungi prima l'integrazione in **Impostazioni → Dispositivi e servizi**.",
  },
};

defineDashboardStrategy("swiss-public-alerts", {
  domain: "swiss_public_alerts",
  title: "Alertswiss",
  icon: "mdi:alert-outline",
  description: "Official Swiss public alerts: ticker, home status, map and hazard levels.",
  strings: AW_STRINGS,

  async build({ t, config, domain, entities, allEntities, helpers }) {
    const { heading, grid, tile, mapCard } = helpers;

    // One config entry per region; the first one carries the home-related
    // sensors. Suffix lookup mirrors the integration's unique_id scheme,
    // so a user-renamed entity_id keeps working.
    const entryId = entities.find((e) => e.config_entry_id)?.config_entry_id;
    const ids = helpers.bySuffix(allEntities, entryId);

    const active = ids.active_alerts;
    const homeCount = ids.home_alerts;
    const affected = ids.home_affected;
    const hasHazards = Boolean(ids.highest_hazard);

    const sections = [];

    // Ticker across the full width — the one card that is always useful,
    // even when nothing is going on.
    if (active) {
      sections.push(
        grid(
          [
            {
              type: "custom:alertswiss-ticker-card",
              entity: active,
              seconds_per_item: 4,
              empty_text: t("no_alerts"),
            },
          ],
          2
        )
      );
    }

    if (affected || homeCount) {
      sections.push(
        grid([
          heading(t("home"), "mdi:home-alert"),
          affected && tile(affected, { color: "red", grid_options: { columns: 6 } }),
          homeCount &&
            tile(homeCount, { name: t("count"), color: "orange", grid_options: { columns: 6 } }),
          affected && { type: "custom:alertswiss-alert-card", entity: affected },
        ])
      );
    }

    sections.push(
      grid([heading(t("map"), "mdi:map-marker-alert"), mapCard(domain, { zoom: 8 })])
    );

    if (active) {
      sections.push(
        grid(
          [
            heading(t("all"), "mdi:format-list-bulleted", [
              { type: "entity", entity: active, show_state: true },
            ]),
            {
              type: "custom:alertswiss-list-card",
              entity: active,
              show_time: true,
              show_distance: true,
            },
          ],
          2
        )
      );
    }

    // Natural hazard sensors only exist when the user enabled that option
    // during setup — the section appears and disappears with them.
    if (hasHazards) {
      // Highest level first, then the individual hazards in a stable order —
      // object key order would otherwise shuffle the tiles between renders.
      const hazardTiles = [
        tile(ids.highest_hazard, { grid_options: { columns: 12 } }),
        ...Object.keys(ids)
          .filter((s) => s.startsWith("hazard_"))
          .sort()
          .map((s) => tile(ids[s], { grid_options: { columns: 6 } })),
      ];
      sections.push(grid([heading(t("hazards"), "mdi:image-filter-hdr"), ...hazardTiles], 2));
    }

    return [
      {
        title: t("view"),
        path: "alerts",
        type: "sections",
        icon: "mdi:alert-outline",
        max_columns: 2,
        header: {
          layout: "responsive",
          card: { type: "markdown", text_only: true, content: t("header") },
        },
        sections,
      },
    ];
  },
});
})();
