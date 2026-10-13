from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

OWN = (
    "a Telegram cardholder reads their own cards and those cards' accounts "
    "only through wallet_telegram.privilege_read_own_wallet, which no user holds"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestWalletTelegramAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "wallet_user_a": Persona("wallet.group_wallet_user"),
        "wallet_manager_a": Persona("wallet.group_wallet_manager"),
        "wallet_manager_b": Persona("wallet.group_wallet_manager", company="b"),
        "admin_a": Persona("base.group_system"),
        "portal_c": Persona(portal="customer_c"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "wallet.account",
            "account_a",
            note=OWN,
            wallet_user_a="r",
            wallet_manager_a="rwcd",
        ),
        Cell(
            "wallet.account",
            "account_b",
            note="another company's wallet account stays behind the company guard",
            wallet_manager_b="rwcd",
        ),
        Cell(
            "wallet.card",
            "card_a",
            note=OWN,
            wallet_user_a="r",
            wallet_manager_a="rwcd",
        ),
        Cell(
            "wallet.card",
            "card_b",
            note="another company's card stays behind the company guard",
            wallet_manager_b="rwcd",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        issuer = env["res.partner"].create({"name": "matrix issuer"})
        records = {}
        for key in ("a", "b"):
            company = cls.companies[key]
            account = (
                env["wallet.account"]
                .with_company(company)
                .create(
                    {
                        "name": f"matrix wallet {key}",
                        "kind": "toll",
                        "issuer_id": issuer.id,
                        "company_id": company.id,
                    }
                )
            )
            records[f"account_{key}"] = account
            records[f"card_{key}"] = (
                env["wallet.card"]
                .with_company(company)
                .create(
                    {
                        "number": f"MATRIX0000{key.upper()}",
                        "account_id": account.id,
                        "holder_id": cls.users["employee_a"].partner_id.id,
                    }
                )
            )
        return records
