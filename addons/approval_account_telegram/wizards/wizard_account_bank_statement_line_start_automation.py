from odoo import models


class WizardAccountBankStatementLineStartAutomation(models.TransientModel):
    _inherit = "wizard.account.bank.statement.line.start.automation"

    def _link_approval_request(self, runtime) -> None:
        super()._link_approval_request(runtime)

        if not self.st_line_id:
            return

        approval = self.env["approval.request"].search(
            [
                ("bank_statement_line_id", "=", self.st_line_id.id),
                ("automation_runtime_id", "=", False),
                ("state", "not in", ("refused", "cancelled")),
            ],
            limit=1,
        )
        if approval:
            approval.automation_runtime_id = runtime.id
