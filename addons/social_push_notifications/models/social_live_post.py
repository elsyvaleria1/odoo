import ast
from datetime import UTC

from odoo import Command, fields, models
from odoo.fields import Domain
from odoo.libs.datetime import timezone


class SocialLivePost(models.Model):
    _inherit = "social.live.post"

    reached_visitor_ids = fields.Many2many(
        comodel_name="website.visitor",
        string="Reached Visitors",
    )

    push_notification_title = fields.Char(related="post_id.push_notification_title")
    push_notification_target_url = fields.Char(
        related="post_id.push_notification_target_url"
    )
    push_notification_image = fields.Binary(related="post_id.push_notification_image")

    def _post(self):

        push_notifications_live_posts = self._filtered_by_media_types(
            ["push_notifications"]
        )
        super(SocialLivePost, (self - push_notifications_live_posts))._post()

        push_notifications_live_posts.write({"state": "ready"})

    def _post_push_notifications(self) -> None:
        for live_post in self:
            post = live_post.post_id
            account = live_post.account_id
            title = post.push_notification_title or self.env._("New Message")
            icon_url = (
                "/social_push_notifications/social_post/%s/push_notification_image"
                % post.id
                if post.push_notification_image
                else "/mail/static/src/img/odoobot_transparent.png"
            )

            visitor_domain = Domain(ast.literal_eval(live_post.post_id.visitor_domain))
            if account.website_id:
                if account.website_id.firebase_enable_push_notifications:
                    visitor_domain &= Domain("website_id", "=", account.website_id.id)
                else:
                    live_post.write({"state": "posted"})
                    continue

            target_link = ""
            if post.push_notification_target_url:
                link_tracker_values = live_post._prepare_utm_vals()
                link_tracker_values["url"] = post.push_notification_target_url
                link_tracker = self.env["link.tracker"].search_or_create(
                    [link_tracker_values]
                )
                target_link = link_tracker.short_url

            if not post.use_visitor_timezone or not post.scheduled_date:
                target_visitors = self.env["website.visitor"].search(visitor_domain)
            else:
                post_date = post.scheduled_date
                post_user_datetime = (
                    post_date.replace(tzinfo=UTC)
                    .astimezone(timezone(post.create_uid.tz))
                    .replace(tzinfo=None)
                )
                now_utc = fields.Datetime.now().replace(tzinfo=UTC)
                pending_visitors = self.env["website.visitor"].search(
                    visitor_domain
                    & Domain("id", "not in", live_post.reached_visitor_ids.ids)
                )
                target_visitors = pending_visitors.browse(
                    [
                        visitor.id
                        for visitor in pending_visitors
                        if now_utc.astimezone(
                            timezone(visitor.timezone or "UTC")
                        ).replace(tzinfo=None)
                        > post_user_datetime
                    ]
                )

            account._firebase_send_message(
                {
                    "title": title,
                    "body": live_post.message,
                    "icon": icon_url,
                    "target_url": target_link,
                },
                target_visitors,
            )

            if post.use_visitor_timezone:
                values = {
                    "reached_visitor_ids": [
                        Command.link(target_visitor.id)
                        for target_visitor in target_visitors
                    ]
                }
                if len(pending_visitors) == len(target_visitors):
                    values["state"] = "posted"

                live_post.write(values)
            else:
                live_post.write({"state": "posted"})

    def _clean_unregistered_tokens(self, result) -> None:

        matched_registrations = result[0]
        batch_results = result[1]

        all_responses = []
        for batch_result in batch_results:
            all_responses.extend(batch_result.responses)

        registration_token_to_remove = []
        for i, response in enumerate(all_responses):
            if (
                not response.success
                and response.exception.code == "registration-token-not-registered"
            ):
                registration_token_to_remove.append(matched_registrations[i]["token"])

        if registration_token_to_remove:
            self.env["website.visitor.push.subscription"].search(
                [("push_token", "in", registration_token_to_remove)]
            ).sudo().unlink()
