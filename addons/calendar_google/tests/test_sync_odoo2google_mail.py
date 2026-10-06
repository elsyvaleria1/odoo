from datetime import datetime
from unittest.mock import patch

from freezegun import freeze_time

from odoo.tests import tagged

from odoo.addons.calendar_google.tests.test_sync_common import TestSyncGoogle
from odoo.addons.calendar_sync.models.res_users import ResUsers as CalendarSyncUsers
from odoo.addons.mail.tests.common import MailCommon


@tagged("odoo2google")
class TestSyncOdoo2GoogleMail(TestSyncGoogle, MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.users = [
            cls.env["res.users"].create(
                {"name": login, "login": login, "email": f"{login}@odoo.com"}
            )
            for login in ("user1", "user2")
        ]

    @patch.object(
        CalendarSyncUsers,
        "_calendar_sync_connection",
        lambda user, code=None: "a-connection" if user.login == "user1" else False,
    )
    @freeze_time("2020-01-01")
    def test_event_creation_for_user(self):
        organizer1 = self.users[0]
        organizer2 = self.users[1]
        user_root = self.env.ref("base.user_root")
        event_values = {
            "name": "Event",
            "start": datetime(2020, 1, 15, 8, 0),
            "stop": datetime(2020, 1, 15, 18, 0),
        }
        partner = self.env["res.partner"].create(
            {"name": "Jean-Luc", "email": "jean-luc@opoo.com"}
        )
        for create_user, organizer, responsible, expect_mail, is_public in [
            (user_root, organizer1, organizer1, False, True),
            (user_root, None, user_root, True, True),
            (organizer1, None, organizer1, False, False),
            (organizer1, organizer2, organizer1, False, True),
        ]:
            with self.subTest(
                create_uid=create_user.name if create_user else None,
                user_id=organizer.name if organizer else None,
            ):
                with (
                    self.mock_mail_gateway(),
                    self.mock_google_sync(user_id=responsible),
                ):
                    self.env["calendar.event"].with_user(create_user).create(
                        {
                            **event_values,
                            "partner_ids": [(4, partner.id)],
                            "user_id": organizer.id if organizer else False,
                        }
                    )
                if not expect_mail:
                    self.assertNotSentEmail()
                    self.assertGoogleEventInserted(
                        {
                            "attendees": [
                                {
                                    "email": "jean-luc@opoo.com",
                                    "responseStatus": "needsAction",
                                }
                            ],
                            "id": False,
                            "start": {
                                "dateTime": "2020-01-15T08:00:00+00:00",
                                "date": None,
                            },
                            "end": {
                                "dateTime": "2020-01-15T18:00:00+00:00",
                                "date": None,
                            },
                            "guestsCanModify": is_public,
                            "organizer": {"email": organizer.email, "self": False}
                            if organizer
                            else False,
                            "summary": "Event",
                            "reminders": {"useDefault": False, "overrides": []},
                        },
                        timeout=3,
                    )
                else:
                    self.assertGoogleEventNotInserted()
                    self.assertMailMail(partner, "sent", author=user_root.partner_id)
