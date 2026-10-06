from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    leave_ids = fields.One2many(
        comodel_name="hr.leave",
        inverse_name="employee_id",
        groups="hr.group_hr_user",
    )
