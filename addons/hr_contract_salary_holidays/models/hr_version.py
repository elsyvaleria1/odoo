from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrVersion(models.Model):
    _inherit = "hr.version"

    leave_allocation_id = fields.Many2one(
        comodel_name="hr.leave.allocation",
        string="Allocation",
        readonly=True,
        tracking=True,
        groups="hr.group_hr_user",
    )

    def write(self, vals):
        res = super().write(vals)
        if "state" in vals and vals["state"] == "cancel":
            for record in self.filtered(
                lambda r: (
                    r.leave_allocation_id and r.leave_allocation_id.state != "refuse"
                )
            ):
                _debug.lifecycle(
                    "contract_cancelled_allocation_refused",
                    version=record,
                    allocation=record.leave_allocation_id,
                    was_state=record.leave_allocation_id.state,
                )
                record.leave_allocation_id.write({"state": "refuse"})
                record.leave_allocation_id.message_post(
                    body=self.env._("Contract has been cancelled."),
                )
        return res

    def action_list_leaves(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "hr_holidays.hr_leave_allocation_action_all"
        )
        action["context"] = {"search_default_employee_id": self.employee_id.id}
        return action
