import uuid

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict

from .device_transport_event import ENROLLMENT_SNAPSHOT_FIELDS

_debug = DebugLog(__name__)


class DeviceEnrollment(models.Model):
    _name = "device.enrollment"
    _description = "Device Software Enrollment"
    _access_anchors = frozendict({"company": models.Anchor("company_id", shared=False)})

    name = fields.Char(required=True)
    key = fields.Char(
        default=lambda self: uuid.uuid4().hex,
        copy=False,
        readonly=True,
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        required=True,
    )
    device_id = fields.Many2one(
        comodel_name="device.device",
        index=True,
        ondelete="restrict",
        check_company=True,
        help="Optional binding to an existing operational device. Enrollment alone proves no physical identity.",
    )
    credential_id = fields.Many2one(
        comodel_name="credential.credential",
        copy=False,
        ondelete="restrict",
        check_company=True,
    )
    service_user_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda self: self.env.ref("device_transport.user_channel_receiver"),
        required=True,
        domain=[("principal_type", "=", "service")],
        ondelete="restrict",
    )
    state = fields.Selection(
        selection=[("draft", "Draft"), ("active", "Active"), ("revoked", "Revoked")],
        default="draft",
        copy=False,
        required=True,
    )
    channel_ids = fields.One2many(
        comodel_name="device.channel",
        inverse_name="enrollment_id",
    )

    _key_unique = models.Constraint("UNIQUE(key)", "An enrollment key must be unique.")

    _credential_unique = models.Constraint(
        "UNIQUE(credential_id)", "A credential belongs to only one enrollment."
    )

    @api.constrains(
        "company_id", "device_id", "credential_id", "service_user_id", "state", "key"
    )
    def _check_configuration(self):
        for record in self:
            try:
                valid_key = uuid.UUID(record.key).hex == record.key
            except ValueError, AttributeError:
                valid_key = False
            if not valid_key:
                raise ValidationError(self.env._("Use the generated enrollment key."))
            if record.device_id and record.device_id.company_id != record.company_id:
                raise ValidationError(
                    self.env._(
                        "The enrollment and device must belong to the same company."
                    )
                )
            credential = record._credential_for_validation()
            if credential and credential.company_id != record.company_id:
                raise ValidationError(
                    self.env._(
                        "The enrollment and credential must belong to the same company."
                    )
                )
            if record.service_user_id.principal_type != "service" or (
                record.state == "active" and not record.service_user_id.active
            ):
                raise ValidationError(
                    self.env._("An enrollment must run as an active service principal.")
                )
            if record.state == "active" and (
                not credential
                or not credential.active
                or not credential.is_provisioned
                or credential.is_expired
            ):
                raise ValidationError(
                    self.env._(
                        "Provision a current credential before activating this enrollment."
                    )
                )

    def _audit_snapshot(self) -> dict:
        self.check_singleton()
        return {
            name: self[name].id if name.endswith("_id") else self[name]
            for name in ENROLLMENT_SNAPSHOT_FIELDS
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.env["device.transport.event"]._append(
            "created",
            [(record.id, None, record._audit_snapshot()) for record in records],
        )
        records._place_service_user()
        return records

    def _place_service_user(self) -> None:
        Gate = self.env["mixin.inbound.gate"]
        live = self.filtered(lambda enrollment: enrollment.state != "revoked")
        for principal, enrollments in live.grouped("service_user_id").items():
            Gate._place_principal_in_companies(principal, enrollments.company_id)

    def write(self, vals):
        self.check_access("write")
        before = (
            {record.id: record._audit_snapshot() for record in self}
            if set(vals) & set(ENROLLMENT_SNAPSHOT_FIELDS)
            else {}
        )
        for record in self:
            for name in ("key", "company_id"):
                if name in vals and vals[name] != (
                    record[name].id if name == "company_id" else record[name]
                ):
                    raise UserError(
                        self.env._(
                            "Enrollment identity and company cannot be changed; create a new enrollment."
                        )
                    )
            if (
                record.state != "draft"
                and "device_id" in vals
                and vals["device_id"] != record.device_id.id
            ):
                raise UserError(
                    self.env._(
                        "An activated enrollment cannot be rebound to another device."
                    )
                )
            if (
                record.state != "draft"
                and "service_user_id" in vals
                and vals["service_user_id"] != record.service_user_id.id
            ):
                raise UserError(
                    self.env._("An activated enrollment retains its service principal.")
                )
            if record.state == "revoked" and vals.get("state", "revoked") != "revoked":
                raise UserError(
                    self.env._("A revoked enrollment cannot be reactivated.")
                )
            if record.state == "active" and vals.get("state") == "draft":
                raise UserError(
                    self.env._(
                        "Revoke the enrollment instead of resetting it to draft."
                    )
                )
        result = super().write(vals)
        changes = [
            (record.id, before[record.id], after)
            for record in self
            if record.id in before
            and before[record.id] != (after := record._audit_snapshot())
        ]
        self.env["device.transport.event"]._append("changed", changes)
        if "service_user_id" in vals or "state" in vals:
            self._place_service_user()
        if "state" in vals or "credential_id" in vals:
            _debug.lifecycle(
                "enrollment_changed",
                enrollment_ids=self.ids,
                state=vals.get("state"),
                credential_changed="credential_id" in vals,
            )
        return result

    def unlink(self):
        self.check_access("unlink")
        changes = [(record.id, record._audit_snapshot(), None) for record in self]
        result = super().unlink()
        self.env["device.transport.event"]._append("deleted", changes)
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_draft(self) -> None:
        if any(record.state != "draft" for record in self):
            raise UserError(
                self.env._(
                    "Retain activated enrollments and their history; revoke them instead."
                )
            )

    def _credential_for_validation(self):
        self.check_singleton()
        return self.credential_id.with_privilege(
            "device_transport.privilege_validate_enrollment",
            reason="validate the enrollment's current credential metadata",
        )

    def action_provision_credential(self) -> None:
        self.check_access("write")
        for record in self:
            if record.state == "revoked":
                raise UserError(self.env._("Create a new enrollment after revocation."))
            record.credential_id = self.env["device.device"]._create_inbound_credential(
                f"{record.name} {uuid.uuid4().hex}", record.company_id.id
            )

    def action_activate(self):
        self.write({"state": "active"})

    def action_revoke(self):
        self.write({"state": "revoked"})

    @api.model
    def _probe_integrity(self, limit=100, after_id=0):
        if not self.env.is_system():
            raise AccessError(
                self.env._("Only administrators can inspect enrollment integrity.")
            )
        limit = max(1, min(int(limit), 1000))
        records = self.search([("id", ">", int(after_id))], order="id", limit=limit + 1)
        page = records[:limit]
        findings = []
        with _debug.perf("enrollment_integrity_probe", cr=self.env.cr, limit=limit):
            latest = {}
            if page:
                self.env.cr.execute(
                    SQL(
                        "SELECT e.id, history.after FROM device_enrollment e "
                        "LEFT JOIN LATERAL (SELECT after FROM device_transport_event "
                        "WHERE enrollment_ref = e.id AND subject_kind = 'enrollment' ORDER BY id DESC LIMIT 1) history ON TRUE "
                        "WHERE e.id IN %s",
                        tuple(page.ids),
                    )
                )
                latest = dict(self.env.cr.fetchall())
            for record in page:
                credential = record._credential_for_validation()
                reasons = []
                if latest.get(record.id) is None:
                    reasons.append("missing_journal")
                elif latest[record.id] != record._audit_snapshot():
                    reasons.append("journal_drift")
                if (
                    record.device_id
                    and record.device_id.company_id != record.company_id
                ):
                    reasons.append("device_company_mismatch")
                if credential and credential.company_id != record.company_id:
                    reasons.append("credential_company_mismatch")
                if (
                    not record.service_user_id.active
                    or record.service_user_id.principal_type != "service"
                ):
                    reasons.append("invalid_service_principal")
                if record.state == "active":
                    if (
                        not credential
                        or not credential.active
                        or not credential.is_provisioned
                        or credential.is_expired
                    ):
                        reasons.append("unusable_credential")
                    if record.device_id and not record.device_id.active:
                        reasons.append("inactive_device")
                if reasons:
                    findings.append({"id": record.id, "reasons": reasons})
            _debug.logic(
                "enrollment_integrity",
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
