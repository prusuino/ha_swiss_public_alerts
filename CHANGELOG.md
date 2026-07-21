# Changelog

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
