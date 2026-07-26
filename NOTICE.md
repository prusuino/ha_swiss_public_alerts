# Data Source & Attribution

This integration retrieves public alert data at runtime from the **Alertswiss** platform (`www.alert.swiss`), operated by the Swiss **Federal Office for Civil Protection (FOCP/BABS)** together with the cantons.

According to the Alertswiss legal notice, the website content is copyright of the Swiss federal authorities and released under **[CC BY-NC-SA 2.5](https://creativecommons.org/licenses/by-nc-sa/2.5/)**. Content may be passed on **free of charge only** and requires the minimal source reference:

> **Quelle: www.alertswiss.ch**

This integration fulfills that requirement by setting the `attribution` attribute (`"Quelle: www.alertswiss.ch (Alertswiss, Federal Office for Civil Protection)"`) on every entity it creates, which Home Assistant surfaces in the entity's "More Info" dialog. The integration itself is free and non-commercial. If you build dashboards, automations, or republish this data elsewhere, please keep that attribution visible and respect the non-commercial license of the data.

The cantonal coats of arms bundled with this integration are official Swiss insignia (public domain as state emblems, sourced from Wikimedia Commons). They are used purely to indicate which canton issued an alert; no affiliation with or endorsement by any authority is implied. The severity symbols are original artwork of this project, merely following the same visual convention (shape/color) as official Swiss alerting so that their meaning is immediately familiar.

## Natural Hazards Portal (optional data source)

When enabled, this integration additionally retrieves the current natural hazard danger levels from the **Natural Hazards Portal of the Confederation** (`www.naturgefahren.ch` / `www.natural-hazards.ch`), where the federal specialist agencies (MeteoSwiss, FOEN, SLF, SED) publish their joint hazard assessment. Entities based on this data carry the attribution:

> **Quelle: www.naturgefahren.ch**

Warnings may only be passed on promptly and unaltered; this integration polls the portal's published data at a short interval and does not modify its content. The bundled location-to-warning-region dataset is a snapshot derived from the portal's public location list and is only used to determine which warning regions apply to the configured postal code.

This integration is unofficial and not affiliated with, endorsed by, or supported by the FOCP/BABS, Alertswiss, or the natural hazards specialist agencies of the Confederation. It only reads their publicly published data.

Official platforms: https://www.alert.swiss/ · https://www.naturgefahren.ch/
