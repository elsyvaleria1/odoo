from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain


class SocialPost(models.Model):
    _inherit = "social.post"

    youtube_video = fields.Char(
        string="YouTube Video",
        help="Simply holds the filename of the video as the video itself is uploaded directly to YouTube",
    )
    youtube_video_id = fields.Char(
        string="YouTube Video Id",
        help="Contains the ID of the video as returned by the YouTube API",
    )
    youtube_video_category_id = fields.Char(
        string="YouTube Category Id",
        help="Contains the ID of the video category as returned by the YouTube API",
    )
    youtube_access_token = fields.Char(
        string="YouTube Access Token",
        compute="_compute_youtube_access_token",
    )
    youtube_title = fields.Char(string="YouTube Video Title")
    youtube_description = fields.Text(string="YouTube Video Description")
    youtube_preview = fields.Html(
        string="YouTube Preview",
        compute="_compute_youtube_preview",
    )
    youtube_accounts_count = fields.Integer(
        string="Selected YouTube Accounts",
        compute="_compute_youtube_accounts_count",
    )
    youtube_accounts_other_count = fields.Integer(
        string="Selected Other Accounts",
        compute="_compute_youtube_accounts_count",
    )
    youtube_video_privacy = fields.Selection(
        selection=[
            ("public", "Public"),
            ("unlisted", "Unlisted"),
            ("private", "Private"),
        ],
        string="Video Privacy",
        default="public",
        help="Once posted, set the video as Public/Private/Unlisted",
    )
    youtube_video_url = fields.Char(
        string="YouTube Video Url",
        compute="_compute_youtube_video_url",
    )
    youtube_thumbnail_url = fields.Char(
        string="YouTube Thumbnail Url",
        compute="_compute_youtube_thumbnail_url",
    )

    @api.constrains("message", "image_ids")
    def _check_has_message_or_image(self) -> None:
        youtube_posts_only = self.filtered(
            lambda post: all(media.media_type == "youtube" for media in post.media_ids)
        )
        super(SocialPost, self - youtube_posts_only)._check_has_message_or_image()

    @api.depends("youtube_video_id")
    def _compute_stream_posts_count(self) -> None:
        super()._compute_stream_posts_count()

    @api.depends("account_ids.media_type", "account_ids.youtube_access_token")
    def _compute_youtube_access_token(self) -> None:
        for post in self:
            youtube_account = post.account_ids.filtered(
                lambda account: account.media_type == "youtube"
            )
            if len(youtube_account) == 1:
                youtube_account._refresh_youtube_token()
                post.youtube_access_token = youtube_account.youtube_access_token
            else:
                post.youtube_access_token = False

    @api.depends(
        "youtube_title",
        "youtube_description",
        "youtube_video_id",
        "scheduled_date",
        "youtube_accounts_count",
    )
    def _compute_youtube_preview(self) -> None:
        for post in self:
            if not (post.youtube_accounts_count == 1 and post.youtube_title):
                post.youtube_preview = False
                continue
            post.youtube_preview = self.env["ir.qweb"]._render(
                "social_youtube.youtube_preview",
                {
                    "youtube_title": post.youtube_title or self.env._("Video"),
                    "youtube_description": post.youtube_description,
                    "youtube_video_id": post.youtube_video_id,
                    "published_date": post.scheduled_date or fields.Datetime.now(),
                    "post_link": "https://www.youtube.com/watch?v=%s"
                    % post.youtube_video_id
                    if post.youtube_video_id
                    else "",
                },
            )

    @api.depends("account_ids.media_type")
    def _compute_youtube_accounts_count(self) -> None:
        for post in self:
            post.youtube_accounts_count = len(
                post.account_ids.filtered(
                    lambda account: account.media_type == "youtube"
                )
            )
            post.youtube_accounts_other_count = (
                len(post.account_ids) - post.youtube_accounts_count
            )

    @api.depends("youtube_video_id")
    def _compute_youtube_thumbnail_url(self) -> None:
        for post in self:
            post.youtube_thumbnail_url = (
                "http://i3.ytimg.com/vi/%s/hqdefault.jpg" % post.youtube_video_id
            )

    @api.depends("youtube_video_id")
    def _compute_youtube_video_url(self) -> None:
        for post in self:
            post.youtube_video_url = (
                "https://www.youtube.com/watch?v=%s" % post.youtube_video_id
            )

    def _check_post_access(self) -> None:
        super()._check_post_access()

        for social_post in self:
            if social_post.youtube_accounts_count > 1:
                raise UserError(
                    self.env._("Please select a single YouTube account at a time.")
                )
            if (
                not social_post.youtube_video_id
                and "youtube" in social_post.media_ids.mapped("media_type")
            ):
                raise UserError(
                    self.env._("You have to upload a video when posting on YouTube.")
                )
            if social_post.youtube_title:
                if ">" in social_post.youtube_title or "<" in social_post.youtube_title:
                    raise ValidationError(
                        self.env._("Title should not contain > or < symbol.")
                    )
                if len(social_post.youtube_title) > 100:
                    raise ValidationError(
                        self.env._("Title cannot exceed 100 characters.")
                    )
            if social_post.youtube_description:
                if (
                    ">" in social_post.youtube_description
                    or "<" in social_post.youtube_description
                ):
                    raise ValidationError(
                        self.env._("Description should not contain > or < symbol.")
                    )
                if len(social_post.youtube_description) > 5000:
                    raise ValidationError(
                        self.env._("Description cannot exceed 5000 characters.")
                    )

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if (
                not values.get("message")
                and not values.get("name")
                and values.get("youtube_title")
            ):
                values["name"] = self.env["utm.source"]._generate_name(
                    self, values.get("youtube_title")
                )
        return super().create(vals_list)

    def _get_domain_stream_post(self):
        domain = super()._get_domain_stream_post()
        youtube_video_ids = [
            youtube_video_id
            for youtube_video_id in self.mapped("youtube_video_id")
            if youtube_video_id
        ]
        if youtube_video_ids:
            return Domain.OR([domain, [("youtube_video_id", "in", youtube_video_ids)]])
        else:
            return domain

    @api.model
    def _prepare_post_content(self, message, media_type, **kw):
        message = super()._prepare_post_content(message, media_type, **kw)
        if media_type != "youtube" and kw.get("youtube_video_id"):
            message += f"\n\nhttps://youtube.com/watch?v={kw.get('youtube_video_id')}"
        return message

    @api.model
    def _get_fields_post_message_modifying(self):
        return super()._get_fields_post_message_modifying() + ["youtube_video_id"]
