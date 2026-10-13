from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestPurchaseTenderTeamAccessMatrix(AccessMatrixCase):
    personas = {
        "member_a": Persona("purchase_team.group_purchase_user_team"),
        "teammate_a": Persona("purchase.group_purchase_user"),
        "outsider_a": Persona("purchase_team.group_purchase_user_team"),
    }
    cells = (
        Cell(
            "purchase.tender",
            "tender_teammate",
            note="a team member reaches the tenders of the team's members",
            member_a="rwcd",
            teammate_a="rwcd",
        ),
        Cell(
            "purchase.tender.line",
            "need_teammate",
            member_a="rwcd",
            teammate_a="rwcd",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        a = cls.companies["a"]
        env["team.team"].create(
            {
                "name": "matrix team",
                "use_purchase": True,
                "company_id": a.id,
                "member_ids": [
                    Command.set((cls.users["member_a"] | cls.users["teammate_a"]).ids)
                ],
            }
        )
        product = env["product.product"].create({"name": "matrix need"})
        tender = env["purchase.tender"].create(
            {
                "company_id": a.id,
                "user_id": cls.users["teammate_a"].id,
                "line_ids": [Command.create({"product_id": product.id})],
            }
        )
        return {"tender_teammate": tender, "need_teammate": tender.line_ids}
