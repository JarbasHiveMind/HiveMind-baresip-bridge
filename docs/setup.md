# Setup walkthrough

This walks a total beginner from nothing to a phone call that talks to
your OVOS/HiveMind assistant. No prior SIP experience is assumed.

## What you are building

A phone call is answered by [baresip](https://github.com/baresip/baresip),
a SIP softphone. This bridge sits between baresip and your HiveMind hub:
it turns the caller's speech into text, sends that text to hivemind-core,
and plays the hub's spoken reply back into the call.

You need three things: a SIP account (something that lets a phone number
or SIP URI ring baresip), a running hivemind-core hub, and this bridge
installed alongside a baresip binary.

## 1. Get a SIP account

You have two options. Pick one.

### Option A: self-host Asterisk (what the reference deployment uses)

This is the approach used on the project's own demo box. You run
[Asterisk](https://www.asterisk.org/), a SIP server, and register two SIP
extensions on it: one for baresip (the bridge) and one for whatever
device or softphone calls in. Asterisk does not need to reach the public
internet — it only needs to be reachable by baresip and by your calling
device, so a LAN or a Tailscale network is enough.

A minimal Asterisk setup needs two config files:

- `pjsip.conf` (or `sip.conf` on older Asterisk) defines the extensions —
  a username and password per extension, e.g. `1000` for the bridge and
  `1001` for a test caller.
- `extensions.conf` defines the dialplan — which extension can dial which,
  and routes calls to the bridge's extension.

Run Asterisk in Docker if you don't want to install it on the host
directly; the official `andrius/asterisk` image or a plain Debian image
with `apt install asterisk` both work. Once Asterisk is running and the
two extensions are registered, you have a working SIP account for the
bridge: the extension number is `sip_user`, the extension password is
`sip_password`, and the Asterisk host is `sip_gateway`.

To actually place a test call, use any SIP softphone (Linphone, Zoiper,
or a second baresip instance) registered as the other extension and dial
the bridge's extension number.

### Option B: use a SIP trunk provider

If you don't want to run your own SIP server, sign up with any SIP
trunking provider (for example a VoIP reseller that gives you a DID
number and SIP credentials). They give you a SIP username, password, and
a gateway hostname — the same three values `sip_config.json` needs. This
gets you a real phone number that the public can dial, at the cost of a
subscription.

## 2. Set up a HiveMind hub

You need a running `hivemind-core` somewhere the bridge can reach, and a
client credential for the bridge:

```bash
hivemind-core add-client --name baresip-bridge
```

This prints an access key and a password. Keep them.

## 3. Install the bridge

This package is **not on PyPI yet** (see
[issue #5](https://github.com/JarbasHiveMind/HiveMind-baresip-bridge/issues/5)).
`pip install HiveMind-baresip-bridge` will fail with "No matching
distribution found". Until that is fixed, install from source, or better,
use Docker so you don't have to install a native `baresip` binary
yourself:

```bash
git clone https://github.com/JarbasHiveMind/HiveMind-baresip-bridge
cd HiveMind-baresip-bridge
docker build -t hivemind-baresip-bridge .
```

The Dockerfile installs the `baresip` package from Debian, creates a
Python virtualenv with `uv`, and installs this repo's `src/` into it
along with `ovos-stt-plugin-server` and `ovos-vad-plugin-silero` — the
speech-to-text and voice-activity-detection plugins the bridge needs to
turn call audio into text.

If you'd rather run from a plain checkout without Docker, you need a
`baresip` binary on `PATH` (`apt install baresip` on Debian/Ubuntu) plus:

```bash
pip install .
```

## 4. Configure

Two separate config files are involved.

**HiveMind identity** (hub host, access key, password) — set once:

```bash
hivemind-client set-identity --key <access-key> --password <password> --host ws://core.example.com
```

**SIP settings** — a JSON file, `~/.hivemind_baresip_bridge.json` by
default:

```json
{
  "sip_user": "1000",
  "sip_password": "secret",
  "sip_gateway": "sip.example.com",
  "sip_transport": "udp",
  "auto_answer": true,
  "allowlist": []
}
```

`allowlist` restricts which caller numbers are answered. Leave it empty
(as above) to accept calls from anyone — fine for a first test, but
tighten it once the bridge is reachable from the outside.

If you run in Docker, mount this file and the HiveMind identity file into
the container's `XDG_CONFIG_HOME` (the reference deployment sets
`XDG_CONFIG_HOME=/app/config` and mounts a `config/hivemind` and
`config/mycroft` directory tree in from the host).

## 5. Register the bridge and whitelist its messages

A freshly added HiveMind client is denied every message type by default.
This is the step beginners miss, and the symptom is confusing: the
bridge connects fine, calls get answered, but hivemind-core never seems
to respond. Whitelist the messages the bridge actually needs:

```bash
hivemind-core allow-msg recognizer_loop:utterance <client_id>
hivemind-core allow-msg speak:b64_audio <client_id>
hivemind-core allow-msg baresip.dtmf <client_id>
```

`<client_id>` is printed by `add-client` and by `hivemind-core
list-clients`.

## 6. Run it

```bash
hivemind-baresip-bridge --host ws://core.example.com --key <access-key> --password <password>
```

Or, in Docker, `docker run` the image built above with the config volume
mounted, or use a `docker-compose.yml` if you have one.

## 7. Verify the round trip

Call the SIP extension you configured (from your softphone, or by
dialing the DID your provider gave you). You should see, in order:

1. Asterisk (or your provider) logs the call being routed to the
   bridge's extension.
2. The bridge logs the call being answered (`auto_answer` is on by
   default).
3. Once you speak, the bridge's local VAD segments your speech and the
   STT plugin transcribes it; the bridge logs the recognized text and
   sends `recognizer_loop:utterance` to the hub.
4. hivemind-core logs receiving the utterance, routes it to OVOS skills,
   and returns a `speak:b64_audio` message.
5. The bridge decodes the audio and plays it into the call — you should
   hear the assistant's reply through the phone.

If step 5 never happens but step 3 did, the almost-certain cause is the
missing `allow-msg` whitelist from step 5 above, or the reply-path fix
this bridge shipped (older checkouts did not speak back into the call at
all — make sure you are on a current `dev`).

## Troubleshooting

**"invalid api key" on connect**: the bridge's `hivemind_bus_client`
version is too old for the hub's protocol version. Update the bridge
(`pip install -U` or rebuild the Docker image).

**Calls connect but nothing is ever said back**: check `allow-msg` for
`speak:b64_audio` on this client, and confirm your `hivemind-core`
version includes the reply-audio path — the bridge itself never
synthesizes speech, it only plays back what the hub sends.

**"reconnect worker already running" in the logs, or duplicate
connections**: this was a bug in older `hivemind_bus_client` where a
lost connection could spawn a second reconnect loop. It is fixed
upstream — update your `hivemind-bus-client` dependency.

**Stale pinned key after the hub was reinstalled / its identity
changed**: the bridge pins the hub's Noise public key on first connect
and will refuse to talk to a hub that suddenly presents a different key
(this is a security feature, not a bug). Run:

```bash
hivemind-client reset-noise-pin
```

and reconnect.

**No audio heard on the call at all**: check that `ffmpeg` is available
in the environment (the Docker image installs it) — the bridge uses it
to transcode between the call's RTP audio and the WAV format the STT
plugin and TTS playback expect.

## Related documents

- [../README.md](../README.md) — architecture overview and quick
  reference.
