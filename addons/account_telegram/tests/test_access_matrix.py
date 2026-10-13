from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

OWN = (
    "a Telegram contact's own statement reads it only through "
    "account_telegram.privilege_print_own_statement, which no user holds"
)


@tagged("post_install", "-at_install", "access_matrix")
class TestAccountTelegramAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "accountant_a": Persona("account.group_account_readonly"),
        "admin_a": Persona("base.group_system"),
        "portal_c": Persona(portal="customer_c"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "telegram.financial.report.log",
            "log",
            note="the bot logs a statement it sends only through "
            "telegram.privilege_operate_bot; who asked for whose statement is "
            "read where the statements are",
            accountant_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "res.partner",
            "customer_c",
            note="an accounting reader prints any customer's statement from "
            "Telegram as the partner ledger shows it in Odoo; " + OWN,
            employee_a="r",
            accountant_a="r print_statement",
            admin_a="rwcd",
            portal_c="r",
        ),
        Cell(
            "report.formula",
            "partner_ledger",
            note=OWN,
            accountant_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "report.formula.line",
            "partner_ledger_line",
            note=OWN,
            accountant_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "report.formula.column",
            "partner_ledger_column",
            note=OWN,
            accountant_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "account.report.horizontal.group",
            "horizontal_group",
            note=OWN,
            accountant_a="r",
        ),
        Cell(
            "account.return.type",
            "return_type",
            note=OWN,
            accountant_a="r",
        ),
        Cell(
            "account.fiscal.year",
            "fiscal_year",
            note=OWN,
            accountant_a="r",
        ),
        Cell(
            "account.group",
            "account_group",
            note=OWN,
            accountant_a="r",
        ),
        Cell(
            "report.paperformat",
            "paperformat",
            note=OWN,
            employee_a="r",
            accountant_a="r",
            admin_a="rwcd",
        ),
        Cell(
            "account.report.annotation",
            "annotation",
            note=OWN,
            accountant_a="r",
        ),
        Cell(
            "account.move",
            "invoice_c",
            note=OWN,
            accountant_a="r",
            portal_c="r",
        ),
        Cell(
            "account.move.line",
            "invoice_c_receivable",
            note=OWN,
            accountant_a="r",
            portal_c="r",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        a = cls.companies["a"]
        customer_c = cls.partners["customer_c"]
        ledger = env.ref("account.partner_ledger_report")
        product = env["product.product"].create(
            {"name": "matrix product", "list_price": 10.0}
        )
        invoice = (
            env["account.move"]
            .with_company(a)
            .create(
                {
                    "move_type": "out_invoice",
                    "partner_id": customer_c.id,
                    "invoice_date": "2026-09-01",
                    "invoice_line_ids": [
                        Command.create({"product_id": product.id, "price_unit": 10.0})
                    ],
                }
            )
        )
        invoice.action_post()
        account = env["telegram.account"].create({"tg_user_id": "920001"})
        env["telegram.binding"].create(
            {
                "account_id": account.id,
                "partner_id": customer_c.id,
                "method": "session",
            }
        )
        horizontal_group = env["account.report.horizontal.group"].create(
            {
                "name": "matrix horizontal group",
                "report_ids": [Command.link(ledger.id)],
                "rule_ids": [
                    Command.create({"field_name": "partner_id", "domain": "[]"})
                ],
            }
        )
        return {
            "log": env["telegram.financial.report.log"].create(
                {"target_partner_id": customer_c.id}
            ),
            "customer_c": customer_c,
            "partner_ledger": ledger,
            "partner_ledger_line": env["report.formula.line"].create(
                {"name": "matrix ledger line", "report_id": ledger.id}
            ),
            "partner_ledger_column": ledger.column_ids[:1],
            "horizontal_group": horizontal_group,
            "return_type": env["account.return.type"].create(
                {"name": "matrix return type", "report_id": ledger.id}
            ),
            "fiscal_year": env["account.fiscal.year"].create(
                {
                    "name": "matrix fiscal year",
                    "date_from": "2026-01-01",
                    "date_to": "2026-12-31",
                    "company_id": a.id,
                }
            ),
            "account_group": env["account.group"].create(
                {
                    "name": "matrix account group",
                    "code_prefix_start": "999",
                    "company_id": a.id,
                }
            ),
            "paperformat": env.ref("base.paperformat_euro"),
            "annotation": env["account.report.annotation"].create(
                {
                    "message_id": invoice.message_post(body="matrix").id,
                    "date": "2026-09-01",
                }
            ),
            "invoice_c": invoice,
            "invoice_c_receivable": invoice.line_ids.filtered(
                lambda line: line.account_id.account_type == "asset_receivable"
            ),
        }
