"""Configuration loading for the SIP side of the bridge.

HiveMind-core credentials (access key, password, host, port, self-signed
flag, site id) are resolved the same way HiveMind-voice-relay does it: from
a `hivemind_bus_client.identity.NodeIdentity`, overridable by CLI flags.

SIP credentials, the caller allowlist and the auto-answer flag are not part
of `NodeIdentity` (it knows nothing about telephony), so they live in a
small JSON config file, itself overridable by environment variables and CLI
flags. This mirrors voice-relay's "identity file + CLI overrides" style,
just with a second file for the SIP-specific bits.
"""
import json
import os
from dataclasses import dataclass, field
from os.path import expanduser, isfile, join
from typing import List, Optional

DEFAULT_CONFIG_PATH = join(expanduser("~"), ".hivemind_baresip_bridge.json")


@dataclass
class SIPConfig:
    """SIP registration / dialing settings for baresipy."""
    user: Optional[str] = None
    password: Optional[str] = None
    gateway: Optional[str] = None
    transport: str = "udp"
    auto_answer: bool = True
    # empty allowlist == accept all callers
    allowlist: List[str] = field(default_factory=list)

    def is_allowed(self, number: str) -> bool:
        if not self.allowlist:
            return True
        return number in self.allowlist


def _load_json(path: str) -> dict:
    if not path or not isfile(path):
        return {}
    with open(path) as f:
        return json.load(f)


def load_sip_config(config_path: Optional[str] = None,
                     user: Optional[str] = None,
                     password: Optional[str] = None,
                     gateway: Optional[str] = None,
                     transport: Optional[str] = None,
                     auto_answer: Optional[bool] = None,
                     allowlist: Optional[List[str]] = None) -> SIPConfig:
    """Resolve SIP settings from (in ascending priority): the JSON config
    file, environment variables, then explicit keyword arguments.
    """
    path = config_path or os.environ.get("HIVEMIND_BARESIP_CONFIG") or \
        DEFAULT_CONFIG_PATH
    data = _load_json(path)

    cfg = SIPConfig(
        user=data.get("sip_user"),
        password=data.get("sip_password"),
        gateway=data.get("sip_gateway"),
        transport=data.get("sip_transport", "udp"),
        auto_answer=data.get("auto_answer", True),
        allowlist=list(data.get("allowlist", [])),
    )

    cfg.user = os.environ.get("HIVEMIND_BARESIP_SIP_USER", cfg.user)
    cfg.password = os.environ.get("HIVEMIND_BARESIP_SIP_PASSWORD", cfg.password)
    cfg.gateway = os.environ.get("HIVEMIND_BARESIP_SIP_GATEWAY", cfg.gateway)
    cfg.transport = os.environ.get("HIVEMIND_BARESIP_SIP_TRANSPORT", cfg.transport)

    cfg.user = user or cfg.user
    cfg.password = password or cfg.password
    cfg.gateway = gateway or cfg.gateway
    cfg.transport = transport or cfg.transport
    if auto_answer is not None:
        cfg.auto_answer = auto_answer
    if allowlist:
        cfg.allowlist = allowlist

    return cfg


# kept for parity with the rest of the codebase's "Config" naming; a thin
# alias so callers can `from hivemind_baresip_bridge.config import
# BridgeConfig` without caring this is really `SIPConfig`.
BridgeConfig = SIPConfig
