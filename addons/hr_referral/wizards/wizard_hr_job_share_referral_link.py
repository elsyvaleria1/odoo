from odoo import api, fields, models
from odoo.libs.web import urljoin as url_join


class HrReferralLink(models.TransientModel):
    _name = "wizard.hr.job.share.referral.link"
    _description = "Referral Link To Share"

    job_id = fields.Many2one(
        comodel_name="hr.job",
        default=lambda self: self.env.context.get("active_id", None),
    )
    channel = fields.Selection(
        selection=[
            ("direct", "Link"),
            ("facebook", "Facebook"),
            ("twitter", "X"),
            ("linkedin", "Linkedin"),
        ],
        default="direct",
    )
    url = fields.Char(
        compute="_compute_url",
        compute_sudo=True,
        readonly=True,
    )

    @api.depends("channel")
    def _compute_url(self) -> None:
        channel_to_medium = {
            "direct": "utm.utm_medium_direct",
            "facebook": "utm.utm_medium_facebook",
            "twitter": "utm.utm_medium_twitter",
            "linkedin": "utm.utm_medium_linkedin",
        }

        if not self.env.user.utm_source_id:
            self.env.user.utm_source_id = (
                self.env["utm.source"]
                .create(
                    {
                        "name": self.env["utm.source"]._generate_name(
                            self.env.user, self.env.user.name
                        ),
                    }
                )
                .id
            )

        jobs_without_campaign = [
            wizard.job_id
            for wizard in self
            if wizard.job_id and not wizard.job_id.utm_campaign_id
        ]
        if jobs_without_campaign:
            utm_campaign = [
                {"name": self.env._("Referral: %(name)s", name=job.name)}
                for job in jobs_without_campaign
            ]
            utm_campaign_ids = self.env["utm.campaign"].create(utm_campaign).ids
            for utm_campaign_id, job in zip(
                utm_campaign_ids, jobs_without_campaign, strict=True
            ):
                job.utm_campaign_id = utm_campaign_id

        link_trackers_values = []
        for wizard in self:
            url = (
                url_join(self.get_base_url(), "/jobs")
                if not wizard.job_id
                else wizard.job_id.full_url
            )
            link_trackers_values.append(
                {
                    "title": self.env._("Referral: %(url)s", url=url),
                    "url": url,
                    "campaign_id": wizard.job_id.utm_campaign_id.id,
                    "source_id": wizard.env.user.utm_source_id.id,
                }
            )

            medium_reference = channel_to_medium.get(wizard.channel)
            medium = (
                self.env.ref(medium_reference, raise_if_not_found=False)
                if medium_reference
                else False
            )
            if medium:
                link_trackers_values[-1]["medium_id"] = medium.id

        link_trackers = self.env["link.tracker"].search_or_create(link_trackers_values)

        for wizard, link_tracker in zip(self, link_trackers, strict=True):
            if wizard.channel == "direct":
                wizard.url = link_tracker.short_url
            elif wizard.channel == "facebook":
                wizard.url = (
                    "https://www.facebook.com/sharer/sharer.php?u=%s"
                    % link_tracker.short_url
                )
            elif wizard.channel == "twitter":
                new_line_code = "%0A"
                hashtag_code = "%23"
                text_message = self.env._(
                    "🚀 An exciting opportunity for a %(job_name)s at my company. "
                    "If you're looking for a new challenge, check it out!👇%(new_line_code)s"
                    "🔗%(short_url)s%(new_line_code)s"
                    "%(hashtag_code)sHiring %(hashtag_code)sJobOpening %(hashtag_code)sCareerOpportunity",
                    job_name=self.job_id.name,
                    short_url=link_tracker.short_url,
                    new_line_code=new_line_code,
                    hashtag_code=hashtag_code,
                )
                wizard.url = f"https://twitter.com/intent/tweet?tw_p=tweetbutton&text={text_message}"
            elif wizard.channel == "linkedin":
                wizard.url = (
                    "https://www.linkedin.com/sharing/share-offsite?url=%s"
                    % link_tracker.short_url
                )
