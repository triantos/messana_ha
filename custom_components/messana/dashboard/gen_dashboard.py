#!/usr/bin/env python3
"""Generate a Messana HVAC dashboard YAML by querying Home Assistant registries.

Usage:
    python gen_dashboard.py --ha-url http://homeassistant.local:8123 --ha-token YOUR_TOKEN

    Or if running from the HA config directory (can read registry files directly):
    python gen_dashboard.py --config-dir /config

Environment variables can also be used:
    HA_URL, HA_TOKEN, HA_CONFIG_DIR

The script will:
1. Discover Messana climate entities from Home Assistant
2. Look up area and floor assignments for each entity
3. Group zones by floor automatically
4. Output a complete dashboard YAML file
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
import yaml


class HomeAssistantClient:
    """Client to query Home Assistant REST API."""

    def __init__(self, base_url: str, token: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_states(self) -> list[dict[str, Any]]:
        """Get all entity states."""
        resp = requests.get(
            f"{self.base_url}/api/states",
            headers=self.headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def render_template(self, template: str) -> str:
        """Render a Jinja2 template."""
        resp = requests.post(
            f"{self.base_url}/api/template",
            headers=self.headers,
            json={"template": template},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.text


def load_registry_file(config_dir: Path, filename: str) -> dict[str, Any]:
    """Load a Home Assistant registry file from .storage directory."""
    path = config_dir / ".storage" / filename
    if not path.exists():
        return {}
    with open(path) as f:
        data = json.load(f)
    return data.get("data", {})


def discover_zones_from_registry(config_dir: Path) -> tuple[
    list[dict[str, Any]],
    dict[str, list[dict[str, Any]]],
]:
    """Discover Messana zones from HA registry files.

    Returns:
        Tuple of (zones_list, floors_dict)
    """
    # Load registries
    entity_reg = load_registry_file(config_dir, "core.entity_registry")
    area_reg = load_registry_file(config_dir, "core.area_registry")
    floor_reg = load_registry_file(config_dir, "core.floor_registry")

    # Build area lookup: area_id -> {name, floor_id}
    areas = {}
    for area in area_reg.get("areas", []):
        areas[area["id"]] = {
            "name": area.get("name", area["id"]),
            "floor_id": area.get("floor_id"),
        }

    # Build floor lookup: floor_id -> {name, level}
    floors = {}
    for floor in floor_reg.get("floors", []):
        floors[floor["floor_id"]] = {
            "name": floor.get("name", floor["floor_id"]),
            "level": floor.get("level", 0),
        }

    # Find Messana climate entities and build zone info
    zones = []
    for entity in entity_reg.get("entities", []):
        entity_id = entity.get("entity_id", "")
        platform = entity.get("platform", "")

        # Look for Messana climate entities
        if platform == "messana" and entity_id.startswith("climate."):
            # Extract the slug from entity_id (e.g., "climate.basement" -> "basement")
            slug = entity_id.replace("climate.", "")

            # Get the friendly name from the entity or derive from slug
            name = entity.get("name") or entity.get("original_name") or slug.replace("_", " ").title()

            # Look up area and floor
            area_id = entity.get("area_id")
            area_name = None
            floor_id = None
            floor_name = None

            if area_id and area_id in areas:
                area_info = areas[area_id]
                area_name = area_info["name"]
                floor_id = area_info.get("floor_id")
                if floor_id and floor_id in floors:
                    floor_name = floors[floor_id]["name"]

            zones.append({
                "entity_id": entity_id,
                "name": name,
                "slug": slug,
                "area_id": area_id,
                "area_name": area_name,
                "floor_id": floor_id,
                "floor_name": floor_name,
                "climate_entity": entity_id,
                "humidity_sensor": f"sensor.{slug}_humidity",
                "active_binary_sensor": f"binary_sensor.{slug}_active",
                "detach_button": f"button.{slug}_detach_schedule",
            })

    # Sort floors by level
    floor_order = {
        fid: info["level"] for fid, info in floors.items()
    }

    # Group zones by floor
    floors_grouped: dict[str, list[dict[str, Any]]] = {}
    unassigned = []

    for zone in zones:
        floor_name = zone.get("floor_name")
        if floor_name:
            if floor_name not in floors_grouped:
                floors_grouped[floor_name] = []
            floors_grouped[floor_name].append(zone)
        else:
            unassigned.append(zone)

    # Sort floors by level (using floor_id to look up level)
    def get_floor_level(floor_name: str) -> int:
        for fid, info in floors.items():
            if info["name"] == floor_name:
                return info["level"]
        return 999

    sorted_floors = dict(
        sorted(floors_grouped.items(), key=lambda x: get_floor_level(x[0]))
    )

    # Add unassigned zones at the end
    if unassigned:
        sorted_floors["Other"] = unassigned

    return zones, sorted_floors


def discover_zones_from_api(client: HomeAssistantClient) -> tuple[
    list[dict[str, Any]],
    dict[str, list[dict[str, Any]]],
]:
    """Discover Messana zones from HA REST API.

    Returns:
        Tuple of (zones_list, floors_dict)
    """
    # Get all states to find Messana climate entities
    states = client.get_states()

    zones = []
    for state in states:
        entity_id = state.get("entity_id", "")
        # Look for climate entities that have messana-specific attributes
        if entity_id.startswith("climate.") and "zone_id" in state.get("attributes", {}):
            attrs = state["attributes"]
            slug = entity_id.replace("climate.", "")
            name = attrs.get("friendly_name", slug.replace("_", " ").title())

            zones.append({
                "entity_id": entity_id,
                "name": name,
                "slug": slug,
                "climate_entity": entity_id,
                "humidity_sensor": f"sensor.{slug}_humidity",
                "active_binary_sensor": f"binary_sensor.{slug}_active",
                "detach_button": f"button.{slug}_detach_schedule",
            })

    # Try to get area/floor info via template
    # This requires the template to have access to area_name and floor functions
    for zone in zones:
        try:
            area_template = f"{{{{ area_name('{zone['entity_id']}') }}}}"
            area_name = client.render_template(area_template).strip()
            if area_name and area_name != "None":
                zone["area_name"] = area_name

                # Try to get floor for this area
                floor_template = f"{{{{ floor_name(area_id('{zone['entity_id']}')) }}}}"
                floor_name = client.render_template(floor_template).strip()
                if floor_name and floor_name != "None":
                    zone["floor_name"] = floor_name
        except Exception:
            pass  # Template functions may not be available in older HA versions

    # Group by floor
    floors_grouped: dict[str, list[dict[str, Any]]] = {}
    unassigned = []

    for zone in zones:
        floor_name = zone.get("floor_name")
        if floor_name:
            if floor_name not in floors_grouped:
                floors_grouped[floor_name] = []
            floors_grouped[floor_name].append(zone)
        else:
            unassigned.append(zone)

    if unassigned:
        floors_grouped["Other"] = unassigned

    return zones, floors_grouped


def generate_zone_card(zone: dict[str, Any]) -> dict[str, Any]:
    """Generate a zone card (stack-in-card with climate info and detach button)."""
    climate_entity = zone["climate_entity"]
    humidity_sensor = zone["humidity_sensor"]
    detach_button = zone["detach_button"]
    zone_name = zone["name"]

    # The main climate template card
    climate_card = {
        "type": "custom:mushroom-template-card",
        "entity": climate_entity,
        "primary": zone_name,
        "secondary": (
            "{% set cur = state_attr(entity,'current_temperature') %}\n"
            "{% set tgt = state_attr(entity,'temperature') %} "
            f"{{% set rh  = states('{humidity_sensor}') %}} "
            "{% set rhv = rh | float(-9999) %} "
            "{% set ts  = state_attr(entity,'thermal_status') | int(0) %} "
            "{{ (cur | round(1)) if cur is number else '\u2014' }}\u00b0 \u2192 "
            "{{ (tgt | round(1)) if tgt is number else '\u2014' }}\u00b0 \u2022 "
            '{{ (rhv | round(1)) if rhv > -3000 else \'\u2014\' }}% {{ "\\n" }} '
            "{% if ts == 1 %}Heating{% elif ts == 2 %}Cooling{% elif ts == 3 %}Heating + Cooling{% else %}Idle{% endif %} "
            "{% set cs = state_attr(entity,'control_source') %} "
            '{{ "\\n" }}\u2022 '
            '{% if cs == "program" %}Scheduled{% elif cs == "program_enabled" %}Schedule enabled{% else %}Manual{% endif %}'
        ),
        "icon": (
            "{% set ts = state_attr(entity,'thermal_status') | int(0) %} "
            "{% if ts == 1 or ts == 3 %} mdi:radiator "
            "{% elif ts == 2 %} mdi:snowflake "
            "{% else %} mdi:radiator-disabled {% endif %}"
        ),
        "icon_color": (
            "{% set ts = state_attr(entity,'thermal_status') | int(0) %} "
            "{% if ts == 1 or ts == 3 %} orange "
            "{% elif ts == 2 %} blue "
            "{% else %} disabled {% endif %}"
        ),
        "tap_action": {"action": "more-info"},
        "card_mod": {"style": "ha-card { width: 100%; }"},
    }

    # The detach schedule button
    detach_card = {
        "type": "custom:mushroom-template-card",
        "primary": "",
        "secondary": "",
        "icon": "mdi:calendar-remove",
        "icon_color": "amber",
        "tap_action": {
            "action": "call-service",
            "service": "button.press",
            "target": {"entity_id": detach_button},
        },
        "hold_action": {"action": "none"},
        "double_tap_action": {"action": "none"},
        "visibility": [
            {
                "condition": "template",
                "value_template": (
                    f"{{{{ state_attr('{climate_entity}','control_source') in "
                    "['program','program_enabled'] }}"
                ),
            }
        ],
        "card_mod": {
            "style": (
                "ha-card {\n"
                "  width: 64px;\n"
                "  min-width: 64px;\n"
                "  max-width: 64px;\n"
                "  margin: 0;\n"
                "}"
            )
        },
    }

    # Wrap in stack-in-card with horizontal-stack
    return {
        "type": "custom:stack-in-card",
        "cards": [
            {
                "type": "horizontal-stack",
                "cards": [climate_card, detach_card],
            }
        ],
        "card_mod": {
            "style": (
                "#root > * { margin: 0 !important; }\n"
                "#root > * ha-card {\n"
                "  box-shadow: none !important;\n"
                "  border: none !important;\n"
                "  background: none !important;\n"
                "}\n"
                "#root > *:nth-child(1) > *:nth-child(2) ha-card {\n"
                "  display: flex;\n"
                "  align-items: center;\n"
                "  justify-content: center;\n"
                "}"
            )
        },
    }


def generate_system_view(zones: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate the System view."""
    # Build list of binary sensor entities for active count
    active_sensors = [z["active_binary_sensor"] for z in zones]
    humidity_sensors = [z["humidity_sensor"] for z in zones]
    zone_count = len(zones)

    # Format sensor lists for templates
    active_list = ",\n                  ".join(f"'{s}'" for s in active_sensors)
    humidity_list = ",\n                ".join(f"states('{s}')" for s in humidity_sensors)

    return {
        "title": "System",
        "path": "system",
        "icon": "mdi:home-thermometer",
        "cards": [
            {
                "type": "custom:mushroom-chips-card",
                "alignment": "justify",
                "chips": [
                    {
                        "type": "entity",
                        "entity": "switch.system_power",
                        "name": "Power",
                        "icon": "mdi:power",
                    },
                    {
                        "type": "entity",
                        "entity": "select.h_c_group_0_mode",
                        "name": "Mode",
                        "icon": "mdi:autorenew",
                    },
                    {
                        "type": "action",
                        "icon": "mdi:format-list-bulleted",
                        "name": "Zones",
                        "tap_action": {
                            "action": "navigate",
                            "navigation_path": "/messana-hvac/zones",
                        },
                    },
                ],
            },
            {
                "type": "custom:mushroom-template-card",
                "primary": "Messana System",
                "secondary": (
                    "Power: {{ 'On' if is_state('switch.system_power','on') else 'Off' }} \u2022\n"
                    "Mode: {{ states('select.h_c_group_0_mode') }}"
                ),
                "icon": "mdi:water-thermometer",
                "entity": "switch.system_power",
                "tap_action": {"action": "more-info"},
            },
            {
                "type": "grid",
                "columns": 2,
                "square": False,
                "cards": [
                    {
                        "type": "custom:mushroom-template-card",
                        "primary": "Zones Active",
                        "secondary": (
                            "{{\n"
                            "  [\n"
                            f"                  {active_list}\n"
                            "                ]\n"
                            "                | map('states')\n"
                            "                | select('eq','on')\n"
                            "                | list\n"
                            "                | length\n"
                            f"              }} / {zone_count}"
                        ),
                        "icon": "mdi:fire",
                        "tap_action": {
                            "action": "navigate",
                            "navigation_path": "/messana-hvac/zones",
                        },
                    },
                    {
                        "type": "custom:mushroom-template-card",
                        "primary": "Avg Humidity",
                        "secondary": (
                            "{% set vals = [\n"
                            f"                {humidity_list}\n"
                            "              ] %}\n"
                            "              {% set nums = vals\n"
                            "                | reject('in', ['unknown','unavailable','none',''])\n"
                            "                | map('float')\n"
                            "                | select('>=', 0)\n"
                            "                | select('<=', 100)\n"
                            "                | list\n"
                            "              %}\n"
                            "              {% if (nums | length) > 0 %}\n"
                            "                {{ ((nums | sum) / (nums | length)) | round(1) }}%\n"
                            "              {% else %}\n"
                            "                \u2014\n"
                            "              {% endif %}"
                        ),
                        "icon": "mdi:water-percent",
                        "tap_action": {"action": "none"},
                    },
                ],
            },
            {"type": "custom:mushroom-title-card", "title": "Plant"},
            {
                "type": "markdown",
                "content": (
                    "**Coming next:** Raymagic / Buffer Tank / ATU blocks (like the Messana app).\n\n"
                    "Once the integration exposes plant entities, we'll replace this section with real cards."
                ),
            },
        ],
    }


def generate_zones_view(
    floors: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Generate the Zones view with zones grouped by floor."""
    cards: list[dict[str, Any]] = [
        {
            "type": "custom:mushroom-chips-card",
            "chips": [
                {
                    "type": "template",
                    "content": "Back",
                    "icon": "mdi:arrow-left",
                    "tap_action": {
                        "action": "navigate",
                        "navigation_path": "/messana-hvac/system",
                    },
                },
                {
                    "type": "entity",
                    "entity": "switch.system_power",
                    "name": "Power",
                },
                {
                    "type": "entity",
                    "entity": "select.h_c_group_0_mode",
                    "name": "Mode",
                },
            ],
        }
    ]

    for floor_name, floor_zones in floors.items():
        # Add floor title
        cards.append({"type": "custom:mushroom-title-card", "title": floor_name})

        # Add grid with zone cards
        zone_cards = [generate_zone_card(zone) for zone in floor_zones]
        cards.append({
            "type": "grid",
            "columns": 1,
            "square": False,
            "cards": zone_cards,
        })

    return {
        "title": "Zones",
        "path": "zones",
        "icon": "mdi:home-thermometer-outline",
        "cards": cards,
    }


def generate_dashboard_from_floors(
    zones: list[dict[str, Any]],
    floors: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Generate the complete dashboard with pre-grouped floors."""
    return {
        "title": "Messana HVAC",
        "views": [
            generate_system_view(zones),
            generate_zones_view(floors),
        ],
    }


def represent_str_multiline(dumper: yaml.Dumper, data: str) -> yaml.Node:
    """Use literal block style for multiline strings."""
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def main():
    parser = argparse.ArgumentParser(
        description="Generate Messana HVAC dashboard YAML by discovering zones from Home Assistant"
    )
    parser.add_argument(
        "--ha-url",
        default=os.environ.get("HA_URL"),
        help="Home Assistant URL (or set HA_URL), e.g. http://homeassistant.local:8123",
    )
    parser.add_argument(
        "--ha-token",
        default=os.environ.get("HA_TOKEN"),
        help="Home Assistant long-lived access token (or set HA_TOKEN)",
    )
    parser.add_argument(
        "--config-dir",
        default=os.environ.get("HA_CONFIG_DIR"),
        help="Home Assistant config directory path (or set HA_CONFIG_DIR). "
             "If provided, reads registry files directly instead of using API.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output file path (default: stdout)",
    )

    args = parser.parse_args()

    # Determine discovery method
    zones = []
    floors: dict[str, list[dict[str, Any]]] = {}

    if args.config_dir:
        # Direct file access to registries
        config_path = Path(args.config_dir)
        if not config_path.exists():
            print(f"Error: Config directory not found: {args.config_dir}", file=sys.stderr)
            sys.exit(1)

        print(f"Reading registries from {args.config_dir}...", file=sys.stderr)
        zones, floors = discover_zones_from_registry(config_path)

    elif args.ha_url and args.ha_token:
        # Use REST API
        print(f"Querying Home Assistant at {args.ha_url}...", file=sys.stderr)
        client = HomeAssistantClient(args.ha_url, args.ha_token)
        zones, floors = discover_zones_from_api(client)

    else:
        # Try to auto-detect config directory
        # Common locations when running inside HA container or from config dir
        for candidate in ["/config", ".", ".."]:
            candidate_path = Path(candidate)
            storage_path = candidate_path / ".storage" / "core.entity_registry"
            if storage_path.exists():
                print(f"Auto-detected config directory: {candidate_path.resolve()}", file=sys.stderr)
                zones, floors = discover_zones_from_registry(candidate_path)
                break
        else:
            print(
                "Error: Could not discover zones. Provide one of:\n"
                "  --config-dir PATH  (to read registry files directly)\n"
                "  --ha-url URL --ha-token TOKEN  (to use REST API)",
                file=sys.stderr,
            )
            sys.exit(1)

    if not zones:
        print("Error: No Messana climate entities found", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(zones)} zones:", file=sys.stderr)
    for zone in zones:
        floor_info = f" [{zone.get('floor_name', 'No floor')}]" if zone.get("floor_name") else ""
        area_info = f" in {zone.get('area_name', '')}" if zone.get("area_name") else ""
        print(f"  {zone['name']}{area_info}{floor_info} -> {zone['climate_entity']}", file=sys.stderr)

    print(f"\nFloor groupings:", file=sys.stderr)
    for floor_name, floor_zones in floors.items():
        print(f"  {floor_name}: {', '.join(z['name'] for z in floor_zones)}", file=sys.stderr)

    # Generate dashboard
    dashboard = generate_dashboard_from_floors(zones, floors)

    # Custom YAML dumper for better formatting
    yaml.add_representer(str, represent_str_multiline)

    yaml_output = yaml.dump(
        dashboard,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )

    # Output
    if args.output:
        with open(args.output, "w") as f:
            f.write(yaml_output)
        print(f"\nDashboard written to {args.output}", file=sys.stderr)
    else:
        print(yaml_output)


if __name__ == "__main__":
    main()
