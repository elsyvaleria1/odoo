from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestStockBarcodeMrpAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "stock_user_a": Persona("stock.group_stock_user"),
        "mrp_user_a": Persona("mrp.group_mrp_user"),
    }
    cells = (
        Cell(
            "stock.picking.type",
            "operation_type_a",
            note="a manufacturing user prints the manufacturing barcode sheet",
            employee_a="r",
            stock_user_a="r print_barcode_sheet",
            mrp_user_a="r print_barcode_sheet print_mrp_barcode_sheet",
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
