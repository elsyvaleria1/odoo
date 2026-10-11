from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestPurchaseTenderAccessMatrix(AccessMatrixCase):
    personas = {
        "user_a": Persona("purchase.group_purchase_user"),
        "user_all_a": Persona("purchase.group_purchase_user_all"),
        "manager_a": Persona("purchase.group_purchase_manager"),
        "reader_a": Persona("purchase.group_purchase_readonly"),
        "employee_a": Persona(),
        "user_b": Persona("purchase.group_purchase_user", company="b"),
        "manager_ab": Persona("purchase.group_purchase_manager", companies=("a", "b")),
    }
    cells = (
        Cell(
            "purchase.tender",
            "tender_a",
            user_all_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "purchase.tender.line",
            "need_a",
            user_all_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "purchase.tender",
            "tender_b",
            user_b="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "purchase.tender.line",
            "need_b",
            user_b="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "purchase.tender",
            "tender_own",
            user_a="rwcd",
            user_all_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "purchase.tender.line",
            "need_own",
            user_a="rwcd",
            user_all_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "purchase.tender",
            "tender_unset",
            user_a="rwcd",
            user_all_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "purchase.tender.line",
            "need_unset",
            user_a="rwcd",
            user_all_a="rwcd",
            manager_a="rwcd",
            reader_a="r",
            manager_ab="rwcd",
        ),
    )

    @classmethod
    def build(cls):
        product = cls.env["product.product"].create({"name": "matrix need"})
        records = {}
        for key, company in (("a", cls.companies["a"]), ("b", cls.companies["b"])):
            tender = (
                cls.env["purchase.tender"]
                .with_company(company)
                .create(
                    {
                        "company_id": company.id,
                        "user_id": cls.users[
                            "manager_a" if key == "a" else "user_b"
                        ].id,
                        "line_ids": [Command.create({"product_id": product.id})],
                    }
                )
            )
            records[f"tender_{key}"] = tender
            records[f"need_{key}"] = tender.line_ids
        for key, owner in (("own", cls.users["user_a"]), ("unset", False)):
            tender = cls.env["purchase.tender"].create(
                {
                    "company_id": cls.companies["a"].id,
                    "user_id": owner and owner.id,
                    "line_ids": [Command.create({"product_id": product.id})],
                }
            )
            records[f"tender_{key}"] = tender
            records[f"need_{key}"] = tender.line_ids
        return records
