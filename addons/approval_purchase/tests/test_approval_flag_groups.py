from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestApprovalFlagGroups(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.buyer = cls.env["res.users"].create(
            {
                "name": "Plain Buyer",
                "login": "apo2_buyer",
                "group_ids": [
                    Command.set([cls.env.ref("purchase.group_purchase_user").id]),
                ],
            }
        )
        cls.vendor = cls.env["res.partner"].create(
            {"name": "APO2 Vendor", "supplier_rank": 1}
        )

    def test_buyer_cannot_write_vendor_flag(self):
        with self.assertRaises(AccessError):
            self.vendor.with_user(self.buyer).write({"po_approval_required": True})

    def test_buyer_cannot_read_the_vendor_approval_notes(self):
        self.vendor.po_approval_notes = "Verify credentials before approving"

        with self.assertRaises(AccessError):
            self.vendor.with_user(self.buyer).read(["po_approval_notes"])

    def test_notes_still_reach_the_approval_reason_of_a_buyer_po(self):
        self.vendor.po_approval_notes = "Verify credentials before approving"
        product = self.env["product.product"].create(
            {
                "name": "Noted Product",
                "type": "consu",
                "categ_id": self.env["product.category"]
                .create(
                    {
                        "name": "Noted Category",
                        "po_approval_notes": "Category needs a safety sheet",
                    },
                )
                .id,
                "po_approval_notes": "Controlled product",
            },
        )
        po = (
            self.env["purchase.order"]
            .with_user(self.buyer)
            .create(
                {
                    "partner_id": self.vendor.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": product.id,
                                "product_qty": 1.0,
                                "price_unit": 10.0,
                            },
                        ),
                    ],
                },
            )
        )

        reason = po._get_approval_reason_html()

        self.assertIn("Verify credentials", reason)
        self.assertIn("Controlled product", reason)
        self.assertIn("Category needs a safety sheet", reason)

    def test_flag_still_triggers_approval_for_buyer_po(self):
        self.vendor.po_approval_required = True
        po = (
            self.env["purchase.order"]
            .with_user(self.buyer)
            .create({"partner_id": self.vendor.id})
        )
        self.assertTrue(
            po.approval_required,
            "the compute reads the flag despite the buyer not being a manager",
        )
