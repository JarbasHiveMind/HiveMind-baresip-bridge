"""Helpers shared with the demo caller container.

The caller talks to the bridge purely over SIP/RTP through the Asterisk PBX.
The only side channel is the bind-mounted /shared volume, used for status
breadcrumbs and the final results.json the e2e test reads back.
"""
import json
import time
from os import makedirs
from os.path import isdir, join

from baresipy.config import render_config

SHARED = "/shared"


def write_status(name: str, msg: str) -> None:
    if not isdir(SHARED):
        makedirs(SHARED, exist_ok=True)
    line = "{ts:.3f} [{name}] {msg}\n".format(ts=time.time(), name=name, msg=msg)
    print(line, end="", flush=True)
    with open(join(SHARED, name + "_status.log"), "a") as f:
        f.write(line)


def write_json(filename: str, data: dict) -> None:
    if not isdir(SHARED):
        makedirs(SHARED, exist_ok=True)
    with open(join(SHARED, filename), "w") as f:
        json.dump(data, f, indent=2)


def headless_registering_config(config_path: str,
                                bind: str = "0.0.0.0:5062") -> None:
    """Write a headless baresip config that binds a SIP listen address the
    Asterisk container can route media back to."""
    if not isdir(config_path):
        makedirs(config_path, exist_ok=True)
    cfg = render_config(headless=True)
    cfg = cfg.replace("#sip_listen\t\t0.0.0.0:5060", "sip_listen\t\t" + bind)
    # Telephony negotiates 8kHz PCMU/PCMA, but the headless ausine source only
    # runs at 48kHz. Pin the source/player rates so baresip resamples between
    # 48kHz and the 8kHz codec instead of failing to start the audio device.
    cfg = cfg.replace("#ausrc_srate\t\t48000", "ausrc_srate\t\t48000")
    cfg = cfg.replace("#auplay_srate\t\t48000", "auplay_srate\t\t48000")
    with open(join(config_path, "config"), "w") as f:
        f.write(cfg)
