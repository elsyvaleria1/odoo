from datetime import timedelta

from freezegun import freeze_time

from odoo.tests import Form, tagged, users, warmup

from odoo.addons.test_event_full.tests.common import TestEventFullCommon
from odoo.addons.website.tests.test_performance import UtilPerf


@tagged("event_performance", "post_install", "-at_install", "-standard")
class EventPerformanceCase(TestEventFullCommon):
    def setUp(self):
        super().setUp()
        self.patch(self.env.registry, "ready", True)
        self._mock_smtplib_connection()

        self._flush_tracking()

    def _flush_tracking(self):
        self.env.flush_all()
        self.cr.flush()


@tagged("event_performance", "post_install", "-at_install", "-standard")
class TestEventPerformance(EventPerformanceCase):
    @users("event_user")
    @warmup
    def test_event_create_batch_notype(self):
        batch_size = 20

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=335),
        ):
            self.env.cr._now = self.reference_now
            event_values = [
                dict(self.event_base_vals, website_menu=False)
                for x in range(batch_size)
            ]
            self.env["event.event"].create(event_values)

    @users("event_user")
    @warmup
    def test_event_create_batch_notype_website(self):
        batch_size = 20

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=3418),
        ):
            self.env.cr._now = self.reference_now
            event_values = [
                dict(self.event_base_vals, website_menu=True) for x in range(batch_size)
            ]
            self.env["event.event"].with_context(lang="en_US").create(event_values)

    @users("event_user")
    @warmup
    def test_event_create_batch_wtype(self):
        batch_size = 20
        event_type = self.env["event.type"].browse(self.test_event_type.ids)

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=432),
        ):
            self.env.cr._now = self.reference_now
            event_values = [
                dict(
                    self.event_base_vals,
                    event_type_id=event_type.id,
                    website_menu=False,
                )
                for x in range(batch_size)
            ]
            self.env["event.event"].create(event_values)

    @users("event_user")
    @warmup
    def test_event_create_batch_wtype_website(self):
        batch_size = 20
        event_type = self.env["event.type"].browse(self.test_event_type.ids)

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=3522),
        ):
            self.env.cr._now = self.reference_now
            event_values = [
                dict(
                    self.event_base_vals,
                    event_type_id=event_type.id,
                )
                for x in range(batch_size)
            ]
            self.env["event.event"].with_context(lang="en_US").create(event_values)

    @users("event_user")
    @warmup
    def test_event_create_form_notype(self):
        has_social = "social_menu" in self.env["event.event"]

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=108),
        ):
            self.env.cr._now = self.reference_now
            with self.debug_mode():
                with Form(self.env["event.event"]) as event_form:
                    event_form.name = "Test Event"
                    event_form.date_begin = self.reference_now + timedelta(days=1)
                    event_form.date_end = self.reference_now + timedelta(days=5)
                    event_form.website_menu = False
                    if has_social:
                        event_form.social_menu = False
                _event = event_form.save()

    @users("event_user")
    @warmup
    def test_event_create_form_notype_website(self):
        has_social = "social_menu" in self.env["event.event"]

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=429),
        ):
            self.env.cr._now = self.reference_now
            with self.debug_mode():
                with Form(self.env["event.event"]) as event_form:
                    event_form.name = "Test Event"
                    event_form.date_begin = self.reference_now + timedelta(days=1)
                    event_form.date_end = self.reference_now + timedelta(days=5)
                    event_form.website_menu = True
                    if has_social:
                        event_form.social_menu = False
                _event = event_form.save()

    @users("event_user")
    @warmup
    def test_event_create_form_type_website(self):
        event_type = self.env["event.type"].browse(self.test_event_type.ids)
        has_social = "social_menu" in self.env["event.event"]

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=472),
        ):
            self.env.cr._now = self.reference_now
            with self.debug_mode():
                with Form(self.env["event.event"]) as event_form:
                    event_form.name = "Test Event"
                    event_form.date_begin = self.reference_now + timedelta(days=1)
                    event_form.date_end = self.reference_now + timedelta(days=5)
                    event_form.event_type_id = event_type
                    if has_social:
                        event_form.social_menu = False

    @users("event_user")
    @warmup
    def test_event_create_single_notype(self):
        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=31),
        ):
            self.env.cr._now = self.reference_now
            event_values = dict(self.event_base_vals, website_menu=False)
            self.env["event.event"].create([event_values])

    @users("event_user")
    @warmup
    def test_event_create_single_notype_website(self):
        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=242),
        ):
            self.env.cr._now = self.reference_now
            event_values = dict(self.event_base_vals, website_menu=True)
            self.env["event.event"].with_context(lang="en_US").create([event_values])

    @users("event_user")
    @warmup
    def test_event_create_single_wtype(self):
        event_type = self.env["event.type"].browse(self.test_event_type.ids)

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=52),
        ):
            self.env.cr._now = self.reference_now
            event_values = dict(
                self.event_base_vals, event_type_id=event_type.id, website_menu=False
            )
            self.env["event.event"].create([event_values])

    @users("event_user")
    @warmup
    def test_event_create_single_wtype_website(self):
        event_type = self.env["event.type"].browse(self.test_event_type.ids)

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=274),
        ):
            self.env.cr._now = self.reference_now
            event_values = dict(
                self.event_base_vals,
                event_type_id=event_type.id,
            )
            self.env["event.event"].with_context(lang="en_US").create([event_values])


@tagged(
    "event_performance",
    "registration_performance",
    "post_install",
    "-at_install",
    "-standard",
)
class TestRegistrationPerformance(EventPerformanceCase):
    @users("event_user")
    @warmup
    def test_registration_create_batch(self):
        event = self.env["event.event"].browse(self.test_event.ids)

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=638),
        ):
            self.env.cr._now = self.reference_now
            registration_values = [
                dict(reg_data, event_id=event.id) for reg_data in self.customer_data
            ]
            registration_values += [
                {
                    "event_id": event.id,
                    "partner_id": partner.id,
                }
                for partner in self.partners
            ]
            _registrations = self.env["event.registration"].create(registration_values)

    @users("event_user")
    @warmup
    def test_registration_create_batch_nolead(self):
        event = self.env["event.event"].browse(self.test_event.ids)

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=165),
        ):
            self.env.cr._now = self.reference_now
            registration_values = [
                dict(reg_data, event_id=event.id) for reg_data in self.customer_data
            ]
            registration_values += [
                {
                    "event_id": event.id,
                    "partner_id": partner.id,
                }
                for partner in self.partners
            ]
            _registrations = (
                self.env["event.registration"]
                .with_context(event_lead_rule_skip=True)
                .create(registration_values)
            )

    @users("event_user")
    @warmup
    def test_registration_create_batch_website(self):
        event = self.env["event.event"].browse(self.test_event.ids)

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=651),
        ):
            self.env.cr._now = self.reference_now
            registration_values = [
                dict(reg_data, event_id=event.id)
                for reg_data in self.website_customer_data
            ]
            registration_values += [
                {
                    "event_id": event.id,
                    "partner_id": partner.id,
                    "registration_answer_ids": self.website_customer_data[0][
                        "registration_answer_ids"
                    ],
                }
                for partner in self.partners
            ]
            _registrations = self.env["event.registration"].create(registration_values)

    @users("event_user")
    @warmup
    def test_registration_create_form_customer(self):
        event = self.env["event.event"].browse(self.test_event.ids)

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=145),
        ):
            self.env.cr._now = self.reference_now
            phone = self.env["phone.number"].create({"number": "0456000000"})
            with Form(self.env["event.registration"]) as reg_form:
                reg_form.event_id = event
                reg_form.email = "email.00@test.example.com"
                reg_form.name = "My Customer"
                reg_form.phone_ids.add(phone)
            _registration = reg_form.save()

    @users("event_user")
    @warmup
    def test_registration_create_form_partner(self):
        event = self.env["event.event"].browse(self.test_event.ids)

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=146),
        ):
            self.env.cr._now = self.reference_now
            with Form(self.env["event.registration"]) as reg_form:
                reg_form.event_id = event
                reg_form.partner_id = self.partners[0]
            _registration = reg_form.save()

    @users("event_user")
    @warmup
    def test_registration_create_form_partner_nolead(self):
        event = self.env["event.event"].browse(self.test_event.ids)

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=63),
        ):
            self.env.cr._now = self.reference_now
            with Form(
                self.env["event.registration"].with_context(event_lead_rule_skip=True)
            ) as reg_form:
                reg_form.event_id = event
                reg_form.partner_id = self.partners[0]
            _registration = reg_form.save()

    @users("event_user")
    @warmup
    def test_registration_create_single_customer(self):
        event = self.env["event.event"].browse(self.test_event.ids)

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=122),
        ):
            self.env.cr._now = self.reference_now
            registration_values = dict(self.customer_data[0], event_id=event.id)
            _registration = self.env["event.registration"].create([registration_values])

    @users("event_user")
    @warmup
    def test_registration_create_single_partner(self):
        event = self.env["event.event"].browse(self.test_event.ids)

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=121),
        ):
            self.env.cr._now = self.reference_now
            registration_values = {
                "event_id": event.id,
                "partner_id": self.partners[0].id,
            }
            _registration = self.env["event.registration"].create([registration_values])

    @users("event_user")
    @warmup
    def test_registration_create_single_partner_nolead(self):
        event = self.env["event.event"].browse(self.test_event.ids)

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=39),
        ):
            self.env.cr._now = self.reference_now
            registration_values = {
                "event_id": event.id,
                "partner_id": self.partners[0].id,
            }
            _registration = (
                self.env["event.registration"]
                .with_context(event_lead_rule_skip=True)
                .create([registration_values])
            )

    @users("event_user")
    @warmup
    def test_registration_create_single_website(self):
        event = self.env["event.event"].browse(self.test_event.ids)

        with (
            freeze_time(self.reference_now),
            self.assertQueryCount(event_user=126),
        ):
            self.env.cr._now = self.reference_now
            registration_values = dict(self.website_customer_data[0], event_id=event.id)
            _registration = self.env["event.registration"].create([registration_values])


@tagged("event_performance", "event_online", "post_install", "-at_install", "-standard")
class TestOnlineEventPerformance(EventPerformanceCase, UtilPerf):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "channel_id" in cls.env["website"]:
            cls.env["website"].search([]).channel_id = False

        cash_journal = cls.env["account.journal"].create(
            {"name": "Cash - Test", "type": "cash", "code": "CASH - Test"}
        )
        cls.env["payment.provider"].search([("code", "=", "test")]).write(
            {"journal_id": cash_journal.id, "state": "test"}
        )

        cls.env["event.event"].search([("name", "!=", "Test Event")]).write(
            {"active": False}
        )
        cls.noise_events = cls.env["event.event"].create(
            [
                {
                    "name": "Event %02d" % idx,
                    "date_begin": cls.reference_now
                    + timedelta(days=(-2 + int(idx / 10))),
                    "date_end": cls.reference_now + timedelta(days=5),
                    "is_published": True,
                }
                for idx in range(50)
            ]
        )

    def _test_url_open(self, url):
        return self.url_open(url)

    @warmup
    def test_event_page_event_manager(self):
        with freeze_time(self.reference_now):
            self.authenticate("user_eventmanager", "user_eventmanager")
            with self.assertQueryCount(default=35):
                self._test_url_open("/event/%i" % self.test_event.id)

    @warmup
    def test_event_page_public(self):
        with freeze_time(self.reference_now):
            self.authenticate(None, None)
            with self.assertQueryCount(default=25):
                self._test_url_open("/event/%i" % self.test_event.id)

    @warmup
    def test_events_browse_event_manager(self):
        with freeze_time(self.reference_now):
            self.authenticate("user_eventmanager", "user_eventmanager")
            with self.assertQueryCount(default=43):
                self._test_url_open("/event")

    @warmup
    def test_events_browse_public(self):
        with freeze_time(self.reference_now):
            self.authenticate(None, None)
            with self.assertQueryCount(default=39):
                self._test_url_open("/event")

    @warmup
    def test_register_public(self):
        with freeze_time(self.reference_now + timedelta(hours=3)):
            self.assertTrue(self.test_event.event_registrations_started)
            self.authenticate(None, None)
            with self.assertQueryCount(default=1197):
                self.start_tour(
                    "/event/%i/register" % self.test_event.id,
                    "wevent_performance_register",
                    login=None,
                    timeout=200,
                )

        self.assertEqual(len(self.test_event.registration_ids), 3)
        self.assertEqual(len(self.test_event.registration_ids.visitor_id), 1)
