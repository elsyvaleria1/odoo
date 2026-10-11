from odoo import Command, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.account_followup.models.followup_request import FollowupRequest


class WizardResPartnerSendFollowup(models.TransientModel):
    _name = "wizard.res.partner.send.followup"
    _inherit = ["mixin.mail.composer"]
    _description = "Wizard for sending manual reminders to clients"

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        active_ids = self.env.context.get("active_ids") or []
        if (
            self.env.context.get("active_model") != "res.partner"
            or len(active_ids) != 1
        ):
            raise UserError(
                self.env._("Open this reminder from a single customer's form.")
            )
        partner = self.env["res.partner"].browse(active_ids)
        followup_line = partner.followup_line_id
        if followup_line:
            defaults.update(self._get_defaults_from_followup_line(followup_line))
        defaults.update(
            partner_id=partner.id,
            attachment_ids=[
                Command.set(
                    partner.unreconciled_aml_ids.move_id.message_main_attachment_id.ids
                )
            ],
            render_model="res.partner",
        )
        return defaults

    partner_id = fields.Many2one(comodel_name="res.partner")

    email = fields.Boolean()
    email_recipient_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="rel_followup_manual_reminder_res_partner",
        string="Extra Recipients",
        compute="_compute_email_recipient_ids",
        store=True,
        readonly=False,
    )

    sms = fields.Boolean()
    sms_body = fields.Char(
        compute="_compute_sms_body",
        store=True,
        readonly=False,
    )
    sms_template_id = fields.Many2one(
        comodel_name="sms.template",
        domain=[("model", "=", "res.partner")],
    )

    print_letter = fields.Boolean(
        string="Letter",
        default=True,
    )
    join_invoices = fields.Boolean(string="Attach Invoices")

    attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        bypass_search_access=True,
    )

    show_send_button = fields.Boolean(compute="_compute_show_send_button")
    show_print_button = fields.Boolean(compute="_compute_show_print_button")

    @api.depends("email", "sms")
    def _compute_show_send_button(self) -> None:
        for wizard in self:
            wizard.show_send_button = wizard.email or wizard.sms

    @api.depends("print_letter")
    def _compute_show_print_button(self) -> None:
        for wizard in self:
            wizard.show_print_button = wizard.print_letter

    def _compute_render_model(self) -> None:
        self.render_model = "res.partner"

    def _get_defaults_from_followup_line(self, followup_line):
        return {
            "email": followup_line.send_email,
            "sms": followup_line.send_sms,
            "template_id": followup_line.mail_template_id.id,
            "sms_template_id": followup_line.sms_template_id.id,
            "join_invoices": followup_line.join_invoices,
        }

    @api.depends("template_id")
    def _compute_subject(self) -> None:
        report = self.env["account.followup.report"]
        for wizard in self:
            wizard.subject = report._get_email_subject(
                FollowupRequest.prepare(
                    wizard.partner_id, mail_template=wizard.template_id
                )
            )

    @api.depends("template_id")
    def _compute_body(self) -> None:
        report = self.env["account.followup.report"]
        for wizard in self:
            wizard.body = report._get_main_body(
                FollowupRequest.prepare(
                    wizard.partner_id, mail_template=wizard.template_id
                )
            )

    @api.depends("template_id")
    def _compute_email_recipient_ids(self) -> None:
        for wizard in self:
            partner = wizard.partner_id
            template = wizard.template_id
            wizard.email_recipient_ids = partner._get_followup_contact() or partner
            if template:
                rendered_values = template._prepare_recipient_vals(
                    [partner.id],
                    {"partner_to", "email_cc", "email_to"},
                    find_or_create_partners=True,
                )[partner.id]
                if rendered_values.get("partner_ids"):
                    wizard.email_recipient_ids = [
                        Command.link(partner_id)
                        for partner_id in rendered_values["partner_ids"]
                    ]

    @api.depends("sms_template_id")
    def _compute_sms_body(self) -> None:
        report = self.env["account.followup.report"]
        for wizard in self:
            wizard.sms_body = report._get_sms_body(
                FollowupRequest.prepare(
                    wizard.partner_id, sms_template=wizard.sms_template_id
                )
            )

    def _get_followup_request(self):
        return FollowupRequest.prepare(
            self.partner_id,
            manual=True,
            mail_template=self.template_id,
            sms_template=self.sms_template_id,
            subject=self.subject,
            body=self.body,
            sms_body=self.sms_body,
            email_from=self.template_id.email_from,
            email_recipients=self.email_recipient_ids,
            author=self.env.user.partner_id,
            attachment_ids=self.attachment_ids.ids,
            join_invoices=self.join_invoices,
            print_letter=self.print_letter,
            channels={"email": self.email, "sms": self.sms},
        )

    def process_followup(self):
        action = self.partner_id._execute_followup_and_print(
            self._get_followup_request()
        )
        return action or {
            "type": "ir.actions.act_window_close",
        }
