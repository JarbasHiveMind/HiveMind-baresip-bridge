FROM python:3.12-slim

# `baresip` is the real SIP UA binary baresipy drives; ffmpeg backs pydub's
# audio conversion/resampling for send_audio.
RUN apt-get update && apt-get install -y --no-install-recommends \
    baresip ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --pre "baresipy>=1.0.0a8" "pydub"

WORKDIR /app
COPY caller/caller.py caller/_common.py /app/
COPY audio /app/audio

ENV SIP_USER=caller \
    SIP_PASSWORD=caller-demo-pw \
    SIP_GATEWAY=asterisk \
    BRIDGE_URI=sip:hmbridge@asterisk \
    QUESTION_WAV=/app/audio/what_time_is_it.wav \
    NUM_CALLS=2

CMD ["python", "/app/caller.py"]
