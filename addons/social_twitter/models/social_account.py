import base64

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.web import urljoin as url_join

TWITTER_IMAGES_UPLOAD_ENDPOINT = "https://api.x.com/2/media/upload"


class SocialAccount(models.Model):
    _inherit = "social.account"
    _CREDENTIAL_FIELDS = {
        "twitter_oauth_token": "twitter_oauth_token",
        "twitter_oauth_token_secret": "twitter_oauth_token_secret",
    }

    twitter_user_id = fields.Char(string="X User ID")
    twitter_oauth_token = fields.Char(
        string="X OAuth Token",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
    )
    twitter_oauth_token_secret = fields.Char(
        string="X OAuth Token Secret",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
    )

    def _update_statistics(self):

        twitter_accounts = self._filtered_by_media_types(["twitter"])
        super(SocialAccount, (self - twitter_accounts))._update_statistics()

        for account in twitter_accounts:
            account_stats = account._get_account_stats()
            last_tweets_stats = account._get_last_tweets_stats()

            if account_stats and last_tweets_stats:
                account.write(
                    {
                        "audience": account_stats.get("data", [{}])[0]
                        .get("public_metrics", {})
                        .get("followers_count"),
                        "engagement": last_tweets_stats["engagement"],
                        "stories": last_tweets_stats["stories"],
                    }
                )

    def _compute_stats_link(self) -> None:
        twitter_accounts = self._filtered_by_media_types(["twitter"])
        super(SocialAccount, (self - twitter_accounts))._compute_stats_link()

        for account in twitter_accounts:
            account.stats_link = (
                f"https://analytics.twitter.com/user/{account.social_account_handle}"
            )

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        res.filtered(
            lambda account: account.media_type == "twitter"
        )._create_default_stream_twitter()
        return res

    def twitter_get_user_by_username(self, username):
        user_search_endpoint = url_join(
            self.env["social.media"]._TWITTER_ENDPOINT,
            "/2/users/by/username/%s" % username,
        )
        params = {"user.fields": "id,name,username,description,profile_image_url"}
        headers = self._get_twitter_oauth_header(
            user_search_endpoint, params=params, method="GET"
        )
        response = self.env["ir.egress"].request(
            "GET",
            user_search_endpoint,
            purpose="social_twitter",
            params=params,
            headers=headers,
            timeout=5,
        )
        return response.json().get("data", False) if response.ok else False

    def _create_default_stream_twitter(self) -> None:

        if not self:
            return

        own_tweets_stream_type_id = self.env.ref(
            "social_twitter.stream_type_twitter_follow"
        ).id
        streams_to_create = []
        for account in self:
            twitter_followed_account = self.env["social.twitter.account"].create(
                {
                    "name": account.name,
                    "twitter_id": account.twitter_user_id,
                    "image": account.image,
                }
            )
            streams_to_create.append(
                {
                    "media_id": account.media_id.id,
                    "stream_type_id": own_tweets_stream_type_id,
                    "account_id": account.id,
                    "twitter_followed_account_id": twitter_followed_account.id,
                }
            )
        self.env["social.stream"].create(streams_to_create)

    def _get_account_stats(self):

        self.check_singleton()

        twitter_account_info_url = url_join(
            self.env["social.media"]._TWITTER_ENDPOINT, "/2/users/by"
        )
        params = {
            "user.fields": "public_metrics",
            "usernames": self.social_account_handle,
        }

        headers = self._get_twitter_oauth_header(
            twitter_account_info_url,
            params=params,
            method="GET",
        )

        result = self.env["ir.egress"].request(
            "GET",
            twitter_account_info_url,
            purpose="social_twitter",
            params=params,
            headers=headers,
            timeout=5,
        )

        if isinstance(result.json(), dict) and result.json().get("errors"):
            self._action_disconnect_accounts(result.json())
            return False

        return result.json()

    def _get_last_tweets_stats(self):

        self.check_singleton()

        tweets_endpoint_url = url_join(
            self.env["social.media"]._TWITTER_ENDPOINT,
            "/2/users/%s/tweets" % self.twitter_user_id,
        )
        params = {
            "max_results": 100,
            "tweet.fields": "public_metrics",
        }
        headers = self._get_twitter_oauth_header(
            tweets_endpoint_url, params=params, method="GET"
        )
        result = self.env["ir.egress"].request(
            "GET",
            tweets_endpoint_url,
            purpose="social_twitter",
            headers=headers,
            timeout=10,
            params=params,
        )

        if isinstance(result.json(), dict) and result.json().get("errors"):
            self._action_disconnect_accounts(result.json())
            return False

        last_tweets_stats = {"engagement": 0, "stories": 0}
        for tweet in result.json().get("data", []):
            public_metrics = tweet.get("public_metrics", {})
            last_tweets_stats["engagement"] += public_metrics.get("like_count", 0)
            last_tweets_stats["stories"] += public_metrics.get("retweet_count", 0)
        return last_tweets_stats

    def _get_twitter_oauth_header(self, url, headers=None, params=None, method="POST"):
        self.check_singleton()
        headers = dict(headers or {})
        params = {} if params is None else params
        headers.update(
            {
                "oauth_token": self.twitter_oauth_token,
                "oauth_token_secret": self.twitter_oauth_token_secret,
            }
        )
        return self.media_id._get_twitter_oauth_header(
            url, headers=headers, params=params, method=method
        )

    def _format_attachments_to_images_twitter(self, image_ids):
        return self._format_images_twitter(
            [
                {
                    "bytes": base64.decodebytes(image.datas),
                    "file_size": image.file_size,
                    "mimetype": image.mimetype,
                }
                for image in image_ids
            ]
        )

    def _format_images_twitter(self, image_ids):

        self.check_singleton()

        if not image_ids:
            return False

        media_ids = []
        for image in image_ids:
            media_id = self._init_twitter_upload(image)
            self._process_twitter_upload(image, media_id)
            self._finish_twitter_upload(media_id)
            media_ids.append(media_id)

        return media_ids

    def _init_twitter_upload(self, image):
        data = {
            "total_bytes": image["file_size"],
            "media_category": "tweet_gif"
            if image["mimetype"] == "image/gif"
            else "tweet_image",
            "media_type": image["mimetype"],
        }
        url_endpoint = f"{TWITTER_IMAGES_UPLOAD_ENDPOINT}/initialize"
        headers = self._get_twitter_oauth_header(url_endpoint)
        result = self.env["ir.egress"].request(
            "POST",
            url_endpoint,
            purpose="social_twitter",
            json=data,
            headers=headers,
            timeout=5,
        )
        if not result.ok:
            generic_api_error = result.json().get("error", "")
            raise UserError(
                self.env._(
                    "We could not upload your image, it may be corrupted, it may exceed size limit or API may have send improper response (error: %s).",
                    generic_api_error,
                )
            )

        return result.json().get("data").get("id")

    def _process_twitter_upload(self, image, media_id) -> None:
        files = {"media": image["bytes"]}
        data = {"segment_index": 0}
        url_endpoint = f"{TWITTER_IMAGES_UPLOAD_ENDPOINT}/{media_id}/append"
        headers = self._get_twitter_oauth_header(url_endpoint)
        self.env["ir.egress"].request(
            "POST",
            url_endpoint,
            purpose="social_twitter",
            files=files,
            data=data,
            headers=headers,
            timeout=15,
        )

    def _finish_twitter_upload(self, media_id) -> None:
        url_endpoint = f"{TWITTER_IMAGES_UPLOAD_ENDPOINT}/{media_id}/finalize"
        headers = self._get_twitter_oauth_header(url_endpoint)
        self.env["ir.egress"].request(
            "POST", url_endpoint, purpose="social_twitter", headers=headers, timeout=5
        )
