from lxml import etree

from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestApprovalFlagGroups(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.seller = cls.env["res.users"].create(
            {
                "name": "Plain Seller",
                "login": "sale4_seller",
                "group_ids": [
                    Command.set([cls.env.ref("sale.group_sale_salesman").id]),
                ],
            }
        )
        cls.customer = cls.env["res.partner"].create({"name": "SALE4 Customer"})

    def test_the_customer_flag_is_manager_only(self):
        self.assertEqual(
            self.env["res.partner"]._fields["so_approval_required"].groups,
            "sale.group_sale_manager",
        )
        self.assertNotIn(
            "so_approval_required",
            self.env["res.partner"].with_user(self.seller).fields_get(),
        )

    def test_a_partner_writer_who_is_not_a_sales_manager_is_refused(self):
        # A plain seller cannot write ANY res.partner field, so an AccessError
        # on this one proves nothing about its `groups=` — the model ACL fires
        # first and the assertion holds with the attribute deleted. This user
        # can write res.partner and is not a sales manager, so the only thing
        # left that can refuse is the field attribute itself.
        writer = self.env["res.users"].create(
            {
                "name": "Partner Writer",
                "login": "sale4_partner_writer",
                "group_ids": [
                    Command.set(
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("base.group_partner_manager").id,
                        ],
                    ),
                ],
            }
        )

        with self.assertRaises(AccessError):
            self.customer.with_user(writer).write({"so_approval_required": True})

        # Control: a field on the same model with no `groups=` goes through, so
        # the refusal above is the attribute and not the ACL.
        self.customer.with_user(writer).write({"comment": "written by the same user"})

    def test_flag_still_triggers_approval_for_seller_so(self):
        self.customer.so_approval_required = True
        so = (
            self.env["sale.order"]
            .with_user(self.seller)
            .create({"partner_id": self.customer.id})
        )
        self.assertTrue(
            so.approval_required,
            "the compute reads the flag despite the seller not being a manager",
        )

    def test_the_approval_sections_vanish_with_their_content(self):
        # `so_approval_required` carries `groups=` on the model, so the ORM
        # strips its widget for a plain seller. The wrapping sections carried no
        # `groups=` of their own, so the seller got a titled section with
        # nothing in it. The partner form has no section of ours any more --
        # both fields sit in the base Sales group, which holds other widgets --
        # so there what must vanish is the pair of fields.
        for model, xpath in (
            ("product.category", "//group[@name='sale_approval']"),
            ("product.template", "//group[@name='sales_approval']"),
        ):
            arch = (
                self.env[model]
                .with_user(self.seller)
                .get_view(view_type="form")["arch"]
            )
            tree = etree.fromstring(arch.encode())
            self.assertFalse(
                tree.xpath(xpath),
                f"{model}: the section must go with the fields it holds",
            )
            self.assertFalse(tree.xpath("//field[@name='so_approval_required']"))
            self.assertFalse(tree.xpath("//field[@name='so_approval_notes']"))

        arch = (
            self.env["res.partner"]
            .with_user(self.seller)
            .get_view(view_type="form")["arch"]
        )
        tree = etree.fromstring(arch.encode())
        self.assertTrue(
            tree.xpath("//group[@name='sale']"),
            "the base Sales group stays, it is not ours to hide",
        )
        self.assertFalse(tree.xpath("//field[@name='so_approval_required']"))
        self.assertFalse(tree.xpath("//field[@name='so_approval_notes']"))

    def test_a_sales_manager_still_sees_the_approval_sections(self):
        manager = self.env["res.users"].create(
            {
                "name": "Flag Manager",
                "login": "sale4_manager",
                "group_ids": [
                    Command.set(
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("sale.group_sale_manager").id,
                        ],
                    ),
                ],
            }
        )

        for model, xpath in (
            ("product.category", "//group[@name='sale_approval']"),
            ("product.template", "//group[@name='sales_approval']"),
            ("res.partner", "//group[@name='sale']"),
        ):
            arch = self.env[model].with_user(manager).get_view(view_type="form")["arch"]
            tree = etree.fromstring(arch.encode())
            self.assertTrue(tree.xpath(xpath), model)
            self.assertTrue(tree.xpath("//field[@name='so_approval_required']"), model)
