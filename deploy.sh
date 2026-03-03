#!/bin/bash
# Deploy Messana integration to HAOS
# Requires: HAOS SSH add-on (Advanced SSH & Web Terminal)
HAOS_HOST="homeassistant.home.triantos.com"
HAOS_PORT="22222"

rsync -av --delete -e "ssh -p $HAOS_PORT" \
  custom_components/messana/ \
  root@${HAOS_HOST}:/config/custom_components/messana/

ssh -p $HAOS_PORT root@${HAOS_HOST} 'ha core restart'
