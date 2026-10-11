from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestFsmStockUI(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Customer Task",
                "email": "customer@task.com",
                "phone_ids": [Command.create({"number": "42", "type": "landline"})],
            }
        )
        cls.user_admin = cls.env.ref("base.user_admin")
        cls.fsm_project = cls.env.ref("industry_fsm.fsm_project")
        today = fields.Date.context_today(cls.fsm_project)
        cls.task = (
            cls.env["project.task"]
            .with_context({"mail_create_nolog": True})
            .create(
                {
                    "name": "Fsm task",
                    "user_ids": cls.user_admin,
                    "partner_id": cls.partner.id,
                    "project_id": cls.fsm_project.id,
                    "date_start": today,
                    "date_end": today + relativedelta(days=1),
                }
            )
        )
        exiting_products = cls.env["product.product"].search(
            [("is_favorite", "!=", False)]
        )
        exiting_products.write({"is_favorite": False})
        cls.product_not_lot, cls.product_lot = cls.env["product.product"].create(
            [
                {
                    "name": "Product A",
                    "invoice_policy": "transferred",
                    "list_price": 885.0,
                    "is_storable": True,
                },
                {
                    "name": "Product B",
                    "list_price": 2950.0,
                    "is_storable": True,
                    "invoice_policy": "transferred",
                    "taxes_id": False,
                    "tracking": "lot",
                },
            ]
        )
        (cls.product_not_lot + cls.product_lot).product_tmpl_id.is_favorite = True
        cls.lot_id1 = cls.env["product.trace"].create(
            {
                "product_id": cls.product_lot.id,
                "name": "Lot_1",
            }
        )
        cls.warehouse_A = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        if not cls.warehouse_A:
            cls.warehouse_A, cls.warehouse_B = cls.env["stock.warehouse"].create(
                [
                    {
                        "name": "WH A",
                        "code": "WHA",
                        "company_id": cls.env.company.id,
                        "partner_id": cls.env.company.partner_id.id,
                    },
                    {
                        "name": "WH B",
                        "code": "WHB",
                        "company_id": cls.env.company.id,
                        "partner_id": cls.env.company.partner_id.id,
                    },
                ]
            )
        else:
            cls.warehouse_B = cls.env["stock.warehouse"].create(
                {
                    "name": "WH B",
                    "code": "WHB",
                    "company_id": cls.env.company.id,
                    "partner_id": cls.env.company.partner_id.id,
                }
            )
        warehouses = [cls.warehouse_A, cls.warehouse_B]
        quants_vals_list = [
            {
                "product_id": cls.product_not_lot.id,
                "inventory_quantity": 4,
                "location_id": warehouse.lot_stock_id.id,
            }
            for warehouse in warehouses
        ] + [
            {
                "product_id": cls.product_lot.id,
                "inventory_quantity": 2,
                "trace_id": cls.lot_id1.id,
                "location_id": warehouse.lot_stock_id.id,
            }
            for warehouse in warehouses
        ]
        quants = (
            cls.env["stock.quant"]
            .with_context(inventory_mode=True)
            .create(quants_vals_list)
        )
        quants.action_apply_inventory()

    def test_ui(self):
        self.user_admin.write({"property_warehouse_id": self.warehouse_A.id})
        self.user_admin.group_ids += self.env.ref("stock.group_production_lot")
        if not self.user_admin.tz:
            self.user_admin.tz = "Europe/Brussels"
        self.start_tour(
            "/odoo", "industry_fsm_stock_test_tour", login=self.user_admin.login
        )
