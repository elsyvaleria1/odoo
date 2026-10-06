from odoo import api, fields, models, tools
from odoo.api import ValuesType
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.libs.debug_log import DebugLog

from odoo.addons.base.models.mixin_access_graph import AccessGrantNames

_debug = DebugLog(__name__)


MEMBER_SIGNUP_SCOPE = tools.register_signed_scope(
    "documents-member-signup-token",
    purpose="sign up as the partner a document or folder was shared with",
    lifetime="undated: bound to the membership, which revoking the share ends",
)


class DocumentsAccess(models.Model):
    _name = "document.access"
    _inherit = ["mixin.access.grant"]
    _description = "Document Grant"
    _log_access = False
    _access_grant_names = AccessGrantNames(resource="document_id")

    document_id = fields.Many2one(
        comodel_name="document.document",
        index=True,
        required=True,
        ondelete="cascade",
        bypass_search_access=True,
    )
    role = fields.Selection(
        selection=[("view", "Viewer"), ("edit", "Editor"), ("manage", "Manager")],
        index=True,
        required=True,
    )

    _unique_document_access_member = models.UniqueIndex(
        "(document_id, partner_id) WHERE partner_id IS NOT NULL",
        "This partner is already set on this document.",
    )
    _unique_document_access_group = models.UniqueIndex(
        "(document_id, group_id, COALESCE(company_id, 0)) WHERE group_id IS NOT NULL",
        "This group is already set on this document.",
    )

    @api.constrains("partner_id", "role")
    def _check_partner_id(self) -> None:
        public_partner = self.env.ref("base.public_user").partner_id
        for access in self:
            if access.role and access.partner_id == public_partner:
                _debug.logic("member_refused", reason="public_partner", access=access)
                raise ValidationError(self.env._("This user can not be member."))

    def _prepare_create_values(self, vals_list: list[ValuesType]) -> list[dict]:
        vals_list = super()._prepare_create_values(vals_list)
        documents = self.env["document.document"].browse(
            [vals["document_id"] for vals in vals_list]
        )
        documents.check_access("write")
        _debug.lifecycle("access_create", count=len(vals_list), documents=documents)
        return vals_list

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> DocumentsAccess:
        accesses = super().create(vals_list)
        self.env["document.document"]._invalidate_permission_cache([])
        return accesses

    def unlink(self) -> bool:
        result = super().unlink()
        self.env["document.document"]._invalidate_permission_cache([])
        return result

    def write(self, vals: dict) -> bool:
        if "partner_id" in vals or "document_id" in vals:
            _debug.logic("access_write_refused", reason="identity_change")
            raise AccessError(
                self.env._("Access documents and partners cannot be changed.")
            )

        self.document_id.check_access("write")
        self._check_membership_write(vals)
        _debug.lifecycle("access_write", access=self, fields=sorted(vals))
        result = super().write(vals)
        self.env["document.document"]._invalidate_permission_cache([])
        return result

    def _check_membership_write(self, vals: dict) -> None:
        if self.env.su:
            return
        user = self.env.user
        if user.share:
            _debug.logic("access_write_refused", reason="share_user")
            raise AccessError(
                self.env._("Only internal users can change who can access documents.")
            )
        if (
            {"role", "date_to"} & set(vals)
            and any(
                access.partner_id == user.partner_id
                and access.document_id.owner_id != user
                for access in self
            )
            and not self.env["document.document"]._is_documents_manager()
        ):
            _debug.logic("access_write_refused", reason="own_membership")
            raise AccessError(
                self.env._(
                    "You cannot change your own access to documents you do not own."
                )
            )

    @api.autovacuum
    def _gc_expired(self) -> tuple[int, bool]:
        limit = 1000
        expired = self.search([("date_to", "<=", fields.Datetime.now())], limit=limit)
        if not expired:
            return 0, False
        _debug.lifecycle("access_expired", removed=len(expired))
        expired.unlink()
        return len(expired), len(expired) == limit

    def _is_signup_available(self) -> bool:
        return (
            self.env["res.users"].sudo()._get_signup_invitation_scope() == "b2c"
            and self.partner_id
            and (not self.date_to or self.date_to > fields.Datetime.now())
            and not self.partner_id.with_context(active_test=False).user_ids
        )

    def _get_member_signup_token(self) -> str:
        self.check_singleton()
        if not self._is_signup_available():
            _debug.logic("member_invite_refused", access=self)
            raise UserError(self.env._("Cannot invite this member."))

        return tools.hmac(
            self.env(su=True), MEMBER_SIGNUP_SCOPE, (self.id, self.partner_id.id)
        )

    @api.model
    def _get_member_from_token(
        self, member_id: int, token: str
    ) -> DocumentsAccess | bool:
        member_sudo = self.browse(member_id).sudo().exists()
        if not member_sudo or not member_sudo._is_signup_available():
            _debug.logic("signup_token_refused", reason="unavailable", member=member_id)
            return False
        # `consteq` is `hmac.compare_digest`, which raises TypeError on a `str`
        # holding non-ASCII. `token` is the raw, public, attacker-controlled
        # `member_signup_token` query parameter, so without this guard any
        # non-ASCII value turned `/documents/<anything>` into an
        # unauthenticated HTTP 500 -- no valid document token needed, only a
        # `document.access` id, which is a small guessable integer. A real
        # token is `tools.hmac` output (hex), so non-ASCII simply never matches.
        if not isinstance(token, str) or not token.isascii():
            _debug.logic("signup_token_refused", reason="non_ascii", member=member_id)
            return False
        if not tools.is_hmac_valid(
            self.env,
            MEMBER_SIGNUP_SCOPE,
            (member_sudo.id, member_sudo.partner_id.id),
            token,
        ):
            _debug.logic("signup_token_refused", reason="mismatch", member=member_id)
            return False
        _debug.logic("signup_token_accepted", member=member_id)
        return member_sudo

    @api.model
    def _get_signup_url(
        self,
        member_id: int,
        member_signup_token: str,
        access_token: str,
        redirect_url: str,
    ) -> str:
        if not member_id or not member_signup_token or not access_token:
            return ""

        member_sudo = self._get_member_from_token(member_id, member_signup_token)
        if not member_sudo:
            return ""

        member_sudo.partner_id.signup_get_auth_param()
        return member_sudo.partner_id._get_signup_url_for_action(url=redirect_url)[
            member_sudo.partner_id.id
        ]
