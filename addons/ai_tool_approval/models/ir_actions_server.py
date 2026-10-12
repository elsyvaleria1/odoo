from typing import Any

from odoo import fields, models


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    ai_approval_category_id = fields.Many2one(
        comodel_name="approval.category",
        string="Approval",
        ondelete="restrict",
        help="When set, an agent's call of this tool is held as a proposal until "
        "this category's approvers grant it.",
    )

    def _ai_tool_call(
        self, record: models.BaseModel | None, arguments: dict[str, Any]
    ) -> Any:
        if not self.ai_approval_category_id:
            return super()._ai_tool_call(record, arguments)
        call = self.env["ai.tool.call"]._propose(self, record, arguments)
        return call._get_proposal_answer()
