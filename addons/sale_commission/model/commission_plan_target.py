from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleCommissionPlanTarget(models.Model):
    _name = "sale.commission.plan.target"
    _description = "Commission Plan Target"
    _order = "id"

    plan_id = fields.Many2one(
        comodel_name="sale.commission.plan",
        index="btree_not_null",
        ondelete="cascade",
    )
    name = fields.Char(
        string="Period",
        readonly=True,
        required=True,
    )
    date_from = fields.Date(
        string="From",
        index=True,
        readonly=True,
        required=True,
    )
    date_to = fields.Date(
        string="To",
        index=True,
        readonly=True,
        required=True,
    )
    payment_date = fields.Date(
        compute="_compute_payment_date",
        store=True,
        index=True,
        readonly=False,
    )
    amount = fields.Monetary(
        string="Target",
        currency_field="currency_id",
        default=0,
        required=True,
    )
    payment_amount = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_payment_amount",
        store=True,
        help="Sum of amounts paid on the same payment date",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="plan_id.currency_id",
    )

    @api.constrains("plan_id", "date_from", "date_to")
    def _check_overlapping_dates(self) -> None:
        targets_by_plans = self._read_group(
            domain=[("plan_id", "in", self.plan_id.ids)],
            groupby=["plan_id"],
            aggregates=["id:recordset"],
        )
        for plan_id, target_ids in targets_by_plans:
            if len(target_ids) < 2:
                continue
            target_ids = target_ids.sorted(lambda t: (t.date_from, t.date_to))
            for idx in range(len(target_ids) - 1):
                current = target_ids[idx]
                next_one = target_ids[idx + 1]
                if current.date_from >= current.date_to:
                    _debug.logic(
                        "target_period_rejected",
                        target=current,
                        reason="dates_inverted",
                    )
                    raise ValidationError(
                        self.env._(
                            "The start date must be before the end date.\nPeriod: %s"
                        )
                        % current.name
                    )
                if current.date_to >= next_one.date_from:
                    _debug.logic(
                        "target_period_rejected",
                        plan=plan_id,
                        target=current,
                        overlaps=next_one,
                    )
                    raise ValidationError(
                        self.env._(
                            "Overlapping periods detected for plan '%(plan)s':\n"
                            "- %(c_name)s [%(c_from)s → %(c_to)s]\n"
                            "- %(n_name)s [%(n_from)s → %(n_to)s]",
                            plan=plan_id.display_name,
                            c_name=current.name,
                            c_from=current.date_from,
                            c_to=current.date_to,
                            n_name=next_one.name,
                            n_from=next_one.date_from,
                            n_to=next_one.date_to,
                        )
                    )

    @api.depends("date_to")
    def _compute_payment_date(self) -> None:
        for target in self:
            if not target.payment_date:
                target.payment_date = target.date_to

    @api.depends("payment_date", "amount", "plan_id")
    def _compute_payment_amount(self) -> None:
        amount_per_payment_date = defaultdict(list)
        total_per_date = defaultdict(float)
        for target in self.plan_id.target_ids:
            key = (target.plan_id, target.payment_date)
            amount_per_payment_date[key].append(target.id)
            total_per_date[key] += target.amount
        for keys, target_ids in amount_per_payment_date.items():
            targets = self.browse(target_ids)
            targets.payment_amount = total_per_date[keys]
