from lxml import html

from odoo import Command, http
from odoo.exceptions import ValidationError
from odoo.tests import freeze_time, tagged
from odoo.tools import mute_logger

from odoo.addons.account_payment_provider.tests.common import AccountPaymentCommon
from odoo.addons.appointment_account_payment.tests.common import (
    AppointmentAccountPaymentCommon,
)
from odoo.addons.payment.tests.http_common import PaymentHttpCommon


class AppointmentAccountPaymentFlowsCommon(
    AccountPaymentCommon, AppointmentAccountPaymentCommon, PaymentHttpCommon
):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.calendar_booking = cls.env["calendar.booking"].create(
            {
                "appointment_type_id": cls.appointment_users_payment.id,
                "duration": 1.0,
                "partner_id": cls.apt_manager.partner_id.id,
                "product_id": cls.appointment_users_payment.product_id.id,
                "staff_user_id": cls.staff_user_bxls.id,
                "start": cls.start_slot,
                "stop": cls.stop_slot,
            }
        )
        cls.booking_invoice = cls.calendar_booking._create_booking_invoices()

    @classmethod
    def get_default_groups(cls):
        return super().get_default_groups() | cls.quick_ref(
            "calendar.group_appointment_manager"
        )


@tagged("-at_install", "post_install")
class AppointmentAccountPaymentFlowsTest(AppointmentAccountPaymentFlowsCommon):
    """Code is inspired from TestFlows and (Http)Common classes in payment module,
    as well as TestFlows in account_payment module."""

    def test_cancellation_cannot_orphan_a_delayed_payment(self):
        self.authenticate("apt_manager", "apt_manager")
        tx = self._create_transaction(
            "direct",
            invoice_ids=[Command.set(self.booking_invoice.ids)],
            amount=self.booking_invoice.amount_total,
            partner_id=self.booking_invoice.partner_id.id,
            currency_id=self.booking_invoice.currency_id.id,
        )
        tx._set_pending()
        response = self.url_open(
            f"/calendar_booking/{self.calendar_booking.booking_token}/cancel",
            data={"csrf_token": http.Request.csrf_token(self)},
            allow_redirects=False,
        )
        tx._set_done()
        tx._post_process()
        self.assertTrue(tx.payment_id)
        self.assertEqual(self.booking_invoice.state, "posted")
        self.assertTrue(self.booking_invoice.calendar_booking_ids.calendar_event_id)
        self.assertEqual(response.status_code, 409)

    def test_cancelled_booking_invoice_cannot_start_payment(self):
        self.assertTrue(self.calendar_booking._cancel_pending_booking())
        self.assertEqual(self.booking_invoice.state, "cancel")
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._create_transaction(
                "direct",
                invoice_ids=[Command.set(self.booking_invoice.ids)],
                amount=self.booking_invoice.amount_total,
            )
        self.assertFalse(self.booking_invoice.transaction_ids)

    def test_draft_payment_already_prevents_booking_cancellation(self):
        tx = self._create_transaction(
            "direct", invoice_ids=[Command.set(self.booking_invoice.ids)]
        )
        self.assertEqual(tx.state, "draft")
        self.assertFalse(self.calendar_booking._cancel_pending_booking())
        self.assertTrue(self.calendar_booking.exists())
        self.assertEqual(self.booking_invoice.state, "draft")

    def test_cancellation_cannot_cancel_another_bookings_invoice(self):
        other = self.calendar_booking.copy({"account_move_id": self.booking_invoice.id})
        self.assertFalse(self.calendar_booking._cancel_pending_booking())
        self.assertTrue(self.calendar_booking.exists())
        self.assertTrue(other.exists())
        self.assertEqual(self.booking_invoice.state, "draft")

    def test_booking_cancellation_requires_post_and_csrf(self):
        self.authenticate("apt_manager", "apt_manager")
        booking = self.calendar_booking
        url = f"/calendar_booking/{booking.booking_token}/cancel"
        response = self.url_open(url, allow_redirects=False)
        self.assertEqual(response.status_code, 405)
        self.assertTrue(booking.exists())

        for data in ({"csrf_token": "invalid"}, {"submit": "cancel"}):
            response = self.url_open(url, data=data)
            self.assertEqual(response.status_code, 400)
            self.assertTrue(booking.exists())

        response = self.url_open(
            url,
            data={"csrf_token": http.Request.csrf_token(self)},
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertFalse(booking.exists())

    def test_public_booking_cancellation_requires_post_and_csrf(self):
        self.authenticate(None, None)
        url = f"/calendar_booking/{self.calendar_booking.booking_token}/cancel"
        self.assertEqual(self.url_open(url).status_code, 405)
        self.assertEqual(self.url_open(url, data={"submit": "cancel"}).status_code, 400)
        self.assertTrue(self.calendar_booking.exists())
        response = self.url_open(
            url,
            data={"csrf_token": http.Request.csrf_token(self)},
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertFalse(self.calendar_booking.exists())

    def test_confirmed_booking_cannot_be_cancelled(self):
        self.authenticate("apt_manager", "apt_manager")
        self.calendar_booking._create_event_from_paid_booking()
        event = self.calendar_booking.calendar_event_id
        self.assertTrue(event)
        response = self.url_open(
            f"/calendar_booking/{self.calendar_booking.booking_token}/cancel",
            data={"csrf_token": http.Request.csrf_token(self)},
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(self.calendar_booking.exists())
        self.assertTrue(event.exists())

    def test_appointment_successful_payment_flow(self):
        token = self._generate_test_access_token(
            self.booking_invoice.partner_id.id,
            self.booking_invoice.amount_total,
            self.booking_invoice.currency_id.id,
        )
        payment_page_url = self._build_url("/payment/pay")
        route_kwargs = {
            "appointment_type_id": self.appointment_users_payment.id,
            "invoice_id": self.booking_invoice.id,
            "access_token": token,
            "amount": self.booking_invoice.amount_total,
        }
        self.authenticate("apt_manager", "apt_manager")
        response = self._make_http_get_request(payment_page_url, route_kwargs)
        self.assertEqual(response.status_code, 200)
        cancel_form = html.fromstring(response.content).xpath(
            "//form[contains(@action, '/cancel')]"
        )
        self.assertEqual(len(cancel_form), 1)
        self.assertEqual(cancel_form[0].get("method"), "post")
        self.assertTrue(cancel_form[0].xpath(".//input[@name='csrf_token']/@value"))

        tx_context = self._get_payment_context(response)
        tx_url = self._build_url(tx_context["transaction_route"])
        tx_route_kwargs = {
            "access_token": tx_context["access_token"],
            "amount": tx_context["amount"],
            "flow": "direct",
            "landing_route": tx_context["landing_route"],
            "payment_method_id": self.payment_method_id,
            "provider_id": self.provider.id,
            "token_id": False,
            "tokenization_requested": False,
        }
        with mute_logger("odoo.addons.payment.models.payment_transaction"):
            processing_values = self._get_processing_values(
                tx_route=tx_url, **tx_route_kwargs
            )

        tx_sudo = self._get_tx(processing_values["reference"])
        self.booking_invoice.invalidate_recordset(["transaction_ids"])
        self.assertEqual(self.booking_invoice.transaction_ids, tx_sudo)

        tx_sudo._set_done()
        tx_sudo._post_process()

        self.assertTrue(self.booking_invoice.calendar_booking_ids.calendar_event_id)

        landing_page_url = self._build_url(tx_context["landing_route"])
        response = self._make_http_get_request(landing_page_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("/calendar/view", response.url)

    @freeze_time("2022-02-14")
    def test_appointment_service_product_type_appointment(self):
        if (
            self.env["ir.module.module"].search([("name", "=", "sale_project")]).state
            == "uninstalled"
        ):
            self.skipTest("This test won't work if sale_project is not installed")
        service_product = self.env.ref(
            "appointment_account_payment.default_booking_product"
        )
        service_product.service_tracking = "task_global_project"
        service_product.list_price = 0
        service_appt_type = self.env["appointment.type"].create(
            {
                "appointment_tz": "Europe/Brussels",
                "name": "Test Appt Type",
                "product_id": service_product.id,
                "has_payment_step": True,
                "staff_user_ids": [(4, self.staff_user_bxls.id)],
                "question_ids": False,
            }
        )
        self.authenticate(self.env.user.login, self.env.user.login)
        self.url_open(
            f"/appointment/{service_appt_type.id}/submit",
            {
                "csrf_token": http.Request.csrf_token(self),
                "datetime_str": "2022-02-14 11:00:00",
                "duration_str": "1.0",
                "email": "test1@test.example.com",
                "name": "Test",
                "staff_user_id": self.staff_user_bxls.id,
            },
        )
        self.assertTrue(
            self.env["calendar.booking"].search(
                [
                    ("appointment_type_id", "=", service_appt_type.id),
                ]
            ),
            "Calendar booking should have been created.",
        )
