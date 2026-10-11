from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MixinResourceAllocation(models.AbstractModel):
    _name = "mixin.resource.allocation"
    _description = "Resource Allocation Mixin"
    _inherit = ["mixin.resource.scheduling"]

    allocated_percentage = fields.Float(
        string="Allocation %",
        default=100.0,
        help="Percentage of the resource's work capacity allocated to this record.",
    )
    allocated_hours = fields.Float(
        compute="_compute_allocated_hours",
        store=True,
        help="Working hours the record's reservations book: none, while it is not scheduled.",
    )

    @api.constrains("allocated_percentage")
    def _check_allocated_percentage(self) -> None:
        for record in self:
            if not 0.0 <= record.allocated_percentage <= 100.0:
                raise ValidationError(
                    self.env._(
                        "%(name)s: allocation %% must be between 0 and 100.",
                        name=record.display_name,
                    )
                )

    @api.depends("reservation_ids.allocated_hours", "reservation_ids.active")
    def _compute_allocated_hours(self) -> None:
        for record in self:
            record.allocated_hours = sum(
                record.reservation_ids.filtered("active").mapped("allocated_hours")
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if any("allocated_hours" in vals for vals in vals_list):
            records._recompute_allocated_hours()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "allocated_hours" in vals:
            self._recompute_allocated_hours()
        return result

    def _recompute_allocated_hours(self) -> None:
        self.env.add_to_compute(self._fields["allocated_hours"], self)

    def _get_fields_sync_trigger(self):
        return super()._get_fields_sync_trigger() | {"allocated_percentage"}

    def _sync_reservations(self) -> None:
        super()._sync_reservations()
        if self:
            records = self.sudo()
            records.env.add_to_compute(records._fields["allocated_hours"], records)
            records.mapped("allocated_hours")
