from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import pool_step


@tagged("post_install", "-at_install")
class TestApprovalRequestCount(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.company.so_validation_level = "manager_amount"

        cls.env["approval.category"].search(
            [("approval_type", "=", "sale"), ("target_model", "=", False)],
        ).write({"active": False})

        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Count Customer",
                "customer_rank": 1,
                "property_payment_term_id": cls.env.ref(
                    "payment_term.account_payment_term_immediate"
                ).id,
            },
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Count Product", "type": "consu"},
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Count Category",
                "approval_type": "sale",
                "target_model": False,
                "approval_minimum": 1,
                "allow_self_approval": True,
                "so_approval_mode": "combined",
                "company_id": cls.company.id,
                "step_ids": pool_step([(cls.env.user.id, True, 10)], minimum=1),
            },
        )

    def _source_request(self):
        category = self.env["approval.category"].create(
            {
                "name": "Count Source Category",
                "approval_type": "sale",
                "target_model": "sale.order",
                "approval_minimum": 1,
                "company_id": self.company.id,
            },
        )
        return self.env["approval.request"].create(
            {
                "name": "Count Source",
                "category_id": category.id,
                "request_owner_id": self.env.user.id,
                "company_id": self.company.id,
            },
        )

    def _order_from(self, request):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "company_id": self.company.id,
            },
        )
        request._link_produced_documents(order)
        return order

    def _pending_order(self, price=20000.0):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "price_unit": price,
                        },
                    ),
                ],
            },
        )
        order.action_confirm()
        return order

    def test_a_request_with_no_orders_counts_zero(self):
        request = self.env["approval.request"].create(
            {
                "name": "Empty Request",
                "category_id": self.category.id,
                "request_owner_id": self.env.user.id,
                "company_id": self.company.id,
            },
        )

        self.assertEqual(request.count_sale_order, 0)

    def test_the_mixin_leg_is_counted(self):
        order = self._pending_order()

        self.assertEqual(order.approval_request_id.count_sale_order, 1)

    def test_two_orders_on_one_request_count_once_each(self):
        request = self._source_request()
        self._order_from(request)
        self._order_from(request)
        self.env.invalidate_all()

        self.assertEqual(request.count_sale_order, 2)

    def test_the_count_is_right_across_a_recordset(self):
        first = self._pending_order().approval_request_id
        second = self._source_request()
        self._order_from(second)
        self._order_from(second)

        requests = first | second
        self.env.invalidate_all()

        self.assertEqual(
            [request.count_sale_order for request in requests],
            [1, 2],
        )

    def test_the_recordset_read_does_not_search_per_record(self):
        requests = self.env["approval.request"]
        for _ in range(4):
            requests |= self._pending_order().approval_request_id

        self.env.invalidate_all()
        with self.assertQueryCount(__system__=3):
            requests.mapped("count_sale_order")
