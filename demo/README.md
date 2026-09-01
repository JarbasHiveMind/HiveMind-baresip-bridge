# SIP voice demo and session-isolation e2e test

This demo brings up a complete, offline HiveMind voice stack and places real
SIP calls into it. A caller dials the bridge, asks "what time is it?", and
hears a spoken answer. The same stack is a continuous-integration end-to-end
test that proves **per-call session isolation**: every call the bridge answers
gets its own session, with no state shared between calls.

## What it shows

```
caller ──SIP/RTP──> asterisk ──SIP/RTP──> bridge ──HiveMind bus──> hub
                                                                     │
                                                       OVOS bus (messagebus)
                                                                     │
                                                                   agent
```

- **caller** — a headless `baresipy` client. It registers to the PBX, plays a
  pre-recorded question into the call, and records the answer audio.
- **asterisk** — a small PBX that bridges the audio between the caller and the
  bridge. Two accounts (`caller` and `hmbridge`) and one dialplan rule.
- **bridge** — the HiveMind-baresip-bridge, built from this repository. It
  answers the call, runs the caller's speech through speech-to-text, forwards
  the recognized text to the hub, and plays the hub's spoken reply back.
- **hub** — `hivemind-core`. It relays each client's traffic onto the internal
  OVOS bus and routes replies back to the call that asked.
- **agent** — a minimal skill on the OVOS bus. It answers "what time is it?"
  and records the session id of every request it receives.
- **stt** — an offline speech-to-text server (faster-whisper, tiny model).
- **messagebus** — the internal OVOS bus.

The stack is fully offline at run time. The only network access is at image
build time, when the speech-to-text model is baked into its image.

## Run it

```
cd demo
docker compose up --build
```

The caller places two calls, then the stack settles. Watch for these lines:

```
[caller] registered to asterisk
[caller] call #1: dialling sip:hmbridge@asterisk
[caller] call established
[caller] call #2: dialling sip:hmbridge@asterisk
[caller] call established
```

On the agent side, each call arrives as a distinct session id:

```
recorded session_id='<nonce>:<call-uuid-A>' utterance='what time is it'
recorded session_id='<nonce>:<call-uuid-B>' utterance='what time is it'
```

Two calls, two different session ids — this is per-call session isolation.

## Run the end-to-end test

```
pytest demo/test/test_e2e_session_isolation.py -m e2e
```

The test runs the compose stack, drives two sequential calls, and asserts:

1. Both calls established and the bridge forwarded an utterance for each.
2. The hub relayed **two distinct** Layer-1 session ids to the agent — the
   core regression this demo guards.
3. When call audio flows, the caller captured non-empty answer audio. A finicky
   container audio path does not fail the isolation proof; the session-id
   evidence stands on its own.

The test is skipped automatically where docker is not available.

## How it maps to the session model

The bridge mints a fresh session id the moment a call is answered
(`handle_call_established` in `hivemind_baresip_bridge/bridge.py`). That id
travels with every message the call produces. Because the bridge holds one
long-lived connection to the hub across both calls, the two calls share a
connection nonce but carry different call ids, so the hub sees
`<nonce>:<call-uuid-A>` and `<nonce>:<call-uuid-B>` — two separate sessions.

This is the real-world proof of the session model shipped in
`hivemind-core >= 4.13.18a1` and `hivemind-bus-client >= 1.0.16a1`, where the
declared session travels per message. Before that model, two calls on one
connection could collapse into a single session and bleed state across callers.
The e2e test fails loudly if that regression returns.

## Timezone fidelity

The agent answers "what time is it?" for the timezone declared on the call's
session: a call declaring `Europe/Berlin` hears Berlin time, not server time.
This exercises the contents-fidelity side of the session model — the session
carries not just an identity but the caller's context.

The stock bridge declares a session id but does not yet populate a location
timezone, so in the default demo the agent answers with the hub's clock,
labelled UTC. To see per-call timezone answers, populate
`session.location.timezone.code` in the bridge's message context
(`_context()` in `bridge.py`); the agent already reads it.
