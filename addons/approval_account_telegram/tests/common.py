from datetime import date

from odoo import Command

from odoo.addons.approval.tests.common import pool_step
from odoo.addons.telegram.tests.common import TelegramBotTestCase


class PaymentApprovalTelegramTestCase(TelegramBotTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.ref("base.main_company")

        cls.approval_category = cls.env["approval.category"].create(
            {
                "name": "Test Payment Approval",
                "sequence_code": "TGPAY",
                "has_bsl": "required",
                "has_date": "required",
                "company_id": cls.company.id,
                "step_ids": pool_step(
                    [(cls.env.ref("base.user_admin").id, True, 10)], minimum=1
                ),
            }
        )

        cls.approval_category.telegram_intake = "payment"

        cls.pago_command = cls.env["telegram.command"]._for_name("/pago")
        cls.test_bot.write({"command_ids": [(4, cls.pago_command.id)]})

        cls.especie_approval_category = cls.env["approval.category"].create(
            {
                "name": "Test Especie Approval",
                "sequence_code": "TGESP",
                "has_bsl": "no",
                "has_date": "required",
                "has_amount": "required",
                "has_partner": "required",
                "has_automation": "no",
                "company_id": cls.company.id,
                "step_ids": pool_step(
                    [(cls.env.ref("base.user_admin").id, True, 10)], minimum=1
                ),
            }
        )

        cls.especie_approval_category.telegram_intake = "especie"

        cls.especie_command = cls.env["telegram.command"]._for_name("/especie")
        cls.test_bot.write({"command_ids": [(4, cls.especie_command.id)]})

        cls.partner_fx = cls._create_partner(
            {
                "name": "Invoice Partner FX",
            }
        )
        cls.partner_cn = cls._create_partner(
            {
                "name": "Payment Partner CN",
            }
        )

    def create_approval_request(self, vals=None):
        default_vals = {
            "name": "Test Payment Request",
            "category_id": self.approval_category.id,
            "request_owner_id": self.test_user.id,
            "company_id": self.company.id,
            "date": date.today(),
        }
        if vals:
            default_vals.update(vals)
        return self.env["approval.request"].create(default_vals)

    def create_statement_line(self, when, amount):
        journal = self.env["account.journal"].search(
            [
                ("type", "=", "bank"),
                ("company_id", "=", self.company.id),
                ("suspense_account_id", "!=", False),
            ],
            limit=1,
        ) or self.env["account.journal"].create(
            {
                "name": "TG Bank",
                "code": "TGBNK",
                "type": "bank",
                "company_id": self.company.id,
                "suspense_account_id": self.env["account.account"]
                .create(
                    {
                        "name": "TG Bank Suspense",
                        "code": "TGBNKS",
                        "account_type": "asset_current",
                        "reconcile": True,
                        "company_ids": [Command.link(self.company.id)],
                    }
                )
                .id,
            }
        )
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": journal.id,
                "date": when,
                "amount": amount,
                "payment_ref": f"TEST BSL {when}",
            }
        )

    def get_payment_details_message(
        self,
        partner_fx="Invoice Partner FX",
        category="Agroquimicos",
        cfdi="Gastos en general",
        method="Transferencia",
        company="LMMR",
        partner_cn="Payment Partner CN",
        payment_date="2024-06-15",
        amount="1500.50",
    ):
        return f"{partner_fx}\n{category}\n{cfdi}\n{method}\n{company}\n{partner_cn}\n{payment_date}\n{amount}"

    def get_especie_details_message(
        self,
        partner_fx="Invoice Partner FX",
        category="Vehiculos",
        partner_cn="Payment Partner CN",
        especie_date="2024-06-15",
        amount="1500.50",
        product_ref="174",
    ):
        return f"{partner_fx}\n{category}\n{partner_cn}\n{especie_date}\n{amount}\n{product_ref}"
