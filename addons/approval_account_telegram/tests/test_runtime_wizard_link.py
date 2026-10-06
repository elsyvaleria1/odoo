from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from .common import PaymentApprovalTelegramTestCase


@tagged("post_install", "-at_install")
class TestRuntimeWizardApprovalLink(PaymentApprovalTelegramTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.automation = cls.env["automation.rule"].create(
            {
                "name": "Test Statement Workflow",
                "model_id": cls.env["ir.model"]._get_id("automation.runtime"),
                "trigger": "on_hand",
                "action_server_ids": [
                    Command.create(
                        {
                            "name": "Noop step",
                            "model_id": cls.env["ir.model"]._get_id(
                                "automation.runtime",
                            ),
                            "state": "code",
                            "code": "pass",
                        },
                    ),
                ],
            }
        )
        cls.account_bank = cls.env["account.account"].create(
            {
                "name": "TG Bank",
                "code": "TGBK01",
                "account_type": "asset_cash",
                "company_ids": [Command.link(cls.company.id)],
            }
        )
        cls.account_suspense = cls.env["account.account"].create(
            {
                "name": "TG Bank Suspense",
                "code": "TGBS01",
                "account_type": "asset_current",
                "reconcile": True,
                "company_ids": [Command.link(cls.company.id)],
            }
        )
        cls.journal_bank = cls.env["account.journal"].create(
            {
                "name": "TG Bank Journal",
                "code": "TGBJ",
                "type": "bank",
                "company_id": cls.company.id,
                "default_account_id": cls.account_bank.id,
                "suspense_account_id": cls.account_suspense.id,
            }
        )

    def _statement_line(self, ref):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.journal_bank.id,
                "payment_ref": ref,
                "partner_id": self.test_partner.id,
                "amount": 3000.0,
            }
        )

    def _runtime_from(self, st_line, automation=None):
        wizard = (
            self.env["wizard.account.bank.statement.line.start.automation"]
            .with_context(
                active_model="account.bank.statement.line",
                active_id=st_line.id,
            )
            .create(
                {
                    "automation_id": (automation or self.automation).id,
                    "partner_id": self.test_partner.id,
                    "amount": 3000.0,
                }
            )
        )
        action = wizard.action_create_runtime()
        return self.env["automation.runtime"].browse(action["res_id"])

    def test_the_runtime_is_linked_back_to_the_statement_approval(self):
        st_line = self._statement_line("BSL-LINK-001")
        approval = self.create_approval_request(
            {"bank_statement_line_id": st_line.id},
        )

        runtime = self._runtime_from(st_line)

        self.assertEqual(approval.automation_runtime_id, runtime)

    def _refuse(self, approval):
        self.env.cr.execute(
            "UPDATE approval_request SET state = 'refused' WHERE id = %s",
            (approval.id,),
        )
        approval.invalidate_recordset(["state"])

    def test_a_refused_approval_on_the_line_is_ignored(self):
        st_line = self._statement_line("BSL-LINK-002")
        dead = self.create_approval_request(
            {"bank_statement_line_id": st_line.id},
        )
        self._refuse(dead)
        live = self.create_approval_request(
            {"bank_statement_line_id": st_line.id},
        )

        runtime = self._runtime_from(st_line)

        self.assertEqual(live.automation_runtime_id, runtime)
        self.assertFalse(dead.automation_runtime_id)

    def test_a_line_cannot_hold_two_live_requests(self):
        st_line = self._statement_line("BSL-LINK-004")
        self.create_approval_request({"bank_statement_line_id": st_line.id})

        with self.assertRaises(ValidationError):
            self.create_approval_request(
                {"bank_statement_line_id": st_line.id},
            )

    def test_an_approval_that_already_owns_a_runtime_is_left_alone(self):
        st_line = self._statement_line("BSL-LINK-003")
        approval = self.create_approval_request(
            {"bank_statement_line_id": st_line.id},
        )
        first = self._runtime_from(st_line)
        self.assertEqual(approval.automation_runtime_id, first)

        second = self._runtime_from(
            st_line, self.automation.copy({"name": "Second Statement Workflow"})
        )

        self.assertEqual(approval.automation_runtime_id, first)
        self.assertNotEqual(first, second)

    def test_a_wizard_without_a_statement_line_links_nothing(self):
        wizard = self.env["wizard.account.bank.statement.line.start.automation"].create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.test_partner.id,
                "amount": 3000.0,
            }
        )
        action = wizard.action_create_runtime()
        runtime = self.env["automation.runtime"].browse(action["res_id"])

        self.assertFalse(
            self.env["approval.request"].search_count(
                [("automation_runtime_id", "=", runtime.id)],
            ),
        )
