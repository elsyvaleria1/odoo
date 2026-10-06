from odoo import api, fields, models


class HrWorkEntry(models.Model):
    _inherit = "hr.work.entry"

    planning_slot_id = fields.Many2one(
        comodel_name="planning.slot",
        index="btree_not_null",
        groups="hr.group_hr_user",
    )

    @api.model
    def _get_fields_to_nullify_on_regeneration(self):
        return super()._get_fields_to_nullify_on_regeneration() + ["planning_slot_id"]
