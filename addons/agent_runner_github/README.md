# Agent Runners on GitHub (`agent_runner_github`)

Hands an agent run a GitHub token for its repository alone, and links the run to the pull
request of the branch it pushed. Nothing here knows what the run is for; the module that
queued it reacts to the link.

## A token per run

A run naming a repository (`github_repository`, `owner/name`) is handed, with its lease
(`credentials["github"]`), an installation token of the company's GitHub App limited to that
repository and to `contents` and `pull_requests` write, `checks` and `metadata` read. A kind
that needs less narrows it by overriding `_github_permissions`. GitHub expires the token
within the hour; nothing standing on the runner outlives the run. Without a GitHub App, the
run is told so in its events and gets no token.

## The link is the branch

When a run completes, the runner reports the branch it pushed (`result["branch"]`). The pull
request whose head is that branch, in that repository, is the run's -- whichever GitHub or
the runner reports first, the other links it. The pull request then calls `_run_attached(run)`,
the hook the owning module overrides.

Setting up the App and its webhook: `integration_github`.
