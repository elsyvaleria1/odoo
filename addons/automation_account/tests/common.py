from odoo.fields import Command
from odoo.tests.common import TransactionCase


class AutomationAccountCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company
        cls.model_line = cls.env.ref("automation.model_automation_runtime_line")

        cls.immediate = cls.env.ref("payment_term.account_payment_term_immediate")
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Automation Customer",
                "property_payment_term_id": cls.immediate.id,
            }
        )
        cls.third_party = cls.env["res.partner"].create(
            {"name": "Automation Third Party"},
        )

        cls.account_receivable = cls.env["account.account"].create(
            {
                "name": "Automation Receivable",
                "code": "TAAC110",
                "account_type": "asset_receivable",
                "reconcile": True,
                "company_ids": [Command.link(cls.company.id)],
            },
        )
        cls.account_income = cls.env["account.account"].create(
            {
                "name": "Automation Income",
                "code": "TAAC400",
                "account_type": "income",
                "company_ids": [Command.link(cls.company.id)],
            },
        )

        cls.journal_sale = cls._make_journal("sale", "TAASL")
        cls.journal_bank = cls._make_journal("bank", "TAABK")

        cls.template_invoice = cls.env["account.move.template"].create(
            {
                "name": "TEST - Customer Invoice",
                "journal_code": cls.journal_sale.code,
                "move_type": "out_invoice",
                "invoice_payment_term_id": cls.immediate.id,
                "line_ids": [
                    Command.create(
                        {
                            "name": "Invoice Item",
                            "account_code": cls.account_income.code,
                            "sequence": 10,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

        cls.automation = cls.env["automation.rule"].create(
            {
                "name": "TEST - Accounting Workflow",
                "model_id": cls.model_line.id,
                "trigger": "on_hand",
            },
        )

    @classmethod
    def _make_journal(cls, journal_type, code):
        journal = cls.env["account.journal"].search(
            [
                ("type", "=", journal_type),
                ("company_id", "=", cls.company.id),
            ],
            limit=1,
        )
        if journal:
            return journal

        return cls.env["account.journal"].create(
            {
                "name": f"Automation {journal_type}",
                "code": code,
                "type": journal_type,
                "company_id": cls.company.id,
            },
        )

    def _make_step(self, code, name="Step", predecessors=None, automation=None):
        step = self.env["ir.actions.server"].create(
            {
                "name": name,
                "automation_rule_id": (automation or self.automation).id,
                "model_id": self.model_line.id,
                "state": "code",
                "code": code,
            },
        )
        self._link_steps(predecessors, step)
        return step

    def _link_steps(self, sources, target):
        if not sources:
            return self.env["workflow.edge"]
        return self.env["workflow.edge"].create(
            [
                {"source_node_id": source.id, "target_node_id": target.id}
                for source in sources
            ],
        )

    def _link_lines(self, sources, target):
        if not sources:
            return self.env["automation.runtime.edge"]
        return self.env["automation.runtime.edge"].create(
            [
                {
                    "runtime_id": target.runtime_id.id,
                    "source_line_id": source.id,
                    "target_line_id": target.id,
                }
                for source in sources
            ],
        )

    def _make_chain(self, codes, automation=None):
        steps = self.env["ir.actions.server"]
        previous = None
        for index, code in enumerate(codes):
            step = self._make_step(
                code,
                name=f"Step {index + 1}",
                predecessors=previous,
                automation=automation,
            )
            step.sequence = 10 + index
            steps |= step
            previous = step
        return steps

    def _make_runtime(self, automation=None, **vals):
        runtime_vals = {
            "automation_id": (automation or self.automation).id,
            "name": "TEST - Run",
            "partner_id": self.partner.id,
            "amount": 100.0,
            "date": "2026-08-27",
        }
        runtime_vals.update(vals)
        runtime = self.env["automation.runtime"].create(runtime_vals)
        runtime.action_start()
        return runtime
