# Agent Runners (`agent_runner`)

Queues agent runs and leases each to exactly one runner machine with the capability it
needs. The runner is a program on another machine -- the reference one is
`tooling/agent_runner/runner.py` -- that claims a run, keeps its lease alive, reports events
and finishes it. Odoo holds the queue, the leases, the credentials and the spend; a runner
holds nothing between runs.

## Runners

**Settings > Technical > Agent Runners > Runners.** A runner has the capabilities it may
claim (`sandbox`, `test`, `deploy`; a module adds its own), how many runs it may hold at once,
and a bearer token. **Issue Token** shows a new token once and stops the previous one; it is
stored encrypted, so the server needs `ODOO_API_ENCRYPTION_KEY`. The runner reads it from
`AGENT_RUNNER_TOKEN`, never from its command line.

Each runner is an inbound gate (`mixin.inbound.gate`): its calls are authenticated,
rate-limited and logged on `integration.exchange` like any other inbound integration, and run
as its service user (`agent_runner.user_agent_runner` unless the runner names one). Polling --
a claim, a heartbeat -- leaves no row.

## Runs

A module hands out work by creating an `agent.run`: a `kind` (it adds its own to the
selection), the `capability_id` a runner must have, a JSON `payload`, a `priority`, the
`company_id` whose budget pays for it, and optionally the record it works for (`res_model`,
`res_id`). That record hears how the run ended: `_agent_run_ended(run)` when it defines one,
and a note in its chatter.

```
queued -> leased -> running -> succeeded
                             -> failed      (no attempts left, or not retryable)
          (any live state)   -> cancelled   (a user cancelled it)
leased/running -> queued     (lease expired, or a retryable failure, while attempts remain)
```

## The protocol

All `POST` with a JSON body under `/agent_runner/v1/`, `Authorization: Bearer <token>`.

| Call | Body | Answer |
|---|---|---|
| `claim` | `{}` | `{"run": null}` or `{"run": {id, kind, capability, payload, attempt, lease_token, lease_seconds, credentials}}` |
| `heartbeat` | `{run, lease_token}` | `{"cancel": bool, "lease_seconds"}` -- extends the lease; the first one marks the run running |
| `events` | `{run, lease_token, events: [{type, message, data}]}` | `{"accepted": n}` -- `type` is info, progress, warning or error; at most 100 per call, messages masked |
| `complete` | `{run, lease_token, result, usage: {input_tokens, output_tokens, cost}}` | `{"state", "replayed"}` |
| `fail` | `{run, lease_token, error, retryable, usage}` | `{"state"}` -- queued again or failed; `usage` as for `complete` |

- **A runner works for one company.** It claims its own company's runs only, and is handed
  that company's keys; a machine serving several companies runs one runner per company.
- **A runner reaches only the runs it holds.** A call naming any other run -- another
  runner's, one that does not exist -- answers `409 lease_lost`, so ids reveal nothing.
- **Credentials that cannot be prepared** -- GitHub unreachable, a credential misconfigured
  -- put the run back in the queue with one attempt fewer, so it neither blocks the runner
  nor retries without end; credentials refused (a data policy, a repository the App does not
  reach) fail it at once.
- **One run, one runner.** A claim locks the runner's row, so its concurrency holds, and picks
  the run under `FOR UPDATE SKIP LOCKED`, so runners racing for one run never both get it.
- **A lease is a token.** Only its SHA-256 is stored; a call under any other token -- a
  stale lease the run has since moved on from, a forgery -- answers `409 lease_lost`.
- **`complete` and `fail` are idempotent** on the lease token: a call lost on the network is
  sent again, and the replay changes nothing and counts no spend twice.
- **Expiry.** Every minute, a run whose lease ran out is queued again with one attempt fewer,
  or failed once `max_attempts` are spent. The lease lasts `agent_runner.lease_seconds` (300;
  at least 30), renewed by each heartbeat.
- **Credentials per run.** `credentials` in the lease answer is what the run needs and only
  it -- `agent.run._prepare_credentials()`, which the modules that hand out work extend.
- **The model key follows the data policy.** A run whose agent calls a model names what it
  sends it in `ml_purpose` (`ai.project.code`, `error_incident.autofix`). It is handed the
  company's Anthropic key (`credentials["anthropic"]`) only while the company's
  machine-learning data policy lets that purpose reach Anthropic; a run the policy refuses
  fails for good at the claim, and the runner is handed the next one. Without a key, the run
  is told so and the runner uses its own model login.

## Spend

The `usage` of a `complete` -- or of a `fail`: an attempt that failed spent too -- lands on
that call's `integration.exchange` row as `ml_cost`,
`ml_input_tokens` and `ml_output_tokens`, under the run's company -- exactly where
`res.company._ml_spend_this_month()` reads machine-learning spend. A company at its
`ml_monthly_budget` is handed no more runs until the month turns.
