from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestStockBarcodeAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "stock_user_a": Persona("stock.group_stock_user"),
        "stock_manager_a": Persona("stock.group_stock_manager"),
    }
    cells = (
        Cell(
            "stock.picking.type",
            "operation_type_a",
            note="an inventory user prints the barcode sheets",
            employee_a="r",
            stock_user_a="r print_barcode_sheet",
            stock_manager_a="rwcd print_barcode_sheet",
        ),
        Cell(
            "stock.picking.type",
            "operation_type_b",
            note="another company's operation type",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        return {
            "operation_type_a": cls.env.ref("stock.picking_type_in"),
            "operation_type_b": cls.env["stock.picking.type"].search(
                [("company_id", "=", cls.companies["b"].id)], limit=1
            ),
        }
