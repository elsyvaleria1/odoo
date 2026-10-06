from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardHrEmployeeUpdateContract(models.TransientModel):
    _name = "wizard.hr.employee.update.contract"
    _description = "Contract Template Wizard"

    contract_template_id = fields.Many2one(
        comodel_name="hr.version",
        required=True,
        domain=lambda self: [
            ("company_id", "=", self.env.company.id),
            ("employee_id", "=", False),
        ],
        groups="hr.group_hr_user",
        help="Select a contract template to auto-fill the contract form with predefined values. You can still edit the fields as needed after applying the template.",
    )

    def action_load_template(self) -> None:
        self.check_singleton()
        employee_id = self.env.context.get("active_id")
        if not employee_id or not self.contract_template_id:
            _debug.logic(
                "contract_load_skipped",
                active_id=employee_id,
                template=self.contract_template_id.id,
            )
            return
        employee = self.env["hr.employee"].browse(employee_id)
        template_vals = self.env["hr.version"]._prepare_vals_from_contract_template(
            self.contract_template_id
        )
        _debug.pipeline(
            "template_applied",
            template=self.contract_template_id.id,
            employee=employee_id,
            keys=sorted(template_vals),
        )
        employee.write(
            {**template_vals, "contract_template_id": self.contract_template_id.id}
        )
