from datetime import UTC, datetime
from urllib.parse import urlsplit

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, tools

OPEN_SCOPE = tools.register_signed_scope(
    "mass_mailing-mail_mail-open",
    purpose="record that a mailing's mail was opened (its tracking pixel)",
    lifetime="undated: embedded in the mail",
)


class MailMail(models.Model):
    _inherit = "mail.mail"

    mailing_id = fields.Many2one(
        comodel_name="mailing.mailing",
        string="Mass Mailing",
    )
    mailing_trace_ids = fields.One2many(
        comodel_name="mailing.trace",
        inverse_name="mail_mail_id",
        string="Statistics",
    )

    def _get_tracking_url(self):
        token = self._generate_mail_recipient_token(self.id)
        return tools.urls.urljoin(
            self.get_base_url(), f"mail/track/{self.id}/{token}/blank.gif"
        )

    @api.model
    def _generate_mail_recipient_token(self, mail_id):
        return tools.hmac(self.env(su=True), OPEN_SCOPE, mail_id)

    @api.model
    def _is_mail_recipient_token(self, mail_id, token) -> bool:
        return tools.is_hmac_valid(self.env, OPEN_SCOPE, mail_id, token)

    def _prepare_outgoing_body(self):
        self.check_singleton()
        body = super()._prepare_outgoing_body()

        if body and self.mailing_id and self.mailing_trace_ids:
            Wrapper = body.__class__
            for match in set(tools.mail.URL_REGEX.findall(body)):
                href = match[0]
                url = match[1]

                parsed = urlsplit(url, scheme="http")

                if parsed.scheme.startswith("http") and parsed.path.startswith("/r/"):
                    new_href = href.replace(
                        url, f"{url}/m/{self.mailing_trace_ids[0].id}"
                    )
                    body = body.replace(Wrapper(href), Wrapper(new_href))

            tracking_url = self._get_tracking_url()
            body = tools.mail.add_html_content(
                body,
                f'<img src="{tracking_url}"/>',
                plaintext=False,
            )
        return body

    def _prepare_outgoing_list(
        self,
        mail_server=False,
        doc_to_followers=None,
        smtp_session=None,
        already_sent_pids=None,
    ):
        email_list = super()._prepare_outgoing_list(
            mail_server=mail_server,
            doc_to_followers=doc_to_followers,
            smtp_session=smtp_session,
            already_sent_pids=already_sent_pids,
        )
        if not self.res_id or not self.mailing_id:
            return email_list

        base_url = self.mailing_id.get_base_url()
        for email_values in email_list:
            if not email_values["email_to"]:
                continue

            email_normalized = tools.email_normalize(
                email_values["email_to"][0], strict=False
            )
            email_to = email_normalized or email_values["email_to"][0]

            unsubscribe_url = self.mailing_id._get_unsubscribe_url(
                email_to, self.res_id
            )
            unsubscribe_oneclick_url = self.mailing_id._get_unsubscribe_oneclick_url(
                email_to, self.res_id
            )
            view_url = self.mailing_id._get_view_url(email_to, self.res_id)

            if not tools.is_html_empty(email_values["body"]):
                if f"{base_url}/unsubscribe_from_list" in email_values[
                    "body"
                ] and not self.env.context.get("mailing_test_mail"):
                    email_values["body"] = email_values["body"].replace(
                        f"{base_url}/unsubscribe_from_list",
                        unsubscribe_url,
                    )
                if f"{base_url}/view" in email_values["body"]:
                    email_values["body"] = email_values["body"].replace(
                        f"{base_url}/view",
                        view_url,
                    )

            email_values["headers"].update(
                {
                    "List-Unsubscribe": f"<{unsubscribe_oneclick_url}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                    "Precedence": "list",
                    "X-Auto-Response-Suppress": "OOF",
                }
            )
        return email_list

    def _postprocess_sent_message(
        self,
        success_partners,
        success_emails,
        failure_reason=False,
        failure_type=None,
        **kwargs,
    ) -> None:
        if failure_type:
            self.filtered("mailing_id").mailing_trace_ids.set_failed(
                failure_type=failure_type
            )
        else:
            self.filtered("mailing_id").mailing_trace_ids.set_sent()
        super()._postprocess_sent_message(
            success_partners,
            success_emails,
            failure_reason=failure_reason,
            failure_type=failure_type,
            **kwargs,
        )

    _GC_CANCELED_BATCH_SIZE = 10000

    @api.autovacuum
    def _gc_canceled_mail_mail(self) -> tuple:
        months_limit = self.env.registry.settings.get_int(
            self.env, "mass_mailing.cancelled_mails_months_limit", 6
        )
        if months_limit <= 0:
            return 0, False
        history_deadline = datetime.now(UTC) - relativedelta(months=months_limit)
        canceled_mails = self.with_context(active_test=False).search(
            [("state", "=", "cancel"), ("write_date", "<=", history_deadline)],
            order="id asc",
            limit=self._GC_CANCELED_BATCH_SIZE,
        )

        canceled_mails.with_context(prefetch_fields=False).mail_message_id.unlink()
        return len(canceled_mails), len(canceled_mails) == self._GC_CANCELED_BATCH_SIZE
