# Authentication clients and diagnostic probes

`auth.user.client` recognizes one user's browser profile or session-scoped application. It is not physical equipment. `device.device` is the communication endpoint registry; neither model depends on the other.

Login creates a mandatory `auth.user.client.session` binding before the HTTP session is published. The session carries the client ID, its revocation generation and the user's session epoch. Each authenticated request reads these authorities and the active session-family association from a fresh read-only cursor on the primary database. Replica lag, an old business snapshot and token-cache entries cannot extend a revoked binding. Changing a recognition cookie or user agent cannot change an existing binding.

Revocation increments the client's generation and ends its associations. Removing session-store entries is postcommit cleanup; a rollback discards it, and a cleanup failure cannot restore authority. A fresh login may reactivate the recognized client, but its earlier generations stay invalid. Ending the user's other sessions increments the user epoch and rotates the retained session. This action requires the owner or a settings administrator with write access to the target user. Bulk client revocation includes inactive clients, since logging out does not discard their remembered trust. Session associations record their end time and reason. User-wide revocation ends every association except the rotated session that is retained, including siblings on the same client. Session endings touch the client before changing associations, so concurrent last-session logouts retry against a fresh snapshot rather than leaving an active client behind.

Activity and GeoIP collection are optional. They update the bound client's summaries and `auth.user.client.address`, an aggregate of first/last observations per client and IP address. Observations cannot create bindings or reactivate revoked clients. Disabling tracking does not disable binding or revocation.

`auth.totp.trust` owns its user-bound, expiring credential policy. It shares only the secret-generation/hash/verification functions in `odoo.libs.secret_key` with API keys. It has no API-key scope or API-key issuance method. A trust-based login checks the credential again while holding the client binding lock, closing the verification/revocation race. `totp_trust_ids` retains every grant issued to or used by a client. A grant can be associated with several recognized clients when its cookie survives a recognition reset. Revoking a client removes all of its associated grants. `_end_sessions()` only invalidates sessions; `_revoke()` additionally forgets remembered trust through the authentication extension. Retention preserves a client with an active association, retained session history or unexpired trust.

`base.device_retention_days` defaults to 90 days; nonpositive values disable client, session and address expiration. Ended associations expire from `ended_at`, falling back to `last_activity` for legacy rows without an end time. Inactive clients expire only when their last activity and every ended association are older than the cutoff, with no active association or unexpired trust. This preserves recently ended sessions regardless of cleanup order. Address retention still follows last activity and preserves the client’s current address.

`auth.event` records completed client/session revocations, logout, user-wide session invalidation and TOTP trust issuance/revocation in the same transaction as the action. It retains actor/subject and numeric record references after client or credential deletion. Public create/write/delete are refused. Global administrators read all events; a company-scoped administrator is limited by the subject user’s company membership. Users read their own subject events. Logout on an unauthenticated route can record an unknown actor while preserving the session’s subject. Each append batch has a correlation UUID. These are committed security actions, not failed-login attempts or address observations.

Event retention is independent: `auth.event_retention_days` defaults to 365 days, with nonpositive values disabling expiration. Cleanup processes at most 5000 oldest events per batch. No cookie, key, session-store identifier or payload is copied into the event.

## Upgrade

Base 1.125 adds the event table. Base 1.124 renames the three client tables and their metadata in place; auth_totp 1.2 separates trust storage from API scope policy. Auth_totp 1.3 migrates recorded client links to a relation supporting multiple grants. Auth_totp 1.4 and auth_portal 1.2 make the trust badge reflect unexpired grants, while retaining expired associations until cleanup. Unassociated legacy grants have lost their client provenance; migration expires them and records credential-revocation events rather than guessing their associations. Those browsers require MFA again. Recorded links retain their IDs, hashes and original expiry. Upgrade base and the installed authentication/portal addons together:

```sh
odoo-bin -c <config> -d <database> -u base,auth_totp,portal,auth_portal,auth_totp_mail --stop-after-init
```

The migration preserves client/session/address IDs, recognition hashes, trust hashes, expiry, links and scoped stored expressions. Existing authenticated sessions require a new login because they have no authoritative binding claims. Legacy recognition provenance is marked unclassified until a new login establishes it. Recognition and trusted-browser cookies retain their wire names. Do not deploy the new code against an unmigrated database.

## Diagnostics

The probes are private, administrator-only, bounded, read-only inspections of persisted state. From an Odoo shell:

```python
env["auth.user.client"]._probe_integrity(limit=100)
env["device.device"]._probe_integrity(limit=100)
```

The client probe finds inactive clients with active associations and active clients without active associations. The device probe finds missing company scope and cross-company parent links; the resource bridge adds incompatible resource companies and non-material identities, while GPS adds duplicate receiver keys and malformed IMEIs. Several endpoints may represent the same resource. It also reports orphan connection and stream IDs whose declared device owner no longer exists. Each result indicates truncation. The probes do not establish that a device-to-asset mapping is semantically correct.

Enable a scoped channel, for example:

```text
--log-handler=odoo.debug.lifecycle.base.auth_user_client:DEBUG
--log-handler=odoo.debug.logic.base.auth_user_client:DEBUG
--log-handler=odoo.debug.perf.base.auth_user_client:DEBUG
--log-handler=odoo.debug.perf.device.device_device:DEBUG
--log-handler=odoo.debug.perf.device.device_device_stream:DEBUG
```

Session and address models have their own `base.auth_user_client_session` and `base.auth_user_client_address` scopes. Trust uses `auth_totp.auth_totp_trust`. Shared stream operations live in `device/models/device_device_stream.py`; MQTT, WebSocket and Modbus adapters retain their protocol entry points and format-specific behavior. Modbus reads still return measurements, while MQTT/WebSocket reads return stream status. Stream control, command sending and HTTP transport require write access to the device before elevation or network activity; read-only device access does not authorize these operations. Stream company scope and default MQTT client identity follow changes to their source device fields. Device transport, stream reconciliation, polling, health checks and ingest emit elapsed-time/query-count spans. These events contain record IDs, counts and reason codes; they do not include cookies, credentials, session identifiers or raw telemetry payloads.

Device 19.0.2.3.0 changes the existing part hierarchy’s foreign key from cascade to restrict. Upgrade `device` before relying on deletion cleanup. Deleting a hierarchy now checks access to all parts, including archived and rule-hidden ones, and deletes leaves through the ORM so their connections, streams and pending commands are removed. A concurrent attachment outside the deleting transaction’s snapshot is refused by the foreign key. This retains the current containment deletion policy; the planned gateway/attachment split remains separate. Scoped lifecycle logging reports root and part counts through `device.device_device`.

Optional physical resource representation is implemented by `device_resource`; `asset_device` projects the asset vocabulary from that reference. The base probe runs bounded checks contributed by these capability modules and GPS, without depending on an asset column or treating several endpoints for one resource as duplicate equipment. Channel and enrollment redesign remain separate.
