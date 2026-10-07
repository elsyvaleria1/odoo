# Error Incidents (`error_incident`)

Records the server's and the browser's unexpected errors as grouped, tracked incidents, and
shows whoever hit one where it stands, live, in the error dialog.

## What is recorded, and from where

| Source | Hook | Written |
|---|---|---|
| Request | `ir.http._handle_error` | after the request's cursor is released, on a cursor of its own |
| Scheduled action | `ir.cron._prepare_failure_vals` (status `failed`) | with the job's failure |
| Background job | `ir.job._notify_failed` | with the job's failed state |
| Browser | the error dialog, through `/error_incident/report` | in that request |

Errors raised for the user to read -- `UserError`, `AccessError`, `ValidationError`,
`RedirectWarning`, an expired session, an HTTP 4xx -- are answers, not defects, and are not
recorded. A rule (**Settings > Technical > Error Incidents > Rules**) sets a new incident
aside by source, exception or module.

Messages and tracebacks pass `odoo.libs.redact.mask_text` before storage. That masks secrets,
not personal data: a traceback can carry a customer's name or email, which matters wherever
it is sent on (`error_incident_autofix` sends it to a model only under the company's data
policy).

Not recorded: an error raised outside a request's transaction -- while its session or route
is resolved, or while a response streams -- which never reaches `_handle_error`.

A resolved incident that occurs again on the server is reopened as regressed. A browser's
report of it is recorded but does not reopen it: anyone signed in can make one up, so the
incident's chatter says a browser reported it again, and a person decides.

## What makes two occurrences one incident

The exception's type and where in our code it happened -- never the line number, which moves
with every unrelated edit.

- **Server**: the innermost frame of an addon or the framework: its module, file and function.
- **Browser**: the innermost frame of an addon's `static/src`, located through the bundle's
  source map, and the text of the line that failed. Without a map, the message, its numbers
  and quoted values masked.

## Browser errors need source maps kept on the server

A production bundle is minified: a browser frame names a column of one long line. To locate it,
set the system parameter

```
web.esbuild.source_maps = external
```

`external` writes each bundle's map beside it and links it nowhere; the asset route serves it
to administrators only, since it carries every bundled source. `linked` would serve it to
whoever loads the bundle.

## The dialog

An unexpected request error carries `data.context.error_incident = {fingerprint, occurrence}`.
The dialog asks `/error_incident/journey` once for that occurrence and is then pushed
`error_incident/journey` over the bus -- on capture, state change and regression -- so it never
polls. A browser error is reported by the dialog itself and followed the same way.

Internal users only, and only their own occurrences: the routes read through the code-only
privilege `error_incident.privilege_follow_own_errors`, whose rows reach a user's own records.
An administrator also gets **Open the incident**.

Resolving an incident tells each internal user it affected, in their language.

## Retention

Daily, occurrences older than `error_incident.occurrence_retention_days` (90) go, and each
incident keeps at most `error_incident.occurrences_kept_per_incident` (50). Incidents and their
counts stay.
