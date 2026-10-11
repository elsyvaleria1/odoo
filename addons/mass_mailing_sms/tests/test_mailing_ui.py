from odoo.tests import HttpCase, tagged, users


@tagged("post_install", "-at_install", "mail_activity")
class TestMailingUi(HttpCase):
    @users("admin")
    def test_tour_mailing_activities_split(self):
        user_admin = self.env.ref("base.user_admin")
        user_admin.write(
            {
                "email": "mitchell.admin@example.com",
            }
        )
        sms_rec, email_rec = self.env["mailing.mailing"].create(
            [
                {
                    "body_plaintext": "Some sms spam",
                    "mailing_type": "sms",
                    "name": "SMS record with an activity",
                    "subject": "New SMS!",
                },
                {
                    "body_html": "<p>Some email spam</p>",
                    "mailing_type": "mail",
                    "name": "Email record with an activity",
                    "subject": "New Email!",
                },
            ]
        )

        sms_rec.activity_schedule(
            act_type_xmlid="mail.mail_activity_data_todo", user_id=user_admin.id
        )
        email_rec.activity_schedule(
            act_type_xmlid="mail.mail_activity_data_todo", user_id=user_admin.id
        )

        self.start_tour("/odoo", "mailing_activities_split", login="admin")
