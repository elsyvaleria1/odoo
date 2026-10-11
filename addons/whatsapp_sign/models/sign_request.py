from odoo import api, fields, models, tools
from odoo.exceptions import ValidationError
from odoo.tools.i18n import format_list


class SignRequest(models.Model):
    _inherit = "sign.request"

    send_channel = fields.Selection(
        selection_add=[("whatsapp", "WhatsApp")],
        ondelete={
            "whatsapp": "set default"
        },
    )
    signers_name = fields.Char(
        string="Signers name",
        compute="_compute_signers_name",
    )
    refuser_partner = fields.Many2one(
        comodel_name="res.partner",
        compute="_compute_refuser_partner",
    )
    refusal_reason = fields.Char(string="Refusal reason")
    raw_optional_message = fields.Char(
        string="Optional Message",
        compute="_compute_raw_optional_message",
    )

    @api.constrains("send_channel")
    def _check_send_channel(self) -> None:
        whatsapp_sign_configured = self.env[
            "sign.request.item"
        ]._check_whatsapp_template_exists()
        for sign_request in self:
            if sign_request.send_channel == "whatsapp" and not whatsapp_sign_configured:
                raise ValidationError(
                    self.env._(
                        "All Whatsapp templates must be configured before creating the sign request."
                    )
                )

    @api.depends("request_item_ids")
    def _compute_signers_name(self) -> None:
        for sign_request in self:
            names = sign_request.request_item_ids.mapped("display_name")
            if self.env["sign.request.item"]._check_whatsapp_template_exists():
                template_id = self.env.registry.settings.get(
                    self.env, "whatsapp_sign.whatsapp_completion_template_id", False
                )
                template = self.env["whatsapp.template"].browse(int(template_id))
                sign_request.signers_name = format_list(
                    self.env, names, lang_code=template.lang_code
                )
            else:
                sign_request.signers_name = ", ".join(names)

    @api.depends("sign_log_ids", "state")
    def _compute_refuser_partner(self) -> None:
        canceled_requests = self.filtered(lambda r: r.state == "canceled")
        refusal_logs = self.env["sign.log"]._read_group(
            [
                ("sign_request_id", "in", canceled_requests.ids),
                ("action", "=", "refuse"),
            ],
            ["sign_request_id"],
            aggregates=["id:recordset"],
        )
        logs_per_request = dict(refusal_logs)

        for sign_request in self:
            refusal_log = logs_per_request.get(sign_request, self.env["sign.log"])
            sign_request.refuser_partner = refusal_log.sign_request_item_id.partner_id

    @api.depends("message")
    def _compute_raw_optional_message(self) -> None:
        for sign_request in self:
            raw_html = sign_request.message
            sign_request.raw_optional_message = (
                tools.html2plaintext(raw_html) if raw_html else "-"
            )

    def _send_completed_documents_message(
        self,
        signers,
        request_edited,
        partner,
        access_token=None,
        with_message_cc=True,
        force_send=False,
        sign_request_item=None,
    ):
        self.check_singleton()

        is_whatsapp = self.send_channel == "whatsapp"
        misconfiguration = (
            is_whatsapp
            and not self.env["sign.request.item"]._check_whatsapp_template_exists()
        )
        if misconfiguration:
            self.send_channel = "email"
        if misconfiguration or not is_whatsapp:
            return super()._send_completed_documents_message(
                signers,
                request_edited,
                partner,
                access_token,
                with_message_cc,
                force_send,
            )
        elif not sign_request_item:
            return None

        template_id = self.env.registry.settings.get(
            self.env, "whatsapp_sign.whatsapp_completion_template_id", False
        )
        whatsapp_template = self.env["whatsapp.template"].browse(int(template_id))
        whatsapp_composer = (
            self.env["wizard.whatsapp.message.send"]
            .with_context({"active_id": sign_request_item.id})
            .create(
                {
                    "wa_template_id": whatsapp_template.id,
                    "res_model": "sign.request.item",
                }
            )
        )
        whatsapp_composer.sudo()._send_whatsapp_template(
            force_send_by_cron=not force_send
        )
        return None

    def _send_refused_message(
        self,
        refuser,
        refusal_reason,
        partner,
        access_token=None,
        force_send=False,
        sign_request_item=None,
    ):
        self.check_singleton()

        is_whatsapp = self.send_channel == "whatsapp"
        misconfiguration = (
            is_whatsapp
            and not self.env["sign.request.item"]._check_whatsapp_template_exists()
        )
        if misconfiguration:
            self.send_channel = "email"
        if misconfiguration or not is_whatsapp:
            return super()._send_refused_message(
                refuser, refusal_reason, partner, access_token, force_send
            )
        elif not sign_request_item:
            return None

        template_id = self.env.registry.settings.get(
            self.env, "whatsapp_sign.whatsapp_refusal_template_id", False
        )
        whatsapp_template = self.env["whatsapp.template"].browse(int(template_id))
        self.refusal_reason = refusal_reason

        whatsapp_composer = (
            self.env["wizard.whatsapp.message.send"]
            .with_context({"active_id": sign_request_item.id})
            .create(
                {
                    "wa_template_id": whatsapp_template.id,
                    "res_model": "sign.request.item",
                }
            )
        )
        whatsapp_composer.sudo()._send_whatsapp_template(
            force_send_by_cron=not force_send
        )
        return None
