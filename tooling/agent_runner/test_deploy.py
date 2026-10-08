import json
import subprocess
import threading
import time

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
        root = tmp_path

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
            "base_branch": "19.0-marin",
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


def _push_base(host, path, content, message):
    _git(host.dev, "checkout", "-q", "19.0-marin")
    sha = _commit(host.dev, path, content, message)
    _git(host.dev, "push", "-q", str(host.origin), "19.0-marin")
    return sha


def _new_fix(host, branch, path, content):
    _git(host.dev, "checkout", "-q", "-B", branch, "19.0-marin")
    sha = _commit(host.dev, path, content, f"fix {branch}")
    _git(host.dev, "push", "-q", "-f", str(host.origin), branch)
    return sha


def test_a_hotfix_brings_the_fix_alone_not_the_bases_unreleased_commits(host):
    _push_base(host, "addons/other_mod/__manifest__.py", "{}\n", "other module")
    _push_base(host, "addons/other_mod/m.py", "UNRELEASED\n", "unreleased")
    fix = _new_fix(
        host, "19.0-marin-fix-y-i4-a1", "addons/stock_x/models.py", "fixed\n"
    )
    outcome = deploy.hotfix(
        _hotfix_lease(host, branch="19.0-marin-fix-y-i4-a1", commit=fix), StubReporter()
    )
    assert outcome.result["modules"] == ["stock_x"]
    assert host.file() == "fixed\n"
    assert not (host.production / "addons/other_mod/m.py").exists()
    assert host.calls() == ["upgrade stock_x", "restart"]


def test_a_fix_that_conflicts_with_production_is_refused_cleanly(host):
    (host.production / "addons/stock_x/models.py").write_text("hand-made\n")
    _git(
        host.production,
        "-c",
        "user.name=p",
        "-c",
        "user.email=p@x",
        "commit",
        "-qam",
        "prod",
    )
    before = host.head()
    with pytest.raises(agent.Permanent, match="does not apply"):
        deploy.hotfix(_hotfix_lease(host), StubReporter())
    assert host.head() == before
    assert _git(host.production, "status", "--porcelain") == ""
    assert host.file() == "hand-made\n"
    assert host.calls() == []


def test_a_commit_not_on_the_named_branch_is_refused(host):
    other = _new_fix(host, "19.0-marin-other", "addons/stock_x/models.py", "other\n")
    with pytest.raises(agent.Permanent, match="is not on"):
        deploy.hotfix(_hotfix_lease(host, commit=other), StubReporter())
    assert host.calls() == []


def test_an_applied_fix_never_confirmed_running_is_activated_again(host):
    deploy.hotfix(_hotfix_lease(host), StubReporter())
    _git(host.production, "update-ref", "-d", deploy.HEALTHY)
    outcome = deploy.hotfix(_hotfix_lease(host), StubReporter())
    assert outcome.result["contained"] == [host.fix]
    assert host.calls() == ["upgrade stock_x", "restart", "upgrade stock_x", "restart"]
    deploy.hotfix(_hotfix_lease(host), StubReporter())
    assert len(host.calls()) == 4, "confirmed running: nothing to do"


def test_a_revert_that_fails_says_production_needs_a_person(host, monkeypatch):
    host.sicken()
    calls = []

    def activate(modules):
        calls.append(modules)
        if len(calls) == 2:
            raise RuntimeError("the upgrade crashed")

    monkeypatch.setattr(deploy, "_activate", activate)
    with pytest.raises(agent.Permanent, match="production needs a person"):
        deploy.hotfix(_hotfix_lease(host), StubReporter())


def test_a_host_command_keeps_its_own_braces(host, monkeypatch):
    monkeypatch.setenv(
        "AGENT_RUNNER_DEPLOY_HEALTH", "sh -c 'test %{http_code} = %{http_code}'"
    )
    outcome = deploy.hotfix(_hotfix_lease(host), StubReporter())
    assert outcome.result["contained"] == [host.fix]


def test_a_module_is_found_whatever_its_files_are_named(host):
    fix = _new_fix(host, "19.0-marin-fix-z-i5-a1", "addons/stock_x/données.py", "x\n")
    outcome = deploy.hotfix(
        _hotfix_lease(host, branch="19.0-marin-fix-z-i5-a1", commit=fix), StubReporter()
    )
    assert outcome.result["modules"] == ["stock_x"]


def test_a_stop_and_start_take_the_server_down_for_the_upgrade(host, monkeypatch):
    script = host.root / "record"
    monkeypatch.setenv("AGENT_RUNNER_DEPLOY_STOP", f"{script} stop")
    monkeypatch.setenv("AGENT_RUNNER_DEPLOY_START", f"{script} start")
    deploy.hotfix(_hotfix_lease(host), StubReporter())
    assert host.calls() == ["stop", "upgrade stock_x", "start"]


def test_host_commands_never_see_the_runners_token(host, monkeypatch):
    monkeypatch.setenv("AGENT_RUNNER_TOKEN", "runner-secret")
    seen = host.root / "env.txt"
    monkeypatch.setenv("AGENT_RUNNER_DEPLOY_RESTART", f"sh -c 'env > {seen}'")
    deploy.hotfix(_hotfix_lease(host), StubReporter())
    assert "runner-secret" not in seen.read_text()


def test_a_hanging_health_check_is_bounded(host, monkeypatch):
    monkeypatch.setattr(deploy, "HEALTH_CALL_TIMEOUT", 0.5)
    monkeypatch.setenv("AGENT_RUNNER_DEPLOY_HEALTH", "sleep 30")
    monkeypatch.setenv("AGENT_RUNNER_DEPLOY_HEALTH_WAIT", "1")
    with pytest.raises(agent.Permanent, match="reverted"):
        deploy.hotfix(_hotfix_lease(host), StubReporter())


def test_a_fix_production_already_holds_is_contained_not_failed(host):
    (host.production / "addons/stock_x/models.py").write_text("fixed\n")
    _git(
        host.production,
        "-c",
        "user.name=p",
        "-c",
        "user.email=p@x",
        "commit",
        "-qam",
        "same fix by hand",
    )
    head = host.head()
    outcome = deploy.hotfix(_hotfix_lease(host), StubReporter())
    assert outcome.result == {"revision": head, "contained": [host.fix], "modules": []}
    assert host.calls() == []


def test_a_hotfix_a_person_reverted_is_applied_again(host):
    deploy.hotfix(_hotfix_lease(host), StubReporter())
    _git(
        host.production,
        "-c",
        "user.name=p",
        "-c",
        "user.email=p@x",
        "revert",
        "--no-edit",
        "HEAD",
    )
    assert host.file() == "broken\n"
    deploy.hotfix(_hotfix_lease(host), StubReporter())
    assert host.file() == "fixed\n"


def test_a_normal_deploy_does_not_unconfirm_a_hotfix(host):
    deploy.hotfix(_hotfix_lease(host), StubReporter())
    calls = len(host.calls())
    _commit(host.production, "addons/stock_x/other.py", "x\n", "a normal deploy")
    deploy.hotfix(_hotfix_lease(host), StubReporter())
    assert len(host.calls()) == calls, "confirmed already: nothing restarted"


def test_a_command_that_times_out_is_killed_with_what_it_started(
    host, monkeypatch, tmp_path
):
    marker = tmp_path / "orphan"
    wrapper = tmp_path / "slow-upgrade"
    wrapper.write_text(f"#!/bin/sh\n(sleep 2; touch {marker}) &\nsleep 30\n")
    wrapper.chmod(0o755)
    with pytest.raises(RuntimeError, match="timed out"):
        deploy._run([str(wrapper)], "the upgrade", timeout=0.5)
    time.sleep(3)
    assert not marker.exists()


def _lines(**changed):
    lines = [f"line{i}\n" for i in range(1, 11)]
    for index, text in changed.items():
        lines[int(index[1:]) - 1] = f"{text}\n"
    return "".join(lines)


def test_a_fix_applied_where_production_differs_from_base_is_found_applied(host):
    # production runs behind the base: the text around the fix differs there,
    # and the hotfix commit -- made on production's files -- is what is checked
    _push_base(host, "addons/stock_x/models.py", _lines(), "ten lines")
    _git(host.production, "pull", "-q", "--ff-only")
    _push_base(host, "addons/stock_x/models.py", _lines(l3="line3 newer"), "unreleased")
    fix = _new_fix(
        host,
        "19.0-marin-fix-z-i5-a1",
        "addons/stock_x/models.py",
        _lines(l3="line3 newer", l5="line5 fixed"),
    )
    lease = _hotfix_lease(host, branch="19.0-marin-fix-z-i5-a1", commit=fix)
    deploy.hotfix(lease, StubReporter())
    assert host.file() == _lines(l5="line5 fixed")
    _git(host.production, "update-ref", "-d", deploy.HEALTHY)
    deploy.hotfix(lease, StubReporter())
    assert host.calls()[-2:] == ["upgrade stock_x", "restart"]
    assert len(host.calls()) == 4, "activated again, not taken for contained"


def test_a_fix_branch_updated_by_merging_its_base_is_hotfixed(host):
    branch = "19.0-marin-fix-m-i6-a1"
    _new_fix(host, branch, "addons/stock_x/models.py", "fixed\n")
    _push_base(host, "addons/other_mod/m.py", "UNRELEASED\n", "unreleased")
    _git(host.dev, "checkout", "-q", branch)
    _git(
        host.dev,
        "-c",
        "user.name=d",
        "-c",
        "user.email=d@x",
        "merge",
        "-q",
        "--no-ff",
        "-m",
        "Merge branch '19.0-marin' into the fix",
        "19.0-marin",
    )
    _git(host.dev, "push", "-q", str(host.origin), branch)
    merged = _git(host.dev, "rev-parse", "HEAD")
    outcome = deploy.hotfix(
        _hotfix_lease(host, branch=branch, commit=merged), StubReporter()
    )
    assert outcome.result["contained"] == [merged]
    assert host.file() == "fixed\n"
    assert not (host.production / "addons/other_mod/m.py").exists()


def test_a_command_whose_detached_child_holds_its_output_is_bounded():
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="timed out"):
        deploy._run(
            ["sh", "-c", "setsid sleep 15 & sleep 60"], "the upgrade", timeout=1
        )
    assert time.monotonic() - started < 1 + agent.OUTPUT_GRACE + 3
    started = time.monotonic()
    deploy._run(["sh", "-c", "setsid sleep 15 &"], "the restart", timeout=30)
    assert time.monotonic() - started < agent.OUTPUT_GRACE + 3


def _fix_writing(host, branch, path, content: bytes):
    _git(host.dev, "checkout", "-q", "-B", branch, "19.0-marin")
    target = host.dev / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    _git(host.dev, "add", ".")
    _git(
        host.dev,
        "-c",
        "user.name=d",
        "-c",
        "user.email=d@x",
        "commit",
        "-qm",
        f"fix {branch}",
    )
    _git(host.dev, "push", "-q", "-f", str(host.origin), branch)
    return _git(host.dev, "rev-parse", "HEAD")


def test_a_patch_reaches_git_byte_for_byte(host, monkeypatch, tmp_path):
    # CRLF lines, a Latin-1 file, and a host whose git colours and unprefixes
    # its diffs: none of it reshapes the patch
    config = tmp_path / "gitconfig"
    config.write_text("[color]\n\tdiff = always\n[diff]\n\tnoprefix = true\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    branch = "19.0-marin-fix-b-i8-a1"
    _fix_writing(host, branch, "addons/stock_x/data.csv", b"a,b\r\n1,2\r\n")
    fix = _fix_writing(
        host, branch, "addons/stock_x/i18n/es.po", "a\u00f1o\n".encode("latin-1")
    )
    _git(host.dev, "checkout", "-q", branch)
    (host.dev / "addons/stock_x/data.csv").write_bytes(b"a,b\r\n1,2\r\n")
    _git(host.dev, "add", ".")
    _git(host.dev, "-c", "user.name=d", "-c", "user.email=d@x", "commit", "-qm", "both")
    _git(host.dev, "push", "-q", "-f", str(host.origin), branch)
    fix = _git(host.dev, "rev-parse", "HEAD")
    deploy.hotfix(_hotfix_lease(host, branch=branch, commit=fix), StubReporter())
    assert (
        host.production / "addons/stock_x/data.csv"
    ).read_bytes() == b"a,b\r\n1,2\r\n"
    assert (
        host.production / "addons/stock_x/i18n/es.po"
    ).read_bytes() == "a\u00f1o\n".encode("latin-1")


@pytest.mark.parametrize("beside", ["l4", "l3"])
def test_a_hotfix_edited_beside_is_activated_not_taken_for_contained(host, beside):
    _push_base(host, "addons/stock_x/models.py", _lines(), "ten lines")
    _git(host.production, "pull", "-q", "--ff-only")
    fix = _new_fix(
        host,
        "19.0-marin-fix-h-i9-a1",
        "addons/stock_x/models.py",
        _lines(l5="line5 fixed"),
    )
    lease = _hotfix_lease(host, branch="19.0-marin-fix-h-i9-a1", commit=fix)
    deploy.hotfix(lease, StubReporter())
    _git(host.production, "update-ref", "-d", deploy.HEALTHY)
    # a later production commit edits beside the hotfix: its patch no longer
    # reverses, though the fix is there
    _commit(
        host.production,
        "addons/stock_x/models.py",
        _lines(**{beside: f"{beside} nearby", "l5": "line5 fixed"}),
        "an edit beside the hotfix",
    )
    outcome = deploy.hotfix(lease, StubReporter())
    assert host.calls()[-2:] == ["upgrade stock_x", "restart"]
    assert len(host.calls()) == 4, "activated, not answered contained"
    assert outcome.result["modules"] == ["stock_x"]


def test_a_fix_merged_into_its_base_already_says_so(host):
    _git(host.dev, "checkout", "-q", "19.0-marin")
    _git(host.dev, "merge", "-q", "--ff-only", "19.0-marin-fix-x-i3-a1")
    _git(host.dev, "push", "-q", str(host.origin), "19.0-marin")
    with pytest.raises(agent.Permanent, match="merged there already"):
        deploy.hotfix(_hotfix_lease(host), StubReporter())


def test_the_modules_are_those_the_change_leaves(host):
    branch = "19.0-marin-fix-n-i10-a1"
    _git(host.dev, "checkout", "-q", "-B", branch, "19.0-marin")
    _git(host.dev, "mv", "addons/stock_x/models.py", "addons/stock_x/core.py")
    _commit(host.dev, "addons/new_mod/__manifest__.py", "{}\n", "a new module")
    _git(host.dev, "push", "-q", "-f", str(host.origin), branch)
    fix = _git(host.dev, "rev-parse", "HEAD")
    outcome = deploy.hotfix(
        _hotfix_lease(host, branch=branch, commit=fix), StubReporter()
    )
    assert outcome.result["modules"] == ["new_mod", "stock_x"]


def test_a_command_that_cannot_start_says_so():
    with pytest.raises(RuntimeError, match="the upgrade cannot start"):
        deploy._run(["/nonexistent/upgrade"], "the upgrade")
