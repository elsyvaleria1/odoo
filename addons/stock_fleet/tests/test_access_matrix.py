from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestStockFleetAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "stock_user_a": Persona("stock.group_stock_user"),
        "driver_a": Persona("stock_fleet.group_trip_driver"),
        "stock_manager_a": Persona("stock.group_stock_manager"),
        "stock_manager_b": Persona("stock.group_stock_manager", company="b"),
        "reviewer_a": Persona("stock_fleet.group_delivery_proof_reviewer"),
    }
    cells = (
        Cell(
            "stock.picking.unbatch.reason",
            "shared_reason",
            note="the catalogue every company offers when a stop comes back",
            stock_user_a="r",
            driver_a="r",
            reviewer_a="r",
            stock_manager_a="rwcd",
            stock_manager_b="rwcd",
        ),
        Cell(
            "stock.picking.unbatch.reason",
            "reason_of_a",
            note="a company's own reason stays inside that company",
            stock_user_a="r",
            driver_a="r",
            reviewer_a="r",
            stock_manager_a="rwcd",
        ),
        Cell(
            "stock.picking",
            "delivery_a",
            note="whoever delivers uploads the photo of the signed slip; only a "
            "reviewer rejects it, rewrites it once delivered or receives the paper",
            stock_user_a="rwcd validate",
            driver_a="rwcd validate",
            stock_manager_a="rwcd validate",
            reviewer_a="rwcd validate reject_delivery_proof accept_delivery_proof "
            "change_delivery_evidence receive_delivery_paper return_delivery_paper",
            installed={"marin": {"stock_manager_a": "validate_without_list"}},
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        reasons = cls.env["stock.picking.unbatch.reason"]
        warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.companies["a"].id)], limit=1
        )
        return {
            "delivery_a": cls.env["stock.picking"].create(
                {
                    "picking_type_id": warehouse.out_type_id.id,
                    "location_id": warehouse.lot_stock_id.id,
                    "location_dest_id": cls.env.ref(
                        "stock.stock_location_customers"
                    ).id,
                }
            ),
            "shared_reason": reasons.create(
                {"name": "Matrix shared reason", "accountable": "customer"}
            ),
            "reason_of_a": reasons.create(
                {
                    "name": "Matrix reason of a",
                    "accountable": "customer",
                    "company_id": cls.companies["a"].id,
                }
            ),
        }
