import base64

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.mail_google.models.mixin_mail_google import GMAIL


class IrMail_Server(models.Model):
    """Represents an SMTP server, able to send outgoing emails, with SSL and TLS capabilities."""

    _name = "ir.mail_server"
    _inherit = ["ir.mail_server", "mixin.mail.google"]
    _oauth2_type_field = "smtp_authentication"

    smtp_authentication = fields.Selection(
        selection_add=[("gmail", "Gmail OAuth Authentication")],
        ondelete={"gmail": "set default"},
    )

    def _oauth2_provider(self):
        if self.smtp_authentication == "gmail":
            return GMAIL
        return super()._oauth2_provider()

    def _compute_smtp_authentication_info(self) -> None:
        gmail_servers = self.filtered(
            lambda server: server.smtp_authentication == "gmail"
        )
        gmail_servers.smtp_authentication_info = self.env._(
            "Connect your Gmail account with the OAuth Authentication process.  \n"
            "By default, only a user with a matching email address will be able to use this server. "
            'To extend its use, you should set a "mail.default.from" system parameter.'
        )
        super(IrMail_Server, self - gmail_servers)._compute_smtp_authentication_info()

    def _compute_smtp_port(self) -> None:
        super(
            IrMail_Server, self.filtered(lambda s: s.smtp_authentication != "gmail")
        )._compute_smtp_port()

    @api.onchange("smtp_authentication")
    def _onchange_smtp_authentication_gmail(self) -> None:
        if self.smtp_authentication == "gmail":
            self.smtp_host = "smtp.gmail.com"
            self.smtp_encryption = "starttls_strict"
            self.smtp_port = 587

    @api.onchange("smtp_user", "smtp_authentication")
    def _on_change_smtp_user_gmail(self) -> None:
        if self.smtp_authentication == "gmail":
            self.from_filter = self.smtp_user

    @api.constrains(
        "smtp_authentication",
        "smtp_pass",
        "smtp_encryption",
        "from_filter",
        "smtp_user",
    )
    def _check_use_google_gmail_service(self) -> None:
        gmail_servers = self.filtered(
            lambda server: server.smtp_authentication == "gmail"
        )
        for server in gmail_servers:
            if server.smtp_pass:
                raise UserError(
                    self.env._(
                        "Please leave the password field empty for Gmail mail server “%s”. "
                        "The OAuth process does not require it",
                        server.name,
                    )
                )

            if server.smtp_encryption not in ("starttls", "starttls_strict"):
                raise UserError(
                    self.env._(
                        "Incorrect Connection Security for Gmail mail server “%s”. "
                        'Please set it to "TLS (STARTTLS)".',
                        server.name,
                    )
                )

            if not server.smtp_user:
                raise UserError(
                    self.env._(
                        'Please fill the "Username" field with your Gmail username (your email address). '
                        "This should be the same account as the one used for the Gmail OAuthentication Token."
                    )
                )

    def _smtp_login__(self, connection, smtp_user, smtp_password) -> None:
        if len(self) == 1 and self.smtp_authentication == "gmail":
            auth_string = self._mail_google_auth_string(smtp_user)
            oauth_param = base64.b64encode(auth_string.encode()).decode()
            connection.ehlo()
            connection.docmd("AUTH", f"XOAUTH2 {oauth_param}")
        else:
            super()._smtp_login__(connection, smtp_user, smtp_password)
