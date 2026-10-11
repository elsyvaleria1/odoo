from odoo import fields, models
from odoo.fields import Command
from odoo.libs.debug_log import DebugLog

from odoo.addons.trade.tools import direction_of

_debug = DebugLog(__name__)


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    is_downpayment = fields.Boolean()

    def _get_fields_order_line_link(self) -> list:
        return []

    def _get_linked_order_lines(self, field_name):
        direction = direction_of(self.env[self._fields[field_name].comodel_name])
        document_lines = self.filtered(
            lambda line: line.move_id.move_type in direction.document_move_types
        )
        _debug.logic(
            "order_lines_linked",
            lines=self,
            field=field_name,
            document_lines=document_lines,
        )
        return document_lines.mapped(field_name)

    def _copy_data_extend_business_fields(self, values) -> None:
        super()._copy_data_extend_business_fields(values)
        linked = self.with_privilege(
            "trade_account.privilege_copy_order_links",
            reason="a reversed or duplicated journal item keeps the order lines it bills",
        )
        for field_name in self._get_fields_order_line_link():
            values[field_name] = [
                Command.set(linked._get_linked_order_lines(field_name).ids)
            ]

    def _related_analytic_distribution(self):
        vals = super()._related_analytic_distribution()
        for field_name in self._get_fields_order_line_link():
            if order_lines := self._get_linked_order_lines(field_name):
                vals |= order_lines[0].analytic_distribution or {}
                _debug.logic(
                    "analytic_from_order_line", line=self, order_line=order_lines[0]
                )
        return vals

    def _compute_warn_msg_from_product(self, field_name, group) -> None:
        has_warning_group = self.env.user.has_group(group)
        _debug.logic(
            "product_warn_msg", lines=self, field=field_name, shown=has_warning_group
        )
        for line in self:
            line[field_name] = line.product_id[field_name] if has_warning_group else ""
