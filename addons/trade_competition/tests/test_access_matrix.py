from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestTradeCompetitionAccessMatrix(AccessMatrixCase):
    personas = {
        "internal_a": Persona("base.group_user"),
        "internal_b": Persona("base.group_user", company="b"),
    }
    cells = (
        Cell(
            "competitor.offer",
            "offer_a",
            note="the module alone gives no user a direct right on an offer: "
            "the count on a partner reads through its privilege, and the sale "
            "and purchase bridges grant the rights",
            internal_a="",
            internal_b="",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        company = cls.companies["a"]
        rival = env["res.partner"].create(
            {"name": "matrix rival", "is_competitor": True}
        )
        counterparty = env["res.partner"].create({"name": "matrix counterparty"})
        offer = env["competitor.offer"].create(
            {
                "competitor_id": rival.id,
                "partner_id": counterparty.id,
                "source": "other",
                "confidence": "reported",
                "company_id": company.id,
            }
        )
        return {"offer_a": offer}
