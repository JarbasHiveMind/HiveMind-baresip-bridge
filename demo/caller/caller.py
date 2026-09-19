"""Demo caller: a headless baresip client that registers to the Asterisk PBX
as `caller`, then places TWO sequential calls to the `hmbridge` extension.

For each call it plays demo/audio/what_time_is_it.wav ("what time is it?")
into the call and records the audio it receives back. It writes results.json
to /shared for the e2e test to assert on:

  - both calls established
  - the bridge answered with non-empty audio (or, if RTP media does not flow
    in this environment, the call still signalled/established and the hub-side
    session-isolation assertion carries the proof — see the demo README)

The per-call session isolation itself is observed on the hub/agent side
(demo/agent/stub_agent.py writes /shared/agent_sessions.jsonl); this caller's
job is to actually place the two real calls that trigger it.
"""
import glob
import os
import sys
import time
from os.path import getmtime, getsize, join

from _common import SHARED, headless_registering_config, write_json, write_status

from baresipy import BareSIP

CONFIG_PATH = "/root/.baresipy_caller"
SIP_USER = os.environ.get("SIP_USER", "caller")
SIP_PASSWORD = os.environ.get("SIP_PASSWORD", "caller-demo-pw")
SIP_GATEWAY = os.environ.get("SIP_GATEWAY", "asterisk")
BRIDGE_URI = os.environ.get("BRIDGE_URI", "sip:hmbridge@asterisk")
QUESTION_WAV = os.environ.get("QUESTION_WAV", "/app/audio/what_time_is_it.wav")
NUM_CALLS = int(os.environ.get("NUM_CALLS", "2"))
RX_DIR = "/root/rx"


class Caller(BareSIP):
    def __init__(self, *args, **kwargs):
        self.established = False
        self.registered = False
        super().__init__(*args, **kwargs)

    def handle_login_success(self) -> None:
        self.registered = True
        write_status("caller", "registered to " + SIP_GATEWAY)

    def handle_call_established(self) -> None:
        self.established = True
        write_status("caller", "call established")

    def handle_call_ended(self, reason: str, number=None) -> None:
        write_status("caller", "call ended reason=" + str(reason))


def _newest_rx(before: set, timeout: float = 8.0):
    """Return the newest *-dec.wav that appeared since `before`, waiting up to
    `timeout` seconds for baresip's sndfile module to flush it."""
    deadline = time.time() + timeout
    pattern = join(RX_DIR, "*-dec.wav")
    while time.time() < deadline:
        now = set(glob.glob(pattern))
        fresh = now - before
        if fresh:
            return max(fresh, key=getmtime)
        time.sleep(0.2)
    return None


def place_call(bs: Caller, index: int) -> dict:
    result = {"index": index, "established": False,
              "rx_wav_size": 0, "rx_non_silent": False, "rx_rms": None}
    before = set(glob.glob(join(RX_DIR, "*-dec.wav")))

    # On a cold start the bridge may still be registering to the PBX when the
    # caller is already up, so an early dial is answered with 404. Retry the
    # dial until the call establishes rather than failing the first call.
    for attempt in range(1, 7):
        bs.established = False
        write_status("caller",
                     f"call #{index}: dialling {BRIDGE_URI} (attempt {attempt})")
        bs.call(BRIDGE_URI)

        deadline = time.time() + 12
        while not bs.call_established and time.time() < deadline:
            time.sleep(0.2)
        if bs.call_established:
            break
        write_status("caller", f"call #{index}: not established, retrying")
        bs.hang()
        time.sleep(5)
    result["established"] = bool(bs.call_established)

    if bs.call_established:
        # The bridge answers, then spins up its per-call speech listener a
        # moment later. Wait for that listener to be capturing before playing
        # the question, otherwise the audio races ahead of it and the bridge
        # transcribes silence.
        time.sleep(3)
        write_status("caller", f"call #{index}: playing question wav")
        try:
            bs.send_audio(QUESTION_WAV)
        except Exception as e:
            write_status("caller", f"call #{index}: send_audio failed: {e}")
        # let the answer audio flow back
        time.sleep(8)

    rx = _newest_rx(before)
    if rx and getsize(rx) > 44:
        result["rx_wav_size"] = getsize(rx)
        try:
            import struct
            with open(rx, "rb") as f:
                raw = f.read()[44:]
            n = len(raw) // 2
            if n:
                samples = struct.unpack("<%dh" % n, raw[:n * 2])
                rms = int((sum(s * s for s in samples) / n) ** 0.5)
                result["rx_rms"] = rms
                result["rx_non_silent"] = rms > 50
        except Exception as e:
            write_status("caller", f"call #{index}: rx analysis failed: {e}")

    bs.hang()
    time.sleep(3)
    return result


def main() -> int:
    os.makedirs(RX_DIR, exist_ok=True)
    headless_registering_config(CONFIG_PATH)
    write_status("caller", "starting")

    bs = Caller(user=SIP_USER, pwd=SIP_PASSWORD, gateway=SIP_GATEWAY,
                transport="udp", headless=True, record_rx=True,
                recording_path=RX_DIR, config_path=CONFIG_PATH,
                autostart=True, block=True, max_login_retries=10,
                login_retry_delay=3.0)

    results = {"calls": [], "all_established": False, "any_audio": False}
    try:
        deadline = time.time() + 40
        while not bs.registered and time.time() < deadline:
            time.sleep(0.2)
        if not bs.registered:
            write_status("caller", "registration timed out")

        for i in range(1, NUM_CALLS + 1):
            results["calls"].append(place_call(bs, i))
            time.sleep(2)

        results["all_established"] = all(c["established"] for c in results["calls"]) \
            and len(results["calls"]) == NUM_CALLS
        results["any_audio"] = any(c["rx_non_silent"] for c in results["calls"])
    finally:
        write_json("results.json", results)
        write_status("caller", "results: " + str(results))
        bs.quit()

    return 0 if results["all_established"] else 1


if __name__ == "__main__":
    sys.exit(main())
