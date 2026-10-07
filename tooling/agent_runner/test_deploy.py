import json
import subprocess
import threading

import pytest

from . import deploy
from . import runner as agent


class StubReporter:
    def __init__(self):
        self.stop = threading.Event()
        self.events = []

    def event(self, message, kind="info", data=None):
        self.events.append((kind, message))


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(cwd, path, content, message):
    (cwd / path).parent.mkdir(parents=True, exist_ok=True)
    (cwd / path).write_text(content)
    _git(cwd, "add", ".")
    _git(cwd, "-c", "user.name=d", "-c", "user.email=d@x", "commit", "-qm", message)
    return _git(cwd, "rev-parse", "HEAD")


@pytest.fixture
def host(tmp_path, monkeypatch):
    origin = tmp_path / "Agro-Marin" / "odoo.git"
    origin.parent.mkdir()
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    dev = tmp_path / "dev"
    _git(tmp_path, "init", "-q", "-b", "19.0-marin", str(dev))
    _commit(dev, "addons/stock_x/__manifest__.py", "{}\n", "module")
    _commit(dev, "addons/stock_x/models.py", "broken\n", "seed")
    _git(dev, "push", "-q", str(origin), "19.0-marin")
    production = tmp_path / "production"
    _git(
        tmp_path, "clone", "-q", "--branch", "19.0-marin", str(origin), str(production)
    )
    _git(dev, "checkout", "-q", "-b", "19.0-marin-fix-x-i3-a1")
    fix = _commit(dev, "addons/stock_x/models.py", "fixed\n", "fix x")
    _git(dev, "push", "-q", str(origin), "19.0-marin-fix-x-i3-a1")

    calls = tmp_path / "calls.log"
    healthy = tmp_path / "healthy"
    healthy.write_text("yes")
    script = tmp_path / "record"
    script.write_text(f'#!/bin/sh\necho "$@" >> {calls}\n')
    script.chmod(0o755)
    health = tmp_path / "health"
    health.write_text(f"#!/bin/sh\ngrep -q yes {healthy}\n")
    health.chmod(0o755)
    monkeypatch.setenv(
        "AGENT_RUNNER_DEPLOY_CHECKOUTS", json.dumps({"odoo": str(production)})
    )
    monkeypatch.setenv("AGENT_RUNNER_DEPLOY_UPGRADE", f"{script} upgrade {{modules}}")
    monkeypatch.setenv("AGENT_RUNNER_DEPLOY_RESTART", f"{script} restart")
    monkeypatch.setenv("AGENT_RUNNER_DEPLOY_HEALTH", str(health))
    monkeypatch.setenv("AGENT_RUNNER_DEPLOY_HEALTH_WAIT", "0")
    monkeypatch.setenv(
        "AGENT_RUNNER_DEPLOY_REMOTE_URL", f"file://{tmp_path}/{{repository}}.git"
    )

    class Host:
        def __init__(self):
            self.fix, self.production, self.dev, self.origin = (
                fix,
                production,
                dev,
                origin,
            )

        def calls(self):
            return calls.read_text().splitlines() if calls.exists() else []

        def sicken(self):
            healthy.write_text("no")

        def head(self):
            return _git(production, "rev-parse", "HEAD")

        def file(self):
            return (production / "addons/stock_x/models.py").read_text()

    return Host()


def _hotfix_lease(host, **payload):
    return {
        "id": 9,
        "credentials": {},
        "payload": {
            "checkout": "odoo",
            "repository": "Agro-Marin/odoo",
            "branch": "19.0-marin-fix-x-i3-a1",
            "commit": host.fix,
            **payload,
        },
    }


def test_a_hotfix_is_applied_upgraded_and_restarted(host):
    before = host.head()
    outcome = deploy.hotfix(_hotfix_lease(host), StubReporter())
    assert outcome.result["contained"] == [host.fix]
    assert outcome.result["modules"] == ["stock_x"]
    assert host.file() == "fixed\n"
    assert host.head() != before and host.head() == outcome.result["revision"]
    assert host.calls() == ["upgrade stock_x", "restart"]


def test_a_hotfix_that_leaves_the_server_unhealthy_is_reverted(host):
    before = host.head()
    host.sicken()
    with pytest.raises(agent.Permanent, match="reverted"):
        deploy.hotfix(_hotfix_lease(host), StubReporter())
    assert host.head() == before
    assert host.file() == "broken\n"
    assert host.calls() == ["upgrade stock_x", "restart", "upgrade stock_x", "restart"]


def test_a_hotfix_refuses_a_checkout_with_local_changes(host):
    (host.production / "addons/stock_x/models.py").write_text("edited on the server\n")
    with pytest.raises(agent.Permanent, match="local changes"):
        deploy.hotfix(_hotfix_lease(host), StubReporter())
    assert host.calls() == []


def test_a_hotfix_runs_only_on_a_checkout_the_host_serves(host):
    with pytest.raises(agent.Permanent, match="no checkout"):
        deploy.hotfix(_hotfix_lease(host, checkout="/etc"), StubReporter())


@pytest.mark.parametrize(
    ("field", "value"),
    [("commit", "HEAD; rm -rf /"), ("branch", "--upload-pack=touch /tmp/x")],
)
def test_a_hotfix_takes_no_option_or_shell_through_its_names(host, field, value):
    with pytest.raises(agent.Permanent):
        deploy.hotfix(_hotfix_lease(host, **{field: value}), StubReporter())
    assert host.calls() == []


def test_an_applied_fix_is_not_applied_twice(host):
    deploy.hotfix(_hotfix_lease(host), StubReporter())
    head = host.head()
    outcome = deploy.hotfix(_hotfix_lease(host), StubReporter())
    assert (outcome.result["contained"], host.head()) == ([host.fix], head)


def test_the_revision_names_which_awaited_fixes_production_runs(host):
    lease = {
        "id": 1,
        "payload": {"checkouts": {"odoo": [host.fix], "nowhere": ["abc1234"]}},
    }
    outcome = deploy.revision(lease, StubReporter())
    assert outcome.result == {
        "revisions": {"odoo": host.head()},
        "contained": [],
    }
    _git(host.dev, "checkout", "-q", "19.0-marin")
    _git(host.dev, "merge", "-q", "--ff-only", host.fix)
    _git(host.dev, "push", "-q", str(host.origin), "19.0-marin")
    _git(host.production, "pull", "-q", "--ff-only")
    assert deploy.revision(lease, StubReporter()).result["contained"] == [host.fix]
