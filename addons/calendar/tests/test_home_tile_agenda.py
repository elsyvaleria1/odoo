from datetime import datetime

from freezegun import freeze_time

from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
@freeze_time("2026-09-26 09:00:00")
class TestHomeTileAgenda(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env, login="tile_agenda", groups="base.group_user", tz=False
        )

    def _event(self, name, start, stop, **values):
        return self.env["calendar.event"].create(
            {
                "name": name,
                "start": start,
                "stop": stop,
                "partner_ids": [Command.link(self.user.partner_id.id)],
                **values,
            }
        )

    def _agenda(self):
        return (
            self.env["home.tile"]
            .with_user(self.user)
            .get_tiles([{"id": "agenda_1", "type": "agenda"}])["agenda_1"]["data"]
        )

    def test_the_agenda_lists_what_is_left_of_today_in_order(self):
        self._event(
            "Standup",
            datetime(2026, 9, 26, 10, 0),
            datetime(2026, 9, 26, 10, 15),
            location="Room 2",
        )
        self._event(
            "Review", datetime(2026, 9, 26, 15, 0), datetime(2026, 9, 26, 16, 0)
        )
        self._event(
            "Yesterday", datetime(2026, 9, 25, 10, 0), datetime(2026, 9, 25, 11, 0)
        )
        self._event(
            "Tomorrow", datetime(2026, 9, 27, 10, 0), datetime(2026, 9, 27, 11, 0)
        )
        declined = self._event(
            "Declined", datetime(2026, 9, 26, 11, 0), datetime(2026, 9, 26, 12, 0)
        )
        declined.attendee_ids.filtered(
            lambda attendee: attendee.partner_id == self.user.partner_id
        ).state = "declined"

        data = self._agenda()
        self.assertEqual(
            [event["name"] for event in data["events"]], ["Standup", "Review"]
        )
        self.assertEqual(data["events"][0]["location"], "Room 2")
        self.assertFalse(data["more"])

    def test_the_agenda_says_when_today_holds_more_than_it_shows(self):
        for hour in range(10, 18):
            self._event(
                f"Slot {hour}",
                datetime(2026, 9, 26, hour, 0),
                datetime(2026, 9, 26, hour, 30),
            )
        data = self._agenda()
        self.assertEqual(len(data["events"]), 6)
        self.assertTrue(data["more"])

    def test_the_agenda_tile_keeps_its_statement_count(self):
        request = [{"id": "agenda_1", "type": "agenda"}]
        self.env["home.tile"].with_user(self.user).get_tiles(request)
        self.env.invalidate_all()
        with self.assertQueryCount(5):
            self.env["home.tile"].with_user(self.user).get_tiles(request)
