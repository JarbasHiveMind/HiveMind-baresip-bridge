FROM python:3.12-slim

# espeak-ng renders the demo agent's spoken answers; ffmpeg is pulled in for
# any wav handling ovos_bus_client's deps expect.
RUN apt-get update && apt-get install -y --no-install-recommends \
    espeak-ng ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --pre \
    "ovos-bus-client>=1.0.0" "ovos-utils" 2>/dev/null || \
    pip install --no-cache-dir "ovos-bus-client" "ovos-utils"

WORKDIR /app
COPY stub_agent.py /app/stub_agent.py

ENV OVOS_BUS_HOST=messagebus \
    OVOS_BUS_PORT=8181 \
    SHARED_DIR=/shared

CMD ["python", "/app/stub_agent.py"]
