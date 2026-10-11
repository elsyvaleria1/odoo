from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools.authority_keys import declare_authority_keys

from odoo.addons.base.models.mixin_access_graph import AccessGrantNames

declare_authority_keys("knowledge", "knowledge_member_skip_writable_check")


class KnowledgeArticleMember(models.Model):
    _name = "knowledge.article.member"
    _inherit = ["mixin.access.grant"]
    _description = "Article Grant"
    _rec_name = "partner_id"
    _access_grant_names = AccessGrantNames(resource="article_id", role="permission")

    article_id = fields.Many2one(
        comodel_name="knowledge.article",
        required=True,
        ondelete="cascade",
    )
    article_member_avatar = fields.Image(related="partner_id.avatar_128")
    permission = fields.Selection(
        selection=[("read", "Can read"), ("write", "Can edit")],
        default="read",
        required=True,
    )
    article_permission = fields.Selection(
        related="article_id.inherited_permission",
        readonly=True,
    )

    _unique_article_member = models.UniqueIndex(
        "(article_id, partner_id) WHERE partner_id IS NOT NULL",
        "You already added this partner on this article.",
    )
    _unique_article_group = models.UniqueIndex(
        "(article_id, group_id, COALESCE(company_id, 0)) WHERE group_id IS NOT NULL",
        "This group is already set on this article.",
    )

    @api.constrains("article_permission", "permission")
    def _check_is_writable(self, on_unlink=False) -> None:
        if self.env.context.get("knowledge_member_skip_writable_check"):
            return

        self.article_id.invalidate_recordset(["inherited_permission"])
        articles_to_check = self.article_id.filtered(
            lambda a: a.inherited_permission != "write"
        )
        if not articles_to_check:
            return

        if on_unlink:
            deleted_members_by_article = dict.fromkeys(
                articles_to_check.ids, self.env["knowledge.article.member"]
            )
            for member in self.filtered(
                lambda member: member.article_id in articles_to_check
            ):
                deleted_members_by_article[member.article_id.id] |= member

        for article in articles_to_check:
            members_to_check = article.article_member_ids
            if on_unlink:
                members_to_check -= deleted_members_by_article[article.id]
            if any(m.permission == "write" for m in members_to_check):
                continue

            members_to_exclude = (
                deleted_members_by_article[article.id] if on_unlink else False
            )
            if not article._has_write_member(members_to_exclude=members_to_exclude):
                raise ValidationError(
                    self.env._(
                        "Article '%s' should always have a writer: inherit write permission, or have a member with write access",
                        article.display_name,
                    )
                )

    PERMISSION_FIELDS = (
        "internal_permission",
        "inherited_permission",
        "inherited_permission_parent_id",
        "user_permission",
        "user_has_access",
        "user_has_write_access",
        "user_can_read",
        "user_can_write",
        "access_role",
    )

    @api.model_create_multi
    def create(self, vals_list):
        members = super().create(vals_list)
        self.env["knowledge.article"].invalidate_model(self.PERMISSION_FIELDS)
        return members

    def write(self, vals):
        if (
            "article_id" in vals or "partner_id" in vals or "group_id" in vals
        ) and not self.env.is_admin():
            raise AccessError(
                self.env._("Can not update the article or partner of a member.")
            )
        result = super().write(vals)
        self.env["knowledge.article"].invalidate_model(self.PERMISSION_FIELDS)
        return result

    def unlink(self):
        result = super().unlink()
        self.env["knowledge.article"].invalidate_model(self.PERMISSION_FIELDS)
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_no_writer(self) -> None:
        self._check_is_writable(on_unlink=True)

    def _get_invitation_token(self) -> str:
        self.check_singleton()
        __, token = (
            self.env["access.link"]
            .with_privilege(
                "base.privilege_manage_links", reason="invite to an article"
            )
            ._issue(self, partner=self.partner_id, role="view", cause="share")
        )
        return token
