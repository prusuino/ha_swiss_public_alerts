/* Alertswiss card suite — shipped and auto-registered by the Swiss Public
 * Alerts integration.
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
      html += `<div class="time">🕐 ${L.published} ${awDate(a.published, lc)} (${awRelative(a.published, lc)})</div>`;
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
        c.show_time !== false && a.published ? `🕐 ${awDate(a.published, lc)}` : null,
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
