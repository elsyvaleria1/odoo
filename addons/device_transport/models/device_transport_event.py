from itertools import batched
from uuid import uuid4

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.tools import SQL, frozendict

_debug = DebugLog(__name__)

# Only typed security metadata belongs here, never names, tokens or payloads.
ENROLLMENT_SNAPSHOT_FIELDS = (
    "state",
    "company_id",
    "device_id",
    "credential_id",
    "service_user_id",
)


CHANNEL_SNAPSHOT_TYPES = {
    "enrollment_id": int,
    "company_id": int,
    "external_identifier": str,
    "purpose": str,
    "active": bool,
    "auth_type": str,
    "processing_mode": str,
    "ip_whitelist": (str, type(None)),
    "max_payload_size": int,
    "rate_limit_enabled": bool,
    "rate_limit_strict": bool,
    "rate_limit_requests": int,
    "rate_limit_window_seconds": int,
    "timestamp_verification_enabled": bool,
    "timestamp_header": (str, type(None)),
    "timestamp_max_age_seconds": int,
    "duplicate_detection_enabled": bool,
    "duplicate_window_seconds": int,
    "log_request_payload_max_bytes": int,
    "log_retention_days": int,
}


class DeviceTransportEvent(models.Model):
    _name = "device.transport.event"
    _description = "Device Transport Event"
    _order = "id desc"
    _rec_name = "event"
    _log_access = False
    _allow_sudo_commands = False
    _access_anchors = frozendict({"company": models.Anchor("company_id", shared=False)})

    subject_kind = fields.Selection(
        selection=[("enrollment", "Enrollment"), ("channel", "Channel")],
        default="enrollment",
        readonly=True,
        required=True,
    )
    channel_id = fields.Many2one(
        comodel_name="device.channel",
        index=True,
        readonly=True,
        ondelete="set null",
    )
    channel_ref = fields.Integer(readonly=True)

    event = fields.Selection(
        selection=[
            ("created", "Created"),
            ("changed", "Security configuration changed"),
            ("deleted", "Draft deleted"),
            ("baseline", "Upgrade baseline"),
        ],
        readonly=True,
        required=True,
    )
    occurred_at = fields.Datetime(
        readonly=True,
        required=True,
    )
    actor_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
        ondelete="set null",
    )
    actor_ref = fields.Integer(
        readonly=True,
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        index=True,
        readonly=True,
        required=True,
        ondelete="restrict",
    )
    enrollment_id = fields.Many2one(
        comodel_name="device.enrollment",
        index=True,
        readonly=True,
        ondelete="set null",
    )
    enrollment_ref = fields.Integer(
        readonly=True,
        required=True,
    )
    before = fields.Json(readonly=True)
    after = fields.Json(readonly=True)
    correlation_id = fields.Char(
        readonly=True,
        required=True,
    )

    _enrollment_history_idx = models.Index(
        "(enrollment_ref, id DESC) WHERE subject_kind = 'enrollment'"
    )
    _channel_history_idx = models.Index(
        "(channel_ref, id DESC) WHERE subject_kind = 'channel'"
    )

    @api.model
    def _append(self, event, changes, *, subject_kind="enrollment"):
        """Append trusted lifecycle snapshots in the caller's transaction."""
        if not changes:
            return self.browse()
        event = self._fields["event"].convert_to_cache(event, self)
        self._fields["subject_kind"].convert_to_cache(subject_kind, self)
        correlation = uuid4().hex
        rows = []
        for subject_ref, before, after in changes:
            for snapshot in (before, after):
                if snapshot is not None:
                    self._check_snapshot(subject_kind, snapshot)
            snapshot = after or before
            enrollment_ref = (
                snapshot["enrollment_id"] if subject_kind == "channel" else subject_ref
            )
            channel_ref = subject_ref if subject_kind == "channel" else None
            rows.append(
                SQL(
                    "(%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)",
                    event,
                    self.env.cr.now(),
                    self.env.uid,
                    self.env.uid,
                    snapshot["company_id"],
                    enrollment_ref
                    if subject_kind == "channel" or event != "deleted"
                    else None,
                    enrollment_ref,
                    json_dumps(before),
                    json_dumps(after),
                    correlation,
                    subject_kind,
                    channel_ref if event != "deleted" else None,
                    channel_ref,
                )
            )
        ids = []
        for batch in batched(rows, 1000, strict=False):
            self.env.cr.execute(
                SQL(
                    "INSERT INTO device_transport_event "
                    "(event, occurred_at, actor_id, actor_ref, company_id, enrollment_id, enrollment_ref, before, after, correlation_id, subject_kind, channel_id, channel_ref) "
                    "VALUES %s RETURNING id",
                    SQL(", ").join(batch),
                )
            )
            ids.extend(row[0] for row in self.env.cr.fetchall())
        _debug.lifecycle(
            "transport_events_appended",
            transport_event=event,
            subject_kind=subject_kind,
            count=len(ids),
        )
        return self.browse(ids)

    @api.model
    def _check_snapshot(self, subject_kind, snapshot) -> None:
        if subject_kind == "enrollment":
            valid = (
                set(snapshot) == set(ENROLLMENT_SNAPSHOT_FIELDS)
                and snapshot["state"] in ("draft", "active", "revoked")
                and all(
                    type(snapshot[name]) in (int, bool)
                    for name in ENROLLMENT_SNAPSHOT_FIELDS
                    if name != "state"
                )
            )
        else:
            valid = (
                set(snapshot) == set(CHANNEL_SNAPSHOT_TYPES)
                and all(
                    isinstance(snapshot[name], kind)
                    for name, kind in CHANNEL_SNAPSHOT_TYPES.items()
                )
                and snapshot["purpose"] in ("telemetry", "commands")
                and snapshot["auth_type"] == "bearer"
                and snapshot["processing_mode"] == "sync"
            )
        if not valid:
            raise ValueError("Transport audit accepts typed security snapshots only")

    @api.model_create_multi
    def create(self, vals_list):
        if not vals_list:
            return self.browse()
        raise AccessError(
            self.env._("Transport events are written by lifecycle actions.")
        )

    def write(self, vals):
        if not self or not vals:
            return True
        raise AccessError(self.env._("Transport history cannot be changed."))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_uninstall(self) -> None:
        if self:
            raise AccessError(self.env._("Transport history must be retained."))
