#!/bin/sh
# Bring up hivemind-core for the demo:
#   1. install the server config pointing the agent bus at the messagebus service
#   2. mint a fresh access key + password for the bridge client (non-interactive)
#   3. publish those credentials on the shared volume for the bridge to pick up
#   4. start listening for HiveMind connections
set -e

mkdir -p "$XDG_CONFIG_HOME/hivemind-core" "$SHARED_DIR"

# Render the agent-bus host from the environment into the server config.
sed "s/OVOS_BUS_HOST_PLACEHOLDER/${OVOS_BUS_HOST}/" \
    /app/server.json > "$XDG_CONFIG_HOME/hivemind-core/server.json"

# Fresh credentials every startup — a strong password to clear the hub's
# 40-bit password-strength policy.
KEY="$(python -c 'import secrets; print(secrets.token_hex(16))')"
PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"

echo "hub: registering bridge client (fresh credentials)"
hivemind-core add-client \
    --name baresip-bridge \
    --access-key "$KEY" \
    --password "$PASSWORD"

# The bridge relays recognized speech onto the OVOS bus as
# recognizer_loop:utterance. hivemind-core denies client-injected messages by
# default, so allow this type for the client; without it the hub drops every
# utterance (acl_disallowed_type) and the agent never sees the calls.
echo "hub: allowing recognizer_loop:utterance for the bridge client"
hivemind-core allow-msg recognizer_loop:utterance

# Hand the credentials to the bridge over the shared volume. Written last and
# atomically so the bridge's wait-for-file loop never reads a partial file.
python - "$KEY" "$PASSWORD" <<'PY'
import json, os, sys
key, password = sys.argv[1], sys.argv[2]
shared = os.environ["SHARED_DIR"]
tmp = os.path.join(shared, ".bridge_identity.tmp")
final = os.path.join(shared, "bridge_identity.json")
with open(tmp, "w") as f:
    json.dump({"key": key, "password": password,
               "host": "ws://hub", "port": 5678}, f)
os.replace(tmp, final)
print("hub: wrote", final)
PY

echo "hub: starting hivemind-core listen"
exec hivemind-core listen
