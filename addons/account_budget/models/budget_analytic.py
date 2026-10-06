import re

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class BudgetAnalytic(models.Model):
    _name = "budget.analytic"
    _description = "Budget"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]
    _order = "date_from desc, id desc"

    # state -> the states it may move to
    STATE_TRANSITIONS = {
        "draft": {"confirmed", "revised", "canceled"},
        "confirmed": {"revised", "done", "canceled", "draft"},
        "revised": {"confirmed", "done", "canceled", "draft"},
        "done": {"draft"},
        "canceled": {"draft"},
    }

    name = fields.Char(
        string="Budget Name",
        required=True,
    )
    parent_id = fields.Many2one(
        comodel_name="budget.analytic",
        string="Revision Of",
        index=True,
        ondelete="cascade",
    )
    children_ids = fields.One2many(
        comodel_name="budget.analytic",
        inverse_name="parent_id",
        string="Revisions",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        default=lambda self: self.env.user,
    )
    date_from = fields.Date(
        string="Start Date",
        required=True,
    )
    date_to = fields.Date(
        string="End Date",
        required=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("confirmed", "Open"),
            ("revised", "Revised"),
            ("done", "Done"),
            ("canceled", "Canceled"),
        ],
        string="Status",
        default="draft",
        copy=False,
        readonly=True,
        required=True,
        tracking=True,
    )
    budget_type = fields.Selection(
        selection=[
            ("revenue", "Revenue"),
            ("expense", "Expense"),
            ("both", "Both"),
        ],
        default="expense",
        required=True,
    )
    budget_line_ids = fields.One2many(
        comodel_name="budget.line",
        inverse_name="budget_analytic_id",
        string="Budget Lines",
        copy=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self) -> None:
        for record in self:
            if record.date_from > record.date_to:
                raise ValidationError(
                    self.env._("Budget end date may not be before the starting date.")
                )

    @api.constrains("parent_id")
    def _check_parent_id(self) -> None:
        for budget in self:
            if budget._has_cycle():
                raise ValidationError(
                    self.env._("You cannot create recursive revision of budget.")
                )

    def _get_revisions(self):
        """Self plus every revision below it, at any depth.

        `parent_id` cascades on delete, so a revision is removed by the database
        without `_unlink_except_draft_or_cancel` ever seeing it.
        """
        budgets = self
        generation = self.children_ids
        while generation:
            budgets |= generation
            generation = generation.children_ids
        return budgets

    @api.ondelete(at_uninstall=False)
    def _unlink_except_draft_or_cancel(self):
        blocking = self._get_revisions().filtered(
            lambda budget: budget.state not in ("draft", "canceled")
        )
        if blocking:
            raise UserError(
                self.env._(
                    "Deletion is only allowed in the Draft and Canceled stages. "
                    "The following budgets or their revisions are not: %(names)s",
                    names=", ".join(blocking.mapped("name")),
                )
            )

    def _set_state(self, target) -> None:
        moving = self.browse()
        for budget in self:
            if budget.state == target:
                continue
            if target not in self.STATE_TRANSITIONS[budget.state]:
                labels = dict(self.fields_get(["state"])["state"]["selection"])
                raise UserError(
                    self.env._(
                        "A budget in state %(current)s cannot move to %(target)s.",
                        current=labels[budget.state],
                        target=labels[target],
                    )
                )
            moving |= budget
        moving.state = target

    def action_budget_confirm(self) -> None:
        self.parent_id.filtered(lambda b: b.state == "confirmed")._set_state("revised")
        superseded = self.filtered(
            lambda b: any(child.state != "canceled" for child in b.children_ids)
        )
        superseded._set_state("revised")
        (self - superseded)._set_state("confirmed")

    def action_budget_draft(self) -> None:
        self._set_state("draft")

    def action_budget_cancel(self) -> None:
        self._set_state("canceled")

    def action_budget_done(self) -> None:
        self._set_state("done")

    def action_create_revision(self):
        revised = self.browse()
        for budget in self:
            revised_budget = budget.copy(
                default={
                    "name": budget._get_revised_budget_name(),
                    "parent_id": budget.id,
                }
            )
            revised += revised_budget
            budget.message_post(
                body=Markup(
                    "%s: <a href='#' data-oe-model='budget.analytic' data-oe-id='%s'>%s</a>"
                )
                % (
                    self.env._("New revision"),
                    revised_budget.id,
                    revised_budget.name,
                )
            )
        return revised._get_records_action()

    def _get_revised_budget_name(self) -> str:
        """Return the budget name with a `` - REV(<timestamp>)`` suffix, replacing any existing revision marker."""
        self.check_singleton()
        current_time = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        datetime_str = current_time.strftime("%Y-%m-%d %H:%M")

        # Extract existing revision pattern and base name
        match = re.search(r"(.*) - REV\([^)]+\)$", self.name.strip())
        base_name = match.group(1).strip() if match else self.name.strip()
        return f"{base_name} - REV({datetime_str})"

    def action_view_budget_lines(self) -> dict:
        context = dict(self.env.context)
        if len(self) == 1:
            context["default_budget_analytic_id"] = self.id
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Budget Lines"),
            "res_model": "budget.line",
            "view_mode": "list,pivot,graph",
            "domain": [("budget_analytic_id", "in", self.ids)],
            "context": context,
        }

    def action_view_budget_report(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Budget Report"),
            "res_model": "budget.report",
            "view_mode": "pivot,list,graph",
            "context": {"search_default_budget_analytic_id": self.id},
        }

    def write(self, vals):
        result = super().write(vals)
        self.env["budget.line"]._invalidate_budget_cache()
        return result

    def unlink(self):
        # budget lines cascade in the database, so `budget.line.unlink` never runs
        self.env["budget.line"]._invalidate_budget_cache()
        return super().unlink()

    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        return self.env["budget.line"]._patch_view(
            arch, view, view_type
        )  # patch the budget lines list view
