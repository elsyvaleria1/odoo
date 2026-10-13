import re
from datetime import datetime, timedelta
from pathlib import Path

from odoo import Command
from odoo.modules import Manifest
from odoo.tests import Form
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.mail.tests.common import MailCase
from odoo.addons.sms.tests.common import SMSCase


class TestFrontDesk(MailCase, SMSCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create(
            {"name": "Test Company", "email": "your.company@example.com"}
        )
        cls.env = cls.env(
            context=dict(cls.env.context, allowed_company_ids=cls.company.ids)
        )
        cls.partner_1, cls.partner_2 = cls.env["res.partner"].create(
            [
                {
                    "name": "Test Partner 1",
                    "email": "test1@example.com",
                },
                {
                    "name": "Test Partner 2",
                    "email": "test2@example.com",
                },
            ]
        )
        cls.user_1, cls.user_2 = cls.env["res.users"].create(
            [
                {
                    "name": "Test User 1",
                    "login": "test_user_1",
                    "partner_id": cls.partner_1.id,
                },
                {
                    "name": "Test User 2",
                    "login": "test_user_2",
                    "partner_id": cls.partner_2.id,
                },
            ]
        )
        cls.employee_1, cls.employee_2 = cls.env["hr.employee"].create(
            [
                {
                    "name": "Host 1",
                    "user_id": cls.user_1.id,
                    "phone_ids": [
                        Command.create({"number": "1234567890", "type": "landline"})
                    ],
                    "work_email": "test_work1@example.com",
                },
                {
                    "name": "Host 2",
                    "user_id": cls.user_2.id,
                    "phone_ids": [
                        Command.create({"number": "0987654321", "type": "landline"})
                    ],
                    "work_email": "test_work2@example.com",
                },
            ]
        )
        cls.drink = cls.env["frontdesk.drink"].create(
            {
                "name": "Coke",
                "notify_user_ids": [(4, cls.user_2.id)],
            }
        )
        cls.station = cls.env["frontdesk.frontdesk"].create(
            {
                "name": "office_1",
                "host_selection": True,
                "drink_offer": True,
                "drink_ids": [(4, cls.drink.id)],
                "ask_email": "required",
                "ask_phone": "required",
                "company_id": cls.company.id,
            }
        )
        cls.visitor_1, cls.visitor_2, cls.visitor_3 = cls.env[
            "frontdesk.visitor"
        ].create(
            [
                {
                    "name": "Visitor_1",
                    "station_id": cls.station.id,
                    "host_ids": [(4, cls.employee_1.id)],
                },
                {
                    "name": "Visitor_2",
                    "station_id": cls.station.id,
                    "host_ids": [(4, cls.employee_2.id)],
                },
                {
                    "name": "Visitor_3",
                    "station_id": cls.station.id,
                    "host_ids": [(4, cls.employee_1.id)],
                },
            ]
        )

    def assert_discuss_notification(self, user_name):
        channel = self.env["discuss.channel"].search_count(
            ["&", ("name", "ilike", "OdooBot"), ("name", "ilike", user_name)]
        )
        self.assertEqual(channel, 1)

    def test_host_notify_discuss(self):

        self.visitor_1.state = "checked_in"
        host_name = self.visitor_1.host_ids.user_id.name
        self.assert_discuss_notification(host_name)

    def test_host_with_no_user_email_fallback(self):

        host = self.env["hr.employee"].create(
            {
                "name": "Host with Email",
                "work_email": "host_email@example.com",
            }
        )
        self.station.notify_discuss = True
        self.station.notify_email = False
        self.station.notify_sms = False
        visitor = self.env["frontdesk.visitor"].create(
            {
                "name": "Visitor_4",
                "station_id": self.station.id,
                "host_ids": [(4, host.id)],
            }
        )
        with self.mock_mail_gateway():
            visitor.state = "checked_in"
        self.assertSentEmail(
            '"OdooBot" <odoobot@example.com>',
            ['"Host with Email" <host_email@example.com>'],
        )

    def test_host_with_no_user_sms_fallback(self):

        host = self.env["hr.employee"].create(
            {
                "name": "Host with SMS",
                "phone_ids": [
                    Command.create({"number": "7778889999", "type": "landline"})
                ],
            }
        )
        self.station.notify_discuss = True
        self.station.notify_email = False
        self.station.notify_sms = False
        visitor = self.env["frontdesk.visitor"].create(
            {
                "name": "Visitor_5",
                "station_id": self.station.id,
                "host_ids": [(4, host.id)],
            }
        )
        with self.mockSMSGateway():
            visitor.state = "checked_in"
        partner_id = host.partner_id.id
        sms_count = self.env["sms.sms"].search_count([("partner_id", "=", partner_id)])
        self.assertEqual(
            sms_count,
            1,
            "Exactly one SMS message should be sent to the host's partner.",
        )

    def test_host_with_all_notify_true_send_email_and_sms(self):

        host = self.env["hr.employee"].create(
            {
                "name": "Host All Channels",
                "work_email": "host_all@example.com",
                "phone_ids": [
                    Command.create({"number": "5551112222", "type": "landline"})
                ],
            }
        )
        self.station.notify_discuss = True
        self.station.notify_email = True
        self.station.notify_sms = True
        visitor = self.env["frontdesk.visitor"].create(
            {
                "name": "Visitor_7",
                "station_id": self.station.id,
                "host_ids": [(4, host.id)],
            }
        )
        with self.mock_mail_gateway(), self.mockSMSGateway():
            visitor.state = "checked_in"
        self.assertSentEmail(
            '"OdooBot" <odoobot@example.com>',
            ['"Host All Channels" <host_all@example.com>'],
        )
        partner_id = host.partner_id.id
        sms_count = self.env["sms.sms"].search_count([("partner_id", "=", partner_id)])
        self.assertEqual(
            sms_count,
            1,
            "Exactly one SMS message should be sent to the host's partner.",
        )

    def test_host_notify_mail(self):

        self.station.notify_email = True
        with self.mock_mail_gateway():
            self.visitor_1.state = "checked_in"
        self.assertSentEmail('"OdooBot" <odoobot@example.com>', self.partner_1)

    def test_host_notify_sms(self):

        self.station.notify_sms = True
        self.visitor_1.state = "checked_in"
        sms = self.env["sms.sms"].search_count(
            [("partner_id", "=", self.employee_1.user_id.partner_id.id)]
        )
        self.assertEqual(sms, 1)

    def test_responsible_notify_discuss(self):

        self.station.write(
            {
                "responsible_ids": [(4, self.user_1.id)],
            }
        )
        responsible_name = self.station.responsible_ids.name
        self.visitor_1.state = "checked_in"
        self.assert_discuss_notification(responsible_name)

    def test_visitor_drink_notify_discuss(self):

        self.visitor_2.write(
            {
                "drink_ids": [(4, self.drink.id)],
            }
        )
        notify_drink_user = self.visitor_2.drink_ids.notify_user_ids.name
        self.visitor_2.state = "checked_in"
        self.assert_discuss_notification(notify_drink_user)

    def test_check_and_notify_visitor_host_on_leave(self):

        check_in_time = datetime.now()
        self.env["resource.schedule.exception"].create(
            {
                "name": "Host Leave",
                "date_from": check_in_time - timedelta(hours=1),
                "date_to": check_in_time + timedelta(hours=1),
                "resource_id": self.employee_1.resource_id.id,
                "calendar_id": self.env.company.resource_calendar_id.id,
            }
        )

        visitor_data = {
            "name": "Visitor_Notify_1",
            "email": "visitornotify@example.com",
            "phone_ids": [Command.create({"number": "1234567890", "type": "mobile"})],
            "station_id": self.station.id,
            "host_ids": [(Command.link(self.employee_1.id))],
            "check_in": check_in_time,
        }

        with self.mock_mail_gateway(), self.mockSMSGateway():
            visitor1 = self.env["frontdesk.visitor"].create(visitor_data)

        visitor_messages = visitor1.message_ids.filtered(
            lambda m: m.message_type in ("comment", "sms")
        )
        self.assertEqual(
            len(visitor_messages), 2, "Visitor should receive 1 email and 1 SMS"
        )
        self.assertEqual(
            set(visitor_messages.mapped("message_type")),
            {"comment", "sms"},
            "Visitor should receive 1 email and 1 SMS",
        )


@tagged("post_install", "-at_install")
class TestKioskUrlGeneration(TransactionCase):
    def test_kiosk_url_generation(self):
        Website = self.env["ir.module.module"].sudo().search([("name", "=", "website")])
        if not Website or Website.state != "installed":
            self.skipTest("The 'website' module is not installed, skipping the test.")

        website = self.env["website"].create(
            {
                "name": "Test Website",
            }
        )

        station = self.env["frontdesk.frontdesk"].create(
            {
                "name": "test_1",
                "host_selection": True,
            }
        )
        station.company_id.website_id = website
        old = station.kiosk_url

        website.domain = "https://www.test.com"
        station._compute_kiosk_url()
        new = station.kiosk_url

        self.assertEqual(
            old, new, "HR related links should not be changed by the website domain."
        )


@tagged("post_install", "-at_install")
class TestFrontdeskGroupReferences(TransactionCase):
    def _referenced_groups(self):
        source = (
            Path(Manifest.for_addon("frontdesk").path) / "controllers" / "main.py"
        ).read_text()
        return set(re.findall(r"has_group\(\s*['\"]([^'\"]+)['\"]", source))

    def test_every_group_the_controllers_name_exists(self):
        referenced = self._referenced_groups()
        self.assertTrue(referenced, "the scan reached no group reference")
        definitions = self.env["res.groups"]._get_group_definitions()
        unresolved = {ref for ref in referenced if definitions.get_id(ref) is None}
        self.assertFalse(
            unresolved,
            f"a group reference resolves to nothing, so the route denies everyone: {unresolved}",
        )

    def test_the_check_out_gate_admits_a_frontdesk_user(self):
        user = self.env["res.users"].create(
            {
                "name": "Frontdesk User",
                "login": "frontdesk_group_probe",
                "group_ids": [
                    Command.link(self.env.ref("frontdesk.frontdesk_group_user").id)
                ],
            }
        )
        self.assertTrue(
            [ref for ref in self._referenced_groups() if user.has_group(ref)],
            "no group the check-out route gates on admits a frontdesk user",
        )


@tagged("post_install", "-at_install")
class TestPhoneTypedOnVisitorForm(TransactionCase):
    def test_a_number_typed_on_a_visitor_takes_its_stations_country(self):
        self.env.company.country_id = self.env.ref("base.fr")
        us = self.env.ref("base.us")
        office = self.env["res.company"].create({"name": "Office", "country_id": us.id})
        station = self.env["frontdesk.frontdesk"].create(
            {"name": "Lobby", "company_id": office.id}
        )
        visitor = self.env["frontdesk.visitor"].create(
            {"name": "Guest", "station_id": station.id, "company_id": office.id}
        )

        context = Form(
            visitor, view="frontdesk.frontdesk_visitor_view_form"
        )._get_context("phone_ids")

        Phone = self.env["phone.number"]
        phone_id, _ = Phone.with_context(context).name_create("202 555 0700")
        self.assertEqual(Phone.browse(phone_id).country_id, us)


@tagged("post_install", "-at_install")
class TestVisitorStationCompany(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.office = cls.env["res.company"].create({"name": "Office"})
        cls.station = cls.env["frontdesk.frontdesk"].create(
            {"name": "Lobby", "company_id": cls.office.id, "ask_email": "required"}
        )
        cls.host = cls.env["hr.employee"].create(
            {
                "name": "Host",
                "company_id": cls.office.id,
                "work_email": "host@example.com",
            }
        )

    def test_a_visitor_belongs_to_its_stations_company(self):
        self.assertNotEqual(self.env.company, self.office)

        visitor = self.env["frontdesk.visitor"].create(
            {"name": "Guest", "station_id": self.station.id}
        )

        self.assertEqual(visitor.company_id, self.office)

    def test_a_visitor_follows_its_station_into_another_company(self):
        visitor = self.env["frontdesk.visitor"].create(
            {"name": "Guest", "station_id": self.station.id}
        )
        branch = self.env["res.company"].create({"name": "Branch"})

        self.station.company_id = branch

        self.assertEqual(visitor.company_id, branch)

    def test_a_host_is_on_leave_on_the_stations_company_holiday(self):
        self.assertNotEqual(
            self.env.company.resource_calendar_id, self.office.resource_calendar_id
        )
        check_in = datetime.now()
        self.env["resource.schedule.exception"].create(
            {
                "name": "Office Holiday",
                "date_from": check_in - timedelta(hours=1),
                "date_to": check_in + timedelta(hours=1),
                "calendar_id": self.office.resource_calendar_id.id,
            }
        )

        visitor = self.env["frontdesk.visitor"].create(
            {
                "name": "Guest",
                "email": "guest@example.com",
                "station_id": self.station.id,
                "host_ids": [Command.link(self.host.id)],
                "check_in": check_in,
            }
        )

        self.assertIn(
            "Your host isn't available", visitor.message_ids.mapped("subject")
        )

    def test_visitors_of_two_companies_hear_of_their_own_hosts_leave(self):
        branch = self.env["res.company"].create({"name": "Branch"})
        branch_station = self.env["frontdesk.frontdesk"].create(
            {"name": "Hall", "company_id": branch.id, "ask_email": "required"}
        )
        branch_host = self.env["hr.employee"].create(
            {
                "name": "Branch Host",
                "company_id": branch.id,
                "work_email": "b@example.com",
            }
        )
        check_in = datetime.now()
        for company in (self.office, branch):
            self.env["resource.schedule.exception"].create(
                {
                    "name": "Holiday",
                    "date_from": check_in - timedelta(hours=1),
                    "date_to": check_in + timedelta(hours=1),
                    "calendar_id": company.resource_calendar_id.id,
                }
            )

        visitors = self.env["frontdesk.visitor"].create(
            [
                {
                    "name": name,
                    "email": f"{name}@example.com",
                    "station_id": station.id,
                    "host_ids": [Command.link(host.id)],
                    "check_in": check_in,
                }
                for name, station, host in (
                    ("office-guest", self.station, self.host),
                    ("branch-guest", branch_station, branch_host),
                )
            ]
        )

        for visitor, company, host in zip(
            visitors, (self.office, branch), (self.host, branch_host), strict=True
        ):
            notice = visitor.message_ids.filtered(
                lambda message: message.subject == "Your host isn't available"
            )
            self.assertEqual(notice.author_id, company.partner_id)
            self.assertIn(host.name, notice.body)

    def test_checking_in_visitors_with_drinks_notifies_each_drinks_people(self):
        barista = self.env.ref("base.user_admin")
        drink = self.env["frontdesk.drink"].create(
            {"name": "Tea", "notify_user_ids": [Command.link(barista.id)]}
        )
        visitors = self.env["frontdesk.visitor"].create(
            [
                {
                    "name": name,
                    "station_id": self.station.id,
                    "drink_ids": [Command.link(drink.id)],
                }
                for name in ("First", "Second")
            ]
        )

        visitors.write({"state": "checked_in"})

        chat = self.env["discuss.channel"]._get_or_create_chat(barista.partner_id.ids)
        drink_notices = [
            body
            for body in chat.message_ids.mapped("body")
            if "Requested Drink" in body
        ]
        self.assertEqual(len(drink_notices), 2)
        for visitor in visitors:
            self.assertTrue(
                any(f'/{visitor.id}">{visitor.name}</a>' in b for b in drink_notices)
            )
