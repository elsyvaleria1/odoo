from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrExpense(models.Model):
    _name = "hr.expense"
    _inherit = ["hr.expense", "mixin.documents.unlink"]

    document_count = fields.Integer(compute="_compute_document_count")

    def _compute_document_count(self) -> None:
        document_data = self.env["document.document"]._read_group(
            [("res_id", "in", self.ids), ("res_model", "=", self._name)],
            groupby=["res_id"],
            aggregates=["__count"],
        )
        mapped_data = dict(document_data)
        _debug.perf.count(
            "expense_document_counts", expenses=self, rows=len(mapped_data)
        )
        for expense in self:
            expense.document_count = mapped_data.get(expense.id, 0)

    def action_view_attachments(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "document.document_action_preference"
        )
        action["domain"] = [("res_model", "=", self._name), ("res_id", "=", self.id)]
        return action
