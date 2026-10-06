# Error Incidents on GitHub (`error_incident_github`)

Ties an incident to the pull requests that fix it, and hands the runs that work on it a
GitHub token for their repository alone.

## The link is the branch

An `agent.run` working for an incident names its repository (`github_repository`,
`owner/name`). When it completes, the runner reports the branch it pushed
(`result["branch"]`). The pull request whose head is that branch, in that repository, is the
run's and the incident's -- whichever GitHub or the runner reports first, the other links it.
No error signature is ever matched against a branch name or a pull request title.

The incident's **Pull Requests** page lists them, and its chatter hears, once each, when one
opens, its checks run, fail or pass, and when it is merged or closed.

## A token per run

A run naming a repository is handed, with its lease (`credentials["github"]`), an
installation token of the company's GitHub App limited to that repository and to `contents`
and `pull_requests` write, `checks` and `metadata` read. GitHub expires it within the hour;
nothing standing on the runner outlives the run. Without a GitHub App, the run is told so in
its events and gets no token.

Setting up the App and its webhook: `integration_github`.
