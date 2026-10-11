from odoo.fields import Command

from odoo.addons.telegram.tests.common import TelegramBotTestCase


class PartnerLedgerTelegramTestCase(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.estadocuentaperiodo_command = cls.env["telegram.command"]._for_name(
            "/estadocuentaperiodo"
        )
        cls.customer_statement_command = cls.env["telegram.command"]._for_name(
            "/edocliente"
        )
        cls.test_bot.write(
            {
                "command_ids": [
                    Command.link(cls.estadocuentaperiodo_command.id),
                    Command.link(cls.customer_statement_command.id),
                ]
            }
        )

    @classmethod
    def _post_statement_line(
        cls, partner, account_type="asset_receivable", company=None
    ):
        company = company or cls.env.company
        receivable = cls._statement_account(company, account_type)
        income = cls._statement_account(company, "income")
        journal = cls.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", company.id)], limit=1
        ) or cls.env["account.journal"].create(
            {
                "name": "Statement Test Journal",
                "code": "STJ",
                "type": "general",
                "company_id": company.id,
            }
        )
        moves = cls.env["account.move"].with_company(company)
        move = moves.create(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "date": "2026-09-01",
                "line_ids": [
                    Command.create(
                        {
                            "account_id": receivable.id,
                            "partner_id": partner.id,
                            "debit": 100.0,
                        }
                    ),
                    Command.create({"account_id": income.id, "credit": 100.0}),
                ],
            }
        )
        move.action_post()
        return move

    @classmethod
    def _statement_account(cls, company, account_type):
        accounts = cls.env["account.account"]
        return accounts.search(
            [("account_type", "=", account_type), ("company_ids", "in", company.id)],
            limit=1,
        ) or accounts.create(
            {
                "name": f"Statement Test {account_type}",
                "code": f"ST{len(account_type)}{account_type[:3].upper()}",
                "account_type": account_type,
                "reconcile": account_type.startswith(
                    ("asset_receivable", "liability_payable")
                ),
                "company_ids": [Command.link(company.id)],
            }
        )
