from datetime import datetime, timedelta
from typing import Self

from odoo import api, fields, models
from odoo.libs.json import dumps as json_dumps
from odoo.tools.misc import _format_time_ago, format_date


class SocialStreamPost(models.Model):
    """A 'stream' post, as opposed to a regular social.post, references a post that
    actually exists on a social.media external database (a Facebook post, a Tweet, ...).

    Stream posts are created by fetching data from the related social media third party API.
    They should not be directly created/modified.

    social.stream.posts are used to fill the 'Feed' view that allows users to follow the social.media activity
    based on their interest (a Facebook Page, a Twitter hashtag, ...).
    They are directly created by their related social.stream."""

    _name = "social.stream.post"
    _description = "Social Stream Post"
    _order = "published_date desc"

    message = fields.Text()
    author_name = fields.Char(
        help="The post author name based on third party information (ex: 'John Doe')."
    )
    author_link = fields.Char(
        compute="_compute_author_link",
        help="Author link to the external social.media (ex: link to the X Account).",
    )
    post_link = fields.Char(
        compute="_compute_post_link",
        help="Post link to the external social.media (ex: link to the actual Facebook Post).",
    )
    stream_id = fields.Many2one(
        comodel_name="social.stream",
        string="Social Stream",
        index="btree_not_null",
        ondelete="cascade",
    )
    media_type = fields.Selection(
        related="stream_id.media_id.media_type",
        string="Related Social Media",
    )
    published_date = fields.Datetime(
        string="Published date",
        help="The post published date based on third party information.",
    )
    formatted_published_date = fields.Char(compute="_compute_formatted_published_date")
    account_id = fields.Many2one(
        related="stream_id.account_id",
        string="Related social Account",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="account_id.company_id",
        string="Company",
    )
    is_author = fields.Boolean(compute="_compute_is_author")

    stream_post_image_ids = fields.One2many(
        comodel_name="social.stream.post.image",
        inverse_name="stream_post_id",
        string="Stream Post Images",
        help="Images that were shared with this post.",
    )
    stream_post_image_urls = fields.Text(
        string="Stream Post Images URLs",
        compute="_compute_stream_post_image_urls",
    )

    link_title = fields.Text()
    link_description = fields.Text()
    link_image_url = fields.Char(string="Link Image URL")
    link_url = fields.Char(string="Link URL")

    def _compute_stream_post_image_urls(self) -> None:
        for stream_post in self:
            stream_post.stream_post_image_urls = json_dumps(
                [image.image_url for image in stream_post.stream_post_image_ids]
            )

    def _compute_author_link(self) -> None:
        for post in self:
            post.author_link = False

    def _compute_post_link(self) -> None:
        for post in self:
            post.post_link = False

    @api.depends("published_date")
    def _compute_formatted_published_date(self) -> None:
        for post in self:
            post.formatted_published_date = (
                self._format_published_date(post.published_date)
                if post.published_date
                else False
            )

    def _compute_is_author(self) -> None:
        self.is_author = False

    def _filtered_by_media_types(self, media_types) -> Self:
        return self.filtered(lambda post: post.media_type in media_types)

    @api.model
    def _format_published_date(self, published_date):
        if (datetime.now() - published_date) < timedelta(hours=12):
            return _format_time_ago(
                self.env, (datetime.now() - published_date), add_direction=False
            )
        else:
            return format_date(self.env, published_date)

    def _get_matching_post(self):

        self.check_singleton()
        return self.env["social.post"]
