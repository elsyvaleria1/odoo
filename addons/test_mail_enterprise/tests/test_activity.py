from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import users
from odoo.tools import mute_logger

from odoo.addons.sms.tests.common import SMSCommon
from odoo.addons.test_mail_sms.tests.common import TestSMSRecipients


@tagged("mail_activity")
class TestActivity(SMSCommon, TestSMSRecipients):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.test_record_voip = cls.env["mail.test.activity.bl.sms.voip"].create(
            {
                "name": "Test Record",
                "customer_id": cls.partner_1.id,
                "email_from": cls.partner_1.email,
                "phone_nbr_ids": [
                    Command.create({"number": "0456999999", "type": "landline"})
                ],
            }
        )

        cls.phonecall_activity = cls.env.ref("mail.mail_activity_data_call")
        cls.phonecall_activity.write(
            {
                "default_user_id": cls.user_admin.id,
                "default_note": "Test Default Note",
                "summary": "Test Default Summary",
            }
        )

        cls.env["mail.activity.type"].search(
            [
                ("category", "=", "phonecall"),
                ("id", "!=", cls.phonecall_activity.id),
            ]
        ).unlink()

    def test_activity_data(self):
        self.assertEqual(self.partner_1._phone_get_number().number, "0456001122")
        self.assertTrue(self.phonecall_activity)
        self.assertEqual(self.phonecall_activity.category, "phonecall")

    @users("employee")
    @mute_logger("odoo.addons.voip.models.mixin_voip_queue")
    def test_create_call_activity(self):
        record = self.test_record_voip.with_env(self.env)

        activity = record.create_call_activity()
        self.assertEqual(activity.activity_type_id, self.phonecall_activity)
        self.assertEqual(activity.phone, record._phone_get_number().number)
        self.assertFalse(activity.note)
        self.assertFalse(activity.summary)

        phonecall_activities = (
            self.env["mail.activity"]
            .sudo()
            .search(
                [
                    ("activity_type_id", "=", self.phonecall_activity.id),
                ]
            )
        )
        phonecall_activities.write({"activity_type_id": False})
        phonecall_activities.flush_recordset()
        self.env.cr.execute(
            "DELETE FROM mail_activity_type WHERE id = ANY(%s)",
            (list(self.phonecall_activity.ids),),
        )
        self.env["ir.model.data"].sudo().search(
            [("name", "=", "mail_activity_data_call"), ("module", "=", "mail")]
        ).unlink()

        self.assertFalse(
            self.env["mail.activity.type"].search([("category", "=", "phonecall")])
        )
        activity = record.create_call_activity()
        new_activity_type = self.env["mail.activity.type"].search(
            [("category", "=", "phonecall")]
        )
        self.assertTrue(bool(new_activity_type))

    @users("employee")
    def test_type_phonecall(self):
        activities = self.env["mail.activity"].create(
            [
                {
                    "activity_type_id": self.phonecall_activity.id,
                    "phone": "+32455001122",
                    "user_id": self.user_employee.id,
                },
                {
                    "activity_type_id": self.phonecall_activity.id,
                    "phone": "+32455334455",
                    "user_id": self.user_employee.id,
                },
            ]
        )
        stored_free = (
            self.env["mail.activity"].get_today_call_activities().get("mail.activity")
        )
        self.assertEqual(
            len(stored_free), len(activities), "Should have one entry / activity"
        )
