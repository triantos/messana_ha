from __future__ import annotations

DOMAIN = "messana"

CONF_BASE_URL = "base_url"
CONF_API_KEY = "api_key"

# Options
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ZONE_COUNT_OVERRIDE = "zone_count_override"

DEFAULT_SCAN_INTERVAL_SECONDS = 30
DEFAULT_ZONE_COUNT_OVERRIDE = 0  # 0 means "no override; use API zoneCount"

PLATFORMS: list[str] = ["climate", "sensor", "switch", "select"]
