from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.libs.web import urljoin as url_join


class SocialAccount(models.Model):
    _inherit = "social.account"
    _CREDENTIAL_FIELDS = {
        "instagram_access_token": "instagram_access_token",
    }

    instagram_account_id = fields.Char(
        string="Instagram Account ID",
        readonly=True,
        help="Instagram Account ID provided by the Facebook API, this should never be set manually.",
    )
    instagram_facebook_account_id = fields.Char(
        string="Instagram Facebook Account ID",
        readonly=True,
        help="""Facebook Account ID provided by the Facebook API, this should never be set manually.
        The Instagram ("Professional") account is always linked to a Facebook account.""",
    )
    instagram_access_token = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        readonly=True,
        help="""Instagram Access Token provided by the Facebook API, this should never be set manually.
        It's used to authenticate requests when posting to or reading information from this account.""",
    )

    def _compute_stats_link(self) -> None:
        instagram_accounts = self._filtered_by_media_types(["instagram"])

        super(SocialAccount, (self - instagram_accounts))._compute_stats_link()

        for account in instagram_accounts:
            account.stats_link = False

    def _update_statistics(self):
        instagram_accounts = self._filtered_by_media_types(["instagram"])

        super(SocialAccount, (self - instagram_accounts))._update_statistics()

        for account in instagram_accounts:
            insights_endpoint_url = url_join(
                self.env["social.media"]._INSTAGRAM_ENDPOINT,
                "/v17.0/%s/insights" % account.instagram_account_id,
            )
            statistics_30d = account._get_statistics_instagram(insights_endpoint_url)
            statistics_360d = account._get_statistics_instagram_360d(
                insights_endpoint_url
            )

            account_global_stats = self.env["ir.egress"].request(
                "GET",
                url_join(
                    self.env["social.media"]._INSTAGRAM_ENDPOINT,
                    "/v17.0/%s" % account.instagram_account_id,
                ),
                purpose="social_instagram",
                params={
                    "fields": "followers_count",
                    "access_token": account.instagram_access_token,
                },
                timeout=5,
            )

            audience = account_global_stats.json().get("followers_count", 0)
            account.write(
                {
                    "audience": audience,
                    "audience_trend": self._compute_trend(
                        audience, statistics_30d.get("follower_count", 0)
                    ),
                    "engagement": statistics_360d.get("reach", 0),
                    "engagement_trend": self._compute_trend(
                        statistics_360d.get("reach", 0), statistics_30d.get("reach", 0)
                    ),
                }
            )

    def _get_statistics_instagram_360d(self, insights_endpoint_url):

        total_statistics = {"reach": 0, "follower_count": 0}
        for index in range(12):
            until = datetime.now() - relativedelta(days=(index * 30))
            since = until - relativedelta(days=30)
            statistics_30d = self._get_statistics_instagram(
                insights_endpoint_url,
                since=int(since.timestamp()),
                until=int(until.timestamp()),
            )
            total_statistics["reach"] += statistics_30d.get("reach", 0)
            total_statistics["follower_count"] += statistics_30d.get(
                "follower_count", 0
            )

        return total_statistics

    def _get_statistics_instagram(
        self, endpoint_url, date_preset="last_30d", since=None, until=None
    ):
        params = {
            "metric": "reach,follower_count",
            "period": "day",
            "access_token": self.instagram_access_token,
        }

        if since and until:
            params["since"] = since
            params["until"] = until
        else:
            params["date_preset"] = date_preset

        response = self.env["ir.egress"].request(
            "GET", endpoint_url, purpose="social_instagram", params=params, timeout=5
        )

        statistics = {"follower_count": 0, "reach": 0}
        if not response.json().get("data"):
            return statistics

        json_data = response.json().get("data")
        for metric in json_data:
            total_value = 0
            metric_values = metric.get("values")
            for value in metric_values:
                total_value += value.get("value")

            metric_name = metric.get("name")
            statistics[metric_name] = total_value

        return statistics

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        res.filtered(
            lambda a: a.media_type == "instagram"
        )._create_default_stream_instagram()
        return res

    def _create_default_stream_instagram(self) -> None:
        stream_type_instagram_posts = self.env.ref(
            "social_instagram.stream_type_instagram_posts"
        )

        self.env["social.stream"].create(
            [
                {
                    "media_id": account.media_id.id,
                    "stream_type_id": stream_type_instagram_posts.id,
                    "account_id": account.id,
                }
                for account in self
            ]
        )
