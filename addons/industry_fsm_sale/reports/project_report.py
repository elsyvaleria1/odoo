from odoo import fields, models
from odoo.tools import frozendict

from odoo.addons.sale import const


class ReportProjectTaskUserFsm(models.Model):
    _inherit = "report.project.task.user.fsm"
    _depends = frozendict(
        {
            "project.task": ["sale_line_id", "sale_order_id"],
            "sale.order": ["invoice_state"],
            "sale.order.line": ["remaining_hours"],
        }
    )

    invoice_state = fields.Selection(
        selection=const.INVOICE_STATE,
        string="Invoice Status",
        readonly=True,
    )

    def _select(self):
        return (
            super()._select()
            + """,
            so.invoice_state as invoice_state
        """
        )

    def _group_by(self):
        return (
            super()._group_by()
            + """,
            so.invoice_state
        """
        )

    def _from(self):
        return (
            super()._from()
            + """
            LEFT JOIN sale_order so ON t.sale_order_id = so.id
        """
        )
