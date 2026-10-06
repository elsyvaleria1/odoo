from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrVersion(models.Model):
    _inherit = "hr.version"

    sign_request_ids = fields.Many2many(
        comodel_name="sign.request",
        string="Requested Signatures",
        tracking=True,
    )
    sign_request_count = fields.Count(count_of="sign_request_ids")

    @api.ondelete(at_uninstall=False)
    def _unlink_if_sign_request_canceled(self) -> None:
        if self.sign_request_ids.filtered(lambda s: s.state != "canceled"):
            raise ValidationError(
                self.env._(
                    "You can't delete a contract linked to a signed document, archive it instead."
                )
            )

    def open_sign_requests(self):
        self.check_singleton()
        return self.env["hr.employee"]._get_sign_requests_action(self.sign_request_ids)

    def action_signature_request_wizard(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "hr_sign.sign_contract_wizard_action"
        )
        action["context"] = {
            "active_id": self.id,
            "active_model": "hr.version",
        }

        return action
