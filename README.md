# HiveMind-baresip-bridge

A SIP-to-HiveMind bridge. It answers phone calls with
[baresipy](https://github.com/TigreGotico/baresipy), runs the caller's
speech through local OVOS listener plugins, sends the recognized text to
[hivemind-core](https://github.com/JarbasHiveMind/HiveMind-core) over the
HiveMind bus, and speaks hivemind-core's replies back into the call.

It works like [HiveMind-voice-relay](https://github.com/JarbasHiveMind/HiveMind-voice-relay),
except the microphone is a phone call.

```
                 SIP/RTP                        HiveMind bus (WebSocket)
SIP caller  <----------------->  baresip  <----------------------------->  hivemind-core  <---> OVOS skills
                                     |
                             hivemind_baresip_bridge
                             (this package: local
                              mic/VAD/STT loop over
                              call audio, DTMF relay,
                              TTS playback into the call)
```

- The bridge is a `baresipy.BareSIP` client. It auto-answers incoming
  calls, optionally gated by an allowlist of caller numbers. Once a call
  is established, it starts a local `ovos_simple_listener.SimpleListener`
  that reads audio straight from the call through
  `baresipy.ovos.BareSIPMicrophone`. The bridge uses no wakeword: the
  answered call is the activation signal, and voice activity detection
  segments the caller's speech into utterances.
- The bridge forwards each recognized utterance to hivemind-core as a
  `recognizer_loop:utterance` message. It sets the caller's number and a
  per-call session ID in `message.context` so replies route back to the
  right call.
- The bridge forwards DTMF digits pressed during the call as
  `baresip.dtmf` messages, so hivemind-core skills can react to them.
- The bridge does not synthesize replies locally. It asks hivemind-core to
  synthesize speech (`speak:b64_audio`) and gets back the rendered audio
  as a base64-encoded WAV in a `speak:b64_audio.response` message. The
  bridge decodes this audio and plays it into the call with
  `BareSIP.send_audio()`. This mirrors how HiveMind-voice-relay receives
  TTS audio.
- When the call ends, the bridge stops the listener and releases its
  resources.

## Install

This package is **not published on PyPI yet**
([issue #5](https://github.com/JarbasHiveMind/HiveMind-baresip-bridge/issues/5)) —
`pip install HiveMind-baresip-bridge` will fail. Install from a checkout,
or build the Docker image, which also gets you a working `baresip` binary
for free:

```bash
git clone https://github.com/JarbasHiveMind/HiveMind-baresip-bridge
cd HiveMind-baresip-bridge
pip install .
```

This installs the `hivemind-baresip-bridge` console command. A working
[baresip](https://github.com/baresip/baresip) binary must be on `PATH`
(`apt install baresip` on Debian/Ubuntu), or use `docker build -t
hivemind-baresip-bridge .` instead.

New to SIP? Read the [setup walkthrough](docs/setup.md) — it covers
getting a SIP account from scratch (self-hosted Asterisk or a provider),
installing, registering on the hub, and verifying a call round-trips.

## Configuration

The bridge resolves hivemind-core credentials (access key, password, host,
port, site ID) from a `hivemind_bus_client.identity.NodeIdentity` file, the
same identity file `hivemind-voice-relay` and the other HiveMind clients
use. Set it once with:

```bash
hivemind-client set-identity --key <access-key> --password <password> --host ws://core.example.com
```

You can override every field per run with a CLI flag (`--host`, `--port`,
`--key`, `--password`, `--selfsigned`, `--siteid`).

SIP settings are not part of `NodeIdentity`. They live in a small JSON
file, `~/.hivemind_baresip_bridge.json` by default (override the path with
`--sip-config` or the `HIVEMIND_BARESIP_CONFIG` environment variable):

```json
{
  "sip_user": "1000",
  "sip_password": "secret",
  "sip_gateway": "sip.example.com",
  "sip_transport": "udp",
  "auto_answer": true,
  "allowlist": ["+15551234567"]
}
```

- You can omit `sip_gateway` to run in registrar-less/direct mode. In this
  mode the bridge uses SIP URIs verbatim and performs no registration.
- `allowlist` lists the caller numbers permitted to reach the bridge.
  Leave it empty, or omit it, to accept calls from anyone.
- You can override every field with an environment variable
  (`HIVEMIND_BARESIP_SIP_USER`, `HIVEMIND_BARESIP_SIP_PASSWORD`,
  `HIVEMIND_BARESIP_SIP_GATEWAY`, `HIVEMIND_BARESIP_SIP_TRANSPORT`) or a
  matching CLI flag (`--sip-user`, `--sip-password`, `--sip-gateway`,
  `--sip-transport`, `--no-auto-answer`).

## Run

```bash
hivemind-baresip-bridge --host ws://core.example.com --key <access-key> --password <password>
```

## Security notes

- **SIP credentials** are stored as plaintext in the JSON config file and
  in environment variables. Restrict the file's permissions
  (`chmod 600 ~/.hivemind_baresip_bridge.json`) and avoid passing
  `--sip-password` on a shared shell history.
- The **hivemind-core access key and password** follow the same handling
  as any other HiveMind client: they live in the `NodeIdentity` file
  (`~/.config/hivemind/_identity.json` by default) and the bridge never
  logs them. Use `--selfsigned` only against a hivemind-core instance
  whose certificate you already trust.
- **Caller allowlisting** is number-based and trusts the `From` header
  reported by the SIP peer. The bridge does not verify this header
  cryptographically, so treat allowlisting as a convenience filter, not
  an authentication mechanism.
- When `record_rx=True`, the bridge writes recorded call audio to a temp
  directory for the lifetime of the call. Make sure the host's temp
  directory is not world-readable if calls may carry sensitive content.

## Related projects

- [hivemind-core](https://github.com/JarbasHiveMind/HiveMind-core) — the
  HiveMind server this bridge connects to.
- [HiveMind-voice-relay](https://github.com/JarbasHiveMind/HiveMind-voice-relay) —
  a sibling bridge that streams microphone audio instead of call audio.
- [baresipy](https://github.com/TigreGotico/baresipy) — the SIP client
  library this bridge uses to answer calls.

## License

Apache-2.0.
