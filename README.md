# HiveMind-baresip-bridge

A SIP <-> HiveMind bridge. It answers phone calls with
[baresipy](https://github.com/TigreGotico/baresipy), runs the caller's
speech through local ovos listener plugins, relays recognized utterances to
[hivemind-core](https://github.com/JarbasHiveMind/HiveMind-core) over the
HiveMind bus, and speaks hivemind-core's replies back into the call.

Think of it as [HiveMind-voice-relay](https://github.com/JarbasHiveMind/HiveMind-voice-relay),
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
  calls (optionally gated by an allowlist of caller numbers) and, once a
  call is established, starts a local `ovos_simple_listener.SimpleListener`
  reading audio straight from the call via `baresipy.ovos.BareSIPMicrophone`.
  No wakeword is used - the call being answered is the activation signal;
  voice activity detection segments the caller's utterances.
- Each recognized utterance is forwarded to hivemind-core as a
  `recognizer_loop:utterance` message, with the caller's number and a
  per-call session id set in `message.context` so replies route back to
  the right call.
- DTMF digits pressed during the call are forwarded as
  `baresip.dtmf` messages so hivemind-core skills can react to them.
- Replies are **not** synthesized locally. hivemind-core is asked to
  synthesize speech (`speak:b64_audio`) and returns the rendered audio as a
  base64-encoded wav in a `speak:b64_audio.response` message; the bridge
  decodes it and plays it into the call with `BareSIP.send_audio()`. This
  mirrors how HiveMind-voice-relay receives TTS audio.
- When the call ends the listener is stopped and its resources released.

## Install

```bash
pip install HiveMind-baresip-bridge
```

Or from a checkout:

```bash
git clone https://github.com/JarbasHiveMind/HiveMind-baresip-bridge
cd HiveMind-baresip-bridge
pip install .
```

This installs the `hivemind-baresip-bridge` console command. A working
[baresip](https://github.com/baresip/baresip) binary must be available on
`PATH`.

## Configuration

hivemind-core credentials (access key, password, host, port, site id) are
resolved from a `hivemind_bus_client.identity.NodeIdentity`, the same
identity file `hivemind-voice-relay` and the other HiveMind clients use.
Set it once with:

```bash
hivemind-client set-identity --key <access-key> --password <password> --host ws://core.example.com
```

Every field can also be overridden per-run with a CLI flag (`--host`,
`--port`, `--key`, `--password`, `--selfsigned`, `--siteid`).

SIP settings (they are not part of `NodeIdentity`) live in a small JSON
file, `~/.hivemind_baresip_bridge.json` by default (override with
`--sip-config` or the `HIVEMIND_BARESIP_CONFIG` env var):

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

- `sip_gateway` may be omitted to run in registrar-less/direct mode (SIP
  URIs are used verbatim, no registration is performed).
- `allowlist` is a list of caller numbers permitted to reach the bridge;
  leave it empty (or omit it) to accept calls from anyone.
- Every field can be overridden by an environment variable
  (`HIVEMIND_BARESIP_SIP_USER`, `HIVEMIND_BARESIP_SIP_PASSWORD`,
  `HIVEMIND_BARESIP_SIP_GATEWAY`, `HIVEMIND_BARESIP_SIP_TRANSPORT`) or a
  matching CLI flag (`--sip-user`, `--sip-password`, `--sip-gateway`,
  `--sip-transport`, `--no-auto-answer`).

## Run

```bash
hivemind-baresip-bridge --host ws://core.example.com --key <access-key> --password <password>
```

## Security notes

- **SIP credentials** are plaintext in the JSON config file and in
  environment variables; restrict the file's permissions
  (`chmod 600 ~/.hivemind_baresip_bridge.json`) and avoid passing
  `--sip-password` on a shared shell history.
- **hivemind-core access key/password** follow the same handling as any
  other HiveMind client: they live in the `NodeIdentity` file
  (`~/.config/hivemind/_identity.json` by default) and are never logged.
  Use `--selfsigned` only against a hivemind-core instance whose
  certificate you already trust.
- **Caller allowlisting** is number-based and trusts the `From` header
  reported by the SIP peer, which is not cryptographically verified; treat
  it as a convenience filter, not an authentication mechanism.
- Recorded call audio (`record_rx=True`) is written to a temp directory for
  the lifetime of the call; ensure the host's temp directory is not
  world-readable if calls may carry sensitive content.
