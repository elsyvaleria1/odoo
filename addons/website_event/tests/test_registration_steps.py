from datetime import datetime, timedelta

from lxml import html

from odoo import http
from odoo.tests import HttpCase, tagged

from odoo.addons.web.controllers.utils import FRAGMENTS_HEADER


@tagged("post_install", "-at_install")
class TestRegistrationSteps(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        begin = datetime.now() + timedelta(days=10)
        cls.event = cls.env["event.event"].create(
            {
                "name": "Stepwise Event",
                "date_begin": begin,
                "date_end": begin + timedelta(days=1),
                "is_published": True,
                "event_ticket_ids": [
                    (0, 0, {"name": "Standard"}),
                    (0, 0, {"name": "Patron"}),
                ],
            }
        )
        cls.standard, cls.patron = cls.event.event_ticket_ids
        cls.slotted = cls.env["event.event"].create(
            {
                "name": "Slotted Event",
                "date_begin": begin,
                "date_end": begin + timedelta(days=3),
                "is_published": True,
                "is_multi_slots": True,
                "event_ticket_ids": [(0, 0, {"name": "Entry"})],
                "event_slot_ids": [
                    (
                        0,
                        0,
                        {
                            "date": (begin + timedelta(days=1)).date(),
                            "start_hour": 9,
                            "end_hour": 12,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "date": (begin + timedelta(days=2)).date(),
                            "start_hour": 9,
                            "end_hour": 12,
                        },
                    ),
                ],
            }
        )
        if "price" in cls.standard._fields:
            (cls.event | cls.slotted).event_ticket_ids.price = 0

    def setUp(self):
        super().setUp()
        self.authenticate(None, None)

    def _post(self, url, data, fragments):
        return self.url_open(
            url,
            data={"csrf_token": http.Request.csrf_token(self), **data},
            headers={FRAGMENTS_HEADER: "1"} if fragments else None,
            allow_redirects=False,
        )

    def _fragment(self, response, key):
        self.assertEqual(response.status_code, 200, response.text)
        (fragment,) = response.json()["fragments"]
        self.assertEqual(fragment["key"], key)
        return html.fragment_fromstring(fragment["html"])

    def _page(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        return html.fromstring(response.content)

    def test_the_register_button_is_a_link_to_the_registration_page(self):
        page = self._page(self.url_open(f"/event/{self.event.id}/register"))

        ctas = page.xpath("//a[contains(@class, 'o_wevent_registration_cta')]")
        self.assertTrue(ctas)
        for cta in ctas:
            self.assertTrue(cta.get("href").endswith(f"-{self.event.id}/registration"))
            self.assertEqual(cta.get("data-bs-toggle"), "modal")

    def test_the_registration_page_offers_the_tickets_as_a_plain_form(self):
        page = self._page(self.url_open(f"/event/{self.event.id}/registration"))

        (form,) = page.xpath("//form[@id='registration_form']")
        self.assertTrue(form.get("action").endswith("/registration/new"))
        self.assertIsNone(form.get("data-fragment-form"))
        self.assertFalse(form.xpath("ancestor::*[contains(@class, 'modal ')]"))
        self.assertFalse(form.xpath(".//button[@type='submit'][@disabled]"))
        self.assertEqual(
            set(form.xpath(".//input[starts-with(@name, 'nb_register-')]/@name")),
            {f"nb_register-{self.standard.id}", f"nb_register-{self.patron.id}"},
        )

    def test_a_slotted_event_s_registration_page_asks_for_a_date(self):
        page = self._page(self.url_open(f"/event/{self.slotted.id}/registration"))

        (form,) = page.xpath("//form[@id='slot_registration_form']")
        self.assertTrue(form.get("action").endswith("/registration/slot/tickets"))
        self.assertEqual(
            sorted(map(int, form.xpath(".//input[@name='event_slot_id']/@value"))),
            sorted(self.slotted.event_slot_ids.ids),
        )

    def test_a_date_s_tickets_come_as_a_modal_or_as_a_page(self):
        slot = self.slotted.event_slot_ids[0]
        url = f"/event/{self.slotted.id}/registration/slot/tickets"

        modal = self._fragment(
            self._post(url, {"event_slot_id": slot.id}, fragments=True),
            "website_event.registration_tickets",
        )
        page = self._page(self._post(url, {"event_slot_id": slot.id}, fragments=False))

        self.assertTrue(modal.xpath("//div[@id='modal_ticket_registration']"))
        self.assertEqual(
            modal.xpath("//form[@id='registration_form']/@data-fragment-form"),
            ["website_event.registration_attendees"],
        )
        self.assertEqual(
            page.xpath(
                "//form[@id='registration_form']//input[@name='event_slot_id']/@value"
            ),
            [str(slot.id)],
        )
        self.assertFalse(page.xpath("//div[@id='modal_ticket_registration']"))

    def test_a_date_of_another_event_is_not_found(self):
        response = self._post(
            f"/event/{self.event.id}/registration/slot/tickets",
            {"event_slot_id": self.slotted.event_slot_ids[0].id},
            fragments=True,
        )

        self.assertEqual(response.status_code, 404)

    def test_the_attendees_come_as_a_modal_or_as_a_page(self):
        url = f"/event/{self.event.id}/registration/new"
        tickets = {
            f"nb_register-{self.standard.id}": 2,
            f"nb_register-{self.patron.id}": 0,
        }

        modal = self._fragment(
            self._post(url, tickets, fragments=True),
            "website_event.registration_attendees",
        )
        page = self._page(self._post(url, tickets, fragments=False))

        self.assertTrue(modal.xpath("//div[@id='modal_attendees_registration']"))
        self.assertEqual(
            page.xpath(
                "//form[@id='attendee_registration']//input[contains(@name, '-event_ticket_id')]/@value"
            ),
            [str(self.standard.id)] * 2,
        )
        self.assertFalse(page.xpath("//div[@id='modal_attendees_registration']"))
        self.assertTrue(
            page.xpath(
                "//form[@id='attendee_registration']//a[contains(@href, '/register')]"
            )
        )

    def test_no_ticket_is_refused_with_a_message(self):
        response = self._post(
            f"/event/{self.event.id}/registration/new",
            {f"nb_register-{self.standard.id}": 0},
            fragments=True,
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["error"]["message"], "Choose at least one ticket."
        )

    def test_a_visitor_registers_from_end_to_end_without_javascript(self):
        page = self._page(
            self._post(
                f"/event/{self.event.id}/registration/new",
                {f"nb_register-{self.patron.id}": 1},
                fragments=False,
            )
        )
        (form,) = page.xpath("//form[@id='attendee_registration']")
        data = {
            field.get("name"): field.get("value") or ""
            for field in form.xpath(".//input[@name]")
            if field.get("type") != "submit"
        }
        for name in data:
            if "-name-" in name:
                data[name] = "Nadia"
            elif "-email-" in name:
                data[name] = "nadia@example.com"

        response = self.url_open(form.get("action"), data=data, allow_redirects=False)

        self.assertEqual(response.status_code, 303, response.text)
        self.assertIn("/registration/success", response.headers["Location"])
        registration = self.event.registration_ids
        self.assertEqual(
            (registration.name, registration.email, registration.event_ticket_id),
            ("Nadia", "nadia@example.com", self.patron),
        )

    def test_a_visitor_registers_for_a_date_through_the_modals(self):
        self.start_tour(f"/event/{self.slotted.id}/register", "event_slot_registration")

        registration = self.slotted.registration_ids
        self.assertEqual(registration.email, "slot.attendee@example.com")
        self.assertIn(registration.event_slot_id, self.slotted.event_slot_ids)
