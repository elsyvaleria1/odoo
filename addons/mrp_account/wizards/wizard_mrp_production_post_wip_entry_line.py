from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardMrpProductionPostWipEntryLine(models.TransientModel):
    _name = "wizard.mrp.production.post.wip.entry.line"
    _description = "Account move line to be created when posting WIP account move"

    account_id = fields.Many2one(comodel_name="account.account")
    label = fields.Char()
    debit = fields.Monetary(
        compute="_compute_debit",
        store=True,
        readonly=False,
    )
    credit = fields.Monetary(
        compute="_compute_credit",
        store=True,
        readonly=False,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        default=lambda self: self.env.company.currency_id,
    )
    wip_accounting_id = fields.Many2one(
        comodel_name="wizard.mrp.production.post.wip.entry",
        string="WIP accounting wizard",
    )

    _check_debit_credit = models.Constraint(
        "CHECK ( debit = 0 OR credit = 0 )",
        "A single line cannot be both credit and debit.",
    )

    @api.depends("credit")
    def _compute_debit(self) -> None:
        for record in self:
            if not record.currency_id.is_zero(record.credit):
                record.debit = 0

    @api.depends("debit")
    def _compute_credit(self) -> None:
        for record in self:
            if not record.currency_id.is_zero(record.debit):
                record.credit = 0
