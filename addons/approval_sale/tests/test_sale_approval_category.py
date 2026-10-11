from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSaleApprovalCategory(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Test Customer",
                "company_id": cls.company.id,
                "customer_rank": 1,
            },
        )

        cls.product_categ = cls.env["product.category"].create(
            {
                "name": "Test Category",
            },
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Product",
                "type": "consu",
                "list_price": 100.0,
                "categ_id": cls.product_categ.id,
            },
        )

    def test_approval_type_sale_option(self):
        category = self.env["approval.category"].create(
            {
                "name": "Sales Category",
                "company_id": self.company.id,
                "approval_type": "sale",
            },
        )

        self.assertEqual(category.approval_type, "sale")

    def test_target_model_sale_order_option(self):
        category = self.env["approval.category"].create(
            {
                "name": "Sales Order Target Category",
                "company_id": self.company.id,
                "target_model": "sale.order",
            },
        )

        self.assertEqual(category.target_model, "sale.order")

    def test_so_approval_mode_options(self):
        modes = ["amount", "partner", "product", "credit", "combined"]

        for mode in modes:
            category = self.env["approval.category"].create(
                {
                    "name": f"Mode {mode} Category",
                    "company_id": self.company.id,
                    "approval_type": "sale",
                    "so_approval_mode": mode,
                },
            )
            self.assertEqual(category.so_approval_mode, mode)

    def test_so_approval_mode_drops_unimplemented_user_option(self):
        modes = dict(
            self.env["approval.category"]._fields["so_approval_mode"].selection,
        )
        self.assertNotIn("user", modes)

    def test_order_amount_range_validation_valid(self):
        category = self.env["approval.category"].create(
            {
                "name": "Valid Amount Range Category",
                "company_id": self.company.id,
                "approval_type": "sale",
                "order_amount_min": 100.0,
                "order_amount_max": 500.0,
            },
        )

        self.assertEqual(category.order_amount_min, 100.0)
        self.assertEqual(category.order_amount_max, 500.0)

    def test_order_amount_range_validation_min_equals_max(self):
        category = self.env["approval.category"].create(
            {
                "name": "Equal Amount Category",
                "company_id": self.company.id,
                "approval_type": "sale",
                "order_amount_min": 100.0,
                "order_amount_max": 100.0,
            },
        )

        self.assertEqual(category.order_amount_min, category.order_amount_max)

    def test_order_amount_range_validation_invalid(self):
        with self.assertRaises(ValidationError):
            self.env["approval.category"].create(
                {
                    "name": "Invalid Amount Range Category",
                    "company_id": self.company.id,
                    "approval_type": "sale",
                    "order_amount_min": 500.0,
                    "order_amount_max": 100.0,
                },
            )

    def test_order_amount_max_zero_means_no_limit(self):
        category = self.env["approval.category"].create(
            {
                "name": "No Max Limit Category",
                "company_id": self.company.id,
                "approval_type": "sale",
                "order_amount_min": 100.0,
                "order_amount_max": 0,
            },
        )

        self.assertEqual(category.order_amount_max, 0)

    def test_order_partner_ids_field(self):
        category = self.env["approval.category"].create(
            {
                "name": "Partner Restricted Category",
                "company_id": self.company.id,
                "approval_type": "sale",
                "order_partner_ids": [(4, self.customer.id)],
            },
        )

        self.assertIn(self.customer, category.order_partner_ids)

    def test_product_categ_ids_field(self):
        category = self.env["approval.category"].create(
            {
                "name": "Product Category Restricted",
                "company_id": self.company.id,
                "approval_type": "sale",
                "product_categ_ids": [(4, self.product_categ.id)],
            },
        )

        self.assertIn(self.product_categ, category.product_categ_ids)

    def test_product_ids_field(self):
        category = self.env["approval.category"].create(
            {
                "name": "Product Restricted Category",
                "company_id": self.company.id,
                "approval_type": "sale",
                "product_ids": [(4, self.product.id)],
            },
        )

        self.assertIn(self.product, category.product_ids)

    def test_the_sales_page_does_not_offer_auto_confirm(self):
        view = self.env.ref("approval_sale.view_approval_category_form_sale")
        self.assertNotIn(
            '<field name="order_auto_confirm"',
            view.arch,
            "a switch the code never reads must not be offered as one",
        )

    def test_check_credit_limit_field(self):
        category = self.env["approval.category"].create(
            {
                "name": "Credit Limit Category",
                "company_id": self.company.id,
                "approval_type": "sale",
                "check_credit_limit": True,
            },
        )

        self.assertTrue(category.check_credit_limit)


@tagged("post_install", "-at_install")
class TestCategoryApplicability(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

        cls.customer1 = cls.env["res.partner"].create(
            {
                "name": "Customer One",
                "company_id": cls.company.id,
            },
        )

        cls.customer2 = cls.env["res.partner"].create(
            {
                "name": "Customer Two",
                "company_id": cls.company.id,
            },
        )

        cls.categ = cls.env["product.category"].create(
            {
                "name": "Special Category",
            },
        )

        cls.product1 = cls.env["product.product"].create(
            {
                "name": "Product One",
                "type": "consu",
                "list_price": 100.0,
                "categ_id": cls.categ.id,
            },
        )

        cls.product2 = cls.env["product.product"].create(
            {
                "name": "Product Two",
                "type": "consu",
                "list_price": 200.0,
            },
        )

    def _create_sale_order(self, partner, products_qty):
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "company_id": self.company.id,
            },
        )

        for product, qty in products_qty:
            self.env["sale.order.line"].create(
                {
                    "order_id": order.id,
                    "product_id": product.id,
                    "product_qty": qty,
                    "price_unit": product.list_price,
                },
            )

        return order

    def test_applicable_wrong_approval_type(self):
        category = self.env["approval.category"].create(
            {
                "name": "General Category",
                "company_id": self.company.id,
                "approval_type": "general",
            },
        )

        order = self._create_sale_order(self.customer1, [(self.product1, 1)])

        self.assertFalse(category._is_applicable_for(order))

    def test_applicable_with_target_model(self):
        category = self.env["approval.category"].create(
            {
                "name": "Creation Flow Category",
                "company_id": self.company.id,
                "approval_type": "sale",
                "target_model": "sale.order",
            },
        )

        order = self._create_sale_order(self.customer1, [(self.product1, 1)])

        self.assertFalse(category._is_applicable_for(order))

    def test_applicable_amount_in_range(self):
        category = self.env["approval.category"].create(
            {
                "name": "Amount Range Category",
                "company_id": self.company.id,
                "approval_type": "sale",
                "order_amount_min": 50.0,
                "order_amount_max": 500.0,
            },
        )

        order = self._create_sale_order(self.customer1, [(self.product1, 1)])

        self.assertTrue(category._is_applicable_for(order))

    def test_applicable_amount_below_min(self):
        category = self.env["approval.category"].create(
            {
                "name": "High Amount Category",
                "company_id": self.company.id,
                "approval_type": "sale",
                "order_amount_min": 500.0,
            },
        )

        order = self._create_sale_order(self.customer1, [(self.product1, 1)])

        self.assertFalse(category._is_applicable_for(order))

    def test_applicable_amount_above_max(self):
        category = self.env["approval.category"].create(
            {
                "name": "Low Amount Category",
                "company_id": self.company.id,
                "approval_type": "sale",
                "order_amount_max": 50.0,
            },
        )

        order = self._create_sale_order(self.customer1, [(self.product1, 1)])

        self.assertFalse(category._is_applicable_for(order))

    def test_applicable_specific_partner(self):
        category = self.env["approval.category"].create(
            {
                "name": "Partner Specific Category",
                "company_id": self.company.id,
                "approval_type": "sale",
                "order_partner_ids": [(4, self.customer1.id)],
            },
        )

        order1 = self._create_sale_order(self.customer1, [(self.product1, 1)])
        order2 = self._create_sale_order(self.customer2, [(self.product1, 1)])

        self.assertTrue(category._is_applicable_for(order1))
        self.assertFalse(category._is_applicable_for(order2))

    def test_applicable_product_category(self):
        category = self.env["approval.category"].create(
            {
                "name": "Product Category Filter",
                "company_id": self.company.id,
                "approval_type": "sale",
                "product_categ_ids": [(4, self.categ.id)],
            },
        )

        order1 = self._create_sale_order(self.customer1, [(self.product1, 1)])
        order2 = self._create_sale_order(self.customer1, [(self.product2, 1)])

        self.assertTrue(category._is_applicable_for(order1))
        self.assertFalse(category._is_applicable_for(order2))

    def test_applicable_specific_product(self):
        category = self.env["approval.category"].create(
            {
                "name": "Product Specific Category",
                "company_id": self.company.id,
                "approval_type": "sale",
                "product_ids": [(4, self.product1.id)],
            },
        )

        order1 = self._create_sale_order(self.customer1, [(self.product1, 1)])
        order2 = self._create_sale_order(self.customer1, [(self.product2, 1)])

        self.assertTrue(category._is_applicable_for(order1))
        self.assertFalse(category._is_applicable_for(order2))

    def test_applicable_combined_conditions(self):
        category = self.env["approval.category"].create(
            {
                "name": "Combined Category",
                "company_id": self.company.id,
                "approval_type": "sale",
                "order_amount_min": 50.0,
                "order_partner_ids": [(4, self.customer1.id)],
                "product_ids": [(4, self.product1.id)],
            },
        )

        order_match = self._create_sale_order(self.customer1, [(self.product1, 1)])
        self.assertTrue(category._is_applicable_for(order_match))

        order_wrong_partner = self._create_sale_order(
            self.customer2, [(self.product1, 1)]
        )
        self.assertFalse(category._is_applicable_for(order_wrong_partner))

        order_wrong_product = self._create_sale_order(
            self.customer1, [(self.product2, 1)]
        )
        self.assertFalse(category._is_applicable_for(order_wrong_product))

    def test_the_sales_page_does_not_repeat_target_model(self):
        view = self.env.ref("approval_sale.view_approval_category_form_sale")
        self.assertNotIn(
            '<field name="target_model"',
            view.arch,
            "base already renders target_model in general_group, always "
            "visible; a second editable widget gives one field two labels",
        )

        arch = self.env["approval.category"].get_view(
            self.env.ref("approval.view_approval_category_form").id,
            "form",
        )["arch"]
        self.assertIn("target_model", arch)

    def test_the_shipped_category_has_no_floor(self):
        category = self.env.ref("approval_sale.approval_category_sale_order")
        self.assertFalse(
            category.order_amount_min,
            "the only shipped sale category must not floor the amount it "
            "approves: an order below the company threshold requires approval "
            "whenever its creator is not a sales manager, so a floor leaves "
            "the ordinary small order matching nothing",
        )

        small = self._create_sale_order(self.customer1, [(self.product1, 1)])
        self.assertLess(small.amount_total, self.env.company.so_validation_amount)
        self.assertTrue(
            category._is_applicable_for(small.with_company(self.env.company)),
            "a small order that requires approval must still match",
        )

    def test_the_shipped_category_has_no_ceiling(self):
        category = self.env.ref("approval_sale.approval_category_sale_order")
        self.assertFalse(
            category.order_amount_max,
            "the only shipped sale category must not cap the amount it approves",
        )

        company = self.env.company
        big = self._create_sale_order(
            self.customer1, [(self.product1, 10 * company.so_validation_amount)]
        )
        self.assertGreater(big.amount_total, company.so_validation_amount)
        self.assertTrue(
            category._is_applicable_for(big.with_company(company)),
            "an order well above the validation threshold must still match",
        )
