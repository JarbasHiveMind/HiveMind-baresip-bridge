import argparse

from ovos_utils import wait_for_exit_signal
from ovos_utils.log import init_service_logger, LOG

from hivemind_bus_client import HiveMessageBusClient
from hivemind_bus_client.identity import NodeIdentity

from hivemind_baresip_bridge.bridge import BaresipBridge
from hivemind_baresip_bridge.config import load_sip_config


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Answer SIP calls and relay them to hivemind-core")
    parser.add_argument("--host", type=str, default="",
                        help="hivemind-core host")
    parser.add_argument("--port", type=int, default=None,
                        help="hivemind-core port number")
    parser.add_argument("--key", type=str, default="",
                        help="hivemind-core access key")
    parser.add_argument("--password", type=str, default="",
                        help="password for key derivation")
    parser.add_argument("--selfsigned", action="store_true",
                        help="accept self signed certificates")
    parser.add_argument("--siteid", type=str, default="",
                        help="location identifier for message.context")
    parser.add_argument("--lang", type=str, default="en-us",
                        help="STT/TTS language")
    parser.add_argument("--sip-user", type=str, default=None,
                        help="SIP account username")
    parser.add_argument("--sip-password", type=str, default=None,
                        help="SIP account password")
    parser.add_argument("--sip-gateway", type=str, default=None,
                        help="SIP registrar/gateway (omit for registrar-less mode)")
    parser.add_argument("--sip-transport", type=str, default=None,
                        help="SIP transport (udp/tcp/tls)")
    parser.add_argument("--sip-config", type=str, default=None,
                        help="path to the SIP JSON config file")
    parser.add_argument("--no-auto-answer", action="store_true",
                        help="disable auto-answering incoming calls")
    return parser


def connect(args=None) -> None:
    """Resolve hivemind-core + SIP settings and run the bridge until an
    exit signal is received.
    """
    parser = get_parser()
    ns = parser.parse_args(args=args)

    init_service_logger("HiveMind-baresip-bridge")

    identity = NodeIdentity()
    password = ns.password or identity.password
    key = ns.key or identity.access_key
    siteid = ns.siteid or identity.site_id or "unknown"
    host = ns.host or identity.default_master
    port = ns.port or identity.default_port or 5678

    if not key or not password or not host:
        raise RuntimeError(
            "NodeIdentity not set, please pass --key/--password/--host or "
            "call 'hivemind-client set-identity'")

    if not host.startswith("ws://") and not host.startswith("wss://"):
        host = "ws://" + host
    if not host.startswith("ws"):
        LOG.error("Invalid host, please specify a protocol")
        LOG.error(f"ws://{host} or wss://{host}")
        exit(1)

    sip_config = load_sip_config(
        config_path=ns.sip_config,
        user=ns.sip_user,
        password=ns.sip_password,
        gateway=ns.sip_gateway,
        transport=ns.sip_transport,
        auto_answer=False if ns.no_auto_answer else None,
    )

    bus = HiveMessageBusClient(key=key,
                               password=password,
                               port=port,
                               host=host,
                               useragent="HiveMind-baresip-bridge",
                               self_signed=ns.selfsigned)
    bus.connect(site_id=siteid)

    bridge = BaresipBridge(sip_config=sip_config, bus=bus, lang=ns.lang)

    wait_for_exit_signal()

    bridge.quit()


def main() -> None:
    connect()


if __name__ == "__main__":
    main()
