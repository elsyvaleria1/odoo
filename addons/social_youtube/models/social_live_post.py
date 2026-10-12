from itertools import batched

from odoo import fields, models
from odoo.libs.web import urljoin as url_join


class SocialLivePost(models.Model):
    _inherit = "social.live.post"

    youtube_video_id = fields.Char(related="post_id.youtube_video_id")

    youtube_title = fields.Char(related="post_id.youtube_title")
    youtube_description = fields.Text(related="post_id.youtube_description")
    youtube_video_privacy = fields.Selection(related="post_id.youtube_video_privacy")

    def _compute_live_post_link(self) -> None:
        youtube_live_posts = self._filtered_by_media_types(["youtube"]).filtered(
            lambda post: post.state == "posted"
        )
        super(SocialLivePost, self - youtube_live_posts)._compute_live_post_link()

        for post in youtube_live_posts:
            post.live_post_link = f"http://youtube.com/watch?v={post.youtube_video_id}"

    def _refresh_statistics(self):
        super()._refresh_statistics()
        youtube_accounts = self.env["social.account"].search(
            [("media_type", "=", "youtube")]
        )

        all_existing_posts = (
            self.env["social.live.post"]
            .sudo()
            .search(
                [
                    ("account_id", "in", youtube_accounts.ids),
                    ("youtube_video_id", "!=", False),
                ]
            )
        )
        posts_per_account = dict.fromkeys(
            youtube_accounts.ids, self.env["social.live.post"]
        )
        for existing_post in all_existing_posts:
            posts_per_account[existing_post.account_id.id] |= existing_post

        existing_live_posts_by_youtube_video_id = {
            live_post.youtube_video_id: live_post for live_post in all_existing_posts
        }

        youtube_videos = []
        for account in youtube_accounts:
            account._refresh_youtube_token()
            video_endpoint_url = url_join(
                self.env["social.media"]._YOUTUBE_ENDPOINT, "youtube/v3/videos"
            )

            youtube_video_ids = posts_per_account[account.id].mapped("youtube_video_id")

            YOUTUBE_BATCH_SIZE = 50
            for video_ids_batch in batched(
                youtube_video_ids, YOUTUBE_BATCH_SIZE, strict=False
            ):
                result = self.env["ir.egress"].request(
                    "GET",
                    video_endpoint_url,
                    purpose="social_youtube",
                    params={
                        "id": ",".join(video_ids_batch),
                        "access_token": account.youtube_access_token,
                        "part": "statistics",
                        "maxResults": YOUTUBE_BATCH_SIZE,
                    },
                    timeout=5,
                )

                if not result.ok:
                    account._action_disconnect_accounts(result.json())
                    break

                youtube_videos += result.json().get("items")

        for video in youtube_videos:
            video_stats = video["statistics"]
            existing_live_posts_by_youtube_video_id.get(video["id"]).write(
                {
                    "engagement": sum(
                        int(video_stats.get(key, 0))
                        for key in [
                            "likeCount",
                            "viewCount",
                            "commentCount",
                            "dislikeCount",
                            "favoriteCount",
                        ]
                    ),
                }
            )

    def _post(self):
        youtube_live_posts = self._filtered_by_media_types(["youtube"])
        super(SocialLivePost, (self - youtube_live_posts))._post()

        for live_post in youtube_live_posts:
            live_post._post_youtube()

    def _post_youtube(self) -> None:
        self.check_singleton()
        self.account_id._refresh_youtube_token()

        youtube_description = self.post_id.youtube_description
        if youtube_description:
            youtube_description = (
                self.env["mixin.mail.render"]
                .sudo()
                ._shorten_links_text(youtube_description, self._prepare_utm_vals())
            )

        video_endpoint_url = url_join(
            self.env["social.media"]._YOUTUBE_ENDPOINT, "youtube/v3/videos"
        )
        result = self.env["ir.egress"].request(
            "PUT",
            video_endpoint_url,
            purpose="social_youtube",
            params={
                "access_token": self.account_id.youtube_access_token,
                "part": "snippet,status",
            },
            json={
                "id": self.youtube_video_id,
                "snippet": {
                    "title": self.post_id.youtube_title,
                    "description": youtube_description,
                    "categoryId": self.post_id.youtube_video_category_id,
                },
                "status": {
                    "privacyStatus": self.post_id.youtube_video_privacy,
                    "embeddable": True,
                },
            },
            timeout=5,
        )

        if result.ok:
            values = {"state": "posted", "failure_reason": False}
        else:
            result_json = result.json()
            error_message = self.env._("An error occurred.")
            youtube_error = result_json.get("error")
            if youtube_error:
                error_reason = youtube_error.get("errors", [{}])[0].get("reason")
                if youtube_error.get("code") == 404 and error_reason == "videoNotFound":
                    error_message = self.env._(
                        "The video you are trying to publish has been deleted from YouTube."
                    )
                elif youtube_error.get("status") == "INVALID_ARGUMENT":
                    error_message = self.env._(
                        "Your video is missing a correct title or description."
                    )
                else:
                    error_message = (
                        youtube_error.get("errors", [{}])[0].get("message")
                        or error_reason
                    )

            values = {"state": "failed", "failure_reason": error_message}

        self.write(values)
