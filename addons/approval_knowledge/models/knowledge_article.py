from odoo import fields, models
from odoo.exceptions import UserError

ARTICLE_ACCESS_ROLES = ("read", "write")


class KnowledgeArticle(models.Model):
    _name = "knowledge.article"
    _inherit = ["knowledge.article", "mixin.approval.access"]
    _access_approval_category = "approval_knowledge.approval_category_article_access"

    access_approver_user_ids = fields.Many2many(
        comodel_name="res.users",
        string="Editors Deciding Access",
        compute="_compute_access_approver_user_ids",
        compute_sudo=True,
    )

    def _compute_access_approver_user_ids(self) -> None:
        permissions = self._get_article_member_permissions()
        for article in self:
            partners = self.env["res.partner"].browse(
                partner_id
                for partner_id, member in permissions.get(article.id, {}).items()
                if member["permission"] == "write"
            )
            article.access_approver_user_ids = partners.user_ids.filtered(
                lambda user: user._is_internal()
            )

    def _get_partner_permission(self, partner) -> str:
        self.check_singleton()
        permissions = {
            self.with_user(user).user_permission for user in partner.user_ids
        }
        if "write" in permissions:
            return "write"
        return "read" if "read" in permissions else "none"

    def _has_access(self, partner, role=False) -> bool:
        permission = self._get_partner_permission(partner)
        return permission == "write" or (permission == "read" and role != "write")

    def _request_access(self, partner, role=False):
        if role not in ARTICLE_ACCESS_ROLES:
            raise UserError(self.env._("Ask to read or to edit an article."))
        return super()._request_access(partner, role)

    def _get_access_request_name(self, partner, role) -> str:
        if role == "write":
            return self.env._(
                "Edit access to %(article)s for %(partner)s",
                article=self.display_name,
                partner=partner.name,
            )
        return self.env._(
            "Read access to %(article)s for %(partner)s",
            article=self.display_name,
            partner=partner.name,
        )

    def _grant_access(self, partner, role=False) -> None:
        self.sudo().invite_members(partner, role)
