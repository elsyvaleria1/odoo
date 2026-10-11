from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError

from odoo.addons.mail_microsoft.models.mixin_mail_microsoft import OUTLOOK


class FetchmailServer(models.Model):

    _name = "fetchmail.server"
    _inherit = ["fetchmail.server", "mixin.mail.microsoft"]
    _oauth2_type_field = "server_type"

    _MAIL_MICROSOFT_SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All"

    server_type = fields.Selection(
        selection_add=[("outlook", "Outlook OAuth Authentication")],
        ondelete={"outlook": "set default"},
    )

    def _oauth2_provider(self):
        if self.server_type == "outlook":
            return OUTLOOK
        return super()._oauth2_provider()

    def _compute_server_type_info(self) -> None:
        outlook_servers = self.filtered(lambda server: server.server_type == "outlook")
        outlook_servers.server_type_info = self.env._(
            "Connect your personal Outlook account using OAuth. \n"
            "You will be redirected to the Outlook login page to accept "
            "the permissions."
        )
        super(FetchmailServer, self - outlook_servers)._compute_server_type_info()

    @api.constrains("server_type", "encryption", "password", "user")
    def _check_use_microsoft_outlook_service(self) -> None:
        for server in self.filtered(lambda s: s.server_type == "outlook"):
            if server.password:
                raise UserError(
                    self.env._(
                        "Please leave the password field empty for Outlook mail server “%s”. "
                        "The OAuth process does not require it.",
                        server.name,
                    )
                )
            if server.encryption not in ("ssl", "ssl_strict"):
                raise UserError(
                    self.env._(
                        "Incorrect Connection Encryption for Outlook mail server “%s”. "
                        'Please set it to "SSL/TLS".',
                        server.name,
                    )
                )
            if not server.user:
                raise UserError(
                    self.env._(
                        'Please fill the "Username" field with your Outlook/Office365 username (your email address). '
                        "This should be the same account as the one used for the Outlook "
                        "OAuthentication Token."
                    )
                )

    def _prepare_server_type_defaults(self) -> ValuesType:
        vals = super()._prepare_server_type_defaults()
        if self.server_type == "outlook":
            vals.update(server="imap.outlook.com", encryption="ssl_strict", port=993)
        return vals

    def _imap_login__(self, connection) -> None:
        self.check_singleton()
        if self.server_type == "outlook":
            auth_string = self._mail_microsoft_auth_string(self.user)
            connection.authenticate("XOAUTH2", lambda x: auth_string)
        else:
            super()._imap_login__(connection)

    def _get_connection_type(self):
        self.check_singleton()
        return (
            "imap" if self.server_type == "outlook" else super()._get_connection_type()
        )
