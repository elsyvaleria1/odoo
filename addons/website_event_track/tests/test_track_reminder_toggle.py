from lxml import html

from odoo import http
from odoo.tests.common import HttpCase, freeze_time, tagged

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.web.controllers.utils import FRAGMENTS_HEADER
from odoo.addons.website_event.tests.common import TestEventOnlineCommon


@tagged("post_install", "-at_install")
@freeze_time("2020-07-05")
class TestTrackReminderToggle(TestEventOnlineCommon, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.attendee = mail_new_test_user(
            cls.env,
            name="Reminder Attendee",
            login="reminder_attendee",
            email="reminder_attendee@example.com",
            groups="base.group_portal",
        )
        cls.event_0.write({"is_published": True})
        cls.track = cls.env["event.track"].create(
            {
                "name": "Remindable talk",
                "event_id": cls.event_0.id,
                "date": cls.event_0.date_begin,
                "is_published": True,
            }
        )

    def _toggle(self, set_reminder_on, track=None, fragments=True):
        return self.url_open(
            "/event/track/toggle_reminder",
            data={
                "csrf_token": http.Request.csrf_token(self),
                "track_id": (track or self.track).id,
                "set_reminder_on": set_reminder_on,
                "redirect": "/event/agenda?x=1",
            },
            headers={FRAGMENTS_HEADER: "1"} if fragments else None,
            allow_redirects=False,
        )

    def _state(self, response):
        (fragment,) = response.json()["fragments"]
        self.assertEqual(
            fragment["key"], f"website_event_track.reminder.{self.track.id}"
        )
        root = html.fragment_fromstring(fragment["html"])
        bell = root.xpath("//i[contains(@class, 'o_wetrack_js_reminder_bell')]")[0]
        return (
            root.xpath("//input[@name='set_reminder_on']/@value")[0],
            "fa-solid" in bell.get("class"),
            bell.get("title"),
        )

    def _reminder_mails(self):
        return self.env["mail.mail"].search(
            [
                ("model", "=", "event.track"),
                ("res_id", "=", self.track.id),
                ("email_to", "=", "reminder_attendee@example.com"),
            ]
        )

    def test_a_signed_in_attendee_s_favorite_answers_its_bell_and_sends_the_reminder(
        self,
    ):
        self.authenticate("reminder_attendee", "reminder_attendee")

        response = self._toggle("1")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self._state(response), ("0", True, "Favorite On"))
        (event,) = response.json()["events"]
        self.assertEqual(event["name"], "website_event_track:reminder_toggled")
        self.assertEqual(
            event["detail"],
            {
                "track_id": self.track.id,
                "reminder_on": True,
                "email": {"success": True},
            },
        )
        self.assertEqual(len(self._reminder_mails()), 1)
        self.assertTrue(
            self.env["event.track.visitor"]
            .search([("track_id", "=", self.track.id)])
            .is_wishlisted
        )

    def test_taking_the_favorite_back_sends_no_reminder(self):
        self.authenticate("reminder_attendee", "reminder_attendee")
        self._toggle("1")

        response = self._toggle("0")

        self.assertEqual(self._state(response), ("1", False, "Set Favorite"))
        (event,) = response.json()["events"]
        self.assertEqual(
            event["detail"],
            {"track_id": self.track.id, "reminder_on": False, "email": None},
        )
        self.assertEqual(len(self._reminder_mails()), 1)

    def test_a_page_out_of_date_gets_the_bell_as_it_is_and_no_event(self):
        self.authenticate("reminder_attendee", "reminder_attendee")
        self._toggle("1")

        response = self._toggle("1")

        self.assertEqual(self._state(response), ("0", True, "Favorite On"))
        self.assertEqual(response.json()["events"], [])
        self.assertEqual(len(self._reminder_mails()), 1)

    def test_a_visitor_s_favorite_is_kept_and_the_email_is_left_to_the_page(self):
        self.authenticate(None, None)

        response = self._toggle("1")

        self.assertEqual(self._state(response), ("0", True, "Favorite On"))
        (event,) = response.json()["events"]
        self.assertIsNone(event["detail"]["email"])
        self.assertTrue(
            self.env["event.track.visitor"]
            .search([("track_id", "=", self.track.id)])
            .visitor_id
        )

    def test_a_key_track_is_taken_out_of_the_favorites_by_blacklisting_it(self):
        self.track.wishlisted_by_default = True
        self.authenticate("reminder_attendee", "reminder_attendee")

        response = self._toggle("0")

        self.assertEqual(self._state(response), ("1", False, "Set Favorite"))
        self.assertTrue(
            self.env["event.track.visitor"]
            .search([("track_id", "=", self.track.id)])
            .is_blacklisted
        )

    def test_without_javascript_the_form_comes_back_to_the_page(self):
        self.authenticate("reminder_attendee", "reminder_attendee")

        response = self._toggle("1", fragments=False)

        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/event/agenda?x=1"))
        self.assertEqual(len(self._reminder_mails()), 1)

    def test_the_agenda_renders_each_bell_as_a_form_of_its_own(self):
        response = self.url_open(f"{self.event_0.website_url}/agenda")

        self.assertEqual(response.status_code, 200)
        page = html.fromstring(response.content)
        forms = page.xpath(
            f"//form[contains(@class, 'o_wetrack_js_reminder')][@data-track-id='{self.track.id}']"
        )
        self.assertTrue(forms)
        for form in forms:
            self.assertFalse(form.xpath("ancestor::form | ancestor::a"))
            self.assertEqual(form.get("action"), "/event/track/toggle_reminder")
            self.assertEqual(
                form.xpath(".//input[@name='set_reminder_on']/@value"), ["1"]
            )
