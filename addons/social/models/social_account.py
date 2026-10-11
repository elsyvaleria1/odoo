import logging
from typing import Self

import requests

from odoo import api, fields, models
from odoo.http import request

_logger = logging.getLogger(__name__)


class SocialAccount(models.Model):
    """A social.account represents an actual account on the related social.media.
    Ex: A Facebook Page or a Twitter Account.

    These social.accounts will then be used to send generic social.posts to multiple social.accounts.
    They are also used to display a 'dashboard' of statistics on the 'Feed' view.

    Account statistic fields are 'computed' manually through the _update_statistics method
    that is overridden by each actual social module implementations (social_facebook, social_twitter, ...).
    The statistics computation is run manually when visualizing the Feed."""

    _name = "social.account"
    _inherit = ["mixin.credential.holder"]
    _description = "Social Account"
    _credential_holder_field = "account_credential_id"
    _credential_purpose = "social:account"

    account_credential_id = fields.Many2one(
        comodel_name="credential.credential",
        string="Credential",
        copy=False,
        ondelete="restrict",
        groups="base.group_system",
        help="Holds this account's access tokens.",
    )

    def _default_company_id(self):
        if request and "social_company_id" in request.session:
            company_id = request.session["social_company_id"]
            if not company_id:
                return False
            if company_id in self.env.companies.ids:
                return company_id
        return self.env.company

    name = fields.Char(required=True)
    social_account_handle = fields.Char(
        string="Handle / Short Name",
        help="Contains the social media handle of the person that created this account. E.g: '@odoo.official' for the 'Odoo' X account",
    )
    active = fields.Boolean(default=True)
    media_id = fields.Many2one(
        comodel_name="social.media",
        string="Social Media",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
        help="Related Social Media (Facebook, X, ...).",
    )
    media_type = fields.Selection(related="media_id.media_type")
    stats_link = fields.Char(
        compute="_compute_stats_link",
        help="Link to the external Social Account statistics",
    )
    image = fields.Image(
        max_width=128,
        max_height=128,
        readonly=True,
    )
    is_media_disconnected = fields.Boolean(
        string="Link with external Social Media is broken"
    )

    audience = fields.Integer(
        readonly=True,
        help="General audience of the Social Account (Page Likes, Account Follows, ...).",
    )
    audience_trend = fields.Float(
        digits=(3, 0),
        readonly=True,
        help="Percentage of increase/decrease of the audience over a defined period.",
    )
    engagement = fields.Integer(
        readonly=True,
        help="Number of people engagements with your posts (Likes, Comments, ...).",
    )
    engagement_trend = fields.Float(
        digits=(3, 0),
        readonly=True,
        help="Percentage of increase/decrease of the engagement over a defined period.",
    )
    stories = fields.Integer(
        readonly=True,
        help="Number of stories created from your posts (Shares, Reposts, ...).",
    )
    stories_trend = fields.Float(
        digits=(3, 0),
        readonly=True,
        help="Percentage of increase/decrease of the stories over a defined period.",
    )
    has_trends = fields.Boolean(
        string="Has Trends?",
        help="Defines whether this account has statistics tends or not.",
    )
    has_account_stats = fields.Boolean(
        default=True,
        help="""Defines whether this account has Audience/Engagements/Stories stats.
        Account with stats are displayed on the dashboard.""",
    )
    utm_medium_id = fields.Many2one(
        comodel_name="utm.medium",
        string="UTM Medium",
        required=True,
        ondelete="restrict",
        help="Every time an account is created, a utm.medium is also created and linked to the account",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self._default_company_id(),
        domain=lambda self: [("id", "in", self.env.companies.ids)],
        help="Link an account to a company to restrict its usage or keep empty to let all companies use it.",
    )

    def _update_statistics(self):
        pass

    def _compute_stats_link(self) -> None:
        for account in self:
            account.stats_link = False

    @api.depends("media_id")
    def _compute_display_name(self):
        for account in self:
            account.display_name = f"[{account.media_id.name}] {account.name or ''}"

    @api.model_create_multi
    def create(self, vals_list):

        if all(vals.get("media_id") and vals.get("name") for vals in vals_list):
            media_all = self.env["social.media"].search(
                [("id", "in", [vals.get("media_id") for vals in vals_list])]
            )
            media_names = {
                social_media.id: social_media.name for social_media in media_all
            }

            medium_all = self.env["utm.medium"].create(
                [
                    {
                        "name": "[%(media_name)s] %(account_name)s"
                        % {
                            "media_name": media_names.get(vals["media_id"]),
                            "account_name": vals["name"],
                        }
                    }
                    for vals in vals_list
                ]
            )

            for vals, medium in zip(vals_list, medium_all, strict=False):
                vals["utm_medium_id"] = medium.id

        res = super().create(vals_list)
        res._update_statistics()
        return res

    def write(self, vals):
        if vals.get("name"):
            for social_account in self.filtered(
                lambda social_account: social_account.utm_medium_id
            ):
                social_account.utm_medium_id.write(
                    {
                        "name": "[%(media_name)s] %(account_name)s"
                        % {
                            "media_name": social_account.media_id.name,
                            "account_name": vals["name"],
                        }
                    }
                )

        return super().write(vals)

    @api.model
    def refresh_statistics(self) -> list | None:
        all_accounts = (
            self.env["social.account"].search([("has_account_stats", "=", True)]).sudo()
        )
        try:
            all_accounts._update_statistics()
        except requests.exceptions.ConnectionError, requests.exceptions.Timeout:
            _logger.warning(
                "Failed to refresh social account statistics.", exc_info=True
            )
        return [
            {
                "id": account.id,
                "name": account.name,
                "is_media_disconnected": account.is_media_disconnected,
                "audience": account.audience,
                "audience_trend": account.audience_trend,
                "engagement": account.engagement,
                "engagement_trend": account.engagement_trend,
                "stories": account.stories,
                "stories_trend": account.stories_trend,
                "has_trends": account.has_trends,
                "media_id": [account.media_id.id],
                "media_type": account.media_id.media_type,
                "stats_link": account.stats_link,
            }
            for account in all_accounts
        ]

    def _compute_trend(self, value, delta_30d):
        return (
            0.0 if value - delta_30d <= 0 else (delta_30d / (value - delta_30d)) * 100
        )

    def _filtered_by_media_types(self, media_types) -> Self:
        return self.filtered(lambda account: account.media_type in media_types)

    def _get_multi_company_error_message(self) -> str | None:
        if not self.env.user.has_group("base.group_multi_company"):
            return None

        allowed_company_ids = set(self.env["ir.http"]._get_cookie_company_ids()) or {
            self.env.company.id
        }

        accounts_other_companies = self.filtered(
            lambda account: (
                account.company_id and account.company_id.id not in allowed_company_ids
            )
        )

        if accounts_other_companies:
            return self.env._(
                "Create other accounts for %(media_names)s for this company or ask %(company_names)s to share their accounts",
                media_names=", ".join(accounts_other_companies.mapped("media_id.name")),
                company_names=", ".join(
                    accounts_other_companies.mapped("company_id.name")
                ),
            )
        return None

    def _action_disconnect_accounts(self, disconnection_info=None) -> None:
        _logger.warning(
            "Social account disconnected: %s. Reason: %s",
            ", ".join(self.mapped("display_name")),
            disconnection_info or "Not provided",
            stack_info=True,
        )
        self.sudo().write({"is_media_disconnected": True})
