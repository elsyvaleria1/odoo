from odoo import fields, models


class HrJob(models.Model):
    _inherit = "hr.job"

    utm_campaign_id = fields.Many2one(
        comodel_name="utm.campaign",
        string="Campaign",
        ondelete="restrict",
    )
    max_points = fields.Integer(compute="_compute_max_points")
    direct_clicks = fields.Integer(compute="_compute_clicks")
    facebook_clicks = fields.Integer(compute="_compute_clicks")
    twitter_clicks = fields.Integer(
        string="X Clicks",
        compute="_compute_clicks",
    )
    linkedin_clicks = fields.Integer(compute="_compute_clicks")

    def _compute_clicks(self) -> None:
        if self.env.user.utm_source_id:
            grouped_data = self.env["link.tracker"]._read_group(
                [
                    ("source_id", "=", self.env.user.utm_source_id.id),
                    ("campaign_id", "in", self.mapped("utm_campaign_id").ids),
                    ("medium_id", "!=", False),
                ],
                ["campaign_id", "medium_id"],
                ["count:sum"],
            )
        else:
            grouped_data = {}
        medium_direct = self.env.ref("utm.utm_medium_direct", raise_if_not_found=False)
        medium_facebook = self.env.ref(
            "utm.utm_medium_facebook", raise_if_not_found=False
        )
        medium_twitter = self.env.ref(
            "utm.utm_medium_twitter", raise_if_not_found=False
        )
        medium_linkedin = self.env.ref(
            "utm.utm_medium_linkedin", raise_if_not_found=False
        )
        mapped_data = {job.utm_campaign_id.id: {} for job in self}
        for campaign, medium, count in grouped_data:
            mapped_data[campaign.id][medium.id] = count
        for job in self:
            data = mapped_data[job.utm_campaign_id.id]
            job.direct_clicks = data.get(medium_direct.id, 0) if medium_direct else 0
            job.facebook_clicks = (
                data.get(medium_facebook.id, 0) if medium_facebook else 0
            )
            job.twitter_clicks = data.get(medium_twitter.id, 0) if medium_twitter else 0
            job.linkedin_clicks = (
                data.get(medium_linkedin.id, 0) if medium_linkedin else 0
            )

    def _compute_max_points(self) -> None:
        for job in self:
            stages = self.env["hr.recruitment.stage"].search(
                [
                    ("use_in_referral", "=", True),
                    "|",
                    ("job_ids", "=", False),
                    ("job_ids", "=", job.id),
                ]
            )
            job.max_points = sum(stages.mapped("points"))

    def search_or_create_referral_links(self, users=None, channel="direct"):

        self.check_singleton()
        chanel_to_medium = {
            "direct": "utm.utm_medium_direct",
            "facebook": "utm.utm_medium_facebook",
            "twitter": "utm.utm_medium_twitter",
            "linkedin": "utm.utm_medium_linkedin",
        }
        if channel not in chanel_to_medium:
            return {}
        medium = self.env.ref(chanel_to_medium[channel], raise_if_not_found=False)
        if not medium:
            return {}
        if users is None:
            users = self.env.user
        elif not users:
            return {}
        users._create_missing_utm_source()
        if not self.utm_campaign_id:
            self.utm_campaign_id = self.env["utm.campaign"].create(
                [{"name": self.name}]
            )

        referral_links_by_user = {}
        trackers = self.env["link.tracker"].search(
            [
                ("url", "=", self.full_url),
                ("campaign_id", "=", self.utm_campaign_id.id),
                ("medium_id", "=", medium.id),
                ("source_id", "in", users.utm_source_id.ids),
            ]
        )
        trackers_by_source_id = {tracker.source_id: tracker for tracker in trackers}
        trackers_to_create = []
        user_without_tracker = []
        for user in users:
            tracker = trackers_by_source_id.get(user.utm_source_id)
            if tracker:
                referral_links_by_user[user] = tracker.short_url
            else:
                user_without_tracker.append(user)
                trackers_to_create.append(
                    {
                        "url": self.full_url,
                        "title": self.env._(
                            "Referral %(user)s: %(job_url)s",
                            user=user,
                            job_url=self.full_url,
                        ),
                        "campaign_id": self.utm_campaign_id.id,
                        "medium_id": medium.id,
                        "source_id": user.utm_source_id.id,
                    }
                )
        LinkTrackers = self.env["link.tracker"]
        if not LinkTrackers.has_access("create") and self.env.user.has_group(
            "hr_recruitment.group_hr_recruitment_manager"
        ):
            LinkTrackers = LinkTrackers.sudo()

        new_trackers = LinkTrackers.create(trackers_to_create)
        for tracker, user in zip(new_trackers, user_without_tracker, strict=True):
            referral_links_by_user[user] = tracker.short_url

        return referral_links_by_user

    def create_referral_url(self, channel: str) -> str:
        self.check_singleton()
        wizard = self.env["wizard.hr.job.share.referral.link"].create(
            {"job_id": self.id, "channel": channel}
        )
        return wizard.url

    def action_share_external(self) -> dict:
        self.check_singleton()
        wizard = self.env["wizard.hr.job.share.referral.link"].create(
            {"job_id": self.id}
        )
        return {
            "name": self.env._("Visit Webpage"),
            "type": "ir.actions.act_url",
            "url": wizard.url,
            "target": "new",
        }

    def action_referral_campaign(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Referral Campaign for %(job)s", job=self.name),
            "type": "ir.actions.act_window",
            "res_model": "wizard.hr.job.send.referral.request",
            "view_mode": "form",
            "target": "new",
        }
