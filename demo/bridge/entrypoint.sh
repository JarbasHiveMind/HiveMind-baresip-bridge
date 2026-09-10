#!/bin/sh
# Wait for the hub to publish the freshly minted bridge credentials on the
# shared volume, render the SIP config from env, then start the bridge.
set -e

IDENTITY="$SHARED_DIR/bridge_identity.json"

echo "bridge: waiting for hub credentials at $IDENTITY"
i=0
while [ ! -f "$IDENTITY" ]; do
    i=$((i + 1))
    if [ "$i" -gt 120 ]; then
        echo "bridge: timed out waiting for hub credentials" >&2
        exit 1
    fi
    sleep 1
done

KEY="$(python -c "import json;print(json.load(open('$IDENTITY'))['key'])")"
PASSWORD="$(python -c "import json;print(json.load(open('$IDENTITY'))['password'])")"
HOST="$(python -c "import json;print(json.load(open('$IDENTITY'))['host'])")"
PORT="$(python -c "import json;print(json.load(open('$IDENTITY'))['port'])")"

# SIP credentials never live in the image or repo; render them at start.
printf '{"sip_user":"%s","sip_password":"%s","sip_gateway":"%s","sip_transport":"udp","auto_answer":true,"allowlist":[]}' \
    "$SIP_USER" "$SIP_PASSWORD" "$SIP_GATEWAY" > /app/sip_config.json

# Telephony calls negotiate 8kHz PCMU/PCMA, but the headless ausine audio
# source only runs at 48kHz. Pre-render baresip's config with the source and
# player sample rates pinned to 48kHz so baresip resamples between 48kHz and
# the 8kHz codec instead of failing to start the audio device when answering.
python - <<'PY'
import os
from baresipy.config import render_config
cfg = render_config(headless=True)
cfg = cfg.replace("#ausrc_srate\t\t48000", "ausrc_srate\t\t48000")
cfg = cfg.replace("#auplay_srate\t\t48000", "auplay_srate\t\t48000")
d = os.path.expanduser("~/.baresipy")
os.makedirs(d, exist_ok=True)
with open(os.path.join(d, "config"), "w") as f:
    f.write(cfg)
print("bridge: wrote baresip config with 48kHz audio rates")
PY

echo "bridge: connecting to hub $HOST:$PORT and registering SIP $SIP_USER@$SIP_GATEWAY"
exec hivemind-baresip-bridge \
    --host "$HOST" --port "$PORT" \
    --key "$KEY" --password "$PASSWORD" \
    --sip-config /app/sip_config.json
