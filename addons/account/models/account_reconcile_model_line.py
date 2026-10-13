import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.libs.numbers import parse_amount
from odoo.tools import frozendict

_debug = DebugLog(__name__)


class AccountReconcileModelLine(models.Model):
    _name = "account.reconcile.model.line"
    _inherit = ["mixin.analytic"]
    _description = "Rules for the reconciliation model"
    _order = "sequence, id"
    _check_company_auto = True
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False, hierarchy="parent_of"),
        }
    )

    model_id = fields.Many2one(
        comodel_name="account.reconcile.model",
        index="btree_not_null",
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="model_id.company_id",
    )
    sequence = fields.Integer(
        default=10,
        required=True,
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
        domain="[('account_type', '!=', 'off_balance')]",
        ondelete="cascade",
        check_company=True,
    )
    partner_id = fields.Many2one(comodel_name="res.partner")
    label = fields.Char(translate=True)
    amount_type = fields.Selection(
        selection=[
            ("fixed", "Fixed"),
            ("percentage", "Percentage of balance"),
            ("percentage_st_line", "Percentage of statement line"),
            ("regex", "From label"),
        ],
        default="percentage",
        required=True,
    )
    amount = fields.Float(
        string="Float Amount",
        compute="_compute_amount",
    )
    amount_string = fields.Char(
        string="Amount",
        default="100",
        required=True,
        help="""Value for the amount of the writeoff line
    * Percentage: Percentage of the balance. Either separator convention is accepted, so 12,5 and 12.5 both read as 12.5.
    * Fixed: The fixed value of the writeoff. The amount will count as a debit if it is negative, as a credit if it is positive.
    * From Label: There is no need for regex delimiter, only the regex is needed. For instance if you want to extract the amount from\nR:9672938 10/07 AX 9415126318 T:5L:NA BRT: 3358,07 C:\nYou could enter\nBRT: ([\\d,]+)
    If the label is "01870912 0009065 00115" and you need the amount in decimal
    format (e.g. 90.65), you can use a regex with capturing groups, for example:
        \\s+0*(\\d+?)(\\d{2})(?=\\s)
    In this case:
    • the first group captures the integer part
    • the second group captures the decimal part (last two digits)
    """,
    )
    tax_ids = fields.Many2many(
        comodel_name="account.tax",
        string="Taxes",
        ondelete="restrict",
        check_company=True,
    )

    @api.onchange("amount_type")
    def _onchange_amount_type(self) -> None:
        self.amount_string = ""
        if self.amount_type in ("percentage", "percentage_st_line"):
            self.amount_string = "100"
        elif self.amount_type == "regex":
            self.amount_string = r"([\d,]+)"

    @api.depends("amount_string", "amount_type")
    def _compute_amount(self):
        for record in self:
            record.amount = (
                0.0
                if record.amount_type == "regex"
                else parse_amount(record.amount_string) or 0.0
            )

    @api.constrains("amount_string", "amount_type")
    @_debug.perf.timed
    def _check_amount(self) -> None:
        for record in self:
            if record.amount_type == "regex":
                try:
                    pattern = re.compile(record.amount_string)
                except re.error as err:
                    _debug.logic(
                        "reco_model_line_rejected",
                        reco_model_line=record,
                        reason="bad_regex",
                    )
                    raise ValidationError(
                        self.env._(
                            "%(model)s: the amount regex is not valid.",
                            model=record.model_id.display_name,
                        )
                    ) from err
                if not pattern.groups:
                    _debug.logic(
                        "reco_model_line_rejected",
                        reco_model_line=record,
                        reason="regex_without_group",
                    )
                    raise ValidationError(
                        self.env._(
                            "%(model)s: the amount regex must capture the amount in "
                            "parentheses, for example BRT: ([\\d,.]+).",
                            model=record.model_id.display_name,
                        )
                    )
                continue

            if parse_amount(record.amount_string) is None:
                _debug.logic(
                    "reco_model_line_rejected",
                    reco_model_line=record,
                    reason="unparsable_amount",
                )
                raise ValidationError(
                    self.env._(
                        "%(model)s: %(value)s is not a valid amount. Write a finite "
                        "number, for example 100 or 12,5.",
                        model=record.model_id.display_name,
                        value=record.amount_string,
                    )
                )
            if not record.amount:
                _debug.logic(
                    "reco_model_line_rejected",
                    reco_model_line=record,
                    reason="zero_amount",
                )
                raise ValidationError(
                    self.env._(
                        "%(model)s: the amount of a %(kind)s line cannot be zero.",
                        model=record.model_id.display_name,
                        kind=dict(
                            record._fields["amount_type"]._description_selection(
                                self.env
                            )
                        )[record.amount_type],
                    )
                )
