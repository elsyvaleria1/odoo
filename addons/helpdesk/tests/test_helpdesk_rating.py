from datetime import date, datetime
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import Command, fields
from odoo.tests.common import HttpCase

from .common import HelpdeskCommon
from odoo.addons.mail.tests.common import MailCase, mail_new_test_user


class TestHelpdeskRating(HelpdeskCommon, HttpCase, MailCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_1 = cls.env["res.partner"].create(
            {
                "name": "Valid Lelitre",
                "email": "valid.lelitre@agrolait.com",
            }
        )
        cls.partner_1_user = mail_new_test_user(
            cls.env,
            name=cls.partner_1.name,
            login="partner_1",
            email=cls.partner_1.email,
            groups="base.group_portal",
        )

        # Enable rating feature
        cls.test_team.write({"helpdesk_use_rating": True})

        HelpdeskTicket = cls.env["helpdesk.ticket"].with_context(
            {"mail_create_nolog": True}
        )
        cls.test_team_ticket1 = HelpdeskTicket.create(
            {
                "name": "Ticket 1",
                "team_id": cls.test_team.id,
                "user_id": cls.helpdesk_manager.id,
            }
        )
        cls.test_team_ticket2 = HelpdeskTicket.create(
            {
                "name": "Ticket 2",
                "team_id": cls.test_team.id,
                "user_id": cls.helpdesk_user.id,
            }
        )

        cls.default_rating_vals = {
            "res_model_id": cls.env["ir.model"]._get("helpdesk.ticket").id,
            "parent_res_model_id": cls.env["ir.model"]._get("team.team").id,
            "parent_res_id": cls.test_team.id,
            "partner_id": cls.partner_1.id,
            "consumed": True,
        }

        # for get_dashboard
        cls.team_sla = cls.test_team.copy({"helpdesk_use_sla": True})
        cls.stage_done.team_ids = [Command.link(cls.team_sla.id)]

        cls.user_sla = cls.env["res.users"].create(
            {
                "name": "SLA user",
                "login": "sj@test.com",
                "tz": "Asia/Singapore",  # UTC +8
                "group_ids": [
                    Command.link(cls.env.ref("helpdesk.group_use_sla").id),
                    Command.link(cls.env.ref("helpdesk.group_helpdesk_manager").id),
                ],
            }
        )
        cls.team_sla.member_ids = [Command.link(cls.user_sla.id)]

    def test_rating_notification(self):
        asked = self.env["rating.rating"].create(
            {
                **self.default_rating_vals,
                "rated_partner_id": self.helpdesk_user.partner_id.id,
                "res_id": self.test_team_ticket2.id,
                "consumed": False,
            }
        )

        rating = 5
        feedback = "Great!"

        self.test_team_ticket2.rating_apply(
            rating, token=asked.access_token, feedback=feedback
        )
        message = self.test_team_ticket2.message_ids

        self.assertEqual(
            len(message), 1, "A message should have been posted in the chatter."
        )
        self.assertEqual(
            message.author_id,
            self.partner_1,
            "The message should be posted by the rating partner.",
        )
        self.assertIn(
            f"{rating}/5", message.body, f"The posted rating should be {rating}/5."
        )
        self.assertIn(
            feedback,
            message.body,
            "The posted rating should contain the customer feedback.",
        )

    def test_helpdesk_dashboard(self):
        """Test the rating stat displayed in the dashboard for the current user.

        Test Cases:
        ==========
        1) Generate some ratings on the current date.
        2) Call the `get_dashboard` method in helpdesk team model to get
           data displayed in the dashboard.
        3) Check the rating values in the dashboard data.
        """
        yesterday = date.today() - relativedelta(days=1)
        with patch.object(self.env.cr, "now", lambda: yesterday):
            ratings = self.env["rating.rating"].create(
                [
                    {
                        **self.default_rating_vals,
                        "rating": 5,
                        "rated_partner_id": self.helpdesk_user.partner_id.id,
                        "res_id": self.test_team_ticket2.id,
                    },
                    {
                        **self.default_rating_vals,
                        "rating": 3,
                        "rated_partner_id": self.helpdesk_manager.partner_id.id,
                        "res_id": self.test_team_ticket1.id,
                    },
                ]
            )
            # Flush INSIDE the patched clock. `create()` seeds `write_date`
            # from `cr.now()`, but the row is re-stamped when it is actually
            # written, so letting the flush escape this block gave the ratings
            # a real-now `write_date` while `create_date` stayed backdated --
            # and `get_dashboard` buckets "today" on `write_date`, so
            # yesterday's ratings counted as today's and the assertion below
            # could never hold. Measured both ways before changing it.
            self.env.flush_all()

        HelpdeskTeam = self.env["team.team"]
        self.assertTrue(
            HelpdeskTeam.with_user(self.helpdesk_manager)._is_rating_feature_enabled(
                True
            )
        )
        data = HelpdeskTeam.with_user(self.helpdesk_manager).get_dashboard()
        self.assertEqual(
            data["today"]["rating"],
            0,
            "The average rating of the Helpdesk Manager should be equal to 0 since no rating is done today.",
        )
        self.assertEqual(
            data["7days"]["rating"],
            3,
            "The average rating of the Helpdesk Manager should be equal to 3 / 5",
        )

        self.assertTrue(
            HelpdeskTeam.with_user(self.helpdesk_user)._is_rating_feature_enabled(True)
        )
        data = HelpdeskTeam.with_user(self.helpdesk_user).get_dashboard()
        self.assertEqual(
            data["today"]["rating"],
            0,
            "The average rating of the Helpdesk user should be equal to 0 since no rating is done today.",
        )
        self.assertEqual(
            data["7days"]["rating"], 5, "The average rating should be equal to 5 / 5."
        )

        # create ratings for today
        ratings = self.env["rating.rating"].create(
            [
                {
                    **self.default_rating_vals,
                    "rating": 1,
                    "rated_partner_id": self.helpdesk_user.partner_id.id,
                    "res_id": self.test_team_ticket2.id,
                },
                {
                    **self.default_rating_vals,
                    "rating": 5,
                    "rated_partner_id": self.helpdesk_manager.partner_id.id,
                    "res_id": self.test_team_ticket1.id,
                },
            ]
        )
        ratings.invalidate_recordset()
        data = HelpdeskTeam.with_user(self.helpdesk_manager).get_dashboard()
        self.assertEqual(
            data["today"]["rating"],
            5,
            "The average rating of the Helpdesk Manager user should be equal to 5 / 5",
        )
        self.assertEqual(
            data["7days"]["rating"],
            4,
            "The average rating of the Helpdesk Manager user should be equal to 4 / 5",
        )

        data = HelpdeskTeam.with_user(self.helpdesk_user).get_dashboard()
        self.assertEqual(
            data["today"]["rating"], 1, "The average rating should be equal to 1 / 5."
        )
        self.assertEqual(
            data["7days"]["rating"], 3, "The average rating should be equal to 3 / 5."
        )

    def test_helpdesk_dashboard_counts_a_rating_given_after_local_midnight(self):
        after_brussels_midnight = datetime(2026, 9, 25, 23, 30)
        with (
            freeze_time(after_brussels_midnight),
            patch.object(self.env.cr, "now", lambda: after_brussels_midnight),
        ):
            self.env["rating.rating"].create(
                {
                    **self.default_rating_vals,
                    "rating": 5,
                    "rated_partner_id": self.helpdesk_manager.partner_id.id,
                    "res_id": self.test_team_ticket1.id,
                }
            )
            self.env.flush_all()
            data = (
                self.env["team.team"].with_user(self.helpdesk_manager).get_dashboard()
            )
        self.assertEqual(data["today"]["rating"], 5)
        self.assertEqual(data["7days"]["rating"], 5)

    def test_helpdesk_dashboard_counts_a_rating_given_this_second(self):
        written = datetime(2026, 9, 25, 10, 0, 0, 400000)
        with (
            freeze_time(written.replace(microsecond=900000)),
            patch.object(self.env.cr, "now", lambda: written),
        ):
            self.env["rating.rating"].create(
                {
                    **self.default_rating_vals,
                    "rating": 5,
                    "rated_partner_id": self.helpdesk_manager.partner_id.id,
                    "res_id": self.test_team_ticket1.id,
                }
            )
            self.env.flush_all()
            data = (
                self.env["team.team"].with_user(self.helpdesk_manager).get_dashboard()
            )
        self.assertEqual(data["today"]["rating"], 5)
        self.assertEqual(data["7days"]["rating"], 5)

    def test_helpdesk_dashboard_user_timing(self):
        """Test that the dashboard properly uses the user's timezone when calculating 'today' and '7days' values"""
        HelpdeskTeam = self.team_sla.with_user(self.user_sla)
        HelpdeskTicket = self.env["helpdesk.ticket"].with_user(self.user_sla)
        context_today = HelpdeskTeam._local_midnight_as_utc()

        with freeze_time(fields.Datetime.to_string(context_today)):
            HelpdeskTicket.create(
                {
                    "name": "Ticket 1",
                    "team_id": HelpdeskTeam.id,
                }
            ).write({"user_id": self.user_sla.id, "stage_id": self.stage_done.id})

        dashboard = HelpdeskTeam.get_dashboard()
        self.assertEqual(dashboard["today"]["count"], 1, "today should include ticket")
        self.assertEqual(dashboard["7days"]["count"], 1, "7days should include ticket")

        tomorrow = context_today + relativedelta(days=1)
        with freeze_time(fields.Datetime.to_string(tomorrow)):
            dashboard = HelpdeskTeam.get_dashboard()
        self.assertEqual(
            dashboard["today"]["count"], 0, "today should NOT include ticket"
        )
        self.assertEqual(dashboard["7days"]["count"], 1, "7days should include ticket")

    def test_email_rating_template(self):
        self.stage_done.template_id = self.env.ref(
            "helpdesk.rating_ticket_request_email_template"
        )

        ticket = self.env["helpdesk.ticket"].create(
            {
                "name": "Test ticket",
                "team_id": self.test_team.id,
                "partner_id": self.partner_1.id,
                "stage_id": self.stage_progress.id,
            }
        )
        self.flush_tracking()

        with self.mock_mail_gateway():
            ticket.with_user(self.helpdesk_manager).write(
                {"stage_id": self.stage_done.id}
            )
            self.flush_tracking()

        mail = self.env["mail.mail"].search(
            [
                ("email_from", "=", self.test_team.helpdesk_alias_email_from),
                ("recipient_ids", "in", self.partner_1.id),
            ]
        )
        self.assertTrue(
            mail,
            "An email from the team email alias should have been sent to the partner",
        )
