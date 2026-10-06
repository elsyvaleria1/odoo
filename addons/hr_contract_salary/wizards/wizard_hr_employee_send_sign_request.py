from odoo import api, fields, models


class WizardHrEmployeeSendSignRequest(models.TransientModel):
    _inherit = "wizard.hr.employee.send.sign.request"

    sign_template_ids = fields.Many2many(
        compute="_compute_sign_template_ids",
        store=True,
        readonly=False,
    )

    @api.depends("version_id")
    def _compute_sign_template_ids(self) -> None:
        for wizard in self:
            version = wizard.version_id
            if not version:
                wizard.sign_template_ids = False
                continue
            current_version = version.employee_id.current_version_id
            if (
                version == current_version
                or version.date_version < current_version.date_version
            ) and version.contract_update_template_id:
                wizard.sign_template_ids = version.contract_update_template_id
            elif (
                version.date_version > current_version.date_version
                and version.sign_template_id
            ):
                wizard.sign_template_ids = version.sign_template_id
            else:
                wizard.sign_template_ids = False
