from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import html2plaintext

_debug = DebugLog(__name__)


class KnowledgeArticleThread(models.Model):
    """Comment thread attached to a knowledge.article's body."""

    _name = "knowledge.article.thread"
    _description = "Article Discussion Thread"
    _inherit = ["mixin.mail.thread"]
    _mail_post_access = (
        "read"
    )
    _order = "write_date desc, id desc"
    _rec_name = "display_name"

    _ANCHOR_TEXT_MAX_LENGTH = 1200

    article_anchor_text = fields.Text(
        string="Anchor Text",
        help="The original highlighted anchor text, giving initial context if that text is modified or removed afterwards.",
    )
    article_id = fields.Many2one(
        comodel_name="knowledge.article",
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    is_resolved = fields.Boolean(
        string="Thread Closed",
        tracking=True,
    )

    @api.depends("article_id")
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.article_id.display_name


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "article_anchor_text" in vals:
                article_anchor_text = html2plaintext(vals["article_anchor_text"])
                vals["article_anchor_text"] = (
                    (article_anchor_text[: self._ANCHOR_TEXT_MAX_LENGTH] + "...")
                    if len(article_anchor_text) > self._ANCHOR_TEXT_MAX_LENGTH
                    else article_anchor_text
                )

        return super(
            KnowledgeArticleThread, self.with_context(mail_create_nolog=True)
        ).create(vals_list)

    def write(self, vals):
        if "is_resolved" in vals:
            self.check_singleton()
        if "article_anchor_text" in vals:
            article_anchor_text = html2plaintext(vals["article_anchor_text"])
            vals["article_anchor_text"] = (
                (article_anchor_text[: self._ANCHOR_TEXT_MAX_LENGTH] + "...")
                if len(article_anchor_text) > self._ANCHOR_TEXT_MAX_LENGTH
                else article_anchor_text
            )
        return super().write(vals)


    _PORTAL_POST_KEYS = frozenset(
        {"attachment_ids", "author_id", "body", "partner_ids"}
    )

    def _message_post_prepare_values(self, post_values) -> None:
        super()._message_post_prepare_values(post_values)
        if self.env.user._is_portal() and self.article_id.user_has_access:
            refused = post_values.keys() - self._PORTAL_POST_KEYS
            _debug.logic("portal_post_filtered", threads=self, refused=sorted(refused))
            for key in refused:
                del post_values[key]
        post_values.update(message_type="comment", subtype_xmlid="mail.mt_comment")

    def _get_access_action(self, access_uid=None, force_website=False):
        self.check_singleton()
        user = (
            self.env["res.users"].sudo().browse(access_uid)
            if access_uid
            else self.env.user
        )
        action = {
            "type": "ir.actions.act_url",
            "url": f"/knowledge/article/{self.article_id.id}",
        }
        if access_uid is None:
            action["target_type"] = "public"
        if self.article_id.with_user(user).user_has_access or access_uid is None:
            return action
        return super()._get_access_action(
            access_uid=access_uid, force_website=force_website
        )

    def _notify_thread_by_email(
        self, message, recipients_data, *, msg_vals=False, **kwargs
    ):
        msg_vals = msg_vals or {}
        msg_vals["email_layout_xmlid"] = "knowledge.knowledge_mail_notification_layout"
        return super()._notify_thread_by_email(
            message, recipients_data, msg_vals=msg_vals, **kwargs
        )

    def _message_compute_subject(self):
        self.check_singleton()
        return self.env._("New Mention in %s") % self.display_name

    def _notify_get_recipients(self, message, msg_vals=False, **kwargs):
        recipients_data = super()._notify_get_recipients(
            message, msg_vals=msg_vals, **kwargs
        )
        return [
            data
            for data in recipients_data
            if data["id"] in (msg_vals or {}).get("partner_ids", [])
        ]

    def _notify_get_recipients_groups(self, message, model_description, msg_vals=False):
        groups = super()._notify_get_recipients_groups(
            message, model_description, msg_vals=msg_vals
        )
        if message.model != "knowledge.article.thread":
            return groups

        self.check_singleton()

        new_groups = [
            (
                "group_knowledge_article_thread_portal_and_users",
                lambda pdata: (
                    pdata["uid"]
                    and self.article_id.with_user(pdata["uid"]).user_has_access
                ),
                {
                    "active": True,
                    "has_button_access": True,
                },
            )
        ]

        return new_groups + groups

    def _process_attachments_for_post(
        self, attachments, attachment_ids, message_values
    ):
        self.env["ir.attachment"].browse(attachment_ids).generate_access_token()
        return super()._process_attachments_for_post(
            attachments, attachment_ids, message_values
        )
