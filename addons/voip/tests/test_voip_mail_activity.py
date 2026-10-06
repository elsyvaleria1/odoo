from datetime import UTC, datetime

from freezegun import freeze_time

from odoo import Command
from odoo.tests import common, tagged


@tagged("voip", "post_install", "-at_install")
class TestVoipMailActivity(common.TransactionCase):
    def test_voip_mail_activity_country_code_mixin(self):
        """Tests that "country_code_from_phone" is properly computed based on a phone field"""
        some_partner = self.env["res.partner"].create(
            {
                "name": "Some partner",
                "phone_ids": [
                    Command.create({"number": "+493023125513", "type": "landline"})
                ],
            }
        )
        activity = some_partner.activity_schedule("mail.mail_activity_data_call")
        self.assertEqual(activity.phone_country_id.code.lower(), "de")

    def test_call_queue_uses_the_assignee_own_day(self):
        """The call queue asks for activities that are already due. "Due" is the
        assignee's own day -- that is what activity_state reads and what the
        systray counts -- not the server's. A user far enough east was losing
        every call the rest of the UI called due today."""
        activity_type = self.env["mail.activity.type"].search(
            [("category", "=", "phonecall")], limit=1
        ) or self.env["mail.activity.type"].create(
            {"name": "Call", "category": "phonecall"}
        )
        user = self.env["res.users"].create(
            {
                "login": "voip_east",
                "name": "East",
                "tz": "Pacific/Kiritimati",  # UTC+14: ahead of the server all day
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        partner = self.env["res.partner"].create(
            {
                "name": "Callee",
                "phone_ids": [
                    Command.create({"number": "+3212345678", "type": "landline"})
                ],
            }
        )

        for moment in (
            datetime(2026, 6, 15, 2, 0, tzinfo=UTC),
            datetime(2026, 6, 15, 12, 0, tzinfo=UTC),
            datetime(2026, 6, 15, 23, 0, tzinfo=UTC),
        ):
            with freeze_time(moment), self.subTest(moment=moment):
                Activity = self.env["mail.activity"]
                activity = Activity.create(
                    {
                        "res_model_id": self.env["ir.model"]._get_id("res.partner"),
                        "res_id": partner.id,
                        "activity_type_id": activity_type.id,
                        "date_deadline": Activity._today_in_tz(user.tz),
                        "user_id": user.id,
                    }
                )
                self.env.flush_all()
                self.env.invalidate_all()

                self.assertEqual(
                    activity.with_user(user).state,
                    "today",
                    "the activity is due today in the assignee's own timezone",
                )
                queued = (
                    self.env["mail.activity"]
                    .with_user(user)
                    .search(self.env["mail.activity"]._domain_todo(user))
                )
                self.assertIn(
                    activity,
                    queued,
                    "an activity the field calls due today must be in the queue",
                )
                self.assertTrue(
                    partner.with_user(user).has_call_in_queue,
                    "and the record must show as queued",
                )
                activity.unlink()
