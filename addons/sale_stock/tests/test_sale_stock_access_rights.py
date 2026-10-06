from odoo.exceptions import AccessError
from odoo.tests import Form, HttpCase, TransactionCase, new_test_user, tagged

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.sale.tests.common import TestSaleCommon


@tagged("post_install", "-at_install")
class TestControllersAccessRights(HttpCase, TestSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portal_user = mail_new_test_user(
            cls.env, login="jimmy-portal", groups="base.group_portal"
        )

    def test_SO_and_DO_portal_acess(self):
        so_form = Form(self.env["sale.order"])
        so_form.partner_id = self.portal_user.partner_id
        with so_form.line_ids.new() as line:
            line.product_id = self.product_a
        so = so_form.save()
        so.action_confirm()
        picking = so.picking_ids

        for login in (None, self.portal_user.login):
            so_url = "/my/orders/%s" % so.id
            picking_url = "/my/picking/pdf/%s" % picking.id

            self.authenticate(login, login)

            if not login:
                so._portal_get_or_create_token()
                so_token = so.access_token
                so_url = "%s?access_token=%s" % (so_url, so_token)
                picking_url = "%s?access_token=%s" % (picking_url, so_token)

            response = self.url_open(
                url=so_url,
                allow_redirects=False,
            )
            self.assertEqual(
                response.status_code,
                200,
                "Should be correct %s"
                % ("with a connected user" if login else "using access token"),
            )
            response = self.url_open(
                url=picking_url,
                allow_redirects=False,
            )
            self.assertEqual(
                response.status_code,
                200,
                "Should be correct %s"
                % ("with a connected user" if login else "using access token"),
            )


@tagged("post_install", "-at_install")
class TestSalespersonCeiling(TransactionCase):
    # a salesperson restricted to their own orders who is also an inventory
    # user reads and changes their own orders only: inventory's access to every
    # order does not widen the salesperson's, as the record rules bounded it
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.seller = new_test_user(
            cls.env,
            login="ceiling_seller",
            groups="sale.group_sale_salesman,stock.group_stock_user",
        )
        cls.other_seller = new_test_user(
            cls.env, login="ceiling_other", groups="sale.group_sale_salesman"
        )
        cls.lead = new_test_user(
            cls.env,
            login="ceiling_lead",
            groups="sale.group_sale_salesman_all_leads,stock.group_stock_user",
        )
        cls.storekeeper = new_test_user(
            cls.env, login="ceiling_storekeeper", groups="stock.group_stock_user"
        )
        partner = cls.env["res.partner"].create({"name": "Ceiling Customer"})
        product = cls.env["product.product"].create({"name": "Ceiling Product"})
        cls.mine, cls.theirs = cls.env["sale.order"].create(
            [
                {
                    "partner_id": partner.id,
                    "user_id": seller.id,
                    "line_ids": [(0, 0, {"product_id": product.id})],
                }
                for seller in (cls.seller, cls.other_seller)
            ]
        )
        cls.orders = cls.mine + cls.theirs

    def visible(self, user, model="sale.order"):
        records = self.orders if model == "sale.order" else self.orders.line_ids
        return self.env[model].with_user(user).search([("id", "in", records.ids)])

    def test_an_own_documents_salesperson_reads_and_changes_their_orders_only(self):
        self.assertEqual(self.visible(self.seller), self.mine)
        self.assertEqual(
            self.visible(self.seller, "sale.order.line"), self.mine.line_ids
        )
        self.mine.with_user(self.seller).write({"client_order_ref": "mine"})

        with self.assertRaises(AccessError):
            self.theirs.with_user(self.seller).write({"client_order_ref": "theirs"})
        with self.assertRaises(AccessError):
            self.theirs.line_ids.with_user(self.seller).check_access("read")

    def test_all_documents_lifts_the_ceiling(self):
        self.assertEqual(self.visible(self.lead), self.orders)
        self.theirs.with_user(self.lead).write({"client_order_ref": "theirs"})

    def test_an_inventory_user_who_sells_nothing_reads_every_order(self):
        self.assertEqual(self.visible(self.storekeeper), self.orders)
        self.assertEqual(
            self.visible(self.storekeeper, "sale.order.line"), self.orders.line_ids
        )
