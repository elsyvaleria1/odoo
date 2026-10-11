import logging
from datetime import datetime

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.libs.web import urljoin as url_join

_logger = logging.getLogger(__name__)


class SocialAccount(models.Model):
    _inherit = "social.account"
    _CREDENTIAL_FIELDS = {
        "facebook_access_token": "facebook_access_token",
    }

    facebook_account_id = fields.Char(
        string="Facebook Account ID",
        readonly=True,
        help="Facebook Page ID provided by the Facebook API, this should never be set manually.",
    )
    facebook_access_token = fields.Char(
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        readonly=True,
        help="""Facebook Page Access Token provided by the Facebook API, this should never be set manually.
            It's used to authenticate requests when posting to or reading information from this account.""",
    )

    def _compute_stats_link(self) -> None:
        facebook_accounts = self._filtered_by_media_types(["facebook"])
        super(SocialAccount, (self - facebook_accounts))._compute_stats_link()

        for account in facebook_accounts:
            account.stats_link = (
                "https://www.facebook.com/%s/insights" % account.facebook_account_id
                if account.facebook_account_id
                else False
            )

    def _update_statistics(self):

        facebook_accounts = self._filtered_by_media_types(["facebook"])
        super(SocialAccount, (self - facebook_accounts))._update_statistics()

        for account in facebook_accounts.filtered("facebook_account_id"):
            insights_endpoint_url = url_join(
                self.env["social.media"]._FACEBOOK_ENDPOINT_VERSIONED,
                "%s/insights" % account.facebook_account_id,
            )
            statistics_30d = account._compute_statistics_facebook(insights_endpoint_url)
            statistics_360d = account._get_statistics_facebook_360d(
                insights_endpoint_url
            )

            page_global_stats = self.env["ir.egress"].request(
                "GET",
                url_join(
                    self.env["social.media"]._FACEBOOK_ENDPOINT_VERSIONED,
                    account.facebook_account_id,
                ),
                purpose="social_facebook",
                params={
                    "fields": "fan_count",
                    "access_token": account.facebook_access_token,
                },
                timeout=5,
            )

            account.write(
                {
                    "audience": page_global_stats.json().get("fan_count"),
                    "audience_trend": self._compute_trend(
                        account.audience, statistics_30d["page_fans"]
                    ),
                    "engagement": statistics_360d["page_post_engagements"],
                    "engagement_trend": self._compute_trend(
                        account.engagement, statistics_30d["page_post_engagements"]
                    ),
                }
            )

    def _get_statistics_facebook_360d(self, insights_endpoint_url):

        total_statistics = {"page_post_engagements": 0, "page_fans": 0}
        for i in range(4):
            until = datetime.now() - relativedelta(days=(i * 90))
            since = until - relativedelta(days=90)
            statistics_90d = self._compute_statistics_facebook(
                insights_endpoint_url,
                since=int(since.timestamp()),
                until=int(until.timestamp()),
            )
            total_statistics["page_post_engagements"] += statistics_90d[
                "page_post_engagements"
            ]
            total_statistics["page_fans"] += statistics_90d["page_fans"]

        return total_statistics

    def _compute_statistics_facebook(
        self, endpoint_url, date_preset="last_30d", since=None, until=None
    ):

        params = {
            "metric": "page_post_engagements,page_follows",
            "period": "day",
            "access_token": self.facebook_access_token,
        }

        if since and until:
            params["since"] = since
            params["until"] = until
        else:
            params["date_preset"] = date_preset

        response = self.env["ir.egress"].request(
            "GET", endpoint_url, purpose="social_facebook", params=params, timeout=5
        )

        statistics = {"page_fans": 0, "page_post_engagements": 0}
        if not response.json().get("data"):
            _logger.warning(
                "Social Facebook: Failed to retrieve page statistics: %s.",
                response.text,
            )
            return statistics

        json_data = response.json().get("data")
        page_follows = {}
        for metric in json_data:
            metric_name = metric.get("name")
            values = metric.get("values") or []
            if metric_name == "page_post_engagements":
                statistics["page_post_engagements"] += sum(
                    v.get("value", 0) for v in values
                )
            elif metric_name == "page_follows":
                page_follows.update(
                    {
                        v["end_time"]: v["value"]
                        for v in values
                        if "end_time" in v and "value" in v
                    }
                )

        if page_follows:
            statistics["page_fans"] = (
                page_follows[max(page_follows)] - page_follows[min(page_follows)]
            )

        return statistics

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        res.filtered(
            lambda account: account.media_type == "facebook"
        )._create_default_stream_facebook()
        return res

    def _create_default_stream_facebook(self) -> None:

        if not self:
            return

        page_posts_stream_type = self.env.ref("social_facebook.stream_type_page_posts")
        streams_to_create = [
            {
                "media_id": account.media_id.id,
                "stream_type_id": page_posts_stream_type.id,
                "account_id": account.id,
            }
            for account in self
        ]
        self.env["social.stream"].create(streams_to_create)
