# Agent runner

The program on the other side of `agent_runner`'s protocol: it claims runs from Odoo, keeps
each lease alive, reports events, and finishes the run. Standard library only, Python 3.10
or later (its tests pass on 3.10, 3.13 and 3.14); it runs on a machine that holds nothing of
Odoo's.

| File | |
|---|---|
| `runner.py` | the protocol client and the loop; `probe`, a fake agent |
| `change.py` | `github.change`: clone, agent with the edit tools, commit, push, pull request |
| `gitops.py` | git as the runner runs it: no hooks, the token in git's environment, time bounds |
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

Its token, in `AGENT_RUNNER_TOKEN`, never on its command line; the runner makes itself
undumpable, so a process of the same user -- the agent -- cannot read it from
`/proc/<runner>/environ`. Everything else arrives with each lease and is gone with the run: a
GitHub App installation token for the run's repository alone, and the company's Anthropic
key when the company's data policy lets the run's purpose reach Anthropic. The agent's
process gets `PATH`, `LANG`, `HOME` and that key, nothing of the runner's environment. Git
gets the repository token in its environment, never on its command line, where every user of
the machine reads it.

The agent writes files. Over the tree it wrote, git runs without hooks or fsmonitor and
reads no configuration but the clone's own -- not a `.gitconfig` the agent left in the tree
or a home directory -- and a run whose agent touched `.git/` fails before anything is
committed. What the agent's file tools may read is the runner user's to limit: the sandbox
service gives that user nothing but its state directory, and a company key spares the runner
a model login of its own there.

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
| `AGENT_RUNNER_DEPLOY_STOP`, `_START` | deploy | commands; when both are set, the server is stopped for the upgrade |
| `AGENT_RUNNER_DEPLOY_UPGRADE_TIMEOUT` | deploy | seconds an upgrade may take (default 3600) |
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

## A change, retried

A change whose answer was lost after its push -- the network, a killed runner -- is retried
by Odoo; the retry finds the branch on the remote and reports that push without running the
agent again. A pull request GitHub refuses to open does not fail a pushed change: the result
says why, and Odoo follows the pull request by webhook once a person opens it. A push to
GitHub without a repository token fails before the agent runs. Every failure after the agent
ran reports what it spent.

## A hotfix

A hotfix applies the fix's own commits -- what its branch adds to the base it was cut from --
onto the revision production runs, as one commit with a `Hotfix-Of: <sha>` trailer; never the
base branch's commits production does not run yet. A fix that does not apply cleanly is
refused, the checkout left as it was. After the upgrade and restart the server must come back
healthy; the revision that did is recorded as `refs/agent-runner/healthy`, so an attempt that
finds the fix applied but never confirmed running activates it again rather than report it
deployed. When the server does not come back, the code is reverted, the modules upgraded and
the server restarted again; the database is not restored, so a fix whose upgrade migrated
data is undone in code only. A revert that itself fails, or leaves the server unhealthy, says
that production needs a person. With `AGENT_RUNNER_DEPLOY_STOP` and `_START` set, the server is
stopped for the upgrade instead of upgraded while it serves.

`SIGTERM` (`systemctl stop`, a restart) stops the agent in hand within a second and hands its
run back to Odoo as retryable, for another runner, instead of leaving it leased until the
lease expires; a run that failed for good stays failed. A hotfix is not interrupted: the
deploy executors finish what they started, the services signal the runner alone
(`KillMode=mixed`) so an upgrade or git it runs is not killed under it, and the deploy service
waits up to two hours to stop.

## Tests

```bash
cd odoo && ../p314o19m/bin/pytest tooling/agent_runner
```

They need `git` and nothing else. The agent is a fake (`fakes.py`), and origins are bare
repositories under the test's temporary directory.
