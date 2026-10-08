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
  **Autofix > Repositories** (`odoo`, `agromarin`, `l10n`), with its base branch. A checkout
  is known by the GitHub repository its `origin` fetches from -- wherever and under whatever
  directory it is cloned, a worktree included -- and by its directory's name only when it
  has no GitHub remote; a GitHub origin no record maps, a fork, is no repository's. An
  incident of no module is never dispatched.
- **One run counts.** Only the incident's newest diagnosis or fix, while the incident waits
  for it, moves it: a run overtaken by a regression or a person's dispatch changes nothing.
- **Regression.** An incident that reopens is the agents' again once, with its attempts
  counted afresh -- not at every occurrence after. A fix branch is numbered over the
  incident's whole life (`-a<n>`), so a later fix never reuses an earlier one's branch.
- **Fix branch.** `<base>-fix-<slug>-i<incident>-a<attempt>`: unique by construction, so a
  recurrence never reuses an old branch.
- **Prompts.** They are versioned records (**Autofix > Prompts**); each run records the
  version it was given.
- **What the runner reads.** `test_autofix.test_the_payload_carries_what_the_runner_reads`
  pins the payload keys.

## On the runner

- The incident reaches the agent fenced off as data, with a fence drawn fresh for each run.
- The agent's environment holds only the run's Anthropic key, handed with the lease from the
  company's `claude` service credential, and only while the company's machine-learning data
  policy lets `error_incident.autofix` reach Anthropic; a run the policy refuses fails at the
  claim. Without a credential, the runner's own model login is used.
- The runner commits the fix itself, with the incident and run as trailers, and with git
  hooks and fsmonitor disabled.
- A run whose agent touched `.git/` is failed before anything is committed.

## From the pull request to production

```
pushed ─► testing ─► test_failed
              └─► test_passed ─► (approved merge) ─► merged ─► deployed
                        └─► (approved hotfix) ─► hotfixing ─► deployed
```

- **Checks.** The pull request of the incident's newest fix is followed by webhook
  (`integration_github`); an earlier fix's pull request no longer speaks for the incident.
  Its checks move the incident: any failure fails it, all passed passes it. A pull request
  with no check at all -- a repository without CI -- waits in Testing, unless the policy's
  **Pass Without Checks** says it counts as passing.
- **Merge and hotfix are verbs behind an approval.** An administrator asks; a member of
  **Autofix Approver** decides. The group may be a tech lead who is no administrator: it reads
  the incident and its pull request.
  - The approval covers the very commit it was asked for. A pull request pushed to since is
    refused, not merged -- by Odoo, and by GitHub too, which is handed that commit with the
    merge however late a webhook arrives.
  - An approval is spent once its merge or hotfix ran: the next one -- another fix, a retry
    after a revert -- is a new decision with a request of its own.
  - An approver reads the incidents put to a decision, and their pull requests, not the
    others.
  - Only a fix whose checks pass is merged or hotfixed.
  - An incident holds one request at a time, so merge and hotfix are alternatives: decide or
    cancel one before asking the other.
- **Production.** A *deploy* runner (`runner.py --role deploy`) runs on the production host and
  never runs an agent.
  - **Hotfix.** It merges the fix commit into the running checkout, upgrades the modules it
    touches, restarts and checks health. When the server does not come back healthy, it
    reverts all of that, and the incident returns to **Tests Passed**.
  - **Merge.** A merged fix waits for production's own deploy. Every ten minutes Odoo asks the
    deploy runner which awaited commits the running checkouts contain -- for the policy's
    **Production Wait** (30 days); a fix production has not run by then is marked **Not
    Deployed**, and the incident says so for a person to deploy or close it.
  - **Resolved.** A contained fix puts the incident **In Production** and resolves it, and its
    users are told it is fixed.
  - **What the runner may do.** The deploy runner's checkouts and its upgrade, restart and
    health commands are the host's own configuration (`tooling/agent_runner/deploy.py`). A
    lease names a checkout and a commit, nothing to execute.
- **Regression.** A recurrence after production reopens the incident as regressed, and it is
  diagnosed again with the fix that did not hold.
