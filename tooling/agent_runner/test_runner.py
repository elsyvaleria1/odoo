import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from . import runner as agent


class FakeClient:

    def __init__(self, leases=(), *, cancel_after=None, lose_on=None, flaky=0):
        self.leases = list(leases)
        self.calls = []
        self.usages = []
        self.beats = 0
        self.cancel_after = cancel_after
        self.lose_on = lose_on
        self.flaky = flaky

    def claim(self):
        self.calls.append(("claim",))
        return self.leases.pop(0) if self.leases else None

    def heartbeat(self, run, lease_token):
        self.beats += 1
        if self.lose_on == "heartbeat":
            raise agent.LeaseLost("heartbeat")
        cancel = self.cancel_after is not None and self.beats >= self.cancel_after
        return {"cancel": cancel}

    def events(self, run, lease_token, events):
        self.calls.append(("events", run, events[0]["message"]))

    def complete(self, run, lease_token, result, usage):
        if self.flaky:
            self.flaky -= 1
            raise agent.TransportError("reset")
        if self.lose_on == "complete":
            raise agent.LeaseLost("complete")
        self.calls.append(("complete", run, result, usage))
        return {"state": "succeeded"}

    def fail(self, run, lease_token, error, *, retryable, usage=None):
        self.calls.append(("fail", run, error, retryable))
        self.usages.append(usage)
        return {"state": "queued" if retryable else "failed"}


def _lease(run=1, kind="probe", lease_seconds=3, **payload):
    return {
        "id": run,
        "kind": kind,
        "attempt": 1,
        "lease_token": "t",
        "lease_seconds": lease_seconds,
        "payload": payload,
    }


def _runner(client, **executors):
    return agent.Runner(client, executors or None, backoff=lambda attempt: 0)


def _finished(client):
    return [call for call in client.calls if call[0] in ("complete", "fail")]


def test_an_empty_queue_is_no_work():
    client = FakeClient()
    assert _runner(client).run_once() is False


def test_a_run_is_worked_and_completed_with_its_usage():
    client = FakeClient([_lease(question=6, cost=0.5, input_tokens=10)])
    assert _runner(client).run_once() is True
    [(verb, run, result, usage)] = _finished(client)
    assert (verb, run) == ("complete", 1)
    assert result["echo"]["question"] == 6
    assert usage == {"input_tokens": 10, "output_tokens": 0, "cost": 0.5}
    assert ("events", 1, "step 1 of 1") in client.calls


def test_an_unexpected_failure_is_retryable():
    client = FakeClient([_lease(fail="boom")])
    _runner(client).run_once()
    assert _finished(client) == [("fail", 1, "RuntimeError: boom", True)]


def test_a_permanent_failure_is_not():
    client = FakeClient([_lease(fail="no such repo", permanent=True)])
    _runner(client).run_once()
    assert _finished(client) == [("fail", 1, "no such repo", False)]


def test_a_kind_it_cannot_run_fails_for_good():
    client = FakeClient([_lease(kind="deploy")])
    _runner(client).run_once()
    assert _finished(client) == [("fail", 1, "this runner cannot run 'deploy'", False)]


def test_a_cancelled_run_stops_and_is_reported_as_stopped():
    client = FakeClient([_lease(seconds=10, lease_seconds=3)], cancel_after=1)
    _runner(client).run_once()
    assert _finished(client) == [("fail", 1, "stopped", False)]
    assert client.beats == 1


def test_a_lost_lease_reports_nothing():
    client = FakeClient([_lease(seconds=10, lease_seconds=3)], lose_on="heartbeat")
    _runner(client).run_once()
    assert _finished(client) == []


def test_a_completion_lost_on_the_network_is_sent_again():
    client = FakeClient([_lease()], flaky=2)
    _runner(client).run_once()
    assert [call[0] for call in _finished(client)] == ["complete"]


def test_a_completion_refused_for_a_lost_lease_is_given_up():
    client = FakeClient([_lease()], lose_on="complete")
    _runner(client).run_once()
    assert _finished(client) == []


def test_serve_stops_when_asked():
    client = FakeClient([_lease()])
    runner = agent.Runner(client, poll_seconds=0.01, backoff=lambda attempt: 0)
    thread = threading.Thread(target=runner.serve)
    thread.start()
    runner.shutdown()
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_a_shutdown_hands_the_run_in_hand_back_for_another_runner():
    client = FakeClient([_lease(seconds=30, lease_seconds=300)])
    runner = agent.Runner(client, poll_seconds=0.01, backoff=lambda attempt: 0)
    thread = threading.Thread(target=runner.serve)
    thread.start()
    while not any(call[0] == "events" for call in client.calls):
        thread.join(timeout=0.01)
    runner.shutdown()
    thread.join(timeout=5)
    assert not thread.is_alive(), "the run was stopped, not waited out"
    assert _finished(client) == [("fail", 1, "the runner was stopped: stopped", True)]


def test_the_token_is_read_from_the_environment_only(monkeypatch):
    monkeypatch.delenv("AGENT_RUNNER_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        agent.main(["--url", "http://127.0.0.1:1", "--once"])


def test_a_shutdown_keeps_a_permanent_failure_permanent():
    def reverts(lease, reporter):
        raise agent.Permanent("reverted: unhealthy")

    client = FakeClient([_lease(kind="deploy")])
    runner = _runner(client, deploy=reverts)
    runner.stopping.set()
    runner.run_once()
    assert _finished(client) == [("fail", 1, "reverted: unhealthy", False)]


def test_a_failure_reports_what_the_attempt_spent():
    def spends(lease, reporter):
        error = RuntimeError("no verdict")
        error.usage = {"input_tokens": 3, "output_tokens": 1, "cost": 0.5}
        raise error

    client = FakeClient([_lease(kind="spender")])
    _runner(client, spender=spends).run_once()
    assert client.usages == [{"input_tokens": 3, "output_tokens": 1, "cost": 0.5}]


def test_an_answer_that_is_not_json_is_a_transport_error(monkeypatch):
    class Page:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"<html>proxy error</html>"

    monkeypatch.setattr(agent.urllib.request, "urlopen", lambda *a, **k: Page())
    with pytest.raises(agent.TransportError):
        agent.Client("http://odoo.test", "t").claim()


def test_the_heartbeat_survives_an_unexpected_error():
    class Flaky(FakeClient):
        def heartbeat(self, run, lease_token):
            self.beats += 1
            if self.beats == 1:
                raise KeyError("cancel")
            return {"cancel": False}

    client = Flaky([_lease(seconds=3, lease_seconds=3)])
    _runner(client).run_once()
    assert client.beats >= 2


def test_an_empty_claim_answer_is_no_run(monkeypatch):
    client = agent.Client("http://odoo.test", "t")
    monkeypatch.setattr(client, "_post", lambda verb, body: {})
    assert client.claim() is None


def test_what_the_readme_installs_is_what_the_runner_imports(tmp_path):
    readme = (Path(__file__).parent / "README.md").read_text()
    [line] = re.findall(r"^install .* -t /opt/agent-runner/$", readme, re.MULTILINE)
    for name in re.findall(r"\b\w+\.py\b", line):
        shutil.copy(Path(__file__).parent / name, tmp_path)
    probe = tmp_path / "probe.py"
    probe.write_text("import change, deploy, incident, runner\n")
    imported = subprocess.run(
        [sys.executable, "-E", "-s", str(probe)],
        cwd="/",
        capture_output=True,
        text=True,
        check=False,
    )
    assert imported.returncode == 0, imported.stderr


def test_a_session_ends_whole_even_a_member_that_made_a_group_of_its_own(tmp_path):
    marker = tmp_path / "survivor"
    agent.run_in_session(
        ["bash", "-c", f"set -m; (sleep 2; touch {marker}) & exit 0"],
        env={"PATH": "/usr/bin:/bin"},
        timeout=10,
        end_on_exit=True,
    )
    time.sleep(3)
    assert not marker.exists()
