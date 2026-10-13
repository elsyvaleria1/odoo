from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestAccountCollectionSaleFleetAccessMatrix(AccessMatrixCase):
    personas = {
        "seller_a": Persona(
            "sale.group_sale_salesman",
            "account_collection.group_collection_collector",
        ),
        "stock_a": Persona("stock.group_stock_user"),
        "employee_a": Persona(),
    }
    cells = (
        Cell(
            "stock.picking.batch",
            "delivery_batch_a",
            note=(
                "a collector reads a delivery batch only while reserving the goods "
                "of their cash sale, through "
                "account_collection_sale.privilege_hand_over_cash_sale"
            ),
            stock_a="rwcd",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        a = cls.companies["a"]
        warehouse = env["stock.warehouse"].search([("company_id", "=", a.id)], limit=1)
        batch = (
            env["stock.picking.batch"]
            .with_company(a)
            .create(
                {
                    "picking_type_id": warehouse.out_type_id.id,
                    "company_id": a.id,
                    "picking_ids": [Command.clear()],
                }
            )
        )
        return {"delivery_batch_a": batch}
