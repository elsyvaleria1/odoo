# Error Incidents on GitHub (`error_incident_github`)

Ties an incident to the pull requests that fix it.

## The link is the branch

The runs that work on an incident are linked to the pull requests of the branches they push
(`agent_runner_github`). A pull request linked to a run whose owner is an incident is that
incident's. No error signature is ever matched against a branch name or a pull request title.

The incident's **Pull Requests** page lists them, and its chatter hears, once each, when one
opens, its checks run, fail or pass, and when it is merged or closed.

Setting up the App and its webhook: `integration_github`.
