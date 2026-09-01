FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# The just-shipped session-model versions this demo is the real-world E2E
# proof for. Floors, not pins, so relocks pull the latest alphas.
RUN pip install --no-cache-dir --pre \
    "hivemind-core>=4.13.18a1" \
    "hivemind-bus-client>=1.0.16a1" \
    "hivemind-ovos-agent-plugin" \
    "hivemind-websocket-protocol" \
    "ovos-utils"

WORKDIR /app
COPY server.json /app/server.json
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV XDG_CONFIG_HOME=/app/config \
    OVOS_BUS_HOST=messagebus \
    OVOS_BUS_PORT=8181 \
    SHARED_DIR=/shared

EXPOSE 5678
ENTRYPOINT ["/app/entrypoint.sh"]
