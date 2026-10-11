from datetime import timedelta

from odoo import Command, fields
from odoo.tests import HttpCase, tagged

from odoo.addons.industry_fsm_sale.tests.common import TestFsmFlowCommon


@tagged("-at_install", "post_install")
class TestFsmSaleProducts(HttpCase, TestFsmFlowCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.my_custom_currency = cls.env["res.currency"].create(
            {
                "name": "TK",
                "symbol": "~M~",
            }
        )
        cls.task.write(
            {
                "user_ids": [Command.link(cls.env.ref("base.user_admin").id)],
                "date_start": fields.Datetime.today() + timedelta(days=1),
                "date_end": fields.Datetime.today() + timedelta(days=2),
            }
        )
        cls.consu_product_ordered.is_featured = True
        cls.my_custom_price_list = cls.env["product.pricelist"].create(
            {
                "name": "TKPriceList",
                "currency_id": cls.my_custom_currency.id,
                "item_ids": [
                    Command.create(
                        {
                            "name": "Reduced 2 Individual Workplace Test",
                            "applied_on": "0_product_variant",
                            "product_id": cls.consu_product_ordered.id,
                            "min_quantity": 1,
                            "fixed_price": "1000",
                        }
                    ),
                    Command.create(
                        {
                            "name": "Reduced 2 Individual Workplace Test",
                            "applied_on": "0_product_variant",
                            "product_id": cls.consu_product_ordered.id,
                            "min_quantity": 2,
                            "fixed_price": "500",
                        }
                    ),
                ],
            }
        )
        cls.partner_1.property_product_pricelist = cls.my_custom_price_list
        cls.task.partner_id = cls.partner_1

    def test_industry_fsm_sale_products_tour(self):
        self.start_tour("/odoo", "industry_fsm_sale_products_tour", login="admin")

    def test_industry_fsm_sale_quantity_products_tour(self):
        self.start_tour(
            "/odoo", "industry_fsm_sale_quantity_products_tour", login="admin"
        )

    def test_industry_fsm_sale_products_from_fsm_tour(self):
        self.partner_1.name = "fsm tester"
        admin = self.env.ref("base.user_admin")
        field_service = self.env.ref("industry_fsm_sale.field_service_product")
        main_so = (
            self.env["sale.order"]
            .with_context(default_user_id=admin.id)
            .create(
                {
                    "partner_id": self.partner_1.id,
                    "line_ids": [
                        Command.create(
                            {
                                "name": "task 1",
                                "product_id": field_service.id,
                            }
                        ),
                        Command.create(
                            {
                                "name": "task 2",
                                "product_id": field_service.id,
                            }
                        ),
                        Command.create(
                            {
                                "name": "task 3",
                                "product_id": field_service.id,
                            }
                        ),
                    ],
                }
            )
        )
        main_so.action_confirm()
        super_product = self.env["product.product"].create(
            {
                "name": "Super Product",
                "invoice_policy": "transferred",
                "list_price": 100.0,
            }
        )
        super_product.product_tmpl_id.is_featured = True
        self.start_tour(
            "/odoo", "industry_fsm_sale_products_compute_catalog_tour", login="admin"
        )
        self.assertTrue(
            main_so.line_ids.filtered(
                lambda sol: (
                    "task 1" in sol.task_id.name and sol.product_id == super_product
                )
            )
        )
        self.assertTrue(
            main_so.line_ids.filtered(
                lambda sol: (
                    "task 2" in sol.task_id.name and sol.product_id == super_product
                )
            )
        )
        self.assertTrue(
            main_so.line_ids.filtered(
                lambda sol: (
                    "task 3" in sol.task_id.name and sol.product_id == super_product
                )
            )
        )

    def test_sol_sequence(self):
        sale_order = self.env["sale.order"].create(
            {
                "partner_id": self.partner_1.id,
                "line_ids": [
                    Command.create(
                        {
                            "name": "",
                            "product_id": self.env["product.product"]
                            .create(
                                {
                                    "name": "pet",
                                    "type": "service",
                                    "list_price": 100,
                                    "service_policy": "ordered_prepaid",
                                    "project_id": self.fsm_project.id,
                                    "service_tracking": "task_global_project",
                                }
                            )
                            .id,
                            "product_qty": 1.0,
                        }
                    ),
                    Command.create(
                        {
                            "name": "",
                            "product_id": self.consu_product_ordered.id,
                            "product_qty": 1.0,
                        }
                    ),
                ],
            }
        )
        previous_sale_order_line_ids = sale_order.line_ids.ids
        sale_order.action_confirm()
        self.consu_product_delivered.with_context(
            fsm_task_id=sale_order.line_ids.task_id.id
        ).set_fsm_quantity(1)

        self.assertNotIn(
            sale_order.line_ids.ids[-1],
            previous_sale_order_line_ids,
            "The last SOL should be the one that was added after the confirmation of the SO.",
        )

    def test_industry_fsm_sale_add_product_on_invoice(self):
        self.env["product.product"].create(
            {
                "name": "Sale Product",
                "invoice_policy": "ordered",
                "list_price": 100,
                "sale_ok": True,
                "purchase_ok": False,
            }
        )
        sale_order_1 = self.env["sale.order"].create(
            {
                "partner_id": self.partner_1.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.consu_product_ordered.id,
                            "product_qty": 10,
                        }
                    )
                ],
            }
        )

        self.task.update(
            {
                "sale_order_id": sale_order_1.id,
            }
        )
        sale_order_1.action_confirm()
        sale_order_1._create_invoices()
        self.start_tour(
            "/odoo/field-service",
            "test_industry_fsm_sale_add_product_on_invoice_tour",
            login="admin",
        )
