# GitHub API Client (`integration_github`)

GitHub's REST API through the shared transport (`integration.service` `github`), with two
ways to authenticate, and pull requests kept current by webhook for other modules to follow.

## Authenticating

**A personal or company token**: a `credential.credential` on the GitHub service holding a
`bearer_token`, as for any bearer service.

**A GitHub App** (preferred): a credential of category **GitHub App** (`github_app`) on the
GitHub service, holding `app_id`, `private_key` (the PEM GitHub generated) and
`installation_id` (the App's installation on the organization). Odoo then:

- signs a nine-minute RS256 JWT with the key for the App's own endpoints (a call made under the
  `github_app_jwt` context);
- calls everything else with an **installation token**, minted on demand and reused until five
  minutes before GitHub expires it (an hour);
- mints, for whoever asks through `tools.mint_installation_token(env, credential, repositories,
  permissions)`, a token limited to the named repositories and permissions -- what
  `error_incident_github` hands an agent run for its repository alone. The minting call is not
  logged: its answer is the token.

## Webhooks

**Integrations > API Transport > GitHub > Webhooks.** A webhook record gives the
**Payload URL** to paste into the App's (or a repository's) webhook settings, content type
`application/json`, and **Issue Secret** shows the signing secret once.

Each delivery is verified against `X-Hub-Signature-256`, claimed by its `X-GitHub-Delivery`
id (a redelivery answers 409), logged on `integration.exchange` under its `X-GitHub-Event`,
and acted on at once -- what it records is small, and GitHub waits ten seconds:

| Event | Effect |
|---|---|
| `pull_request` | the `integration.github.pull` is created or updated: title, branch, head commit, open / closed / merged |
| `check_run`, `workflow_run`, `status` | an `integration.github.check` of the commit; every pull request headed by it recomputes `checks_state` |
| `ping` | answered `pong` |
| anything else | acknowledged, `ignored` |

A check suite is not a check: GitHub requests one for every installed app, and the suite of
an app that never runs stays queued forever.

`checks_state` of a pull request is over the checks of its head commit only: `failure` if any
failed, `pending` while any is unfinished, `success` once all passed, `none` without checks.
A new head starts afresh.

## Following pull requests

A module reacts to what GitHub said by overriding `integration.github.pull._github_updated()`,
called once per actual change -- a redelivered or repeated check is no news. A module that
follows another event adds `_github_<event>(repository, payload)` on
`integration.github.webhook`. **Refresh from GitHub** reads a pull request and its head's
checks through the API, for a missed delivery or a repository without a webhook.
