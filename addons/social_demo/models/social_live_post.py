from odoo import fields, models


class SocialLivePost(models.Model):
    _inherit = "social.live.post"

    def _refresh_statistics(self):
        return

    def _post_facebook(self, facebook_target_id) -> None:
        facebook_stream = self.env.ref(
            "social_demo.social_stream_facebook_page", raise_if_not_found=False
        )
        if facebook_stream:
            self.write({"facebook_post_id": self.id})
            self._post_demo(facebook_stream.id, {"facebook_post_id": self.id})

    def _post_instagram(self) -> None:
        instagram_stream = self.env.ref(
            "social_demo.social_stream_instagram_account", raise_if_not_found=False
        )
        if instagram_stream:
            self.write({"instagram_post_id": self.id})
            self._post_demo(instagram_stream.id, {"instagram_post_id": self.id})

    def _post_twitter(self) -> None:

        twitter_stream_search = self.env.ref(
            "social_demo.social_stream_twitter_search", raise_if_not_found=False
        )
        if twitter_stream_search:
            stream_post_search_to_create = [
                {
                    "stream_id": twitter_stream_search.id,
                    "author_name": "My Company Account",
                    "twitter_profile_image_url": "/web/image/res.users/%s/avatar_128"
                    % self.env.ref("base.user_admin").id,
                    "message": live_post.post_id.message,
                    "published_date": fields.Datetime.now(),
                }
                for live_post in self
                if "#mycompany" in live_post.post_id.message
            ]

            if stream_post_search_to_create:
                self.env["social.stream.post"].create(stream_post_search_to_create)

        twitter_stream_account = self.env.ref(
            "social_demo.social_stream_twitter_account", raise_if_not_found=False
        )
        if twitter_stream_account:
            self.write({"twitter_tweet_id": self.id})
            self._post_demo(twitter_stream_account.id, {"twitter_tweet_id": self.id})

    def _post_linkedin(self) -> None:
        linkedin_stream_page = self.env.ref(
            "social_demo.social_stream_linkedin_page", raise_if_not_found=False
        )
        if linkedin_stream_page:
            self.write({"linkedin_post_id": self.id})
            self._post_demo(
                linkedin_stream_page.id,
                {"linkedin_post_urn": self.id, "linkedin_author_urn": "ABC123"},
            )

    def _post_demo(self, stream_id, additional_vals=None) -> None:

        stream_posts_to_create = [
            dict(
                {
                    "stream_id": stream_id,
                    "author_name": "My Company Account",
                    "twitter_profile_image_url": "/web/image/res.users/%s/avatar_128"
                    % self.env.ref("base.user_admin").id,
                    "message": live_post.post_id.message,
                    "published_date": fields.Datetime.now(),
                },
                **(additional_vals or {}),
            )
            for live_post in self
        ]

        if stream_posts_to_create:
            self.env["social.stream.post"].create(stream_posts_to_create)

        self.write({"state": "posted"})
