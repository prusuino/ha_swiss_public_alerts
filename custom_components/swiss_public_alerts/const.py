"""Constants for the Swiss Public Alerts integration."""

from __future__ import annotations

DOMAIN = "swiss_public_alerts"

# The Alertswiss terms of use require the minimal source reference
# "Quelle: www.alertswiss.ch" whenever content is passed on.
ATTRIBUTION = "Quelle: www.alertswiss.ch (Alertswiss, Federal Office for Civil Protection)"
MANUFACTURER = "Alertswiss (Federal Office for Civil Protection)"

HAZARDS_ATTRIBUTION = "Quelle: www.naturgefahren.ch (Natural Hazards Portal of the Confederation)"
HAZARDS_MANUFACTURER = "Naturgefahrenportal (MeteoSwiss, FOEN, SLF, SED)"

FEED_URL_TEMPLATE = (
    "https://www.alert.swiss/content/alertswiss-internet/{language}/home/"
    "_jcr_content/polyalert.alertswiss_alerts.actual.json"
)
ALERT_URL_TEMPLATE = (
    "https://www.alert.swiss/content/alertswiss-internet/{language}/home.html#{identifier}"
)

HAZARDS_BASE_URL = "https://www.naturgefahren.ch"
HAZARDS_VERSIONS_URL = f"{HAZARDS_BASE_URL}/product/output/versions.json"
HAZARDS_PRODUCT_KEY = "versioned/danger/v3"
HAZARDS_DANGER_PATH = "/product/output/versioned/danger/v3/"

CONF_LANGUAGE = "language"
CONF_MINIMUM_SEVERITY = "minimum_severity"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_DATA_SOURCES = "data_sources"
CONF_PLZ = "plz"

SOURCE_ALERTSWISS = "alertswiss"
SOURCE_HAZARDS = "natural_hazards"
DATA_SOURCES = [SOURCE_ALERTSWISS, SOURCE_HAZARDS]
DEFAULT_DATA_SOURCES = [SOURCE_ALERTSWISS]

# Hazard process keys exactly as they appear in the portal's dangers.json.
HAZARD_TYPES = [
    "wind",
    "thunderstorm",
    "rain",
    "snow",
    "slippery-roads",
    "heat-wave",
    "frost",
    "forestfire",
    "flood",
    "avalanches",
    "drought",
    "earthquake",
]

HAZARD_ICONS = {
    "wind": "mdi:weather-windy",
    "thunderstorm": "mdi:weather-lightning",
    "rain": "mdi:weather-pouring",
    "snow": "mdi:weather-snowy-heavy",
    "slippery-roads": "mdi:snowflake-alert",
    "heat-wave": "mdi:thermometer-alert",
    "frost": "mdi:snowflake-thermometer",
    "forestfire": "mdi:fire-alert",
    "flood": "mdi:home-flood",
    "avalanches": "mdi:landslide",
    "drought": "mdi:water-alert",
    "earthquake": "mdi:vibrate",
}

LANGUAGES = ["de", "en", "fr", "it"]
DEFAULT_LANGUAGE = "de"

SEVERITY_MINOR = "minor"
SEVERITY_MODERATE = "moderate"
SEVERITY_SEVERE = "severe"
SEVERITY_UNKNOWN = "unknown"

SEVERITIES = [SEVERITY_MINOR, SEVERITY_MODERATE, SEVERITY_SEVERE]
SEVERITY_RANK = {
    SEVERITY_UNKNOWN: 0,
    SEVERITY_MINOR: 1,
    SEVERITY_MODERATE: 2,
    SEVERITY_SEVERE: 3,
}
DEFAULT_MINIMUM_SEVERITY = SEVERITY_MINOR

DEFAULT_UPDATE_INTERVAL = 600
MIN_UPDATE_INTERVAL = 60
MAX_UPDATE_INTERVAL = 3600

DEFAULT_TIMEOUT = 20

MAX_LISTED_ALERTS = 25

STATIC_URL_BASE = "/swiss_public_alerts/static"

# Publisher keyword (lowercase, matched on word boundaries) -> canton code.
# Covers German, French and Italian canton names as they appear in feed
# publisher names such as "Kanton Graubünden - Chantun Grischun".
CANTON_KEYWORDS = {
    "aargau": "ag", "argovie": "ag", "argovia": "ag",
    "appenzell ausserrhoden": "ar", "appenzell innerrhoden": "ai",
    "basel-landschaft": "bl", "bâle-campagne": "bl",
    "basel-stadt": "bs", "bâle-ville": "bs",
    "bern": "be", "berne": "be", "berna": "be",
    "freiburg": "fr", "fribourg": "fr", "friburgo": "fr",
    "genf": "ge", "genève": "ge", "geneve": "ge", "ginevra": "ge",
    "glarus": "gl", "glaris": "gl", "glarona": "gl",
    "graubünden": "gr", "grischun": "gr", "grigioni": "gr", "grisons": "gr",
    "jura": "ju",
    "luzern": "lu", "lucerne": "lu", "lucerna": "lu",
    "neuenburg": "ne", "neuchâtel": "ne", "neuchatel": "ne",
    "nidwalden": "nw", "nidwald": "nw",
    "obwalden": "ow", "obwald": "ow",
    "schaffhausen": "sh", "schaffhouse": "sh",
    "schwyz": "sz",
    "solothurn": "so", "soleure": "so", "soletta": "so",
    "st.gallen": "sg", "st. gallen": "sg", "saint-gall": "sg", "san gallo": "sg",
    "tessin": "ti", "ticino": "ti",
    "thurgau": "tg", "thurgovie": "tg", "turgovia": "tg",
    "uri": "ur",
    "waadt": "vd", "vaud": "vd",
    "wallis": "vs", "valais": "vs", "vallese": "vs",
    "zug": "zg", "zoug": "zg", "zugo": "zg",
    "zürich": "zh", "zurich": "zh", "zurigo": "zh",
}
