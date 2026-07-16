import base64
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import baresipy

from hivemind_baresip_bridge.bridge import BaresipBridge, CallCallbacks
from hivemind_baresip_bridge.config import SIPConfig


def make_bridge(**sip_kwargs) -> BaresipBridge:
    """Build a BaresipBridge without spawning a real baresip process and
    with a fake HiveMessageBusClient, mirroring baresipy's own
    `make_baresip` test helper.
    """
    sip_config = SIPConfig(**sip_kwargs)
    bus = MagicMock()
    with patch.object(baresipy.pexpect, "spawn") as mock_spawn:
        mock_spawn.return_value = MagicMock()
        bridge = BaresipBridge(sip_config=sip_config, bus=bus,
                               config_path=tempfile.mkdtemp(),
                               autostart=False, block=False)
    return bridge


class TestUtteranceForwarding(unittest.TestCase):
    def test_utterance_includes_caller_context(self):
        bus = MagicMock()
        cb = CallCallbacks(bus, caller="sip:+15551234567@example.com",
                           session_id="sess-1", lang="en-us")
        cb.text_callback("turn on the lights", "en-us")

        bus.emit.assert_called_once()
        message = bus.emit.call_args[0][0]
        self.assertEqual(message.msg_type, "recognizer_loop:utterance")
        self.assertEqual(message.data["utterances"], ["turn on the lights"])
        self.assertEqual(message.context["caller"], "sip:+15551234567@example.com")
        self.assertEqual(message.context["session"]["session_id"], "sess-1")

    def test_error_callback_emits_unknown(self):
        bus = MagicMock()
        cb = CallCallbacks(bus, caller="1000", session_id="sess-2")
        cb.error_callback(audio=None)
        message = bus.emit.call_args[0][0]
        self.assertEqual(message.msg_type,
                         "recognizer_loop:speech.recognition.unknown")


class TestIncomingCallHandling(unittest.TestCase):
    def test_auto_answer_accepts_allowed_caller(self):
        bridge = make_bridge(auto_answer=True, allowlist=["1000"])
        with patch.object(bridge, "accept_call") as accept:
            bridge.handle_incoming_call("1000")
        accept.assert_called_once()

    def test_rejects_caller_not_in_allowlist(self):
        bridge = make_bridge(auto_answer=True, allowlist=["1000"])
        with patch.object(bridge, "accept_call") as accept, \
                patch.object(bridge, "do_command") as do_cmd:
            bridge.handle_incoming_call("2000")
        accept.assert_not_called()
        do_cmd.assert_called_once_with("b")

    def test_empty_allowlist_accepts_anyone(self):
        bridge = make_bridge(auto_answer=True, allowlist=[])
        with patch.object(bridge, "accept_call") as accept:
            bridge.handle_incoming_call("anyone")
        accept.assert_called_once()

    def test_no_auto_answer_does_not_accept(self):
        bridge = make_bridge(auto_answer=False)
        with patch.object(bridge, "accept_call") as accept:
            bridge.handle_incoming_call("1000")
        accept.assert_not_called()


class TestListenerLifecycle(unittest.TestCase):
    def test_listener_starts_on_call_established(self):
        bridge = make_bridge()
        bridge.current_call = "1000"
        fake_listener = MagicMock()
        with patch("hivemind_baresip_bridge.bridge.SimpleListener",
                   return_value=fake_listener) as sl, \
                patch("hivemind_baresip_bridge.bridge.OVOSSTTFactory"), \
                patch("hivemind_baresip_bridge.bridge.OVOSVADFactory"), \
                patch("hivemind_baresip_bridge.bridge.BareSIPMicrophone"):
            bridge.handle_call_established()
        sl.assert_called_once()
        fake_listener.start.assert_called_once()
        self.assertIs(bridge._listener, fake_listener)
        self.assertIsNotNone(bridge._session_id)

    def test_listener_stops_on_call_ended(self):
        bridge = make_bridge()
        fake_listener = MagicMock()
        bridge._listener = fake_listener
        bridge._session_id = "sess-1"
        bridge._caller = "1000"

        bridge.handle_call_ended("hangup")

        fake_listener.stop.assert_called_once()
        self.assertIsNone(bridge._listener)
        self.assertIsNone(bridge._session_id)
        self.assertIsNone(bridge._caller)

    def test_call_ended_without_listener_is_a_noop(self):
        bridge = make_bridge()
        # no listener was ever started - must not raise
        bridge.handle_call_ended("hangup")
        self.assertIsNone(bridge._listener)


class TestDTMF(unittest.TestCase):
    def test_dtmf_forwarded_as_baresip_dtmf_message(self):
        bridge = make_bridge()
        bridge._caller = "1000"
        bridge._session_id = "sess-1"

        bridge.handle_dtmf_received("5", duration=100)

        bridge.bus.emit.assert_called_once()
        message = bridge.bus.emit.call_args[0][0]
        self.assertEqual(message.msg_type, "baresip.dtmf")
        self.assertEqual(message.data["char"], "5")
        self.assertEqual(message.data["duration"], 100)
        self.assertEqual(message.context["caller"], "1000")


class TestTTSPlayback(unittest.TestCase):
    def test_speak_response_triggers_send_audio(self):
        bridge = make_bridge()
        wav_bytes = b"RIFF....fake-wav-data"
        message = MagicMock()
        message.data = {"audio": base64.b64encode(wav_bytes).decode("utf-8")}

        bridge._call_status = "ESTABLISHED"
        with patch.object(bridge, "send_audio") as send_audio:
            bridge.handle_tts_b64_response(message)

        send_audio.assert_called_once()
        wav_path = send_audio.call_args[0][0]
        with open(wav_path, "rb") as f:
            self.assertEqual(f.read(), wav_bytes)

    def test_speak_response_dropped_without_active_call(self):
        bridge = make_bridge()
        message = MagicMock()
        message.data = {"audio": base64.b64encode(b"data").decode("utf-8")}

        bridge._call_status = "DISCONNECTED"
        with patch.object(bridge, "send_audio") as send_audio:
            bridge.handle_tts_b64_response(message)

        send_audio.assert_not_called()

    def test_speak_response_without_audio_payload_is_ignored(self):
        bridge = make_bridge()
        message = MagicMock()
        message.data = {}
        bridge._call_status = "ESTABLISHED"
        with patch.object(bridge, "send_audio") as send_audio:
            bridge.handle_tts_b64_response(message)
        send_audio.assert_not_called()

    def test_request_speak_emits_b64_audio_request(self):
        bridge = make_bridge()
        bridge._caller = "1000"
        bridge.request_speak("hello there")

        bridge.bus.emit.assert_called_once()
        message = bridge.bus.emit.call_args[0][0]
        self.assertEqual(message.msg_type, "speak:b64_audio")
        self.assertEqual(message.data["utterance"], "hello there")


if __name__ == "__main__":
    unittest.main()
