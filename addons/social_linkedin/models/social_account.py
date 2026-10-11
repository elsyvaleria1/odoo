import base64
import logging
from datetime import datetime, timedelta
from urllib.parse import quote

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.web import urljoin as url_join

from odoo.addons.social.controllers.main import SocialValidationException
from odoo.addons.social_linkedin.utils import id_to_urn, urn_to_id

_logger = logging.getLogger(__name__)


class SocialAccount(models.Model):
    _inherit = "social.account"
    _CREDENTIAL_FIELDS = {
        "linkedin_access_token": "linkedin_access_token",
    }

    linkedin_account_urn = fields.Char(
        string="LinkedIn Account URN",
        readonly=True,
        help="LinkedIn Account URN",
    )
    linkedin_account_id = fields.Char(
        string="LinkedIn Account ID",
        compute="_compute_linkedin_account_id",
    )
    linkedin_access_token = fields.Char(
        string="LinkedIn access token",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        readonly=True,
        help="The access token is used to perform request to the REST API",
    )

    @api.depends("linkedin_account_urn")
    def _compute_linkedin_account_id(self) -> None:
        for social_account in self:
            if social_account.linkedin_account_urn:
                social_account.linkedin_account_id = urn_to_id(
                    social_account.linkedin_account_urn
                )
            else:
                social_account.linkedin_account_id = False

    def _compute_stats_link(self) -> None:
        linkedin_accounts = self._filtered_by_media_types(["linkedin"])
        super(SocialAccount, (self - linkedin_accounts))._compute_stats_link()

        for account in linkedin_accounts:
            account.stats_link = (
                "https://www.linkedin.com/company/%s/admin/analytics/visitors/"
                % account.linkedin_account_id
            )

    def _update_statistics(self):
        linkedin_accounts = self._filtered_by_media_types(["linkedin"])
        super(SocialAccount, (self - linkedin_accounts))._update_statistics()

        for account in linkedin_accounts:
            all_stats_dict = account._get_statistics_linkedin()
            month_stats_dict = account._get_statistics_linkedin(last_30d=True)
            for stat_name in list(all_stats_dict.keys()):
                all_stats_dict["%s_trend" % stat_name] = self._compute_trend(
                    all_stats_dict.get(stat_name, 0), month_stats_dict.get(stat_name, 0)
                )
            account.write(all_stats_dict)

    def _linkedin_get_followers_count(self):
        self.check_singleton()
        endpoint = url_join(
            self.env["social.media"]._LINKEDIN_ENDPOINT,
            "networkSizes/urn:li:organization:%s" % self.linkedin_account_id,
        )
        headers = self._linkedin_bearer_headers()
        headers.pop("X-Restli-Protocol-Version", None)
        response = self.env["ir.egress"].request(
            "GET",
            endpoint,
            purpose="social_linkedin",
            params={"edgeType": "COMPANY_FOLLOWED_BY_MEMBER"},
            headers=headers,
            timeout=3,
        )
        if response.status_code != 200:
            return 0
        return response.json().get("firstDegreeSize", 0)

    def _get_statistics_linkedin(self, last_30d=False) -> dict:
        self.check_singleton()

        endpoint = url_join(
            self.env["social.media"]._LINKEDIN_ENDPOINT,
            "organizationalEntityShareStatistics",
        )
        params = {
            "q": "organizationalEntity",
            "organizationalEntity": self.linkedin_account_urn,
        }

        if last_30d:
            end = int((datetime.now() + timedelta(days=2)).timestamp() * 1000)
            start = int((datetime.now() - timedelta(days=30)).timestamp() * 1000)
            endpoint += (
                "?timeIntervals=%s"
                % "(timeRange:(start:%i,end:%i),timeGranularityType:MONTH)"
                % (start, end)
            )

        response = self.env["ir.egress"].request(
            "GET",
            endpoint,
            purpose="social_linkedin",
            params=params,
            headers=self._linkedin_bearer_headers(),
            timeout=5,
        )

        if response.status_code != 200:
            return {}

        data = response.json().get("elements", [{}])[0].get("totalShareStatistics", {})

        return {
            "audience": self._linkedin_get_followers_count(),
            "engagement": data.get("clickCount", 0)
            + data.get("likeCount", 0)
            + data.get("commentCount", 0),
            "stories": data.get("shareCount", 0) + data.get("shareMentionsCount", 0),
        }

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)

        linkedin_accounts = res.filtered(
            lambda account: account.media_type == "linkedin"
        )
        if linkedin_accounts:
            linkedin_accounts._create_default_stream_linkedin()

        return res

    def _linkedin_bearer_headers(self, linkedin_access_token=None) -> dict:
        if linkedin_access_token is None:
            linkedin_access_token = self.linkedin_access_token
        return {
            "Authorization": "Bearer %s" % linkedin_access_token,
            "cache-control": "no-cache",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202511",
        }

    def _get_linkedin_accounts(self, linkedin_access_token):
        response = self._linkedin_request(
            "organizationAcls",
            params={
                "q": "roleAssignee",
                "role": "ADMINISTRATOR",
                "state": "APPROVED",
            },
            linkedin_access_token=linkedin_access_token,
        )
        if not response.ok:
            raise SocialValidationException(
                self.env._(
                    "An error occurred when fetching your pages: “%s”.", response.text
                )
            )

        account_ids = [
            urn_to_id(organization["organization"])
            for organization in response.json().get("elements", [])
        ]

        response = self._linkedin_request(
            "organizations",
            object_ids=account_ids,
            fields=("id", "name", "localizedName", "vanityName", "logoV2:(original)"),
            linkedin_access_token=linkedin_access_token,
        )
        if not response.ok:
            raise SocialValidationException(
                self.env._(
                    "An error occurred when fetching your pages data: “%s”.",
                    response.text,
                )
            )

        organization_results = response.json().get("results", {})

        images_urns = [
            values.get("logoV2", {}).get("original")
            for values in organization_results.values()
        ]
        image_url_by_id = self._linkedin_request_images(
            images_urns, linkedin_access_token
        )

        accounts = []
        for account_id, organization in organization_results.items():
            image_id = urn_to_id(organization.get("logoV2", {}).get("original"))
            image_url = image_id and image_url_by_id.get(image_id)
            image_data = (
                image_url
                and self.env["ir.egress"]
                .request("GET", image_url, purpose="social_linkedin", timeout=10)
                .content
            )
            accounts.append(
                {
                    "name": organization.get("localizedName"),
                    "linkedin_account_urn": f"urn:li:organization:{account_id}",
                    "linkedin_access_token": linkedin_access_token,
                    "social_account_handle": organization.get("vanityName"),
                    "image": base64.b64encode(image_data) if image_data else False,
                }
            )

        return accounts

    def _create_linkedin_accounts(self, access_token, media) -> None:
        linkedin_accounts = self._get_linkedin_accounts(access_token)
        if not linkedin_accounts:
            message = self.env._(
                "You need a Business Account to post on LinkedIn with Odoo Social.\n Please create one and make sure it is linked to your account"
            )
            documentation_link = (
                "https://business.linkedin.com/marketing-solutions/linkedin-pages"
            )
            documentation_link_label = self.env._("Read More about Business Accounts")
            documentation_link_icon_class = "fa-brands fa-linkedin-in"
            raise SocialValidationException(
                message,
                documentation_link,
                documentation_link_label,
                documentation_link_icon_class,
            )

        social_accounts = (
            self.sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("media_id", "=", media.id),
                    (
                        "linkedin_account_urn",
                        "in",
                        [l.get("linkedin_account_urn") for l in linkedin_accounts],
                    ),
                ]
            )
        )

        error_message = social_accounts._get_multi_company_error_message()
        if error_message:
            raise SocialValidationException(error_message)

        existing_accounts = {
            account.linkedin_account_urn: account
            for account in social_accounts
            if account.linkedin_account_urn
        }

        accounts_to_create = []
        for account in linkedin_accounts:
            if account["linkedin_account_urn"] in existing_accounts:
                existing_accounts[account["linkedin_account_urn"]].write(
                    {
                        "active": True,
                        "linkedin_access_token": account.get("linkedin_access_token"),
                        "social_account_handle": account.get("username"),
                        "is_media_disconnected": False,
                        "image": account.get("image"),
                    }
                )
            else:
                account.update(
                    {
                        "media_id": media.id,
                        "is_media_disconnected": False,
                        "has_trends": True,
                        "has_account_stats": True,
                    }
                )
                accounts_to_create.append(account)

        self.create(accounts_to_create)

    def _create_default_stream_linkedin(self) -> None:
        page_posts_stream_type = self.env.ref(
            "social_linkedin.stream_type_linkedin_company_post"
        )

        streams_to_create = [
            {
                "media_id": account.media_id.id,
                "stream_type_id": page_posts_stream_type.id,
                "account_id": account.id,
            }
            for account in self
            if account.linkedin_account_urn
        ]

        if streams_to_create:
            self.env["social.stream"].create(streams_to_create)


    def _linkedin_request(
        self,
        endpoint,
        params=None,
        linkedin_access_token=None,
        object_ids=None,
        complex_object_ids=None,
        fields=None,
        method=None,
        json=None,
        session=None,
        headers=None,
    ):
        if not linkedin_access_token:
            self.check_singleton()

        if method is None:
            method = "POST" if json else "GET"

        url = url_join(self.env["social.media"]._LINKEDIN_ENDPOINT, endpoint)

        get_params = []
        if object_ids:
            get_params.append("ids=List(%s)" % ",".join(map(quote, object_ids)))
        if complex_object_ids:
            urns = ",".join(
                "("
                + ",".join(f"{name}:{quote(urn)}" for name, urn in obj.items())
                + ")"
                for obj in complex_object_ids
            )
            get_params.append(f"ids=List({urns})")
        if fields:
            get_params.append("fields=%s" % ",".join(fields))
        if get_params:
            url += "?" + "&".join(get_params)

        headers = headers or {}
        headers.update(self._linkedin_bearer_headers(linkedin_access_token))

        return (session or requests).request(
            method,
            url,
            params=params,
            json=json,
            headers=headers,
            timeout=5,
        )

    def _linkedin_request_images(self, images_ids, linkedin_access_token=None):
        images_urns = [
            id_to_urn(image_id, "li:image") for image_id in images_ids if image_id
        ]
        if not images_urns:
            return {}
        response = self._linkedin_request(
            "images",
            object_ids=images_urns,
            fields=("downloadUrl",),
            linkedin_access_token=linkedin_access_token,
        )
        return (
            {
                urn_to_id(image_urn): image_values["downloadUrl"]
                for image_urn, image_values in response.json()
                .get("results", {})
                .items()
            }
            if response.ok
            else {}
        )

    def _linkedin_upload_image(self, image_data):
        self.check_singleton()
        data = {
            "initializeUploadRequest": {
                "owner": self.linkedin_account_urn,
            },
        }
        response = self.env["ir.egress"].request(
            "POST",
            url_join(
                self.env["social.media"]._LINKEDIN_ENDPOINT,
                "images?action=initializeUpload",
            ),
            purpose="social_linkedin",
            headers=self._linkedin_bearer_headers(),
            json=data,
            timeout=10,
        )

        if not response.ok:
            _logger.error("Could not upload the image: %r.", response.text)

        response = response.json()
        if "value" not in response or "uploadUrl" not in response["value"]:
            raise UserError(
                self.env._(
                    "We could not upload your image, try reducing its size and posting it again (error: Failed during upload registering)."
                )
            )

        upload_url = response["value"]["uploadUrl"]
        image_urn = response["value"]["image"]

        headers = self._linkedin_bearer_headers()
        headers["Content-Type"] = "application/octet-stream"

        response = self.env["ir.egress"].request(
            "POST",
            upload_url,
            purpose="social_linkedin",
            data=image_data,
            headers=headers,
            timeout=15,
        )

        if not response.ok:
            raise UserError(
                self.env._(
                    "We could not upload your image, try reducing its size and posting it again."
                )
            )

        return image_urn
