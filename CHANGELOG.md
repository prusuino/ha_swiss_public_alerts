# Changelog

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
