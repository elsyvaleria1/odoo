# Agent runner

The program on the other side of `agent_runner`'s protocol: it claims runs from Odoo, keeps
each lease alive, reports events, and finishes the run. Standard library only, Python 3.10
or later (its tests pass on 3.10, 3.13 and 3.14); it runs on a machine that holds nothing of
Odoo's.

| File | |
|---|---|
| `runner.py` | the protocol client and the loop; `probe`, a fake agent |
| `change.py` | `github.change`: clone, agent with the edit tools, commit, push, pull request |
| `incident.py` | `error_incident.diagnose` (read tools) and `error_incident.fix` (`change.apply`) |
| `deploy.py` | `error_incident.revision` and `error_incident.hotfix`, on the production host |
| `systemd/` | the two services, their environment files, the deploy runner's polkit rule |

## Two roles, two machines

| | `--role sandbox` | `--role deploy` |
|---|---|---|
| Where | the runner machine | the production host |
| Runs | an agent, in a clone under a private `/tmp` that dies with the run | git, and the host's own upgrade, restart and health commands |
| Capability in Odoo | `sandbox` | `deploy` |
| Needs | `git`, Node, Claude Code | `git`, the Odoo checkouts it applies fixes to |
| Never | deploys | runs an agent |

Each is its own **Agent Runners > Runners** record, with its own token and only its own
capability: a sandbox token cannot claim a hotfix.

## What a runner holds

Its token, in `AGENT_RUNNER_TOKEN`, never on its command line. Everything else arrives with
each lease and is gone with the run: a GitHub App installation token for the run's
repository alone, and the company's Anthropic key when the company's data policy lets the
run's purpose reach Anthropic. The agent's process gets `PATH`, `LANG`, `HOME` and that key,
nothing of the runner's environment.

## Configuration

| Variable | Role | |
|---|---|---|
| `AGENT_RUNNER_TOKEN` | both | the token **Issue Token** showed once |
| `AGENT_RUNNER_CLAUDE` | sandbox | the agent's command (default `claude`) |
| `AGENT_RUNNER_GIT_URL` | sandbox | clone URL template, `{repository}` = owner/name (default GitHub over HTTPS) |
| `AGENT_RUNNER_DEPLOY_CHECKOUTS` | deploy | JSON `{"odoo": "/opt/odoo/odoo", ...}`, by the names of **Autofix > Repositories** |
| `AGENT_RUNNER_DEPLOY_UPGRADE` | deploy | command; `{modules}` is the comma-separated list a fix touches |
| `AGENT_RUNNER_DEPLOY_RESTART` | deploy | command |
| `AGENT_RUNNER_DEPLOY_HEALTH` | deploy | command; exit 0 is healthy |
| `AGENT_RUNNER_DEPLOY_HEALTH_WAIT` | deploy | seconds to wait for health (default 120) |
| `AGENT_RUNNER_DEPLOY_REMOTE_URL` | deploy | fetch URL template, for a mirror instead of GitHub |

`sandbox.env.example` and `deploy.env.example` in `systemd/` are the starting points.

## Installing it as a service

```bash
install -D -m 0644 runner.py change.py incident.py deploy.py -t /opt/agent-runner/
install -D -m 0644 systemd/agent-runner-sandbox.service -t /etc/systemd/system/
install -D -m 0600 systemd/sandbox.env.example /etc/agent-runner/sandbox.env   # then edit
systemctl enable --now agent-runner-sandbox.service
```

The sandbox service runs as a user systemd creates for it, under a read-only system, no
home directories, a private `/tmp`, no devices, no new privileges and a system-call allow
list; Node over HTTPS and Claude Code run under it. Install Claude Code where the service
can read it, outside `/home` -- its native installer puts it in `~/.local/bin`, so copy the
binary to `/usr/local/bin` -- and name it in `AGENT_RUNNER_CLAUDE`. Without a company key,
the runner's own model login lives in `/var/lib/agent-runner`.

The deploy service runs as the user that owns the Odoo checkouts (`odoo`), may write only
the checkouts and Odoo's data directory (`ReadWritePaths=`, set with `systemctl edit`), and
restarts `odoo.service` through `50-agent-runner-restart-odoo.rules`, a polkit rule that
grants that user exactly that restart.

`systemd-analyze security` rates the sandbox service 1.4 and the deploy service 1.5, both
"OK".

## Running it by hand

```bash
AGENT_RUNNER_TOKEN=... python3 runner.py --url https://odoo.example.com --once      # one run
AGENT_RUNNER_TOKEN=... python3 runner.py --url https://odoo.example.com --role deploy
```

`--once` handles one run and exits 0, or 1 when there was none and 2 when Odoo was
unreachable.

`SIGTERM` (`systemctl stop`, a restart) stops the agent in hand within a second and hands its
run back to Odoo as retryable, for another runner, instead of leaving it leased until the
lease expires. A hotfix is not interrupted: the deploy executors finish what they started,
which is why the deploy service waits up to five minutes to stop.

## Tests

```bash
cd odoo && ../p314o19m/bin/pytest tooling/agent_runner
```

They need `git` and nothing else. The agent is a fake (`fakes.py`), and origins are bare
repositories under the test's temporary directory.
