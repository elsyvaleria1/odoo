import datetime

from odoo import api, models
from odoo.exceptions import AccessError


class AutomationRuntimeLine(models.Model):
    _inherit = "automation.runtime.line"

    @api.model
    def _selection_created_record_models(self) -> list[tuple[str, str]]:
        selection = super()._selection_created_record_models()

        selection.extend(
            [
                ("account.move", "Journal Entry"),
                ("account.payment", "Payment"),
                ("account.bank.statement.line", "Bank Statement Line"),
            ],
        )

        return selection

    def action_execute(self):
        self.check_singleton()
        if not self.runtime_id._is_intercompany():
            return super().action_execute()
        company_ids = self.runtime_id._execution_company_ids()
        return super(
            AutomationRuntimeLine, self.with_context(allowed_company_ids=company_ids)
        ).action_execute()

    def _workflow_step_detail(self) -> str:
        try:
            summary = self.action_id._get_workflow_step_summary(self.runtime_id)
        except AccessError:
            summary = ""
        return summary or super()._workflow_step_detail()

    def _get_nearest_move(self, visited: set[int] | None = None) -> models.Model:
        if self.created_record_ref and self.created_record_ref._name == "account.move":
            return self.created_record_ref

        visited = self._mark_visited(visited)

        for predecessor in self._get_predecessors():
            if predecessor.id in visited:
                continue
            move = predecessor._get_nearest_move(visited)
            if move:
                return move

        return self.env["account.move"]

    def _get_nearest_payment(self, visited: set[int] | None = None) -> models.Model:
        if (
            self.created_record_ref
            and self.created_record_ref._name == "account.payment"
        ):
            return self.created_record_ref

        visited = self._mark_visited(visited)

        for predecessor in self._get_predecessors():
            if predecessor.id in visited:
                continue
            payment = predecessor._get_nearest_payment(visited)
            if payment:
                return payment

        return self.env["account.payment"]

    def _get_nearest_document_date(
        self, visited: set[int] | None = None
    ) -> datetime.date | bool:
        if self.runtime_id.st_line_id:
            return self.runtime_id.st_line_id.date

        if self.created_record_ref and self.created_record_ref._name == "account.move":
            move = self.created_record_ref
            return move.invoice_date or move.date

        if (
            self.created_record_ref
            and self.created_record_ref._name == "account.payment"
        ):
            return self.created_record_ref.date

        visited = self._mark_visited(visited)

        for predecessor in self._get_predecessors():
            if predecessor.id in visited:
                continue
            date = predecessor._get_nearest_document_date(visited)
            if date:
                return date

        return False

    def _mark_visited(self, visited: set[int] | None) -> set[int]:
        if visited is None:
            visited = set()
        visited.add(self.id)
        return visited
