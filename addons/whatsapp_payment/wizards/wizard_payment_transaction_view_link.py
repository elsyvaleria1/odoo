from odoo import api, fields, models


class WizardPaymentTransactionViewLink(models.TransientModel):
    _inherit = "wizard.payment.transaction.view.link"

    can_send_whatsapp = fields.Boolean(
        string="Can Send WhatsApp",
        compute="_compute_can_send_whatsapp",
    )

    @api.depends("res_model")
    @api.depends_context("uid")
    def _compute_can_send_whatsapp(self) -> None:
        self.can_send_whatsapp = self.env["whatsapp.template"]._can_use_whatsapp(
            "wizard.payment.transaction.view.link"
        )

    def action_send_whatsapp(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": "wizard.whatsapp.message.send",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_res_id": self.id,
                "default_res_model": "wizard.payment.transaction.view.link",
            },
        }

    def _get_fields_whatsapp_safe(self) -> set:
        return {
            "partner_id.name",
            "currency_id.symbol",
            "amount",
            "company_id.name",
            "description",
            "link",
        }
