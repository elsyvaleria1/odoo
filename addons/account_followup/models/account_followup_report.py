from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext, plaintext2html
from odoo.tools.misc import get_lang


class AccountFollowupReport(models.AbstractModel):
    _name = "account.followup.report"
    _description = "Follow-up Report"


    def get_followup_report_html(self, request):
        return self.env["ir.qweb"]._render(
            "account_followup.template_followup_report",
            {
                "doc": request.partner,
                "lang": request.partner.lang or get_lang(self.env).code,
                "followup_request": request,
                "context": self.env.context,
            },
        )


    @api.model
    def _get_rendered_body(self, partner_id, template_src, default_body, **kwargs):
        if template_src:
            return (
                self.env["mixin.mail.composer"]
                .sudo()
                ._render_template(template_src, "res.partner", [partner_id], **kwargs)[
                    partner_id
                ]
            )

        return default_body

    @api.model
    def _get_sms_body(self, request):
        if request.sms_body:
            return request.sms_body

        partner = request.partner
        template_src = request.sms_template.with_context(lang=request.lang).body
        responsible = partner._get_followup_responsible()
        responsible_signature = html2plaintext(
            responsible.signature or responsible.name
        )
        default_body = self.with_context(lang=request.lang).env._(
            "Dear client, we kindly remind you that you still have unpaid invoices. Please check them and take appropriate action. %s",
            responsible_signature,
        )
        return self._get_rendered_body(
            partner.id, template_src, default_body, options={"post_process": True}
        )

    @api.model
    def _get_email_from(self, request):
        email_from = request.email_from or request.mail_template.email_from
        return (
            self.env["mixin.mail.composer"]
            .sudo()
            ._render_template(email_from, "res.partner", [request.partner.id])[
                request.partner.id
            ]
            or None
        )

    @api.model
    def _get_email_reply_to(self, request):
        return request.mail_template.reply_to or self._notify_get_reply_to()[False]

    @api.model
    def _get_main_body(self, request):
        if request.body:
            return request.body

        partner = request.partner
        template_src = None
        if request.mail_template:
            template_src = request.mail_template.with_context(
                lang=request.lang
            ).body_html

        responsible = partner._get_followup_responsible()
        responsible_signature = responsible.signature or responsible.name
        self = self.with_context(lang=request.lang)
        default_body = self.env._(
            """Dear %s,


Exception made if there was a mistake of ours, it seems that the following amount stays unpaid. Please, take appropriate measures in order to carry out this payment in the next 8 days.

Would your payment have been carried out after this mail was sent, please ignore this message. Do not hesitate to contact our accounting department.

Best Regards,

""",
            partner.name,
        )

        default_body_html = (
            plaintext2html(default_body) + responsible_signature
        )
        return self._get_rendered_body(
            partner.id,
            template_src,
            default_body_html,
            engine="qweb",
            options={"post_process": True},
        )

    @api.model
    def _get_email_subject(self, request):
        if request.subject:
            return request.subject

        template_src = None
        if request.mail_template:
            template_src = request.mail_template.with_context(lang=request.lang).subject

        self = self.with_context(lang=request.lang)
        default_body = self.env._(
            "%(company)s Payment Reminder - %(partner)s",
            company=self.env.company.name,
            partner=request.partner.name,
        )
        return self._get_rendered_body(
            request.partner.id,
            template_src,
            default_body,
            options={"post_process": True},
        )

    @api.model
    def _get_email_recipients(self, request):
        if request.email_recipients:
            return request.email_recipients

        partner = request.partner
        recipients = partner._get_followup_contact() or partner
        if request.mail_template:
            rendered_values = request.mail_template._prepare_recipient_vals(
                res_ids=[partner.id],
                render_fields={"partner_to", "email_cc", "email_to"},
                allow_suggested=True,
                find_or_create_partners=True,
            )[partner.id]
            recipients |= partner.browse(rendered_values.get("partner_ids"))
        return recipients


    @api.model
    def _send_sms(self, request) -> None:
        partner = request.partner
        contact = partner._get_followup_contact() or partner
        contact_phone = contact._phone_get_number().number
        if not contact_phone:
            raise UserError(
                self.env._(
                    "You are trying to send an SMS, but no follow-up contact has any mobile/phone number set for customer '%s'",
                    partner.name,
                )
            )
        partner._message_sms(
            body=self.with_context(lang=request.lang)._get_sms_body(request),
            partner_ids=contact.ids,
            sms_pid_to_number={contact.id: contact_phone},
        )

    @api.model
    def _send_email(self, request):
        partner = request.partner
        recipients = self._get_email_recipients(request).filtered(
            lambda contact: contact.email and contact.email.strip()
        )
        if not recipients:
            raise UserError(
                self.env._(
                    "You are trying to send an Email, but no follow-up contact has any email address set for customer '%s'",
                    partner.name,
                )
            )

        report = self.with_context(lang=request.lang)
        message_vals = {
            "attachment_ids": list(request.attachment_ids),
            "body": report.with_context(mail=True).get_followup_report_html(request),
            "email_from": report._get_email_from(request),
            "subject": report._get_email_subject(request),
            "reply_to": report._get_email_reply_to(request),
            "author_id": (
                request.author or partner._get_followup_responsible().partner_id
            ).id,
            "model_description": self.env._("payment reminder"),
            "notify_author": True,
            "email_layout_xmlid": "mail.mail_notification_light",
            "subtype_id": self.env["ir.model.data"]._xmlid_to_res_id("mail.mt_note"),
        }

        author = partner.with_context(mail_post_autofollow=True, lang=request.lang)
        for to_send_partner in recipients:
            author.message_post(partner_ids=[to_send_partner.id], **message_vals)

        if request.followup_line.additional_follower_ids:
            partner.message_subscribe(
                request.followup_line.additional_follower_ids.partner_id.ids
            )

    @api.model
    def _print_followup_letter(self, request) -> dict:
        partner = request.partner
        attachment = partner._create_followup_letter_attachment(request)
        partner.message_post(
            body=self.env._("Follow-up letter generated"),
            attachment_ids=[attachment.id],
        )
        return {
            "type": "ir.actions.client",
            "tag": "close_followup_wizard",
            "params": {
                "url": "/web/content/%s?download=1" % attachment.id,
            },
        }
