from datetime import datetime
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command

from odoo.addons.calendar_microsoft.tests.common import TestCommon, distinct_inserts
from odoo.addons.calendar_microsoft.utils.calendar_microsoft import (
    MicrosoftCalendarService,
)
from odoo.addons.calendar_sync.models.res_users import ResUsers as CalendarSyncUsers
from odoo.addons.mail.tests.common import MailCase


class TestSyncOdoo2MicrosoftMail(TestCommon, MailCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.users = []
        for n in range(1, 4):
            user = cls.env["res.users"].create(
                {
                    "name": f"user{n}",
                    "login": f"user{n}",
                    "email": f"user{n}@odoo.com",
                }
            )
            user._calendar_sync_account("microsoft").sync_token = f"{n}_sync_token"
            cls.users += [user]

    @freeze_time("2020-01-01")
    @patch.object(
        CalendarSyncUsers,
        "_calendar_sync_connection",
        lambda user, code: (
            code == "microsoft"
            and user.login.startswith("user")
            and f"connection of {user.login}"
        ),
    )
    def test_event_creation_for_user(self):
        user_root = self.env.ref("base.user_root")
        self.assertFalse(user_root._calendar_sync_connection("microsoft"))
        partner = self.env["res.partner"].create(
            {"name": "Jean-Luc", "email": "jean-luc@opoo.com"}
        )
        event_values = {
            "name": "Event",
            "start": datetime(2020, 1, 15, 8, 0),
            "stop": datetime(2020, 1, 15, 18, 0),
        }
        paused_sync_user = self.users[2]
        paused_sync_user.write(
            {
                "email": "ms.sync.paused@test.lan",
                "name": "Paused Microsoft Sync User",
                "login": "ms_sync_paused_user",
            }
        )
        paused_sync_user._calendar_sync_account("microsoft").stopped = True
        inserts = distinct_inserts("created")
        for create_user, organizer, mail_notified_partners, attendee in [
            (user_root, self.users[0], False, partner),
            (user_root, None, partner, partner),
            (self.users[0], None, False, partner),
            (self.users[0], self.users[0], False, partner),
            (self.users[0], self.users[1], False, partner),
            (paused_sync_user, self.users[0], False, paused_sync_user.partner_id),
        ]:
            with self.subTest(
                create_uid=create_user.name if create_user else None,
                user_id=organizer.name if organizer else None,
                attendee=attendee.name,
            ):
                with (
                    self.mock_mail_gateway(),
                    patch.object(MicrosoftCalendarService, "insert") as mock_insert,
                ):
                    mock_insert.side_effect = inserts
                    self.env["calendar.event"].with_user(create_user).create(
                        {
                            **event_values,
                            "partner_ids": [
                                (4, organizer.partner_id.id),
                                (4, attendee.id),
                            ]
                            if organizer
                            else [(4, attendee.id)],
                            "user_id": organizer.id if organizer else False,
                        }
                    )
                    self.env.cr.postcommit.run()
                if not mail_notified_partners:
                    self.assertNotSentEmail()
                    mock_insert.assert_called_once()
                    self.assert_dict_equal(
                        mock_insert.call_args[0][0]["organizer"],
                        {
                            "emailAddress": {
                                "address": organizer.email if organizer else "",
                                "name": organizer.name if organizer else "",
                            }
                        },
                    )
                else:
                    mock_insert.assert_not_called()
                    for notified_partner in mail_notified_partners:
                        self.assertMailMail(
                            notified_partner,
                            "sent",
                            author=(organizer or create_user).partner_id,
                        )

    def test_change_organizer_pure_odoo_event(self):
        self.organizer_user._calendar_sync_account("microsoft").stopped = True
        event = (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(
                {
                    "name": "Pure Odoo Event",
                    "start": datetime(2024, 1, 1, 10, 0),
                    "stop": datetime(2024, 1, 1, 11, 0),
                    "user_id": self.organizer_user.id,
                    "partner_ids": [
                        Command.set(
                            [
                                self.organizer_user.partner_id.id,
                                self.attendee_user.partner_id.id,
                            ]
                        )
                    ],
                }
            )
        )

        self.assertFalse(self.held_id(event))
        self.assertTrue(event.active)

        event.write(
            {
                "user_id": self.attendee_user.id,
            }
        )

        self.assertTrue(
            event.active,
            "Pure Odoo event should not be archived when changing organizer",
        )
        self.assertEqual(
            event.user_id, self.attendee_user, "Organizer should be updated"
        )
