from collections import defaultdict

from odoo import api, models


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _get_model_names_to_load(self, config):
        data = super()._get_model_names_to_load(config)
        if self.env.user.has_group(
            "account.group_account_readonly"
        ) or self.env.user.has_group("account.group_account_invoice"):
            data += ["account.move"]
        data += ["ir.ui.view"]
        return data

    def _reconcile_account_move_lines(self, data):
        data = super()._reconcile_account_move_lines(data)
        # Get pay later move lines created in the session (from POS orders not invoiced)
        pay_later_move_lines = data.get("pay_later_move_lines")

        # Add lines from invoiced orders that have been settled during this session
        pay_later_move_lines |= (
            self.order_ids.mapped("lines")
            .filtered(
                lambda l: (
                    (l.settled_invoice_id or l.settled_order_id)
                    and l.order_id.account_move
                )
            )
            .mapped("order_id.payment_ids.account_move_id.line_ids")
            .filtered(
                lambda l: (
                    l.account_id == l.partner_id.property_account_receivable_id
                    and not l.reconciled
                )
            )
        )

        if pay_later_move_lines:
            partner_account_lines = defaultdict(list)
            for move_line in pay_later_move_lines:
                key = (move_line.partner_id.id, move_line.account_id.id)
                partner_account_lines[key] += move_line
            all_session_move_lines = (
                self.order_ids.lines.settled_order_id.session_id.move_id.line_ids
            )
            all_invoice_move_lines = self.order_ids.lines.settled_invoice_id.line_ids

            session_lines_by_key = all_session_move_lines.grouped(
                lambda l: (l.partner_id.id, l.account_id.id)
            )
            invoice_lines_by_key = all_invoice_move_lines.grouped(
                lambda l: (l.partner_id.id, l.account_id.id)
            )
            no_line = all_session_move_lines.browse()
            for (partner_id, account_id), move_lines in partner_account_lines.items():
                session_move_lines = session_lines_by_key.get(
                    (partner_id, account_id), no_line
                ).filtered(lambda l: not l.reconciled and l.parent_state == "posted")
                invoice_move_lines = invoice_lines_by_key.get(
                    (partner_id, account_id), no_line
                ).filtered(lambda l: not l.reconciled and l.parent_state == "posted")
                (
                    self.env["account.move.line"].browse([l.id for l in move_lines])
                    | session_move_lines
                    | invoice_move_lines
                ).reconcile()
        return data
