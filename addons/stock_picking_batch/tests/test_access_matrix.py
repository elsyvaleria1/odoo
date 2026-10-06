from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestStockPickingBatchAccessMatrix(AccessMatrixCase):
    personas = {
        "stock_user_a": Persona("stock.group_stock_user"),
        "stock_manager_a": Persona("stock.group_stock_manager"),
        "employee_a": Persona(),
        "stock_user_b": Persona("stock.group_stock_user", company="b"),
    }
    cells = (
        Cell(
            "stock.picking.batch",
            "batch_a",
            stock_user_a="rwcd",
            stock_manager_a="rwcd",
        ),
    )

    @classmethod
    def build(cls):
        a = cls.companies["a"]
        return {
            "batch_a": cls.env["stock.picking.batch"]
            .with_company(a)
            .create({"company_id": a.id}),
        }
