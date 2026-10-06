from datetime import timedelta

import odoo
from odoo import fields
from odoo.db.schema import column_exists
from odoo.tools import mute_logger

from odoo.addons.base.models.access_link import LinkRefused, hash_token
from odoo.addons.base.models.mixin_bearer_token import hash_bearer_token
from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon
from odoo.addons.portal.utils import is_thread_token_valid


@odoo.tests.tagged("post_install", "-at_install", "access_link")
class TestReceiptLinks(TestPointOfSaleHttpCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({"name": "Receipt customer"})

    def _paid_order(self, reference="Receipt 000000000001"):
        self.main_pos_config.open_ui()
        order = self.env["pos.order"].create(
            {
                "session_id": self.main_pos_config.current_session_id.id,
                "partner_id": self.customer.id,
                "pos_reference": reference,
                "ticket_code": "abcde",
                "amount_tax": 0,
                "amount_total": 0,
                "amount_paid": 0,
                "amount_return": 0,
            }
        )
        order.state = "paid"
        return order

    def _links(self, order):
        return (
            self.env["access.link"]
            .sudo()
            .search([("res_model", "=", "pos.order"), ("res_id", "=", order.id)])
        )

    def test_a_synced_order_gets_a_receipt_link_in_its_customers_name(self):
        self.main_pos_config.open_ui()
        session = self.main_pos_config.current_session_id
        uuid = "33333333-3333-4333-8333-333333333333"
        payload = self.env["pos.order"].sync_from_ui(
            [
                {
                    "uuid": uuid,
                    "session_id": session.id,
                    "company_id": self.env.company.id,
                    "config_id": self.main_pos_config.id,
                    "user_id": self.env.uid,
                    "partner_id": self.customer.id,
                    "state": "draft",
                    "amount_total": 0,
                    "amount_tax": 0,
                    "amount_paid": 0,
                    "amount_return": 0,
                    "lines": [],
                    "payment_ids": [],
                    "date_order": fields.Datetime.to_string(fields.Datetime.now()),
                }
            ]
        )
        order = self.env["pos.order"].search([("uuid", "=", uuid)])
        [sent] = payload["pos.order"]
        self.assertTrue(sent["receipt_token"], "the till is sent the receipt token")
        link = self._links(order)
        self.assertEqual(
            (len(link), link.role, link.cause, link.partner_id),
            (1, "view", "notification", self.customer),
        )
        self.assertAlmostEqual(
            link.date_to,
            fields.Datetime.now() + timedelta(days=365),
            delta=timedelta(minutes=5),
        )
        self.assertEqual(link.token_hash, hash_token(sent["receipt_token"]))
        self.assertEqual(order._receipt_token(), sent["receipt_token"], "reused")
        self.assertNotEqual(sent["receipt_token"], order.access_token)

    @mute_logger("odoo.http")
    def test_the_receipt_token_opens_its_own_order_and_the_bus_token_opens_nothing(
        self,
    ):
        order, other = self._paid_order(), self._paid_order("Receipt 000000000002")
        self.authenticate(None, None)
        url = "/pos/ticket/validate?access_token=%s"
        token = order._receipt_token()
        self.assertEqual(self.url_open(url % token).status_code, 200)
        self.assertEqual(self.url_open(url % order.access_token).status_code, 404)
        self.assertFalse(
            is_thread_token_valid(order, order.access_token),
            "the bus token posts nothing in the order's chatter",
        )
        with self.assertRaises(LinkRefused):
            self.env["access.link"]._resolve(token, model="pos.order", res_id=other.id)
        self._links(order).date_to = fields.Datetime.now() - timedelta(seconds=1)
        self.assertEqual(self.url_open(url % token).status_code, 404, "expired")

    def test_the_bus_token_is_kept_sealed(self):
        order = self._paid_order()
        token = order.access_token
        self.assertTrue(token)
        self.assertFalse(column_exists(self.env.cr, "pos_order", "access_token"))
        self.assertEqual(order.access_token_hash, hash_bearer_token(token))
        self.assertNotIn(token, order.access_token_sealed)
        # a kiosk's handle on its order: found by the token it holds
        self.assertEqual(
            self.env["pos.order"].search([("access_token", "in", [token])]), order
        )
