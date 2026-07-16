"""SIP <-> HiveMind bridge.

Answers SIP calls with `baresipy`, runs caller speech through local ovos
listener plugins (mic/VAD/STT, no wakeword - the call itself is the
activation), relays recognized utterances to hivemind-core over the
HiveMind bus, and plays hivemind-core's synthesized replies back into the
call.

The TTS retrieval mechanism mirrors HiveMind-voice-relay exactly: this
bridge does NOT synthesize speech locally. It asks hivemind-core to
synthesize by emitting a `speak:b64_audio` message, then receives the
rendered audio back as a `speak:b64_audio.response` message carrying a
base64-encoded wav payload, decodes it to a temp file and plays it into the
call with `BareSIP.send_audio()`.
"""
import base64
import tempfile
import threading
from os.path import join
from typing import Optional
from uuid import uuid4

from baresipy import BareSIP
from baresipy.ovos import BareSIPMicrophone
from baresipy.utils.log import LOG
from ovos_bus_client.message import Message
from ovos_plugin_manager.stt import OVOSSTTFactory
from ovos_plugin_manager.vad import OVOSVADFactory
from ovos_simple_listener import ListenerCallbacks, SimpleListener

from hivemind_bus_client.client import HiveMessageBusClient

from hivemind_baresip_bridge.config import SIPConfig


class CallCallbacks(ListenerCallbacks):
    """Forwards recognized utterances from a single call's `SimpleListener`
    to hivemind-core, tagging every message with the caller's number and a
    session id so replies can be routed back to the right call.
    """

    def __init__(self, bus: HiveMessageBusClient, caller: str, session_id: str,
                 lang: str = "en-us"):
        self.bus = bus
        self.caller = caller
        self.session_id = session_id
        self.lang = lang

    def _context(self) -> dict:
        return {
            "session": {"session_id": self.session_id},
            "source": "hivemind-baresip-bridge",
            "destination": ["audio"],
            "caller": self.caller,
            "platform": "hivemind-baresip-bridge",
        }

    def text_callback(self, utterance: str, lang: str) -> None:
        LOG.info(f"STT [{self.caller}]: {utterance}")
        self.bus.emit(Message("recognizer_loop:utterance",
                              {"utterances": [utterance],
                               "lang": lang or self.lang},
                              self._context()))

    def error_callback(self, audio) -> None:
        LOG.warning(f"STT failure for call with {self.caller}")
        self.bus.emit(Message("recognizer_loop:speech.recognition.unknown",
                              {}, self._context()))


class BaresipBridge(BareSIP):
    """A `BareSIP` client that answers calls, streams caller audio through
    a local `SimpleListener` and relays recognized speech to hivemind-core,
    speaking hivemind-core's replies back into the call.
    """

    def __init__(self, sip_config: SIPConfig,
                 bus: HiveMessageBusClient,
                 lang: str = "en-us",
                 config_path: Optional[str] = None,
                 recording_path: Optional[str] = None,
                 autostart: bool = True,
                 block: bool = True):
        self.sip_config = sip_config
        self.bus = bus
        self.lang = lang
        self._listener: Optional[SimpleListener] = None
        self._session_id: Optional[str] = None
        self._caller: Optional[str] = None
        self._lock = threading.Lock()

        self.bus.on("speak:b64_audio.response", self.handle_tts_b64_response)

        super().__init__(user=sip_config.user,
                         pwd=sip_config.password,
                         gateway=sip_config.gateway,
                         transport=sip_config.transport,
                         headless=True,
                         record_rx=True,
                         recording_path=recording_path,
                         config_path=config_path,
                         autostart=autostart,
                         block=block)

    # -- call lifecycle -----------------------------------------------
    def handle_incoming_call(self, number: str) -> None:
        LOG.info(f"Incoming call: {number}")
        if self.call_established:
            LOG.info("already in a call, rejecting")
            self.do_command("b")
            return
        if not self.sip_config.is_allowed(number):
            LOG.info(f"caller {number} is not in the allowlist, rejecting")
            self.do_command("b")
            return
        if self.sip_config.auto_answer:
            LOG.info(f"auto-answering call from {number}")
            self.accept_call()
        else:
            LOG.info(f"call from {number} awaiting manual accept_call()")

    def handle_call_established(self) -> None:
        LOG.info("Call established")
        with self._lock:
            self._caller = self.current_call or "unknown"
            self._session_id = str(uuid4())
            callbacks = CallCallbacks(self.bus, self._caller,
                                      self._session_id, self.lang)
            self._listener = SimpleListener(
                mic=BareSIPMicrophone(sip=self),
                vad=OVOSVADFactory.create(),
                wakeword=None,
                stt=OVOSSTTFactory.create(),
                callbacks=callbacks,
            )
            self._listener.start()

    def handle_call_ended(self, reason: str, number: Optional[str] = None) -> None:
        LOG.info(f"Call ended: {reason}")
        self._stop_listener()

    def _stop_listener(self) -> None:
        with self._lock:
            if self._listener is not None:
                self._listener.stop()
                self._listener = None
            self._session_id = None
            self._caller = None

    def handle_dtmf_received(self, char: str, duration: int) -> None:
        LOG.info(f"DTMF received: {char}")
        context = {
            "caller": self._caller or self.current_call or "unknown",
            "session": {"session_id": self._session_id} if self._session_id else {},
            "source": "hivemind-baresip-bridge",
        }
        self.bus.emit(Message("baresip.dtmf",
                              {"char": char, "duration": duration},
                              context))

    # -- hivemind-core replies ------------------------------------------
    def handle_tts_b64_response(self, message: Message) -> None:
        """Play back audio hivemind-core synthesized for a `speak` reply."""
        if not self.call_established:
            LOG.debug("received TTS audio but no call is active, dropping")
            return
        b64data = message.data.get("audio")
        if not b64data:
            LOG.warning("speak:b64_audio.response had no audio payload")
            return
        wav_bytes = base64.b64decode(b64data)
        wav_file = join(tempfile.gettempdir(), f"hmbaresip_{uuid4().hex}.wav")
        with open(wav_file, "wb") as f:
            f.write(wav_bytes)
        self.send_audio(wav_file)

    def request_speak(self, utterance: str, lang: Optional[str] = None) -> None:
        """Ask hivemind-core to synthesize `utterance` and send the audio
        back over `speak:b64_audio.response`, mirroring how a `speak`
        message flows through PlaybackService on voice-relay.
        """
        context = {
            "caller": self._caller or self.current_call or "unknown",
            "session": {"session_id": self._session_id} if self._session_id else {},
            "source": "hivemind-baresip-bridge",
        }
        self.bus.emit(Message("speak:b64_audio",
                              {"utterance": utterance, "lang": lang or self.lang},
                              context))
