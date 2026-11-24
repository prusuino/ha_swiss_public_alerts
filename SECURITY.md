# Security Policy

## Supported Versions

Only the latest release is supported. Please update to the latest version before reporting an issue.

## Reporting a Vulnerability

What it contacts: `alertswiss.ch` for the alerts, `naturgefahren.ch` for the danger levels (when switched on), and — only when a dashboard card asks for a hazard map — `data.geo.admin.ch` for the open geodata of the FOEN. The requests carry no location. The maps are served to signed-in users of your Home Assistant under `/api/swiss_public_alerts/hazard_map`.

This integration only reads publicly published data from its official Swiss data source over HTTPS — it does not handle credentials, personal data, or write access to any external system. If you still believe you have found a security issue (e.g. in how data is parsed or how entities are exposed), please report it privately via [GitHub Security Advisories](../../security/advisories/new) rather than opening a public issue.

For anything that is not security-sensitive (bugs, feature requests), please use the regular [Issues](../../issues) tab instead.
