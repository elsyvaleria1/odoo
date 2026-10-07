# Error Incident Autofix (`error_incident_autofix`)

Hands an incident to agent runners: one run diagnoses it, and a second fixes a real defect,
in a clone of the module's repository. The code never runs on the Odoo server: the runner is
`tooling/agent_runner/runner.py` with the executors of `tooling/agent_runner/incident.py`.

## Policy

**Settings > Technical > Error Incidents > Autofix > Policy.** One policy:

- **Mode**:
  - **Off** dispatches nothing.
  - **Shadow** diagnoses and proposes fixes for review in **Autofix > Review**. Nothing is
    pushed, and users see nothing.
  - **Live** has the runner push the fix branch and open its pull request, which
    `error_incident_github` then follows to the incident.
- **When** an incident is dispatched on its own:
  - a server error, not a browser error;
  - hit by an internal user;
  - at least **Min Occurrences** (2);
  - not of an excluded exception (access refusals are a person's decision) or module;
  - new or regressed, not in a person's hands.

  **Hand to the Agents** on an incident dispatches it below these thresholds.
- **How much**:
  - **Daily Run Cap** (diagnoses and fixes together);
  - **Max Attempts** per incident, counted again from each regression;
  - the paying company's monthly machine-learning budget, which `agent_runner` enforces.

## The runs

```
incident ─► diagnose ─► not_a_defect | unclear
                 └─► defect ─► fix ─► unchanged
                                └─► proposed (shadow) | pushed (live)
```

`fix_state` is driven only by what the runs report. A failed run leaves the incident at
**Run Failed**; a regression starts again from **Not Dispatched**, with the fixes that did not
hold in the payload.

| Run | Repository token | Agent tools | Model |
|---|---|---|---|
| diagnose | `contents: read` | Read, Grep, Glob | the policy's diagnosis model |
| fix | `contents`, `pull_requests: write` | + Edit, MultiEdit, Write | the policy's fix model |

- **Repository.** It is that of the git checkout the incident's module lives in, mapped in
  **Autofix > Repositories** (`odoo`, `agromarin`, `l10n`), with its base branch.
- **Fix branch.** `<base>-fix-<slug>-i<incident>-a<attempt>`: unique by construction, so a
  recurrence never reuses an old branch.
- **Prompts.** They are versioned records (**Autofix > Prompts**); each run records the
  version it was given.
- **What the runner reads.** `test_autofix.test_the_payload_carries_what_the_runner_reads`
  pins the payload keys.

## On the runner

- The incident reaches the agent fenced off as data, with a fence drawn fresh for each run.
- The agent's environment holds only the run's Anthropic key, handed with the lease from the
  company's `claude` service credential. Without one, the runner's own model login is used.
- The runner commits the fix itself, with the incident and run as trailers, and with git
  hooks and fsmonitor disabled.
- A run whose agent touched `.git/` is failed before anything is committed.
