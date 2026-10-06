import base64
from binascii import Error as binascii_error

from odoo import api, fields, models
from odoo.exceptions import UserError


class SocialPostTemplate(models.Model):
    _inherit = "social.post.template"

    push_notification_message = fields.Text(
        string="Push Notifications Message",
        compute="_compute_message_by_media",
        store=True,
        readonly=False,
    )

    push_notification_title = fields.Char()
    push_notification_target_url = fields.Char(string="Push Target URL")
    push_notification_image = fields.Binary(
        string="Push Icon Image",
        help="This icon will be displayed in the browser notification",
    )
    # Preview
    has_push_notifications_account = fields.Boolean(
        compute="_compute_has_push_notifications_account"
    )
    display_push_notifications_preview = fields.Boolean(
        compute="_compute_display_push_notifications_preview"
    )
    push_notifications_preview = fields.Html(
        compute="_compute_push_notifications_preview"
    )
    # Visitor
    use_visitor_timezone = fields.Boolean(
        string="Send at Visitors' Timezone",
        help="e.g: If you post at 15:00 your time, all visitors will receive the post at 15:00 their time.",
    )
    visitor_domain = fields.Char(
        default=[["has_push_notifications", "!=", False]],
        help="Domain to send push notifications to visitors.",
    )

    @api.constrains("push_notification_message")
    def _check_has_push_notification_message(self) -> None:
        for post in self:
            if (
                post.has_push_notifications_account
                and not post.push_notification_message
            ):
                raise UserError(self.env._("Please specify a Notification Message."))

    @api.depends("account_ids.media_id.media_type")
    def _compute_has_push_notifications_account(self) -> None:
        for post in self:
            post.has_push_notifications_account = (
                "push_notifications" in post.account_ids.media_id.mapped("media_type")
            )

    @api.depends("push_notification_message", "has_push_notifications_account")
    def _compute_display_push_notifications_preview(self) -> None:
        for post in self:
            post.display_push_notifications_preview = (
                post.push_notification_message and post.has_push_notifications_account
            )

    @api.depends(
        "push_notification_message",
        "push_notification_title",
        "push_notification_image",
        "display_push_notifications_preview",
    )
    def _compute_push_notifications_preview(self) -> None:
        for post in self:
            if not post.display_push_notifications_preview:
                post.push_notifications_preview = False
                continue
            icon = False
            icon_url = False
            if post.push_notification_image:
                try:
                    base64.b64decode(post.push_notification_image, validate=True)
                    icon = post.push_notification_image
                except binascii_error:
                    if post.id or (post._origin and post._origin.id):
                        icon_url = (
                            "/web/image/social.post/%s/push_notification_image"
                            % (post.id or post._origin.id)
                        )
            post.push_notifications_preview = self.env["ir.qweb"]._render(
                "social_push_notifications.push_notifications_preview",
                {
                    "title": post.push_notification_title or self.env._("New Message"),
                    "icon": icon,
                    "icon_url": icon_url,
                    "message": post.push_notification_message,
                    "host_name": post.get_base_url() or "https://myapp.com",
                },
            )

    @api.model_create_multi
    def create(self, vals_list):
        """Assign a default push_notification_target_url is none specified and we can extract one from the message"""
        for index, values in enumerate(vals_list):
            if not values.get("push_notification_target_url") and values.get("message"):
                message = self._prepare_post_content(
                    values["message"],
                    "push_notifications",
                    **{
                        field: values[field]
                        for field in set(self._get_fields_post_message_modifying())
                        & values.keys()
                    },
                )
                extracted_url = self._extract_url_from_message(message)
                if extracted_url:
                    vals_list[index]["push_notification_target_url"] = extracted_url
        return super().create(vals_list)

    def write(self, vals):
        """Assign a default push_notification_target_url is none specified and we can extract one from the message"""
        if not any(post.push_notification_target_url for post in self) and vals.get(
            "message"
        ):
            message = self._prepare_post_content(
                vals["message"],
                "push_notifications",
                **{
                    field: vals[field]
                    for field in set(self._get_fields_post_message_modifying())
                    & vals.keys()
                },
            )
            extracted_url = self._extract_url_from_message(message)
            if extracted_url:
                vals["push_notification_target_url"] = extracted_url
        return super().write(vals)

    def _prepare_social_post_values(self):
        """Return the values to generate a social post from the social post template."""
        values = super()._prepare_social_post_values()
        values.update(
            {
                "push_notification_title": self.push_notification_title,
                "push_notification_image": self.push_notification_image,
                "push_notification_target_url": self.push_notification_target_url,
                "use_visitor_timezone": self.use_visitor_timezone,
                "visitor_domain": self.visitor_domain,
            }
        )
        return values

    @api.model
    def _message_fields(self) -> dict:
        """Return the message field per media."""
        return {
            **super()._message_fields(),
            "push_notifications": "push_notification_message",
        }
