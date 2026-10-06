from odoo import fields, models
from odoo.tools import frozendict


class HelpdeskTicketReportAnalysis(models.Model):
    _inherit = "helpdesk.ticket.report.analysis"
    _depends = frozendict(
        {
            "helpdesk.ticket": ["sale_line_id"],
            "sale.order.line": ["remaining_hours"],
        }
    )

    remaining_hours_so = fields.Float(
        string="Remaining Hours on SO",
        readonly=True,
        aggregator="avg",
        groups="hr_timesheet.group_hr_timesheet_user",
    )
    sale_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        string="Sales Order Item",
        readonly=True,
    )

    def _select(self):
        return (
            super()._select()
            + """ ,
            sol.remaining_hours as remaining_hours_so,
            T.sale_line_id as sale_line_id
        """
        )

    def _group_by(self):
        return (
            super()._group_by()
            + """ ,
            sol.remaining_hours,
            T.sale_line_id
        """
        )

    def _from(self):
        from_str = super()._from()
        from_str += """
            LEFT JOIN sale_order_line sol ON T.sale_line_id = sol.id
        """
        return from_str
