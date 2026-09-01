import unittest
from unittest.mock import MagicMock, patch

from hivemind_baresip_bridge.__main__ import connect, DEFAULT_HANDSHAKE_MAX_RETRIES


class TestBoundedHandshake(unittest.TestCase):
    def test_connect_bounds_handshake_retries(self):
        """bus.connect() must be called with a finite handshake_max_retries
        so a stalled/unreachable hub cannot hang the bridge forever.
        """
        fake_identity = MagicMock()
        fake_identity.password = "pw"
        fake_identity.access_key = "key"
        fake_identity.site_id = "site"
        fake_identity.default_master = "127.0.0.1"
        fake_identity.default_port = 5678

        fake_bus = MagicMock()

        with patch("hivemind_baresip_bridge.__main__.NodeIdentity",
                   return_value=fake_identity), \
                patch("hivemind_baresip_bridge.__main__.HiveMessageBusClient",
                      return_value=fake_bus), \
                patch("hivemind_baresip_bridge.__main__.load_sip_config"), \
                patch("hivemind_baresip_bridge.__main__.BaresipBridge"), \
                patch("hivemind_baresip_bridge.__main__.wait_for_exit_signal"):
            connect(args=[])

        fake_bus.connect.assert_called_once()
        _, kwargs = fake_bus.connect.call_args
        self.assertIsNotNone(kwargs.get("handshake_max_retries"))
        self.assertEqual(kwargs.get("handshake_max_retries"),
                          DEFAULT_HANDSHAKE_MAX_RETRIES)


if __name__ == "__main__":
    unittest.main()
