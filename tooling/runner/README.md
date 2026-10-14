# Odoo runner

The program on the other side of `runner`'s protocol: it claims runs from Odoo, keeps
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

Each is its own **Runners > Runners** record, with its own token and only its own
capability: a sandbox token cannot claim a hotfix.

## What a runner holds

Its token, in `RUNNER_TOKEN`, never on its command line; the runner makes itself
undumpable, so a process of the same user -- the agent -- cannot read it from
`/proc/<runner>/environ`. Everything else arrives with each lease and is gone with the run: a
GitHub App installation token for the run's repository alone, and the company's Anthropic key
when the company's data policy lets the run's purpose reach Anthropic. The agent's process
gets `PATH`, `LANG`, `HOME` and that key, nothing of the runner's environment. Git gets the
repository token in its environment, never on its command line, where every user of the
machine reads it. The runner jobs in a session of its own and is ended with everything it
started in it -- when it answers, times out or is stopped -- so no process of it is alive when
git next runs with that token; it has no tool that starts a process, let alone one that leaves
the session, and the runner reads its output as it comes, so even such a process could hold
the run only a moment past its deadline. Its session is not saved in its home. A runner
process holds one run at a time; more at once are more services, each of which systemd gives a
user of its own (`DynamicUser=`).

The agent writes files. Over the tree it wrote, git runs without hooks or fsmonitor and reads
no configuration but the clone's own -- not a `.gitconfig` the agent left in the tree or a
home directory -- and a run whose agent touched `.git/` fails before anything is committed.
Its tools reach its clone alone: each tool rule names `./**`, `dontAsk` refuses whatever no
rule allows -- a path outside the clone, a symlink out of it, and the clone's own `.git/`,
denied outright -- no settings file is read, so no hook runs, and no MCP server loads, not
even the model login's connectors. A bare tool name would reach every file the runner's user
can read or write, the state directory included, where a settings file an agent wrote would
run its hooks in every later run. This needs a Claude Code that knows `--tools`,
`--setting-sources` and the `dontAsk` mode (2.1.293 was verified); an older one refuses the
options and the run fails. The sandbox service gives the runner's user nothing but its state
directory beyond that, and a company key spares the runner a model login of its own there.

## Configuration

| Variable | Role | |
|---|---|---|
| `RUNNER_TOKEN` | both | the token **Issue Token** showed once |
| `RUNNER_CLAUDE` | sandbox | the agent's command (default `claude`) |
| `RUNNER_GIT_URL` | sandbox | clone URL template, `{repository}` = owner/name (default GitHub over HTTPS) |
| `RUNNER_DEPLOY_CHECKOUTS` | deploy | JSON `{"odoo": "/opt/odoo/odoo", ...}`, by the names of **Autofix > Repositories** |
| `RUNNER_DEPLOY_UPGRADE` | deploy | command; `{modules}` is the comma-separated list a fix touches |
| `RUNNER_DEPLOY_RESTART` | deploy | command |
| `RUNNER_DEPLOY_HEALTH` | deploy | command; exit 0 is healthy |
| `RUNNER_DEPLOY_HEALTH_WAIT` | deploy | seconds to wait for health (default 120) |
| `RUNNER_DEPLOY_STOP`, `_START` | deploy | commands; when both are set, the server is stopped for the upgrade |
| `RUNNER_DEPLOY_UPGRADE_TIMEOUT` | deploy | seconds an upgrade may take (default 3600) |
| `RUNNER_DEPLOY_REMOTE_URL` | deploy | fetch URL template, for a mirror instead of GitHub |

`sandbox.env.example` and `deploy.env.example` in `systemd/` are the starting points.

## Installing it as a service

```bash
install -D -m 0644 runner.py gitops.py change.py incident.py deploy.py -t /opt/odoo-runner/
install -D -m 0644 systemd/odoo-runner-sandbox.service -t /etc/systemd/system/
install -D -m 0600 systemd/sandbox.env.example /etc/odoo-runner/sandbox.env   # then edit
systemctl enable --now odoo-runner-sandbox.service
```

The sandbox service runs as a user systemd creates for it, under a read-only system, no
home directories, a private `/tmp`, no devices, no new privileges and a system-call allow
list; Node over HTTPS and Claude Code run under it. Install Claude Code where the service
can read it, outside `/home` -- its native installer puts it in `~/.local/bin`, so copy the
binary to `/usr/local/bin` -- and name it in `RUNNER_CLAUDE`. Without a company key,
the runner's own model login lives in `/var/lib/odoo-runner`.

The deploy service runs as the user that owns the Odoo checkouts (`odoo`), may write only
the checkouts and Odoo's data directory (`ReadWritePaths=`, set with `systemctl edit`), and
restarts `odoo.service` through `50-odoo-runner-restart-odoo.rules`, a polkit rule that
grants that user exactly that restart.

`systemd-analyze security` rates the sandbox service 1.4 and the deploy service 1.5, both
"OK".

## Running it by hand

```bash
RUNNER_TOKEN=... python3 runner.py --url https://odoo.example.com --once      # one run
RUNNER_TOKEN=... python3 runner.py --url https://odoo.example.com --role deploy
```

`--once` handles one run and exits 0, or 1 when there was none and 2 when Odoo was
unreachable.

## A change, retried

A change whose answer was lost after its push -- the network, a killed runner -- is retried by
Odoo; the retry finds the branch on the remote and reports that push without running the agent
again -- only when the branch's tip carries this run's `Runner-Job` trailer: a branch of that
name someone else pushed fails the change instead of passing for its work. A pull request
GitHub refuses to open does not fail a pushed change: the result says why, and Odoo follows
the pull request by webhook once a person opens it. A push to GitHub without a repository
token fails before the runner jobs. Every failure after the agent ran reports what it spent.

## A hotfix

A hotfix applies what the fix's branch adds to its base -- one change, so a merge of the base
into the branch, GitHub's "Update branch", brings nothing more -- onto the revision production
runs, as one commit with a `Hotfix-Of: <sha>` trailer; never the base branch's commits
production does not run yet. A fix that does not apply cleanly is refused, the checkout left
as it was. After the upgrade and restart the server must come back healthy; the revision that
did is recorded as `refs/odoo-runner/healthy`, so an attempt that finds the fix applied but
never confirmed running activates it again rather than report it deployed, and one that finds
the hotfix commit's own lines gone -- a person reverted it; an edit beside them does not count
-- applies it again, while one whose re-application changes nothing is the applied fix,
activated or, if confirmed, reported running. A fix whose change production already holds by
another way, with no hotfix of it, is reported running without a commit. A fix merged into its
base already is refused: it reaches production with the base's deploy. When the server does
not come back, the code is reverted, the modules upgraded and the server restarted again; the
database is not restored, so a fix whose upgrade migrated data is undone in code only. A
revert that itself fails, or leaves the server unhealthy, says that production needs a person.
A host command that runs out of time is killed with every process it started in its session,
so no upgrade goes on under the revert; one that exited is not waited for past a moment,
whatever it left holding its output -- a server it started runs on. With
`RUNNER_DEPLOY_STOP` and `_START` set, the server is stopped for the upgrade instead of
upgraded while it serves.

`SIGTERM` (`systemctl stop`, a restart) stops the agent in hand within a second and hands its
run back to Odoo as retryable, for another runner, instead of leaving it leased until the
lease expires; a run that failed for good stays failed. A hotfix is not interrupted: the
deploy executors finish what they started, the services signal the runner alone
(`KillMode=mixed`) so an upgrade or git it runs is not killed under it, and the deploy service
waits up to two hours to stop.

## Tests

```bash
cd odoo && ../p314o19m/bin/pytest tooling/runner
```

They need `git` and nothing else. The agent is a fake (`fakes.py`), and origins are bare
repositories under the test's temporary directory.
