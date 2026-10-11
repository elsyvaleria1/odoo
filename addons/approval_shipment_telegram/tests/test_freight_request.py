from datetime import datetime

from odoo import Command
from odoo.tests import tagged

from odoo.addons.approval.tests.common import add_category_approver
from odoo.addons.telegram.tests.common import TelegramBotTestCase
from odoo.addons.telegram.tools.authority import operating

SHEET = {
    "destination": "TAPACHULA, CHIS.",
    "service": "ocurre",
    "date": "2026-10-08",
    "subtotal": 4078.66,
    "tax_amount": 652.59,
    "tax_withheld": 0.0,
    "total": 4731.25,
}


@tagged("post_install", "-at_install")
class TestFreightRequest(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.freight = cls.env["product.product"].create(
            {"name": "Freight and haulage", "type": "service"}
        )
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", company.id)], limit=1
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Freight and Hauling",
                "approval_type": "accounting",
                "target_model": "account.move",
                "approval_minimum": 1,
                "has_product": "required",
                "has_partner": "required",
                "has_amount": "required",
                "has_reference": "required",
                "has_location": "required",
                "product_ids": [cls.freight.id],
                "journal_ids": [cls.journal.id],
            }
        )
        add_category_approver(
            cls.category, cls.env.ref("base.user_admin"), required=True
        )
        cls.vendor = cls.env["res.partner"].create(
            {
                "name": "Autotransportes de carga Tresguerras",
                "bank_account_ids": [(0, 0, {"acc_number": "13842190"})],
            }
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Tres Guerras",
                "product_id": cls.env["product.product"]
                .create({"name": "Shipping", "type": "service"})
                .id,
                "tracking_ref_pattern": "[A-Z]{3}[0-9]{8}",
                "tracking_ref_example": "TOL01584640",
                "freight_approval_category_id": cls.category.id,
                "freight_partner_id": cls.vendor.id,
            }
        )
        cls.customer = cls.env["res.partner"].create({"name": "Agro Customer"})
        warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", company.id)], limit=1
        )
        cls.out_type = warehouse.out_type_id
        cls.in_type = warehouse.in_type_id

    def _picking(self, picking_type):
        return self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "partner_id": self.customer.id,
                "carrier_id": self.carrier.id,
            }
        )

    def _sheet(self, reference="TOL01584640", values=SHEET):
        return self.env["telegram.shipment.sheet"].create(
            {
                "bot_id": self.test_bot.id,
                "chat_id": self.test_chat.id,
                "tracking_ref": reference,
                "carrier_id": self.carrier.id,
                "extracted": dict(values),
                "file_name": "sheet.jpg",
            }
        )

    def _freights(self):
        return self.env["approval.request"].search(
            [("category_id", "=", self.category.id)]
        )

    def test_a_sheet_on_a_delivery_prepares_the_freight_draft(self):
        picking = self._picking(self.out_type)
        lines = self._sheet()._assign(picking, b"sheet bytes")

        request = self._freights()
        self.assertEqual(len(request), 1)
        self.assertEqual(request.state, "new", "a draft, never submitted by the bot")
        self.assertEqual(request.partner_id, self.vendor)
        self.assertEqual(request.reference, "TOL01584640")
        self.assertEqual(request.amount, 4731.25)
        self.assertEqual(request.journal_id, self.journal)
        self.assertIn("TAPACHULA", request.location)
        self.assertIn("Agro Customer", request.location)
        self.assertEqual(request.date, datetime(2026, 10, 8, 18, 0))
        self.assertEqual(request.line_ids.product_id, self.freight)
        self.assertEqual(request.line_ids.price_unit, 4731.25)
        self.assertIn("13842190", request.reason)
        self.assertEqual(request.attachment_ids.name, "hoja_embarque_TOL01584640.jpg")
        self.assertEqual(request.shipment_picking_ids, picking)
        self.assertEqual(picking.freight_request_ids, request)
        if "approval_request_id" in picking._fields:  # approval_stock's gate
            self.assertFalse(picking.approval_request_id, "not the transfer's gate")
        self.assertIn("prepared as a draft for $4,731.25", "\n".join(lines))

    def test_a_second_sheet_of_the_same_number_joins_the_open_request(self):
        first, second = self._picking(self.out_type), self._picking(self.out_type)
        self._sheet()._assign(first, b"one")
        lines = self._sheet()._assign(second, b"two")
        request = self._freights()
        self.assertEqual(len(request), 1)
        self.assertEqual(request.shipment_picking_ids, first | second)
        self.assertIn("already covers", "\n".join(lines))

    def test_a_sheet_without_a_total_leaves_the_amount_to_fill(self):
        self._sheet(values={"destination": "MORELIA, MICH."})._assign(
            self._picking(self.out_type), b"sheet"
        )
        request = self._freights()
        self.assertEqual((request.state, request.amount), ("new", 0.0))

    def test_a_receipt_prepares_no_freight(self):
        self._sheet()._assign(self._picking(self.in_type), b"sheet")
        self.assertFalse(self._freights())

    def test_a_carrier_without_a_freight_category_prepares_none(self):
        self.carrier.freight_approval_category_id = False
        self._sheet()._assign(self._picking(self.out_type), b"sheet")
        self.assertFalse(self._freights())

    def test_a_sheet_on_several_deliveries_pays_one_freight(self):
        first, second = self._picking(self.out_type), self._picking(self.out_type)
        sheet = self._sheet()
        sheet._assign(first, b"sheet")
        sheet._sibling()._assign(second, b"sheet")
        request = self._freights()
        self.assertEqual(len(request), 1)
        self.assertEqual(request.shipment_picking_ids, first | second)
        self.assertEqual(request.amount, 4731.25, "the sheet's total, once")

    def test_a_sender_the_category_refuses_keeps_the_tracking_number(self):
        self.category.allowed_user_ids = self.env["res.users"].create(
            {"name": "Freight Clerk", "login": "tg_freight_clerk"}
        )
        picking = self._picking(self.out_type)
        sheet = self._sheet()

        lines = sheet._assign(picking, b"sheet")

        self.assertFalse(self._freights(), "no request is left half made")
        self.assertEqual(picking.carrier_tracking_ref, "TOL01584640")
        self.assertEqual(sheet.state, "done")
        self.assertIn("could not prepare the freight request", "\n".join(lines))

    def test_a_sender_who_may_not_join_the_open_freight_keeps_the_number(self):
        self.category.privacy_visibility = "employees"
        first, second = self._picking(self.out_type), self._picking(self.out_type)
        self._sheet()._assign(first, b"one")
        clerk = self.env["res.users"].create(
            {
                "name": "Dock Clerk",
                "login": "tg_dock_clerk",
                "group_ids": [Command.set([self.env.ref("stock.group_stock_user").id])],
            }
        )
        sheet = operating(self._sheet().with_user(clerk))

        lines = sheet._assign(second.with_user(clerk), b"two")

        request = self._freights()
        self.assertEqual(request.shipment_picking_ids, first, "not someone else's")
        self.assertEqual(second.carrier_tracking_ref, "TOL01584640")
        self.assertIn("could not prepare the freight request", "\n".join(lines))
