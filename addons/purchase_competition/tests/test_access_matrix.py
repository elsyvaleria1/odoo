from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestPurchaseCompetitionAccessMatrix(AccessMatrixCase):
    personas = {
        "user_a": Persona("purchase.group_purchase_user"),
        "manager_a": Persona("purchase.group_purchase_manager"),
        "reader_a": Persona("purchase.group_purchase_readonly"),
        "employee_a": Persona(),
        "user_b": Persona("purchase.group_purchase_user", company="b"),
        "manager_ab": Persona("purchase.group_purchase_manager", companies=("a", "b")),
    }
    cells = (
        Cell(
            "competitor.offer",
            "offer_a",
            user_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "competitor.offer",
            "offer_b",
            user_b="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "competitor.offer",
            "offer_other_direction",
            note="an offer made to a customer is no buyer's",
        ),
        Cell(
            "competitor.offer.line",
            "line_a",
            user_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "competitor.offer.line",
            "line_other_direction",
            note="an offer made to a customer is no buyer's",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        a, b = cls.companies["a"], cls.companies["b"]
        rival = env["res.partner"].create(
            {"name": "matrix rival", "is_competitor": True, "is_company": True}
        )
        counterparty = env["res.partner"].create({"name": "matrix counterparty"})
        product = env["product.product"].create({"name": "matrix product"})

        def offer(company, direction):
            return (
                env["competitor.offer"]
                .with_company(company)
                .create(
                    {
                        "competitor_id": rival.id,
                        "partner_id": counterparty.id,
                        "direction": direction,
                        "company_id": company.id,
                        "currency_id": company.currency_id.id,
                        "line_ids": [
                            Command.create(
                                {"product_id": product.id, "price_unit": 1.0}
                            )
                        ],
                    }
                )
            )

        offer_a = offer(a, "purchase")
        other = offer(a, "sale")
        return {
            "offer_a": offer_a,
            "offer_b": offer(b, "purchase"),
            "offer_other_direction": other,
            "line_a": offer_a.line_ids,
            "line_other_direction": other.line_ids,
        }
