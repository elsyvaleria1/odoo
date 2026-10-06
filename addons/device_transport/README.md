# Device transport

An enrollment identifies an authenticated software installation. It belongs to
one company and may bind to an existing operational device; this does not prove
physical hardware identity. Channels are named communication endpoints within an
enrollment. Their routing keys are not credentials and may repeat across
enrollments.

Device managers create an enrollment, provision its credential, create channels,
and activate it. Store the bearer token in the sender's secret configuration.
Each credential belongs to one enrollment. Rotating it replaces the token for
all of that enrollment’s channels. Distinct security principals require distinct
enrollments, even when they operate the same hardware.
Revocation is terminal; create another enrollment to enroll again. Activated
enrollments and their channel identities cannot be rebound or deleted. Archive
individual channels to disable them.

`GET /device/v1/enrollments/<key>/channels/<channel-key>/status` checks admission.
All scoped routes require the current bearer credential regardless of legacy
receiver audit settings. Integration receivers provide rate limits and exchange
history. A commands purpose reserves a separate endpoint identity; command
execution is not implemented by this module.

With `device_gps`, POST Teltonika JSON to
`/device/v1/enrollments/<key>/channels/<channel-key>/gps`. The channel must be a
telemetry channel bound to a GPS device, and payload field 14 must match its key.
Each accepted observation retains its channel. Existing tracker URLs continue
using their legacy receiver keys; installing this module does not enroll or
reroute them automatically.

Version 19.0.1.2.0 requires `-u device_transport` on an existing installation.
The journal is now `device.transport.event`, covering enrollments and channels.
The upgrade preserves existing enrollment events and their record IDs, and adds
explicit baselines for existing channels, including archived ones. A direct
upgrade from 1.0 also creates enrollment baselines. Neither migration invents
past events; rerunning baseline creation adds no duplicates.

Transport History is immutable through ordinary ORM operations and visible to
device managers within each event's company scope. It records actor, transaction
time, stable numeric identities, typed before/after snapshots and a batch
correlation ID. Enrollment snapshots contain state and identity references.
Channel snapshots contain routing identity, purpose, enablement, authentication,
processing, IP, payload, rate, timestamp, duplicate and diagnostic-retention
policy. Tokens, credential contents, names and telemetry payloads are excluded.
Credential contents remain the vault's responsibility. Cosmetic, activity-only
and no-op writes add no event.

Events and lifecycle changes share a transaction: a rollback removes both, and
journal failures propagate to the caller. Deleting a draft or its former actor
retains numeric references. No automatic journal retention purge is configured.
This is an application audit, not protection against a database administrator.

From an administrator shell, call `_probe_integrity(limit=100, after_id=0)` on
`env['device.enrollment']` or `env['device.channel']`. Follow `next_after_id` while
`truncated` is true. Probes include archived records within the shell's company
scope and report missing or divergent history through indexed latest-event
lookups. The enrollment probe also checks current identity validity. DebugLog
records lifecycle counts, admission verdicts, lock timing and integrity findings,
without credentials or incoming payloads.

Synchronous admission holds shared row locks on the enrollment, its credential,
service principal and channel until the transaction ends. Integration calls the
channel's `_hold_inbound_authority` hook on the request cursor before opening its
separate verdict cursor. The verdict can commit refusal evidence independently,
but it neither owns nor reacquires these authority locks. Calling the decision
method alone does not establish a handler transaction's authority boundary. A revocation or policy
change waits for previously admitted transactions; an older database snapshot
encountering a committed change is retried, then re-evaluates authorization.
The HTTP authentication boundary preserves retryable concurrency errors, and each
receiver attempt clears the previous attempt's admission and refusal renderer.
The locks allow concurrent authorization checks; later writes can still contend
and require transaction retry. Replays retain only request-local rate allowances
and the IDs of their own rolled-back exchange attempts. A database allowance is
reusable after its charging transaction commits; a changed rate policy requires
a new allowance. Authentication and current enrollment validity are checked on
every attempt. Payload deduplication ignores only the same request's still-failed
rollback records, while retaining those records in history. Separate requests
receive neither allowance reuse nor that duplicate-check exception.

This guarantee covers synchronous database work. Physical-device archival and
transfer are checked at admission but are outside this lock boundary. It does
not provide queued-command authorization, remote exactly-once execution or
atomic recovery across local and foreign databases. Those require their own
execution and recovery contracts.
