FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "ovos-messagebus" "ovos-utils"

# Bind the internal OVOS bus on all interfaces so the hub and agent
# containers can reach it across the compose network.
ENV OVOS_CONFIG_BASE_FOLDER=mycroft
COPY mycroft.conf /root/.config/mycroft/mycroft.conf

EXPOSE 8181
CMD ["ovos-messagebus"]
