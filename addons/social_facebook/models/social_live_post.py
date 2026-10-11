from odoo import fields, models
from odoo.exceptions import UserError
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.libs.web import urljoin as url_join


class SocialLivePost(models.Model):
    _inherit = "social.live.post"

    facebook_post_id = fields.Char(string="Actual Facebook ID of the post")

    def _compute_live_post_link(self) -> None:
        facebook_live_posts = self._filtered_by_media_types(["facebook"]).filtered(
            lambda post: post.state == "posted"
        )
        super(SocialLivePost, self - facebook_live_posts)._compute_live_post_link()

        for post in facebook_live_posts:
            post.live_post_link = "http://facebook.com/%s" % post.facebook_post_id

    def _refresh_statistics(self):
        super()._refresh_statistics()
        accounts = self.env["social.account"].search([("media_type", "=", "facebook")])

        for account in accounts:
            posts_endpoint_url = url_join(
                self.env["social.media"]._FACEBOOK_ENDPOINT_VERSIONED,
                "%s/%s" % (account.facebook_account_id, "published_posts"),
            )
            result = self.env["ir.egress"].request(
                "GET",
                posts_endpoint_url,
                purpose="social_facebook",
                params={
                    "access_token": account.facebook_access_token,
                    "fields": "id,shares,likes.limit(1).summary(true),comments.summary(true)",
                },
                timeout=5,
            )

            result_posts = result.json().get("data")
            if not result_posts:
                account._action_disconnect_accounts(result.json())
                return

            facebook_post_ids = [post.get("id") for post in result_posts]
            existing_live_posts = (
                self.env["social.live.post"]
                .sudo()
                .search([("facebook_post_id", "in", facebook_post_ids)])
            )

            existing_live_posts_by_facebook_post_id = {
                live_post.facebook_post_id: live_post
                for live_post in existing_live_posts
            }

            for post in result_posts:
                existing_live_post = existing_live_posts_by_facebook_post_id.get(
                    post.get("id")
                )
                if existing_live_post:
                    likes_count = (
                        post.get("likes", {}).get("summary", {}).get("total_count", 0)
                    )
                    shares_count = post.get("shares", {}).get("count", 0)
                    comments_count = (
                        post.get("comments", {})
                        .get("summary", {})
                        .get("total_count", 0)
                    )
                    existing_live_post.write(
                        {
                            "engagement": likes_count + shares_count + comments_count,
                        }
                    )

    def _post(self):
        facebook_live_posts = self._filtered_by_media_types(["facebook"])
        super(SocialLivePost, (self - facebook_live_posts))._post()

        for live_post in facebook_live_posts:
            live_post._post_facebook(live_post.account_id.facebook_account_id)

    def _post_facebook(self, facebook_target_id) -> None:
        self.check_singleton()
        account = self.account_id
        post_endpoint_url = url_join(
            self.env["social.media"]._FACEBOOK_ENDPOINT_VERSIONED,
            "%s/feed" % facebook_target_id,
        )

        post = self.post_id

        params = {
            "message": self.message,
            "access_token": account.facebook_access_token,
        }

        if self.image_ids and len(self.image_ids) == 1:
            image = self.image_ids[0]
            if image.mimetype == "image/gif":
                endpoint_url = url_join(
                    "https://graph-video.facebook.com",
                    f"/v17.0/{facebook_target_id}/videos",
                )
                params["description"] = params["message"]
            else:
                endpoint_url = url_join(
                    self.env["social.media"]._FACEBOOK_ENDPOINT_VERSIONED,
                    f"{facebook_target_id}/photos",
                )
                params["caption"] = params["message"]

            result = self.env["ir.egress"].request(
                "POST",
                endpoint_url,
                purpose="social_facebook",
                params=params,
                timeout=15,
                files={
                    "source": (
                        image.name,
                        image.with_context(bin_size=False).raw,
                        image.mimetype,
                    )
                },
            )
            if not result.ok:
                generic_api_error = (
                    json_loads(result.text or "{}").get("error", {}).get("message", "")
                )
                self.write(
                    {
                        "state": "failed",
                        "failure_reason": self.env._(
                            "We could not upload your image, try reducing its size and posting it again (error: %s).",
                            generic_api_error,
                        ),
                    }
                )
                return
        else:
            if self.image_ids:
                try:
                    images_attachments = post._format_images_facebook(
                        account.facebook_account_id, account.facebook_access_token
                    )
                except UserError as e:
                    self.write({"state": "failed", "failure_reason": str(e)})
                    return
                images_attachments = post._format_images_facebook(
                    facebook_target_id, account.facebook_access_token
                )
                if images_attachments:
                    params.update(
                        {
                            f"attached_media[{index}]": json_dumps(attachment)
                            for index, attachment in enumerate(images_attachments)
                        }
                    )

            link_url = self.env["social.post"]._extract_url_from_message(self.message)
            if link_url and not self.image_ids:
                params.update({"link": link_url})

            result = self.env["ir.egress"].request(
                "POST",
                post_endpoint_url,
                purpose="social_facebook",
                data=params,
                timeout=15,
            )

        if result.status_code == 200:
            result_json = result.json()
            self.facebook_post_id = result_json.get(
                "post_id", result_json.get("id", False)
            )
            values = {"state": "posted", "failure_reason": False}
        else:
            values = {
                "state": "failed",
                "failure_reason": json_loads(result.text or "{}")
                .get("error", {})
                .get("message", ""),
            }

        self.write(values)
