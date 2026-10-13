from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestStockFleetProofAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "stock_user_a": Persona("stock.group_stock_user"),
        "reviewer_a": Persona("stock_fleet.group_delivery_proof_reviewer"),
    }
    cells = (
        Cell(
            "stock.picking",
            "delivery",
            note="a customer's confirmation ticks the evidence only through "
            "stock_fleet_proof.privilege_accept_customer_confirmation, which no "
            "user holds; stock users work the delivery, reviewers also accept "
            "and reject its evidence",
            stock_user_a="rwcd validate",
            reviewer_a="rwcd validate accept_delivery_proof reject_delivery_proof "
            "change_delivery_evidence receive_delivery_paper return_delivery_paper",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        warehouse = env["stock.warehouse"].search(
            [("company_id", "=", cls.companies["a"].id)], limit=1
        )
        product = env["product.product"].create({"name": "Matrix Freight"})
        picking = env["stock.picking"].create(
            {
                "picking_type_id": warehouse.out_type_id.id,
                "partner_id": env["res.partner"].create({"name": "Matrix Customer"}).id,
                "location_id": warehouse.lot_stock_id.id,
                "location_dest_id": env.ref("stock.stock_location_customers").id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_uom_qty": 1,
                            "location_id": warehouse.lot_stock_id.id,
                            "location_dest_id": env.ref(
                                "stock.stock_location_customers"
                            ).id,
                        }
                    )
                ],
            }
        )
        return {"delivery": picking}
