import datetime

from odoo import api, models
from odoo.exceptions import AccessError, UserError


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

    def _get_source_move(self) -> models.Model:
        self.check_singleton()
        source = self.action_id.workflow_source_step_id
        if source:
            line = self.runtime_id.line_ids.filtered(
                lambda step: step.action_id == source,
            )
            record = line.created_record_ref
            if record and record._name == "account.move":
                return record
            return self.env["account.move"]
        moves = self._get_nearest_moves()
        if len(moves) > 1:
            raise UserError(
                self.env._(
                    "'%(step)s' could act on %(documents)s, each made on another "
                    "branch before it. Name the step whose document it acts on "
                    "in its Acts On.",
                    step=self.name,
                    documents=", ".join(moves.mapped("display_name")),
                ),
            )
        return moves

    def _get_target_move(self) -> models.Model:
        self.check_singleton()
        target = self.action_id.workflow_target_step_id
        if not target:
            return self.env["account.move"]
        line = self.runtime_id.line_ids.filtered(
            lambda step: step.action_id == target,
        )
        record = line.created_record_ref
        if not record or record._name != "account.move":
            raise UserError(
                self.env._(
                    "'%(step)s' applies against the document of '%(target)s', "
                    "which made none in this run.",
                    step=self.name,
                    target=target.name,
                ),
            )
        return record

    def _get_nearest_moves(self, visited: set[int] | None = None) -> models.Model:
        if self.created_record_ref and self.created_record_ref._name == "account.move":
            return self.created_record_ref

        visited = self._mark_visited(visited)

        moves = self.env["account.move"]
        for predecessor in self._get_predecessors():
            if predecessor.id in visited:
                continue
            moves |= predecessor._get_nearest_moves(visited)
        return moves

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

        if self.action_id.workflow_source_step_id:
            move = self._get_source_move()
            return (move.invoice_date or move.date) if move else False

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
