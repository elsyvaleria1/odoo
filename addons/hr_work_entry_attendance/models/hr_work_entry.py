from odoo import api, fields, models


class HrWorkEntry(models.Model):
    _inherit = "hr.work.entry"

    attendance_id = fields.Many2one(comodel_name="hr.attendance")
    overtime_id = fields.Many2one(
        comodel_name="hr.attendance.overtime.line",
        index="btree_not_null",
    )

    @api.model
    def _get_fields_to_nullify_on_regeneration(self):
        return super()._get_fields_to_nullify_on_regeneration() + ["attendance_id"]
