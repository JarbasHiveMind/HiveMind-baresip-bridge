"""Minimal HiveMind demo agent.

This is the smallest thing that behaves like an OVOS skill for the demo. It
connects to the internal OVOS message bus that hivemind-core relays client
traffic onto, listens for `recognizer_loop:utterance`, and answers with
synthesized speech.

It exists to prove two things end to end over a real SIP call:

1. The bridge forwards the caller's recognized utterance to the hub, and the
   hub relays it here.
2. Per-call session isolation: every call the bridge answers mints its own
   Layer-1 session id, so two sequential calls arrive here as two DISTINCT
   session ids. Each received session id is appended to
   `/shared/agent_sessions.jsonl`, which the e2e test reads back.

The answer path mirrors how a `speak` reply reaches this bridge: the bridge
plays back audio delivered as a base64 wav on `speak:b64_audio.response`. The
agent synthesizes the answer with espeak-ng, base64-encodes the wav, and emits
it with the SAME session context so the hub routes it to the call that asked.

Timezone fidelity: if the incoming session declares a location timezone
(`session.location.timezone.code`), the "what time is it" answer uses it, so a
call declaring Europe/Berlin hears Berlin time. The stock bridge does not yet
populate that field (see the demo README, "Timezone fidelity"), so in the
default demo the agent answers with the hub's own clock and labels it UTC.
"""
import base64
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from os.path import join
from zoneinfo import ZoneInfo

from ovos_bus_client import MessageBusClient
from ovos_bus_client.message import Message
from ovos_bus_client.session import SessionManager
from ovos_utils.log import LOG

SHARED = os.environ.get("SHARED_DIR", "/shared")
BUS_HOST = os.environ.get("OVOS_BUS_HOST", "127.0.0.1")
BUS_PORT = int(os.environ.get("OVOS_BUS_PORT", "8181"))


def _session_from(message: Message) -> dict:
    """Best-effort extraction of the session dict declared on a message."""
    sess = message.context.get("session") or {}
    if isinstance(sess, dict):
        return sess
    return {}


def _record_session(session_id: str, utterance: str) -> None:
    os.makedirs(SHARED, exist_ok=True)
    line = json.dumps({"ts": time.time(),
                       "session_id": session_id,
                       "utterance": utterance})
    with open(join(SHARED, "agent_sessions.jsonl"), "a") as f:
        f.write(line + "\n")
    LOG.info(f"recorded session_id={session_id!r} utterance={utterance!r}")


def _answer_text(utterance: str, tz_code: str) -> str:
    u = (utterance or "").lower()
    if "time" in u:
        tz = None
        label = "UTC"
        if tz_code:
            try:
                tz = ZoneInfo(tz_code)
                label = tz_code
            except Exception:
                tz = None
        now = datetime.now(tz or timezone.utc)
        return f"The time is {now.strftime('%H:%M')} {label}."
    return "Hello from the HiveMind baresip bridge demo."


def _synthesize_b64(text: str) -> str:
    """Render `text` to a wav with espeak-ng and return it base64-encoded."""
    wav_path = join(tempfile.gettempdir(), f"agent_{os.getpid()}_{time.time()}.wav")
    subprocess.run(["espeak-ng", "-v", "en-us", "-s", "130", "-w", wav_path, text],
                   check=True)
    with open(wav_path, "rb") as f:
        data = f.read()
    os.remove(wav_path)
    return base64.b64encode(data).decode("ascii")


class DemoAgent:
    def __init__(self):
        self.bus = MessageBusClient(host=BUS_HOST, port=BUS_PORT)

    def run(self):
        self.bus.on("recognizer_loop:utterance", self.handle_utterance)
        self.bus.run_in_thread()
        LOG.info(f"demo agent connected to OVOS bus at {BUS_HOST}:{BUS_PORT}")
        while True:
            time.sleep(1)

    def handle_utterance(self, message: Message):
        utterances = message.data.get("utterances") or [""]
        utterance = utterances[0]
        sess = _session_from(message)
        session_id = sess.get("session_id", "unknown")
        _record_session(session_id, utterance)

        tz_code = ""
        location = sess.get("location") or {}
        if isinstance(location, dict):
            tz_code = (location.get("timezone") or {}).get("code", "")

        answer = _answer_text(utterance, tz_code)
        LOG.info(f"answering [{session_id}]: {answer}")
        try:
            b64 = _synthesize_b64(answer)
        except Exception as e:
            LOG.error(f"tts failed: {e}")
            return

        # Route the audio back to the call that asked by echoing its context
        # (session + destination). This is the same wire shape the bridge
        # listens for on `speak:b64_audio.response`.
        ctx = dict(message.context)
        self.bus.emit(Message("speak:b64_audio.response",
                              {"audio": b64, "utterance": answer},
                              ctx))


if __name__ == "__main__":
    DemoAgent().run()
