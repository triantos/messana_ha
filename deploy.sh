#!/bin/bash
# Deploy Messana integration to HAOS
# Uses the existing SSH alias, including its user, port, and key settings.
set -euo pipefail
cd "$(dirname "$0")"
HAOS_HOST="${HAOS_HOST:-homeassistant}"

ssh "$HAOS_HOST" 'sudo -n test -d /config/custom_components/messana'
COPYFILE_DISABLE=1 tar --exclude='__pycache__' --exclude='*.pyc' \
  -C custom_components/messana -cf - . \
  | ssh "$HAOS_HOST" 'sudo -n tar --no-same-owner -xf - -C /config/custom_components/messana'

echo 'Files copied. Restart Home Assistant to load changed Python source.'
