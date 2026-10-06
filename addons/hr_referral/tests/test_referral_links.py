from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.libs.web import urljoin as url_join
from odoo.tests import HttpCase, tagged

from .common import TestHrReferralBase


@tagged("post_install", "-at_install")
class TestReferralLinks(TestHrReferralBase, HttpCase):
    def test_create_referral_url_creates_wizard_and_reuses_tracking_link(self):
        wizards = self.env["wizard.hr.job.share.referral.link"]
        domain = [("job_id", "=", self.job_dev.id), ("channel", "=", "direct")]
        before = wizards.search_count(domain)
        first = self.job_dev.create_referral_url("direct")
        self.assertIsInstance(first, str)
        self.assertTrue(first)
        self.assertEqual(wizards.search_count(domain), before + 1)
        second = self.job_dev.create_referral_url("direct")
        self.assertEqual(second, first)
        self.assertEqual(wizards.search_count(domain), before + 2)

    def test_campaign_content_is_read_only_and_send_publishes(self):
        self.richard_user.email = "richard@example.test"
        self.env["hr.employee"].create(
            {
                "name": "Richard Employee",
                "company_id": self.company_1.id,
                "user_id": self.richard_user.id,
                "work_email": "richard@example.test",
            }
        )
        wizard = (
            self.env["wizard.hr.job.send.referral.request"]
            .with_company(self.company_1)
            .create({"job_id": self.job_dev.id})
        )
        user = self.richard_user.with_env(wizard.env)
        self.job_dev.is_published = False
        rows = wizard._prepare_personalized_content(user, {user: "provided-link"})
        self.assertEqual(rows[0]["job_url"], "provided-link")
        self.assertEqual(rows[0]["employee_name"], "Richard Employee")
        self.assertFalse(self.job_dev.is_published)
        self.assertFalse(self.job_dev.utm_campaign_id)
        with patch.object(
            type(wizard), "_get_employees", return_value=user.employee_id
        ):
            result = wizard.action_send()
        self.assertEqual(result, {"type": "ir.actions.act_window_close"})
        self.assertTrue(self.job_dev.is_published)
        self.assertTrue(self.job_dev.utm_campaign_id)
        mails = self.env["mail.mail"].search([("subject", "=", wizard.mail_subject)])
        self.assertEqual(len(mails), 1)
        self.assertIn("Richard Employee", str(mails.body_html))
        self.assertNotIn("[job_url]", str(mails.body_html))

    def test_empty_campaign_does_not_publish(self):
        wizard = self.env["wizard.hr.job.send.referral.request"].create(
            {"job_id": self.job_dev.id}
        )
        self.job_dev.is_published = False
        with patch.object(
            type(wizard), "_get_employees", return_value=self.env["hr.employee"]
        ):
            with self.assertRaises(UserError):
                wizard.action_send()
        self.assertFalse(self.job_dev.is_published)
        self.assertFalse(self.job_dev.utm_campaign_id)

    def test_search_or_create_referral_links(self):
        """
        Test the search_or_create_referral_links method of the hr.job model

        This method will test the uniqueness of each link between users and
        between channel. Finally, it will test if no new link have
        been created after the second call of the method.
        """

        users = self.env["res.users"].search([])
        job = self.env["hr.job"].create(
            {
                "name": "test_search_or_create_referral_links",
                "no_of_recruitment": "5",
                "is_published": True,
                "department_id": self.dep_rd.id,
                "company_id": self.company_1.id,
            }
        )

        links_by_user_by_channel = {}
        links = []
        for channel in ["direct", "facebook", "twitter", "linkedin"]:
            # check the uniqueness of the links between users
            channel_links = job.search_or_create_referral_links(users, channel)
            set_links = set(channel_links.values())
            self.assertEqual(
                len(channel_links),
                len(set_links),
                "There are duplicated links between users",
            )
            check_already_created = job.search_or_create_referral_links(users, channel)
            # check the consistency of the links
            for user, link in channel_links.items():
                self.assertEqual(
                    link, check_already_created[user], "The link is not the same"
                )
            links_by_user_by_channel[channel] = channel_links
            links += links_by_user_by_channel[channel].values()
        # check the uniqueness of the links between channel
        all_links_set = set(links)
        self.assertEqual(
            len(links), len(all_links_set), "There are duplicated links between channel"
        )
        # check if no new link have been created
        job_url = url_join(job.get_base_url(), (job.website_url or "/jobs"))
        trackers = self.env["link.tracker"].search(
            [("url", "=", job_url), ("campaign_id", "=", job.utm_campaign_id.id)]
        )
        self.assertEqual(
            len(trackers), len(all_links_set), "There are new links created"
        )

    def test_referral_campaign_tour(self):
        job = self.env["hr.job"].create(
            {
                "name": "Test Job Referral Campaign",
                "no_of_recruitment": "5",
                "company_id": self.company_1.id,
                "is_published": True,
            }
        )
        self.env["hr.employee"].create(
            [
                {
                    "name": "Steve employee",
                    "company_id": self.company_1.id,
                    "user_id": self.steve_user.id,
                },
                {
                    "name": "Richard employee",
                    "company_id": self.company_1.id,
                    "user_id": self.richard_user.id,
                },
                {
                    "name": "Employee without user",
                    "company_id": self.company_1.id,
                },
            ]
        )
        self.steve_user.email = "steve.employee@company_test.com"
        self.richard_user.email = "richard.employee@company_test.com"
        self.steve_user.group_ids += self.env.ref(
            "hr_recruitment.group_hr_recruitment_manager"
        )

        self.assertFalse(job.utm_campaign_id)
        self.steve_user.write(
            {
                "company_ids": [(4, self.company_1.id)],
                "company_id": self.company_1.id,
            }
        )
        self.start_tour("/odoo", "hr_referral_utm_campaign_tour", login="stv")

        self.assertTrue(job.utm_campaign_id.id)
        nb_trackers = self.env["link.tracker"].search_count(
            [("campaign_id", "=", job.utm_campaign_id.id)]
        )
        nb_employee_with_user = self.env["hr.employee"].search_count(
            [("user_id", "!=", False), ("company_id", "=", self.company_1.id)]
        )
        self.assertEqual(nb_trackers, nb_employee_with_user)
