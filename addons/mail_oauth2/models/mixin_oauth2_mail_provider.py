import base64

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.libs.json import loads as json_loads
from odoo.tools import email_normalize

from odoo.addons.integration.tools.exceptions import CommError


def _id_token_claims(id_token) -> dict:
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json_loads(base64.urlsafe_b64decode(payload))
    except AttributeError, IndexError, ValueError:
        return {}
    return claims if isinstance(claims, dict) else {}


class MixinOauth2MailProvider(models.AbstractModel):
    _name = "mixin.oauth2.mail.provider"
    _description = "OAuth2 Mail Provider Mixin"

    _oauth2_type_field = None

    active = fields.Boolean(default=True)
    oauth2_authorized = fields.Boolean(
        string="Authorized",
        compute="_compute_oauth2_authorized",
        help="An account authorized this server, and its grant still holds.",
    )

    def _compute_oauth2_authorized(self) -> None:
        for record in self:
            connection = record.id and record._oauth2_connection()
            record.oauth2_authorized = bool(connection) and (
                connection._is_oauth_authorized()
            )

    def _oauth2_provider(self):
        pass

    def _oauth2_connection(self):
        self.check_singleton()
        return self.env["integration.connection"]._find_bound(self)

    def write(self, vals):
        result = super().write(vals)
        if self._oauth2_type_field in vals:
            for record in self.filtered(lambda record: not record._oauth2_provider()):
                connection = record._oauth2_connection()
                if connection.credential_id:
                    connection._forget_oauth_authorization()
        return result

    def unlink(self):
        connections = (
            self.env["integration.connection"]
            .sudo()
            .search([("res_model", "=", self._name), ("res_id", "in", self.ids)])
        )
        connections._forget_oauth_authorization()
        connections.unlink()
        return super().unlink()

    def _oauth2_open_uri(self, provider) -> dict:
        self.check_singleton()
        if not email_normalize(self[self._email_field]):
            raise UserError(self.env._("Please enter a valid email address."))
        connection = self.env["integration.connection"]._bound(
            self,
            self.env.ref(provider.service),
            provider.resolve(provider.scope, self),
        )
        if not all(connection._oauth_client()):
            raise UserError(
                self.env._("Please configure your %s credentials.", provider.label)
            )
        return {
            "type": "ir.actions.act_url",
            "url": connection._oauth_authorize_url(self._oauth2_return_url()),
            "target": "self",
        }

    def _oauth2_return_url(self) -> str:
        self.check_singleton()
        user = self.env.user
        if (
            self._name != "ir.mail_server" or self != user.outgoing_mail_server_id
        ) and user.has_group("base.group_system"):
            return f"/odoo/{self._name}/{self.id}"
        return f"/odoo/my-preferences/{user.id}"

    def _oauth_authorization_allowed(self, user) -> bool:
        self.check_singleton()
        if "owner_user_id" in self._fields and self.owner_user_id == user:
            return True
        return self.with_user(user).has_access("write")

    def _on_oauth_authorized(self, connection, tokens) -> None:
        self.check_singleton()
        if self._name == "ir.mail_server" and (
            self.owner_user_id or not self.env.user.has_group("base.group_system")
        ):
            claims = _id_token_claims(tokens.get("id_token"))
            email = claims.get("email")
            if (
                not email
                or claims.get("email_verified") is False
                or email_normalize(email) != email_normalize(self[self._email_field])
            ):
                raise UserError(
                    self.env._(
                        "Oops, you're creating an authorization to send from "
                        "%(email_login)s but your address is %(email_server)s. Make "
                        "sure your addresses match!",
                        email_login=email,
                        email_server=self[self._email_field],
                    )
                )
        self.active = True

    def _oauth2_generate_string(self, provider, login) -> str:
        self.check_singleton()
        connection = self._oauth2_connection()
        try:
            access_token = connection and connection._oauth2_access_token()
        except CommError as error:
            raise UserError(error.message) from None
        if not access_token:
            raise UserError(
                self.env._(
                    "Please connect with your %s account before using it.",
                    provider.label,
                )
            )
        return "user=%s\1auth=Bearer %s\1\1" % (login, access_token)
