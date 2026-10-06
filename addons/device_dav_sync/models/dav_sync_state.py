import hashlib
import uuid

from odoo import api, fields, models


class DAVSyncState(models.Model):
    _name = "dav.sync.state"
    _description = "DAV Resource Sync State"
    _order = "write_date desc, id desc"

    device_id = fields.Many2one(
        comodel_name="device.device",
        index=True,
        required=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        related="device_id.dav_user_id",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="device_id.company_id",
        readonly=True,
    )

    resource_type = fields.Selection(
        selection=[
            ("contact", "Contact"),
            ("event", "Calendar Event"),
            ("task", "Task"),
        ],
        index=True,
        required=True,
    )
    resource_model = fields.Char(
        index=True,
        required=True,
        help="Odoo model name (res.partner, calendar.event)",
    )
    resource_id = fields.Integer(
        index=True,
        required=True,
        help="Odoo record ID",
    )
    resource_uid = fields.Char(
        index=True,
        required=True,
        help="Unique identifier for DAV (UUID)",
    )

    etag = fields.Char(
        required=True,
        help="Entity tag for this resource version",
    )
    last_modified = fields.Datetime(
        required=True,
        help="Last modification timestamp",
    )
    sync_status = fields.Selection(
        selection=[
            ("synced", "Synced"),
            ("pending", "Pending Sync"),
            ("conflict", "Conflict"),
            ("error", "Error"),
        ],
        default="synced",
        index=True,
    )
    error_message = fields.Text(help="Error details if sync failed")

    _unique_device_resource = models.Constraint(
        "unique(device_id, resource_model, resource_id)",
        "Each resource can only have one sync state per device!",
    )

    @api.depends("resource_type", "resource_model", "resource_id")
    def _compute_display_name(self):
        for state in self:
            state.display_name = f"{state.resource_type.title()} #{state.resource_id}"

    @api.model
    def get_or_create_sync_state(
        self, device, resource_type, resource_model, resource_id
    ):
        sync_state = self.search(
            [
                ("device_id", "=", device.id),
                ("resource_model", "=", resource_model),
                ("resource_id", "=", resource_id),
            ],
            limit=1,
        )

        if not sync_state:
            record = self.env[resource_model].browse(resource_id)

            if not record.exists():
                raise ValueError(
                    f"Resource {resource_model} #{resource_id} does not exist"
                )

            if resource_model == "res.partner":
                uid = record.vcard_uid or f"{uuid.uuid4()}@odoo"
            elif resource_model == "calendar.event":
                uid = record.ical_uid or f"{uuid.uuid4()}@odoo"
            else:
                uid = f"{resource_model}-{resource_id}@odoo"

            etag = self._get_etag(record)

            sync_state = self.create(
                {
                    "device_id": device.id,
                    "resource_type": resource_type,
                    "resource_model": resource_model,
                    "resource_id": resource_id,
                    "resource_uid": uid,
                    "etag": etag,
                    "last_modified": record.write_date or record.create_date,
                    "sync_status": "pending",
                }
            )

        return sync_state

    _RESOURCE_TYPE_BY_MODEL = {
        "res.partner": "contact",
        "calendar.event": "event",
    }

    @api.model
    def _record(self, device, record, status="synced", error_msg=None):
        if not device or not record:
            return self.browse()
        record.check_singleton()
        state = self._record_many(device, record, status=status)
        if error_msg and state:
            state.error_message = error_msg
        return state

    @api.model
    def _record_many(self, device, records, status="synced"):
        if not device or not records:
            return self.browse()
        model = records._name
        resource_type = self._RESOURCE_TYPE_BY_MODEL.get(model)
        if not resource_type:
            return self.browse()

        perf = self.env["dav.performance"]
        perf.prefetch_for_serialization(records)

        existing = self.search(
            [
                ("device_id", "=", device.id),
                ("resource_model", "=", model),
                ("resource_id", "in", records.ids),
            ]
        )
        by_resource = {state.resource_id: state for state in existing}

        to_create = []
        touched = self.browse()
        for record in records:
            etag = self._get_etag(record)
            last_modified = record.write_date or record.create_date
            uid = self._resource_uid(record)
            state = by_resource.get(record.id)
            if state:
                state.write(
                    {
                        "etag": etag,
                        "last_modified": last_modified,
                        "resource_uid": uid,
                        "sync_status": status,
                        "error_message": False,
                    }
                )
                touched |= state
            else:
                to_create.append(
                    {
                        "device_id": device.id,
                        "resource_type": resource_type,
                        "resource_model": model,
                        "resource_id": record.id,
                        "resource_uid": uid,
                        "etag": etag,
                        "last_modified": last_modified,
                        "sync_status": status,
                    }
                )
        if to_create:
            batch_size = perf._get_sync_batch_size()
            for start in range(0, len(to_create), batch_size):
                touched |= self.create(to_create[start : start + batch_size])
        return touched

    @api.model
    def _resource_uid(self, record):
        if record._name == "res.partner":
            return record.vcard_uid or f"{record._name}-{record.id}@odoo"
        if record._name == "calendar.event":
            return record.ical_uid or f"{record._name}-{record.id}@odoo"
        return f"{record._name}-{record.id}@odoo"

    @api.model
    def _get_etag(self, record):
        if not record:
            return ""

        timestamp = record.write_date or record.create_date
        content = f"{record._name}-{record.id}-{timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()

    def update_sync_state(self, new_etag=None, status="synced", error_msg=None) -> None:
        self.check_singleton()

        record = self.env[self.resource_model].browse(self.resource_id)

        vals = {
            "last_modified": fields.Datetime.now(),
            "sync_status": status,
        }

        if new_etag:
            vals["etag"] = new_etag
        elif record.exists():
            vals["etag"] = self._get_etag(record)

        if error_msg:
            vals["error_message"] = error_msg
        elif status == "synced":
            vals["error_message"] = False

        self.write(vals)

    def action_view_resource(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": self.resource_model,
            "res_id": self.resource_id,
            "view_mode": "form",
            "target": "current",
        }

    def action_retry_sync(self) -> dict:
        self.write({"sync_status": "pending", "error_message": False})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Retry Scheduled",
                "message": "Resource marked for re-sync on next device request",
                "type": "success",
            },
        }
