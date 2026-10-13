from werkzeug import datastructures, http

if hasattr(datastructures.WWWAuthenticate, "from_header"):
    parse_auth = datastructures.WWWAuthenticate.from_header
else:
    parse_auth = http.parse_www_authenticate_header

from odoo import api, fields, models
from odoo.exceptions import AccessDenied, AccessError, UserError

from odoo.addons.auth_signup.models.res_users import SignupError


class ResUsers(models.Model):
    _inherit = "res.users"

    oauth_provider_id = fields.Many2one(
        comodel_name="auth.oauth.provider",
        string="OAuth Provider",
    )
    oauth_uid = fields.Char(
        string="OAuth User ID",
        copy=False,
        help="Oauth Provider user_id",
    )
    oauth_access_token_hash = fields.Char(
        string="OAuth Access Token Hash",
        copy=False,
        readonly=True,
        prefetch=False,
        classification="secret.credential",
        groups=fields.NO_ACCESS,
    )
    has_oauth_access_token = fields.Boolean(
        string="Has OAuth Access Token",
        compute="_compute_has_oauth_access_token",
        groups="base.group_erp_manager",
    )

    _uniq_users_oauth_provider_oauth_uid = models.UniqueIndex(
        "(oauth_provider_id, oauth_uid) "
        "WHERE oauth_provider_id IS NOT NULL AND oauth_uid IS NOT NULL",
        "OAuth UID must be unique per provider",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["has_oauth_access_token"]

    @api.depends("oauth_access_token_hash")
    def _compute_has_oauth_access_token(self) -> None:
        for user in self:
            user.has_oauth_access_token = bool(user.sudo().oauth_access_token_hash)

    def remove_oauth_access_token(self) -> None:
        user = self.env.user
        if not (user.has_group("base.group_erp_manager") or self == user):
            raise AccessError(
                self.env._("You do not have permissions to remove the access token")
            )
        self.sudo().oauth_access_token_hash = False

    def _auth_oauth_rpc(self, endpoint, access_token):
        if self.env.registry.settings.get(
            self.env, "auth_oauth.authorization_header", False
        ):
            response = self.env["ir.egress"].request(
                "GET",
                endpoint,
                purpose="auth_oauth",
                policy="private",
                headers={"Authorization": "Bearer %s" % access_token},
                timeout=10,
            )
        else:
            response = self.env["ir.egress"].request(
                "GET",
                endpoint,
                purpose="auth_oauth",
                policy="private",
                params={"access_token": access_token},
                timeout=10,
            )

        if response.ok:
            return response.json()

        auth_challenge = parse_auth(response.headers.get("WWW-Authenticate"))
        if (
            auth_challenge
            and auth_challenge.type == "bearer"
            and "error" in auth_challenge
        ):
            return dict(auth_challenge)

        return {"error": "invalid_request"}

    @api.model
    def _get_oauth_identity(self, provider, access_token):
        oauth_provider = self.env["auth.oauth.provider"].browse(provider)
        validation = self._auth_oauth_rpc(
            oauth_provider.validation_endpoint, access_token
        )
        if validation.get("error"):
            raise AccessDenied(validation["error"])
        if oauth_provider.data_endpoint:
            data = self._auth_oauth_rpc(oauth_provider.data_endpoint, access_token)
            validation.update(data)
        subject = next(
            filter(
                None,
                [
                    validation.pop(key, None)
                    for key in [
                        "sub",
                        "id",
                        "user_id",
                    ]
                ],
            ),
            None,
        )
        if not subject:
            raise AccessDenied(self.env._("Missing subject identity"))
        validation["user_id"] = subject

        return validation

    @api.model
    def _generate_signup_values(self, provider, validation, params) -> dict:
        oauth_uid = validation["user_id"]
        email = validation.get("email", "provider_%s_user_%s" % (provider, oauth_uid))
        name = validation.get("name", email)
        return {
            "name": name,
            "login": email,
            "email": email,
            "oauth_provider_id": provider,
            "oauth_uid": oauth_uid,
            "oauth_access_token_hash": self._get_crypt_context().hash(
                params["access_token"]
            ),
            "active": True,
        }

    @api.model
    def _auth_oauth_signin(self, provider, validation, params, signup_token=None):
        oauth_uid = validation["user_id"]
        try:
            oauth_user = self.search(
                [("oauth_uid", "=", oauth_uid), ("oauth_provider_id", "=", provider)]
            )
            if not oauth_user:
                raise AccessDenied
            assert len(oauth_user) == 1
            oauth_user.write(
                {
                    "oauth_access_token_hash": self._get_crypt_context().hash(
                        params["access_token"]
                    )
                }
            )
            return oauth_user.login
        except AccessDenied as access_denied_exception:
            if self.env.context.get("no_user_creation"):
                return None
            values = self._generate_signup_values(provider, validation, params)
            try:
                login, _ = self.signup(values, signup_token)
                return login
            except SignupError, UserError:
                raise access_denied_exception from None

    @api.model
    def auth_oauth(self, provider, params, signup_token=None):
        access_token = params.get("access_token")
        validation = self._get_oauth_identity(provider, access_token)

        login = self._auth_oauth_signin(
            provider, validation, params, signup_token=signup_token
        )
        if not login:
            raise AccessDenied
        return (self.env.cr.dbname, login, access_token)

    def _authenticate_credentials(self, credential, env):
        try:
            return super()._authenticate_credentials(credential, env)
        except AccessDenied:
            if not (credential["type"] == "oauth_token" and credential["token"]):
                raise
            passwd_allowed = self._password_allowed(env)
            stored = self.sudo().oauth_access_token_hash
            if (
                passwd_allowed
                and self.active
                and stored
                and self._get_crypt_context().is_password_valid(
                    credential["token"], stored
                )
            ):
                return {
                    "uid": self.id,
                    "auth_method": "oauth",
                    "mfa": "default",
                }
            raise

    def _get_fields_session_token(self):
        return super()._get_fields_session_token() | {"oauth_access_token_hash"}
