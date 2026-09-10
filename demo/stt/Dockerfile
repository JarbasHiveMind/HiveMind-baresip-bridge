FROM python:3.14-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "ovos-stt-http-server" \
    "ovos-stt-plugin-fasterwhisper" "setuptools<81"

# Bake the tiny model into the image so the running stack needs no network.
# (This is the one build-time download; the runtime stack is fully offline.)
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('tiny')"

EXPOSE 8080
# ovos-stt-server reads the engine from the OVOS config; point it at
# fasterwhisper tiny (CPU, English).
COPY mycroft.conf /root/.config/mycroft/mycroft.conf

CMD ["ovos-stt-server", "--engine", "ovos-stt-plugin-fasterwhisper", \
     "--host", "0.0.0.0", "--port", "8080"]
