from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import float_compare

_debug = DebugLog(__name__)


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    deferred_start_date = fields.Date(
        string="Start Date",
        compute="_compute_deferred_start_date",
        store=True,
        index="btree_not_null",
        copy=False,
        readonly=False,
        help="Date at which the deferred expense/revenue starts",
    )
    deferred_end_date = fields.Date(
        string="End Date",
        index="btree_not_null",
        copy=False,
        help="Date at which the deferred expense/revenue ends",
    )
    has_deferred_moves = fields.Boolean(
        compute="_compute_has_deferred_moves",
        exportable=False,
    )
    has_abnormal_deferred_dates = fields.Boolean(
        compute="_compute_has_abnormal_deferred_dates",
        exportable=False,
    )

    def _check_deferred_account_change(self, vals) -> None:
        if "account_id" in vals:
            for line in self:
                if (
                    line.has_deferred_moves
                    and line.deferred_start_date
                    and line.deferred_end_date
                    and vals["account_id"] != line.account_id.id
                ):
                    _debug.logic(
                        "deferred_account_change_blocked",
                        line=line,
                        account_id=vals.get("account_id"),
                    )
                    raise UserError(
                        self.env._(
                            "You cannot change the account for a deferred line in %(move_name)s if it has already been deferred.",
                            move_name=line.move_id.display_name,
                        )
                    )

    @api.depends("move_id.deferred_move_ids")
    def _compute_has_deferred_moves(self) -> None:
        for line in self:
            line.has_deferred_moves = bool(line.move_id.deferred_move_ids)

    @api.depends("deferred_start_date", "deferred_end_date")
    @_debug.perf.timed
    def _compute_has_abnormal_deferred_dates(self) -> None:
        for line in self:
            line.has_abnormal_deferred_dates = (
                line.deferred_start_date
                and line.deferred_end_date
                and line.deferred_start_date != line.deferred_end_date
                and float_compare(
                    self.env["account.move"]._get_deferred_diff_dates(
                        line.deferred_start_date,
                        line.deferred_end_date + relativedelta(days=1),
                    )
                    % 1,
                    1 / 30,
                    precision_digits=2,
                )
                == 0
            )

    def _has_deferred_compatible_account(self) -> bool:
        self.check_singleton()
        return bool(
            (
                self.move_id.is_purchase_document(include_receipts=True)
                and self.account_id.internal_group == "expense"
            )
            or (
                self.move_id.is_sale_document(include_receipts=True)
                and self.account_id.internal_group == "income"
            )
            or (
                self.move_id.is_entry()
                and self.account_id.internal_group in ("expense", "income")
            )
        )

    @api.onchange("deferred_start_date", "account_id")
    def _onchange_deferred_start_date(self) -> None:
        if not self._has_deferred_compatible_account():
            self.deferred_start_date = False
        if self.deferred_start_date and not self.deferred_end_date:
            self.deferred_end_date = self.deferred_start_date

    @api.onchange("deferred_end_date", "account_id")
    def _onchange_deferred_end_date(self) -> None:
        if not self._has_deferred_compatible_account():
            self.deferred_end_date = False
        if self.deferred_end_date and not self.deferred_start_date:
            self.deferred_start_date = self.deferred_end_date

    @api.depends("deferred_end_date", "move_id.invoice_date", "move_id.state")
    def _compute_deferred_start_date(self) -> None:
        for line in self:
            if (
                not line.deferred_start_date
                and line.move_id.invoice_date
                and line.deferred_end_date
            ):
                line.deferred_start_date = line.move_id.invoice_date

    @api.constrains("deferred_start_date", "deferred_end_date", "account_id")
    @_debug.perf.timed
    def _check_deferred_dates(self) -> None:
        for line in self:
            if line.deferred_start_date and not line.deferred_end_date:
                _debug.logic(
                    "deferred_dates_invalid", line=line, reason="start_without_end"
                )
                raise UserError(
                    self.env._(
                        "You cannot create a deferred entry with a start date but no end date."
                    )
                )
            if (
                line.deferred_start_date
                and line.deferred_end_date
                and line.deferred_start_date > line.deferred_end_date
            ):
                _debug.logic(
                    "deferred_dates_invalid", line=line, reason="start_after_end"
                )
                raise UserError(
                    self.env._(
                        "You cannot create a deferred entry with a start date later than the end date."
                    )
                )

    @api.model
    def _get_deferred_ends_of_month(self, start_date, end_date):
        dates = []
        while start_date <= end_date:
            start_date += relativedelta(day=31)
            dates.append(start_date)
            start_date += relativedelta(days=1)
        return dates

    def _get_deferred_periods(self):
        self.check_singleton()
        periods = [
            (
                max(self.deferred_start_date, date.replace(day=1)),
                min(date, self.deferred_end_date),
                "current",
            )
            for date in self._get_deferred_ends_of_month(
                self.deferred_start_date, self.deferred_end_date
            )
        ]
        if not periods or (
            len(periods) == 1
            and periods[0][0].replace(day=1) == self.date.replace(day=1)
        ):
            return []
        else:
            return periods

    @api.model
    def _prepare_deferred_amounts_by_line_values(self, line):
        return {
            "account_id": line["account_id"],
            "product_id": line["product_id"]
            if isinstance(line, dict)
            else line["product_id"].id,
            "product_category_id": line["product_category_id"]
            if isinstance(line, dict)
            else line["product_category_id"].id,
            "balance": line["balance"],
            "move_id": line["move_id"],
        }

    @api.model
    def _prepare_deferred_lines_values(
        self, account_id, balance, ref, analytic_distribution, line=None
    ) -> dict:
        return {
            "account_id": account_id,
            "product_id": line["product_id"]
            if isinstance(line, dict)
            else line["product_id"].id,
            "product_category_id": line["product_category_id"]
            if isinstance(line, dict)
            else line["product_category_id"].id,
            "balance": balance,
            "name": ref,
            "analytic_distribution": analytic_distribution,
        }
