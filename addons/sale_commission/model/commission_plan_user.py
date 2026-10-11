from odoo import Command, api, exceptions, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleCommissionPlanUser(models.Model):
    _name = "sale.commission.plan.user"
    _description = "Commission Plan User"
    _rec_name = "user_id"
    _rec_names_search = ["user_id", "plan_id"]
    _order = "id"

    plan_id = fields.Many2one(
        comodel_name="sale.commission.plan",
        index=True,
        required=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Salesperson",
        index=True,
        required=True,
        domain="[('share', '=', False)]",
    )

    date_from = fields.Date(
        string="From",
        compute="_compute_date_from",
        store=True,
        readonly=False,
    )
    date_to = fields.Date(string="To")

    other_plans = fields.Many2many(
        comodel_name="sale.commission.plan",
        string="Other plans",
        compute="_compute_other_plans",
        readonly=False,
    )

    _user_uniq = models.Constraint(
        "unique (plan_id, user_id)",
        "The user is already present in the plan",
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self) -> None:
        for user in self:
            if user.date_to and user.date_from and user.date_to < user.date_from:
                _debug.logic("plan_user_rejected", reason="dates_inverted")
                raise exceptions.UserError(self.env._("From must be before To"))
            if (
                user.date_from
                and user.plan_id.date_from
                and user.date_from < user.plan_id.date_from
            ):
                raise exceptions.UserError(
                    self.env._("User period cannot start before the plan.")
                )
            if (
                user.date_to
                and user.plan_id.date_to
                and user.date_to > user.plan_id.date_to
            ):
                _debug.logic("plan_user_rejected", reason="ends_after_plan")
                raise exceptions.UserError(
                    self.env._("User period cannot end after the plan.")
                )

    def _compute_display_name(self):
        for record in self:
            record.display_name = self.env._(
                "%(user)s - %(plan)s",
                plan=record.plan_id.name,
                user=record.user_id.name,
            )

    @api.depends(
        "user_id", "plan_id.date_from", "plan_id.date_to", "date_from", "date_to"
    )
    def _compute_other_plans(self) -> None:
        plan_ids = self.search(
            [
                ("user_id", "in", self.user_id.ids),
                ("plan_id.state", "in", ["draft", "approved"]),
            ]
        ).plan_id
        for pu in self:
            pu_date_from = pu.date_from or pu.plan_id.date_from
            pu_date_to = pu.date_to or pu.plan_id.date_to
            other_plans_ids = []
            for plan in plan_ids - pu.plan_id._origin - pu.plan_id:
                if pu.user_id not in plan.user_ids.user_id:
                    continue
                if plan.date_to < pu_date_from or plan.date_from > pu_date_to:
                    continue
                other_plans_ids.append(plan.id)
            pu.other_plans = (
                [Command.clear()]
                if not other_plans_ids
                else [Command.set(other_plans_ids)]
            )

    @api.depends("plan_id", "plan_id.date_from")
    def _compute_date_from(self) -> None:
        for user in self:
            if not user.plan_id.date_from:
                continue
            user.date_from = user.plan_id.date_from
