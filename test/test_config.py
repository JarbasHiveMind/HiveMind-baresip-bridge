import json
import os
import tempfile
import unittest
from os.path import join

from hivemind_baresip_bridge.config import SIPConfig, load_sip_config


class TestSIPConfigAllowlist(unittest.TestCase):
    def test_empty_allowlist_allows_anyone(self):
        cfg = SIPConfig()
        self.assertTrue(cfg.is_allowed("anyone"))

    def test_allowlist_restricts_callers(self):
        cfg = SIPConfig(allowlist=["1000"])
        self.assertTrue(cfg.is_allowed("1000"))
        self.assertFalse(cfg.is_allowed("2000"))


class TestLoadSIPConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config_path = join(self.tmpdir, "config.json")

    def _write(self, data: dict):
        with open(self.config_path, "w") as f:
            json.dump(data, f)

    def test_loads_from_json_file(self):
        self._write({"sip_user": "1000", "sip_password": "secret",
                    "sip_gateway": "sip.example.com", "auto_answer": False,
                    "allowlist": ["1000"]})
        cfg = load_sip_config(config_path=self.config_path)
        self.assertEqual(cfg.user, "1000")
        self.assertEqual(cfg.password, "secret")
        self.assertEqual(cfg.gateway, "sip.example.com")
        self.assertFalse(cfg.auto_answer)
        self.assertEqual(cfg.allowlist, ["1000"])

    def test_missing_file_returns_defaults(self):
        cfg = load_sip_config(config_path=join(self.tmpdir, "nope.json"))
        self.assertIsNone(cfg.user)
        self.assertTrue(cfg.auto_answer)
        self.assertEqual(cfg.allowlist, [])

    def test_env_vars_override_file(self):
        self._write({"sip_user": "from-file"})
        os.environ["HIVEMIND_BARESIP_SIP_USER"] = "from-env"
        try:
            cfg = load_sip_config(config_path=self.config_path)
            self.assertEqual(cfg.user, "from-env")
        finally:
            del os.environ["HIVEMIND_BARESIP_SIP_USER"]

    def test_kwargs_override_env_and_file(self):
        self._write({"sip_user": "from-file"})
        os.environ["HIVEMIND_BARESIP_SIP_USER"] = "from-env"
        try:
            cfg = load_sip_config(config_path=self.config_path, user="from-kwarg")
            self.assertEqual(cfg.user, "from-kwarg")
        finally:
            del os.environ["HIVEMIND_BARESIP_SIP_USER"]


if __name__ == "__main__":
    unittest.main()
