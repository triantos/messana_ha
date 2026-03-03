# Messana HVAC Integration for Home Assistant

Custom integration for [Messana](https://www.messana.com/) hydronic radiant heating/cooling systems (mBox controller).

## Installation (HACS)

1. Add this repository as a custom repository in HACS
2. Install "Messana" from the HACS integrations list
3. Restart Home Assistant
4. Add the integration via Settings > Devices & Services > Add Integration > Messana

## Configuration

You'll need:
- **Base URL**: The URL of your Messana mBox (e.g. `http://192.168.1.100`)
- **API Key**: Your Messana API key

## Features

- Climate entities per zone (temperature, setpoint, on/off)
- Zone humidity and dew point sensors
- H/C group mode select (Heating / Cooling / Auto)
- Executive season sensor (heating vs cooling)
- Zone schedule status and detach buttons
- System on/off switch
