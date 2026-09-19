# Built from the bridge repo root (compose sets context: ..). This is the
# component under test: the real HiveMind-baresip-bridge from THIS checkout.
FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    baresip ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app/bridge-src

# Install the bridge from source, then float the transport client onto the
# just-shipped session-model line this demo proves out.
RUN pip install --no-cache-dir --pre /app/bridge-src && \
    pip install --no-cache-dir --pre -U \
        "hivemind-bus-client>=1.0.16a1" && \
    pip install --no-cache-dir --pre \
        "ovos-stt-plugin-server" "ovos-vad-plugin-silero"

# OVOS config: the SimpleListener inside the bridge builds STT/VAD from this.
# STT is delegated to the offline stt service; VAD is the bundled silero model.
COPY demo/bridge/mycroft.conf /root/.config/mycroft/mycroft.conf
COPY demo/bridge/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV SHARED_DIR=/shared \
    SIP_USER=hmbridge \
    SIP_PASSWORD=hmbridge-demo-pw \
    SIP_GATEWAY=asterisk

ENTRYPOINT ["/app/entrypoint.sh"]
