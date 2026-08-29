# Changelog

## 1.3.0 — 2026-08-29

- **Fixed: map markers go unavailable while the Alertswiss feed is unreachable**, as the sensors already did. Until now a marker kept showing its last known alert indefinitely, however stale the data behind it was; it now follows the feed and comes back by itself once the feed does.
- **New: strategy options.** Keys under `strategy:` are now honoured — `map: false`, `title`, `max_columns`. Unknown keys are ignored, so a typo cannot break the dashboard.
- **New: view strategy.** Next to the dashboard strategy the card file now also registers `ll-strategy-view-...`, so a single view of your own dashboard can be filled by the strategy (`views: - strategy: {type: custom:...}`) while every other view stays hand-editable. Until now the only way to change anything was *Take control*, which permanently stops the dashboard from following your config entries.
- Documented: an entity id follows the localized entity name (`sensor.alertswiss_active_alerts_switzerland` on an English instance, `sensor.alertswiss_aktive_meldungen_schweiz` on a German one), so it differs between installations, and a map marker's id follows the alert title. The README now shows how to look up the ids and how to address markers independently of the language — the map card's `geo_location_sources` and the `source` attribute in templates.
- README: the installation instructions now describe the HACS default listing, with a My Home Assistant button that opens the integration directly in HACS.
- Nothing to do on your side: no migration runs, no configuration changes, and every existing entity keeps its entity id and its history.

## 1.2.0

The integration no longer creates or deletes dashboards and Lovelace
resources. Writing into another component's storage is not something an
integration should do on its own initiative, and the previous implementation
relied on internal Home Assistant APIs that carry no stability guarantee.

**Breaking:**

- The automatically created "Alerts" dashboard is gone. Existing dashboards
  are left untouched — this release simply stops creating, extending and
  deleting them. If you want to keep the dashboard you already have, do
  nothing; it is now yours to edit freely.
- The bundled cards are no longer registered as a Lovelace resource
  automatically. Register the file once under **Settings → Dashboards → ⋮ →
  Resources** with the URL `/swiss_public_alerts/static/alertswiss-ticker-card.js`
  and type *JavaScript module*.

**New:**

- A **dashboard strategy** replaces the auto-created dashboard. It builds the
  same layout — ticker, "At home" section, map, full list, and the natural
  hazard levels when enabled — but generates it in the browser at display
  time, without writing anything to your Lovelace storage. Create an empty
  dashboard and set `strategy: {type: custom:swiss-public-alerts}` in the raw
  configuration editor; the README has step-by-step instructions. Unlike a
  copied YAML config, it follows along when config entries are added or
  removed.

**Fixed:**

- Map marker entities that a user made visible by hand are no longer hidden
  again on every restart. New entities are still hidden by default so they
  don't flood the auto-generated overview map; existing ones are no longer
  rewritten.

**Other:**

- Minimum Home Assistant version declared as 2024.12.0, matching what the
  options flow actually requires. It was previously declared as 2024.7.0,
  where the options dialog would have failed.

## 1.1.0

- New optional data source: natural hazard danger levels from the Natural
  Hazards Portal of the Confederation (naturgefahren.ch — MeteoSwiss, FOEN,
  SLF, SED)
- Data sources are selectable during setup and in the options (default:
  Alertswiss only, existing installations are unaffected)
- One sensor per hazard process (wind, thunderstorm, rain, snow, slippery
  roads, heat wave, frost, forest fire, flood, avalanches, drought,
  earthquake) with the official danger level 1–5 as state (0 = no warning),
  plus a "highest danger level" sensor across all processes
- Location matching via Swiss postal code using the portal's own warning
  regions (separate region systems per specialist agency)
- Outlook (pre-warning) levels, expiry time, and the official description
  text as sensor attributes

## 1.0.1

- Declare `http` and `lovelace` as manifest dependencies (hassfest validation)

## 1.0.0

Initial release.

- Polls the public Alertswiss feed (10-minute default interval, configurable)
- Point-in-polygon matching of the official alert area polygons against the
  Home Assistant home location — "home affected" as a binary sensor with the
  full alert (description, instructions, link) as attributes
- Sensors for all active alerts in Switzerland and for alerts covering the
  home location, each with per-alert summaries (canton, severity, published
  time, distance from home)
- Map markers (`geo_location`) with Alertswiss-style severity symbols,
  hidden from auto-generated maps and shown only on explicit map cards
- Three bundled Lovelace cards with visual editors: scrolling ticker,
  home-alert detail view (with paging), filterable alert list — filters by
  canton, distance from home, and minimum severity
- Automatically created "Alerts" dashboard (removed again with the
  integration)
- Cantonal coat-of-arms support in all cards
- German, English, French, and Italian translations
- Filters out test alerts and all-clear messages; nationwide alerts always
  pass the card filters
