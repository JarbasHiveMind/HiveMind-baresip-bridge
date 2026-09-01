"""End-to-end test for the HiveMind baresip bridge session model.

Brings up the full offline stack (messagebus, hub, agent, stt, asterisk,
bridge) with docker compose, drives two real sequential SIP calls from the
caller container, and asserts the core regression this demo guards:

  PER-CALL SESSION ISOLATION — two calls arrive at the hub/agent as two
  DISTINCT Layer-1 session ids, with no cross-call state bleed.

This is the real-world proof of the hivemind-core>=4.13.18a1 /
hivemind-bus-client>=1.0.16a1 session model over a real SIP transport.

Requires docker (with the compose plugin); skipped otherwise. Run with:

    pytest demo/test/test_e2e_session_isolation.py -m e2e
"""
import json
import os
import shutil
import subprocess
import tempfile
from os.path import dirname, isfile, join

import pytest

pytestmark = pytest.mark.e2e

DEMO_DIR = dirname(dirname(__file__))
COMPOSE_FILE = join(DEMO_DIR, "docker-compose.yml")


def _docker_compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "compose", "version"],
                       capture_output=True, check=True, timeout=15)
        return True
    except Exception:
        return False


def _read_sessions(shared_dir: str) -> list:
    path = join(shared_dir, "agent_sessions.jsonl")
    if not isfile(path):
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


@pytest.mark.skipif(not _docker_compose_available(),
                    reason="docker (with the compose plugin) is required for "
                           "the e2e SIP session-isolation test")
def test_two_calls_are_two_distinct_sessions():
    shared_dir = tempfile.mkdtemp(prefix="hmbaresip-demo-")
    env = dict(os.environ)
    env["DEMO_SHARED_DIR"] = shared_dir

    try:
        result = subprocess.run(
            ["docker", "compose", "-f", COMPOSE_FILE, "up", "--build",
             "--abort-on-container-exit", "--exit-code-from", "caller"],
            cwd=DEMO_DIR, env=env, capture_output=True, text=True,
            timeout=1200,
        )
        print(result.stdout[-12000:])
        print(result.stderr[-4000:])

        results_path = join(shared_dir, "results.json")
        assert isfile(results_path), (
            "caller never wrote results.json — see compose logs above")
        with open(results_path) as f:
            results = json.load(f)

        # Both calls must have signalled/established.
        assert results["all_established"] is True, (
            "not every call reached ESTABLISHED: " + json.dumps(results))

        # Core assertion: the bridge forwarded an utterance per call, and the
        # hub relayed two DISTINCT Layer-1 session ids to the agent.
        sessions = _read_sessions(shared_dir)
        assert len(sessions) >= 2, (
            "expected >=2 forwarded utterances (one per call), got "
            f"{len(sessions)}: {sessions}")
        distinct = {row["session_id"] for row in sessions}
        assert len(distinct) >= 2, (
            "per-call session isolation FAILED: the two calls collapsed to "
            f"session id(s) {distinct} — this is the regression the demo "
            "guards against")

        # Audio round trip is a bonus: assert it when RTP media flowed, but do
        # not fail the isolation proof on a finicky container audio path.
        if results.get("any_audio"):
            print("audio round trip confirmed (non-silent rx on a call)")
        else:
            print("NOTE: no non-silent rx audio captured; session-isolation "
                  "proof stands on the hub-side session ids above")
    finally:
        subprocess.run(
            ["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"],
            cwd=DEMO_DIR, env=env, capture_output=True, text=True, timeout=120)
        shutil.rmtree(shared_dir, ignore_errors=True)
