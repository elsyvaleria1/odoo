from odoo import api, fields, models


class SocialPost(models.Model):
    _inherit = "social.post"

    use_visitor_timezone = fields.Boolean(
        compute="_compute_use_visitor_timezone",
        store=True,
        readonly=False,
    )

    @api.depends("post_method")
    def _compute_use_visitor_timezone(self) -> None:
        for post in self:
            if post.post_method == "now" or not post.use_visitor_timezone:
                post.use_visitor_timezone = False

    def _action_post(self) -> None:

        super()._action_post()

        if "push_notifications" in self.account_ids.mapped("media_type") and any(
            post_method == "now" for post_method in self.mapped("post_method")
        ):
            self.env["ir.cron"]._trigger_ref(
                "social.ir_cron_post_scheduled", fields.Datetime.now()
            )

    @api.model
    def _cron_publish_scheduled(self) -> None:

        super()._cron_publish_scheduled()

        ready_live_posts = self.env["social.live.post"].search(
            [("state", "in", ["ready", "posting"])]
        )
        push_notifications_live_posts = ready_live_posts._filtered_by_media_types(
            ["push_notifications"]
        )
        push_notifications_live_posts.write({"state": "posting"})
        push_notifications_live_posts._post_push_notifications()
