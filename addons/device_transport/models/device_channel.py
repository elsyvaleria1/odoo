from typing import Self

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict

from .device_transport_event import CHANNEL_SNAPSHOT_TYPES

_debug = DebugLog(__name__)


class DeviceChannel(models.Model):
    _name = "device.channel"
    _inherit = ["mixin.integration.receiver"]
    _description = "Device Communication Channel"
    _access_anchors = frozendict({"company": models.Anchor("company_id", shared=False)})
    _inbound_elevated = False

    enrollment_id = fields.Many2one(
        comodel_name="device.enrollment",
        index=True,
        required=True,
        ondelete="restrict",
    )
    external_identifier = fields.Char(
        required=True,
        help="Opaque routing key within this enrollment; never an authentication factor.",
    )
    purpose = fields.Selection(
        selection=[("telemetry", "Telemetry"), ("commands", "Commands")],
        default="telemetry",
        required=True,
    )
    company_id = fields.Many2one(
        related="enrollment_id.company_id",
        default=None,
        store=False,
        index=False,
        readonly=True,
        required=False,
    )
    credential_id = fields.Many2one(
        related="enrollment_id.credential_id",
        compute_sudo=False,
        index=False,
        readonly=True,
    )
    service_user_id = fields.Many2one(
        related="enrollment_id.service_user_id",
        compute_sudo=False,
        readonly=True,
    )
    auth_type = fields.Selection(
        selection=[("bearer", "Bearer Token")],
        default="bearer",
        required=True,
    )
    processing_mode = fields.Selection(
        selection=[("sync", "Synchronous")],
        default="sync",
        required=True,
    )
    duplicate_detection_enabled = fields.Boolean(default=False)

    _route_unique = models.Constraint(
        "UNIQUE(enrollment_id, external_identifier)",
        "A channel key must be unique within its enrollment, including archived channels.",
    )

    @api.constrains("external_identifier", "company_id", "enrollment_id")
    def _check_identity(self):
        for record in self:
            if (
                not record.external_identifier.strip()
                or len(record.external_identifier) > 128
                or "/" in record.external_identifier
            ):
                raise ValidationError(
                    self.env._(
                        "Use a nonblank channel key of at most 128 characters without slashes."
                    )
                )
            if record.company_id != record.enrollment_id.company_id:
                raise ValidationError(
                    self.env._("A channel must belong to its enrollment's company.")
                )

    def _audit_snapshot(self) -> dict:
        self.check_singleton()
        return {
            name: self[name].id
            if name.endswith("_id")
            else (self[name] or None)
            if isinstance(kind, tuple)
            else self[name]
            for name, kind in CHANNEL_SNAPSHOT_TYPES.items()
        }

    @api.model_create_multi
    def create(self, vals_list):
        if any(
            {"credential_id", "service_user_id"} & vals.keys() for vals in vals_list
        ):
            raise UserError(
                self.env._(
                    "Manage credentials and the service principal on the enrollment."
                )
            )
        records = super().create(vals_list)
        self.env["device.transport.event"]._append(
            "created",
            [(record.id, None, record._audit_snapshot()) for record in records],
            subject_kind="channel",
        )
        return records

    def write(self, vals):
        self.check_access("write")
        before = (
            {record.id: record._audit_snapshot() for record in self}
            if set(vals) & CHANNEL_SNAPSHOT_TYPES.keys()
            else {}
        )
        if {"credential_id", "service_user_id"} & vals.keys():
            raise UserError(
                self.env._(
                    "Manage credentials and the service principal on the enrollment."
                )
            )
        for record in self:
            for name in (
                "enrollment_id",
                "external_identifier",
                "company_id",
                "purpose",
            ):
                if name in vals and vals[name] != (
                    record[name].id if name.endswith("_id") else record[name]
                ):
                    raise UserError(
                        self.env._(
                            "Channel identity, purpose and company cannot be changed; create a new channel."
                        )
                    )
        result = super().write(vals)
        changes = [
            (record.id, before[record.id], after)
            for record in self
            if record.id in before
            and before[record.id] != (after := record._audit_snapshot())
        ]
        self.env["device.transport.event"]._append(
            "changed", changes, subject_kind="channel"
        )
        return result

    def unlink(self):
        self.check_access("unlink")
        changes = [(record.id, record._audit_snapshot(), None) for record in self]
        result = super().unlink()
        self.env["device.transport.event"]._append(
            "deleted", changes, subject_kind="channel"
        )
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_unused(self) -> None:
        if any(record.enrollment_id.state != "draft" for record in self):
            raise UserError(
                self.env._(
                    "Archive channels of activated enrollments instead of deleting them."
                )
            )
        if (
            self.env["integration.exchange"]
            .with_privilege(
                "device_transport.privilege_validate_enrollment",
                reason="retain channel exchange history",
            )
            .search_count(
                [
                    (
                        "channel_id",
                        "in",
                        [f"{self._name},{record.id}" for record in self],
                    ),
                ],
                limit=1,
            )
        ):
            raise UserError(
                self.env._(
                    "A channel with exchange history must be archived instead of deleted."
                )
            )

    @api.model
    def _receiver_for_route(self, enrollment_key, channel_key, **_kwargs) -> Self:
        return self.search(
            [
                ("enrollment_id.key", "=", enrollment_key),
                ("external_identifier", "=", channel_key),
            ],
            limit=1,
        )

    def _hold_inbound_authority(self) -> None:
        self._lock_admission_authority()

    def _lock_admission_authority(self) -> bool:
        self.check_singleton()
        enrollment = self.enrollment_id
        with _debug.perf(
            "channel_admission_authority", cr=self.env.cr, channel_id=self.id
        ):
            for table, record_id in (
                ("device_enrollment", enrollment.id),
                ("credential_credential", enrollment.credential_id.id),
                ("res_users", enrollment.service_user_id.id),
                ("device_channel", self.id),
            ):
                if not record_id:
                    return False
                self.env.cr.execute(
                    SQL(
                        "SELECT id FROM %s WHERE id = %s FOR SHARE",
                        SQL.identifier(table),
                        record_id,
                    )
                )
                if not self.env.cr.fetchone():
                    return False
        return True

    def _decide_inbound_request(
        self,
        headers,
        body=None,
        remote_addr=None,
        mode="enforce",
        caller_already_checked=False,
    ):
        self.check_singleton()
        enrollment = self.enrollment_id
        credential = enrollment._credential_for_validation()
        device = enrollment.device_id
        usable = (
            self.active
            and enrollment.state == "active"
            and enrollment.service_user_id.active
            and enrollment.service_user_id.principal_type == "service"
            and self.company_id == enrollment.company_id
            and credential
            and credential.active
            and credential.is_provisioned
            and not credential.is_expired
            and credential.company_id == enrollment.company_id
            and (
                not device
                or (device.active and device.company_id == enrollment.company_id)
            )
        )
        if not usable:
            _debug.logic(
                "channel_refused",
                channel_id=self.id,
                enrollment_id=enrollment.id,
                reason="inactive_identity",
            )
            return False, 403, "Channel enrollment is not active", "inactive_enrollment"
        return super()._decide_inbound_request(
            headers,
            body=body,
            remote_addr=remote_addr,
            mode="enforce",
            caller_already_checked=caller_already_checked,
        )

    @api.model
    def _probe_integrity(self, limit=100, after_id=0):
        if not self.env.is_system():
            raise AccessError(
                self.env._("Only administrators can inspect channel integrity.")
            )
        limit = max(1, min(int(limit), 1000))
        records = self.with_context(active_test=False).search(
            [("id", ">", int(after_id))], order="id", limit=limit + 1
        )
        page = records[:limit]
        findings = []
        with _debug.perf("channel_integrity_probe", cr=self.env.cr, limit=limit):
            latest = {}
            if page:
                self.env.cr.execute(
                    SQL(
                        "SELECT c.id, history.after FROM device_channel c "
                        "LEFT JOIN LATERAL (SELECT after FROM device_transport_event "
                        "WHERE channel_ref = c.id AND subject_kind = 'channel' ORDER BY id DESC LIMIT 1) history ON TRUE "
                        "WHERE c.id IN %s",
                        tuple(page.ids),
                    )
                )
                latest = dict(self.env.cr.fetchall())
            for record in page:
                reason = (
                    "missing_journal"
                    if latest.get(record.id) is None
                    else "journal_drift"
                    if latest[record.id] != record._audit_snapshot()
                    else None
                )
                if reason:
                    findings.append({"id": record.id, "reasons": [reason]})
            _debug.logic(
                "channel_integrity",
                scanned=len(page),
                findings=len(findings),
                truncated=len(records) > limit,
            )
        return {
            "scanned": len(page),
            "findings": findings,
            "truncated": len(records) > limit,
            "next_after_id": page[-1].id if page else int(after_id),
        }
