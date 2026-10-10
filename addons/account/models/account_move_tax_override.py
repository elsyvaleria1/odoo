from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import format_amount

_debug = DebugLog(__name__)


class AccountMoveTaxOverride(models.Model):
    _name = "account.move.tax.override"
    _description = "Manual Tax Amount"
    _order = "move_id, tax_id"

    move_id = fields.Many2one(
        comodel_name="account.move",
        index=True,
        required=True,
        ondelete="cascade",
    )
    tax_id = fields.Many2one(
        comodel_name="account.tax",
        required=True,
        ondelete="cascade",
    )
    tax_group_id = fields.Many2one(related="tax_id.tax_group_id")
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        required=True,
    )
    amount_currency = fields.Monetary(
        string="Manual Amount",
        currency_field="currency_id",
        help="Tax amount of this tax on the document, as typed by hand.",
    )
    amount_computed_currency = fields.Monetary(
        string="Computed Amount",
        currency_field="currency_id",
        help="Tax amount the taxes computed when the manual amount was set.",
    )
    amount_base_currency = fields.Monetary(
        string="Base Amount",
        currency_field="currency_id",
        help="Taxable base the manual amount was set against: once it changes, "
        "the manual amount no longer applies and is removed.",
    )

    _move_tax_unique = models.Constraint(
        "UNIQUE(move_id, tax_id)",
        "A journal entry holds one manual amount per tax.",
    )

    def _get_inapplicable_reason(self, currency, tax_values) -> str | None:
        self.check_singleton()
        if not tax_values:
            return self.env._("the tax is no longer on the document")
        if self.currency_id != currency:
            return self.env._("the currency changed")
        if currency.compare_amounts(
            self.amount_base_currency, tax_values["base_amount_currency"]
        ) or currency.compare_amounts(
            self.amount_computed_currency, tax_values["tax_amount_currency"]
        ):
            return self.env._("its taxable base changed")
        return None

    def _check_moves_in_draft(self, moves) -> None:
        if any(move.state != "draft" for move in moves):
            raise UserError(
                self.env._("Manual tax amounts can only be changed on draft entries.")
            )

    def _format_amount(self, amount):
        return format_amount(self.env, amount, self.currency_id)

    def _log_on_moves(self, bodies) -> None:
        for move, body in bodies:
            move._message_log(body=Markup("<p>%s</p>") % body)

    @api.model_create_multi
    def create(self, vals_list):
        moves = self.env["account.move"].browse(
            {vals["move_id"] for vals in vals_list if vals.get("move_id")}
        )
        self._check_moves_in_draft(moves)
        container = {"records": moves}
        with moves._check_balanced(container), moves._sync_dynamic_lines(container):
            overrides = super().create(vals_list)
        _debug.logic("tax_override_created", overrides=overrides)
        self._log_on_moves(
            [
                (
                    override.move_id,
                    self.env._(
                        "Manual tax amount for %(tax)s set to %(amount)s (computed: %(computed)s).",
                        tax=override.tax_id.name,
                        amount=override._format_amount(override.amount_currency),
                        computed=override._format_amount(
                            override.amount_computed_currency
                        ),
                    ),
                )
                for override in overrides
            ]
        )
        return overrides

    def write(self, vals):
        self._check_moves_in_draft(self.move_id)
        old_amounts = {override: override.amount_currency for override in self}
        container = {"records": self.move_id}
        with (
            self.move_id._check_balanced(container),
            self.move_id._sync_dynamic_lines(container),
        ):
            res = super().write(vals)
        changed = self.filtered(
            lambda override: override.currency_id.compare_amounts(
                old_amounts[override], override.amount_currency
            )
        )
        _debug.logic("tax_override_written", overrides=self, changed=changed)
        self._log_on_moves(
            [
                (
                    override.move_id,
                    self.env._(
                        "Manual tax amount for %(tax)s changed from %(old)s to %(amount)s (computed: %(computed)s).",
                        tax=override.tax_id.name,
                        old=override._format_amount(old_amounts[override]),
                        amount=override._format_amount(override.amount_currency),
                        computed=override._format_amount(
                            override.amount_computed_currency
                        ),
                    ),
                )
                for override in changed
            ]
        )
        return res

    def unlink(self):
        moves = self.move_id
        self._check_moves_in_draft(moves)
        reason = self.env.context.get("tax_override_drop_reason")
        bodies = [
            (
                override.move_id,
                self.env._(
                    "Manual tax amount %(amount)s for %(tax)s removed: %(reason)s.",
                    amount=override._format_amount(override.amount_currency),
                    tax=override.tax_id.name,
                    reason=reason,
                )
                if reason
                else self.env._(
                    "Manual tax amount %(amount)s for %(tax)s removed.",
                    amount=override._format_amount(override.amount_currency),
                    tax=override.tax_id.name,
                ),
            )
            for override in self
        ]
        _debug.logic("tax_override_removed", overrides=self, reason=reason)
        container = {"records": moves}
        with moves._check_balanced(container), moves._sync_dynamic_lines(container):
            res = super().unlink()
        self._log_on_moves(bodies)
        return res
