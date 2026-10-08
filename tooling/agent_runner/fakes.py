"""A fake agent and a scratch origin repository, for the executors' tests."""

import json
import subprocess
import sys
import textwrap
import threading

FAKE_CLAUDE = textwrap.dedent(
    """\
    #!{python}
    import json, os, sys
    from pathlib import Path
    here = Path(__file__).parent
    behaviour = json.loads((here / "behaviour.json").read_text())
    calls = here / "calls.json"
    history = json.loads(calls.read_text()) if calls.exists() else []
    history.append({{"argv": sys.argv[1:], "cwd": os.getcwd(), "env": dict(os.environ)}})
    calls.write_text(json.dumps(history))
    for name, content in behaviour.get("edit", {{}}).items():
        path = Path(os.getcwd(), name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    if behaviour.get("noise"):
        sys.stderr.write("x" * behaviour["noise"])
        sys.stderr.flush()
    if behaviour.get("linger"):
        import subprocess, time
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        (here / "child.pid").write_text(str(child.pid))
        if behaviour["linger"] == "hang":
            time.sleep(120)
    if behaviour.get("exit"):
        sys.exit(behaviour["exit"])
    verdict = behaviour.get("verdict")
    text = "I looked." + (f"\\n```json\\n{{json.dumps(verdict)}}\\n```" if verdict else "")
    result = {{"type": "result", "result": text, "is_error": False, "total_cost_usd": behaviour.get("cost", 0.25),
              "usage": {{"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 5}}}}
    if behaviour.get("verbose"):
        result = [{{"type": "system", "subtype": "init"}}, {{"type": "assistant", "message": {{}}}}, result]
    print(json.dumps(result))
    """
)


class StubReporter:
    def __init__(self):
        self.stop = threading.Event()
        self.events = []

    def event(self, message, kind="info", data=None):
        self.events.append((kind, message))


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def make_world(tmp_path, monkeypatch):
    origin = tmp_path / "Agro-Marin" / "odoo.git"
    origin.parent.mkdir()
    _git(tmp_path, "init", "--quiet", "--bare", str(origin))
    seed = tmp_path / "seed"
    _git(tmp_path, "init", "--quiet", "-b", "19.0-marin", str(seed))
    (seed / "x.py").write_text("broken\n")
    _git(seed, "add", ".")
    _git(seed, "-c", "user.name=s", "-c", "user.email=s@x", "commit", "-qm", "seed")
    _git(seed, "push", "-q", str(origin), "19.0-marin")
    fake = tmp_path / "fake"
    fake.mkdir()
    claude = fake / "claude"
    claude.write_text(FAKE_CLAUDE.format(python=sys.executable))
    claude.chmod(0o755)
    monkeypatch.setenv("AGENT_RUNNER_CLAUDE", str(claude))
    monkeypatch.setenv("AGENT_RUNNER_GIT_URL", f"file://{tmp_path}/{{repository}}.git")

    class World:
        fake = tmp_path / "fake"

        def behave(self, **behaviour):
            (fake / "behaviour.json").write_text(json.dumps(behaviour))

        def calls(self):
            return json.loads((fake / "calls.json").read_text())

        def branches(self):
            return _git(origin, "branch", "--list").split()

        def log(self, branch):
            return _git(origin, "log", "-1", "--format=%an <%ae>%n%B", branch)

    return World()
