import logging
from typing import Self

import requests

from odoo import api, fields, models
from odoo.api import ValuesType

_logger = logging.getLogger(__name__)


class SocialLivePost(models.Model):

    _name = "social.live.post"
    _description = "Social Live Post"

    post_id = fields.Many2one(
        comodel_name="social.post",
        string="Social Post",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    account_id = fields.Many2one(
        comodel_name="social.account",
        string="Social Account",
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    message = fields.Char(
        compute="_compute_message",
        help="Content of the social post message that is post-processed (links are shortened, UTMs, ...)",
    )
    image_ids = fields.Many2many(
        comodel_name="ir.attachment",
        string="Attached Images",
        compute="_compute_image_ids",
    )
    live_post_link = fields.Char(
        string="Post Link",
        compute="_compute_live_post_link",
        help="Link of the live post on the target media.",
    )
    failure_reason = fields.Text(
        readonly=True,
        help="""The reason why a post is not successfully posted on the Social Media (eg: connection error, duplicated post, ...).""",
    )
    state = fields.Selection(
        selection=[
            ("ready", "Ready"),
            ("posting", "Posting"),
            ("posted", "Posted"),
            ("failed", "Failed"),
        ],
        string="Status",
        default="ready",
        readonly=True,
        required=True,
        help="""Most social.live.posts directly go from Ready to Posted/Failed since they result of a single call to the third party API.
        A 'Posting' state is also available for those that are sent through batching (like push notifications).""",
    )
    engagement = fields.Integer(
        help="Number of people engagements with the post (Likes, comments...)"
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="account_id.company_id",
        string="Company",
    )
    media_type = fields.Selection(
        related="account_id.media_type",
        string="Media",
    )

    @api.depends(
        lambda self: (
            [
                "post_id.utm_campaign_id",
                "account_id.media_type",
                "account_id.utm_medium_id",
                "post_id.source_id",
            ]
            + [
                f"post_id.{field}"
                for field in self.env[
                    "social.post"
                ]._get_fields_post_message_modifying()
            ]
            + [
                f"post_id.{field}"
                for field in self.env["social.post"]._message_fields().values()
            ]
        )
    )
    def _compute_message(self) -> None:
        message_field_per_media = self.env["social.post"]._message_fields()
        for live_post in self:
            message_field = message_field_per_media.get(live_post.account_id.media_type)
            if message_field:
                message = (
                    self.env["mixin.mail.render"]
                    .sudo()
                    ._shorten_links_text(
                        live_post.post_id[message_field], live_post._prepare_utm_vals()
                    )
                )

                live_post.message = self.env["social.post"]._prepare_post_content(
                    message,
                    live_post.account_id.media_type,
                    **{
                        field: live_post.post_id[field]
                        for field in self.env[
                            "social.post"
                        ]._get_fields_post_message_modifying()
                    },
                )
            else:
                live_post.message = False

    @api.depends(
        lambda self: [
            f"post_id.{field}"
            for field in self.env["social.post"]._images_fields().values()
        ]
    )
    def _compute_image_ids(self) -> None:
        images_field_per_media = self.env["social.post"]._images_fields()
        for live_post in self:
            image_field = images_field_per_media.get(live_post.media_type)
            live_post.image_ids = (
                live_post.post_id[image_field] if image_field else False
            )

    @api.depends("account_id.media_id")
    def _compute_live_post_link(self) -> None:
        for live_post in self:
            live_post.live_post_link = False

    @api.depends("state", "account_id")
    def _compute_display_name(self):
        state_description_values = dict(
            self._fields["state"]._description_selection(self.env)
        )
        for live_post in self:
            live_post.display_name = f"{live_post.account_id.display_name}: {state_description_values.get(live_post.state)}"

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        res.mapped("post_id")._check_post_completion()
        return res

    def write(self, vals):
        res = super().write(vals)
        if vals.get("state"):
            self.mapped("post_id")._check_post_completion()
        return res

    def action_retry_post(self) -> None:
        self._post()

    @api.model
    def refresh_statistics(self):
        try:
            self.env["social.live.post"]._refresh_statistics()
        except requests.exceptions.ConnectionError, requests.exceptions.Timeout:
            _logger.warning(
                "Failed to refresh the live post statistics.", exc_info=True
            )

    def _refresh_statistics(self):
        pass

    def _post(self):
        pass

    def _prepare_utm_vals(self) -> ValuesType:
        self.check_singleton()

        post_id = self.post_id
        return {
            "campaign_id": post_id.utm_campaign_id.id,
            "medium_id": self.account_id.utm_medium_id.id,
            "source_id": post_id.source_id.id,
        }

    def _filtered_by_media_types(self, media_types) -> Self:
        return self.filtered(
            lambda post: post.account_id.media_id.media_type in media_types
        )
