from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResourceResource(models.Model):
    _name = "resource.resource"
    _inherit = ["resource.resource", "mixin.gps"]
    _check_company_auto = True

    gps_device_id = fields.Many2one(
        index="unique",
        ondelete="restrict",
        check_company=True,
    )

    gps_binding_ids = fields.One2many(
        comodel_name="resource.gps.binding",
        inverse_name="resource_id",
        readonly=True,
        groups="device_gps.group_device_gps_user",
    )

    def _gps_resource(self):
        self.check_singleton()
        return self

    @api.model
    def _check_gps_device_available(self, device_id, resource_ids=()):
        if not device_id:
            return
        occupied = (
            self.sudo()
            .with_context(active_test=False)
            .search(
                [("gps_device_id", "=", device_id), ("id", "not in", resource_ids)],
                limit=1,
            )
        )
        if occupied:
            raise ValidationError(
                self.env._(
                    "This GPS device already supplies observations for another resource."
                )
            )

    @api.model_create_multi
    def create(self, vals_list):
        assigned = set()
        for vals in vals_list:
            device_id = vals.get("gps_device_id")
            if device_id:
                if device_id in assigned:
                    raise ValidationError(
                        self.env._("A GPS device can track only one resource.")
                    )
                assigned.add(device_id)
                self._check_gps_device_available(device_id)
        records = super().create(vals_list)
        tracked = records.filtered("gps_device_id")
        if tracked:
            self.env["resource.gps.binding"]._transition(tracked, fields.Datetime.now())
            self.env["device.data.log.gps.report"]._rolling_mark_stale()
        return records

    @api.constrains("company_id")
    def _check_gps_history_company(self, company_id=None):
        history = (
            self.env["resource.gps.binding"]
            .sudo()
            ._read_group(
                [("resource_id", "in", self.ids)], ["resource_id", "company_id"]
            )
        )
        for resource, company in history:
            kept = resource.company_id.id if company_id is None else company_id
            if company.id != kept:
                raise ValidationError(
                    self.env._(
                        "A resource with GPS attachment history must retain its company."
                    )
                )

    def write(self, vals):
        vals = self._get_vals_to_write(vals)
        if not vals:
            return True
        self.check_access("write")
        if "company_id" in vals:
            self._check_gps_history_company(vals["company_id"])
        changed = (
            self.filtered(
                lambda resource: resource.gps_device_id.id != vals["gps_device_id"]
            )
            if "gps_device_id" in vals
            else self.browse()
        )
        device_id = vals.get("gps_device_id")
        if device_id and self:
            if len(self) > 1:
                raise ValidationError(
                    self.env._("A GPS device can track only one resource.")
                )
            self._check_gps_device_available(device_id, self.ids)
        timezone_changed = "tz" in vals and bool(
            self.env["resource.gps.binding"]
            .sudo()
            .search_count([("resource_id", "in", self.ids)], limit=1)
        )
        if changed:
            with self.env.cr.savepoint():
                result = super().write(vals)
                self.env["resource.gps.binding"]._transition(
                    changed, fields.Datetime.now()
                )
        else:
            result = super().write(vals)
        if "gps_device_id" in vals or timezone_changed:
            self.env["device.data.log.gps.report"]._rolling_mark_stale()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_gps_history(self):
        if (
            self.env["resource.gps.binding"]
            .sudo()
            .search_count([("resource_id", "in", self.ids)], limit=1)
        ):
            raise ValidationError(
                self.env._(
                    "Archive resources with GPS attachment history instead of deleting them."
                )
            )

    def unlink(self):
        tracked = bool(self.gps_device_id)
        result = super().unlink()
        if tracked:
            self.env["device.data.log.gps.report"]._rolling_mark_stale()
        return result

    def _get_in_use_resource_ids(self):
        return super()._get_in_use_resource_ids() | set(
            self.sudo().filtered("gps_device_id").ids
        )
